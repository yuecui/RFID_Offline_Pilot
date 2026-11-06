"""Extracted references responsibilities; original calculations and widget behavior preserved."""
from dashboard_services.quality import _best_acc_percent
from dashboard_services.settings import VERSION
import io
import json
import pandas as pd
import zipfile

def _first_nonempty_value(df: pd.DataFrame, column: str):
    if column not in df.columns:
        return None
    values = df[column].dropna()
    if values.empty:
        return None
    values = values.astype(str).map(str.strip)
    values = values[~values.isin(["", "None", "nan", "<NA>"])]
    if values.empty:
        return None
    return values.iloc[0]

def _numeric_first(df: pd.DataFrame, column: str):
    if column not in df.columns:
        return None
    values = pd.to_numeric(df[column], errors="coerce").dropna()
    if values.empty:
        return None
    return float(values.iloc[0])

def build_reference_session_summary(
    df: pd.DataFrame,
    time_column: str,
):
    """
    Build one row per session and EPC for candidate reference/calibration data.

    This is intentionally based on USER payloads and reference metadata only.
    It does not claim validated physical strain, temperature, or pressure.
    """
    required = {"session_id", "epc"}
    if df.empty or not required.issubset(df.columns):
        return pd.DataFrame()

    work = df.copy()
    if time_column in work.columns:
        work[time_column] = pd.to_datetime(
            work[time_column],
            utc=True,
            errors="coerce",
        )

    rows = []

    grouped = work.groupby(["session_id", "epc"], dropna=True)

    for (session_id, epc), group in grouped:
        if str(session_id).strip() == "":
            continue

        group = group.copy()

        u0 = pd.to_numeric(
            group.get("user0_payload"),
            errors="coerce",
        )
        u1 = pd.to_numeric(
            group.get("user1_payload"),
            errors="coerce",
        )
        rssi = pd.to_numeric(
            group.get("rssi"),
            errors="coerce",
        )

        valid_times = (
            group[time_column].dropna().sort_values()
            if time_column in group.columns
            else pd.Series(dtype="datetime64[ns, UTC]")
        )

        duration_sec = None
        if len(valid_times) >= 2:
            duration_sec = float(
                (
                    valid_times.iloc[-1]
                    - valid_times.iloc[0]
                ).total_seconds()
            )

        strain_best_pct = _best_acc_percent(
            group,
            "strain_best_acc",
        )
        temp_best_pct = _best_acc_percent(
            group,
            "temperature_best_acc",
        )

        rows.append(
            {
                "session_id": str(session_id),
                "epc": str(epc),
                "readings": int(len(group)),
                "duration_s": (
                    None
                    if duration_sec is None
                    else round(duration_sec, 3)
                ),
                "known_pressure_psi": _numeric_first(
                    group,
                    "known_pressure_psi",
                ),
                "known_temperature_c": _numeric_first(
                    group,
                    "known_temperature_c",
                ),
                "test_condition": _first_nonempty_value(
                    group,
                    "test_condition",
                ),
                "operator_note": _first_nonempty_value(
                    group,
                    "operator_note",
                ),
                "user0_payload_mean": (
                    None
                    if u0.dropna().empty
                    else round(float(u0.mean()), 4)
                ),
                "user0_payload_std": (
                    None
                    if u0.dropna().empty
                    else round(float(u0.std(ddof=1)), 4)
                ),
                "user1_payload_mean": (
                    None
                    if u1.dropna().empty
                    else round(float(u1.mean()), 4)
                ),
                "user1_payload_std": (
                    None
                    if u1.dropna().empty
                    else round(float(u1.std(ddof=1)), 4)
                ),
                "rssi_mean_dbm": (
                    None
                    if rssi.dropna().empty
                    else round(float(rssi.mean()), 3)
                ),
                "strain_best_acc_pct": strain_best_pct,
                "temperature_best_acc_pct": temp_best_pct,
                "sensor_format_valid_any": (
                    bool(
                        group["sensor_format_valid"]
                        .fillna(False)
                        .astype(bool)
                        .any()
                    )
                    if "sensor_format_valid" in group.columns
                    else False
                ),
            }
        )

    return pd.DataFrame(rows)

def build_reference_reading_export(
    df: pd.DataFrame,
    selected_sessions: list[str],
    time_column: str,
):
    """Return reading-level candidate reference dataset for selected sessions."""
    if (
        df.empty
        or "session_id" not in df.columns
        or not selected_sessions
    ):
        return pd.DataFrame()

    work = df[
        df["session_id"].astype(str).isin(
            [str(s) for s in selected_sessions]
        )
    ].copy()

    if time_column in work.columns:
        work[time_column] = pd.to_datetime(
            work[time_column],
            utc=True,
            errors="coerce",
        )

    preferred_columns = [
        time_column,
        "reading_id",
        "session_id",
        "session_locked",
        "reader_id",
        "epc",
        "tid_raw",
        "tid_mdid",
        "tid_tmn",
        "tag_manufacturer",
        "tag_chip_family",
        "tag_type",
        "epc_config0",
        "epc_config1",
        "epc_config2",
        "known_pressure_psi",
        "known_temperature_c",
        "test_condition",
        "operator_note",
        "rssi",
        "w0",
        "w1",
        "user0_word",
        "user1_word",
        "user0_payload",
        "user1_payload",
        "strain_best_acc",
        "temperature_best_acc",
        "sensor_format_valid",
        "strain_format_valid",
        "temperature_format_valid",
    ]

    available = [
        col
        for col in preferred_columns
        if col in work.columns
    ]

    return work[available].sort_values(
        [
            col
            for col in ["session_id", time_column, "epc"]
            if col in available
        ]
    )

def candidate_reference_session_status(row: pd.Series):
    """
    Give a conservative software/data-readiness status.

    This is not a scientific calibration-validity decision.
    """
    reasons = []

    if pd.isna(row.get("known_pressure_psi")):
        reasons.append("missing pressure reference")

    if pd.isna(row.get("known_temperature_c")):
        reasons.append("missing temperature reference")

    if int(row.get("readings", 0) or 0) < 20:
        reasons.append("fewer than 20 readings")

    strain_best = row.get("strain_best_acc_pct")
    temp_best = row.get("temperature_best_acc_pct")

    if (
        strain_best is not None
        and not pd.isna(strain_best)
        and float(strain_best) < 90.0
    ):
        reasons.append("strain BEST_ACC < 90%")

    if (
        temp_best is not None
        and not pd.isna(temp_best)
        and float(temp_best) < 90.0
    ):
        reasons.append("temperature BEST_ACC < 90%")

    if reasons:
        return "ATTENTION", "; ".join(reasons)

    return "REFERENCE READY", ""

def build_reference_dataset_zip(
    reading_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    selected_sessions: list[str],
):
    buffer = io.BytesIO()

    manifest = {
        "dataset_type": "RFID candidate reference dataset",
        "dataset_version": "1.0",
        "dashboard_version": VERSION,
        "generated_utc": pd.Timestamp.now(
            tz="UTC"
        ).isoformat(),
        "sessions": selected_sessions,
        "session_count": len(selected_sessions),
        "reading_count": int(len(reading_df)),
        "summary_row_count": int(len(summary_df)),
        "scientific_validation_note": (
            "This export contains reference metadata and RFID sensor payloads. "
            "It is not a validated pressure/strain model and does not resolve "
            "the current ASYGN USER0/USER1 header-format discrepancy."
        ),
        "files": [
            "manifest.json",
            "reference_readings.csv",
            "reference_session_summary.csv",
        ],
    }

    with zipfile.ZipFile(
        buffer,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(
                manifest,
                indent=2,
                default=str,
            ),
        )
        archive.writestr(
            "reference_readings.csv",
            reading_df.to_csv(index=False),
        )
        archive.writestr(
            "reference_session_summary.csv",
            summary_df.to_csv(index=False),
        )

    return buffer.getvalue(), manifest
