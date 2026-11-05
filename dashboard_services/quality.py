"""Extracted quality responsibilities; original calculations and widget behavior preserved."""
from dashboard_services.metrics import align_two_tags
import pandas as pd

def session_summary_table(session_df: pd.DataFrame, time_column: str):
    """Build one summary row per EPC for a selected experiment session."""
    if session_df.empty or "epc" not in session_df.columns:
        return pd.DataFrame()

    rows = []
    for epc, group in session_df.groupby("epc"):
        group = group.sort_values(time_column)
        rssi = pd.to_numeric(group.get("rssi"), errors="coerce")
        u0 = pd.to_numeric(group.get("user0_payload"), errors="coerce")
        u1 = pd.to_numeric(group.get("user1_payload"), errors="coerce")

        rows.append({
            "EPC": str(epc),
            "Readings": len(group),
            "First reading": group[time_column].iloc[0],
            "Last reading": group[time_column].iloc[-1],
            "Mean RSSI (dBm)": None if rssi.dropna().empty else round(float(rssi.mean()), 2),
            "Mean USER0 payload": None if u0.dropna().empty else round(float(u0.mean()), 2),
            "Mean USER1 payload": None if u1.dropna().empty else round(float(u1.mean()), 2),
        })

    return pd.DataFrame(rows)

def session_metadata_value(session_df: pd.DataFrame, column: str):
    """Return the first non-null value for a session-level metadata field."""
    if session_df.empty or column not in session_df.columns:
        return None
    values = session_df[column].dropna()
    if values.empty:
        return None
    # Preserve strings such as test_condition and operator_note.
    value = values.iloc[0]
    if isinstance(value, float) and pd.isna(value):
        return None
    return value

def _safe_numeric(series):
    if series is None:
        return pd.Series(dtype="float64")
    return pd.to_numeric(series, errors="coerce")

def _best_acc_percent(group: pd.DataFrame, column: str):
    if column not in group.columns:
        return None
    values = pd.to_numeric(group[column], errors="coerce").dropna()
    if values.empty:
        return None
    return round(float((values == 1).mean() * 100.0), 2)

def _missing_percent(group: pd.DataFrame, column: str):
    if column not in group.columns or len(group) == 0:
        return None
    values = group[column]
    missing = values.isna()
    if values.dtype == object:
        missing = missing | values.astype(str).str.strip().isin(["", "None", "nan"])
    return round(float(missing.mean() * 100.0), 2)

def _missing_percent_fallback(
    group: pd.DataFrame,
    columns: list[str],
):
    """
    Compute missing percentage using the first available representation.

    Live MQTT rows commonly expose w0/w1, while historical Influx rows may
    expose user0_word/user1_word or user0_payload/user1_payload instead.
    """
    for column in columns:
        if column in group.columns:
            return _missing_percent(group, column)
    return None

def build_session_quality_table(
    session_df: pd.DataFrame,
    time_column: str,
):
    """Build per-tag acquisition-quality metrics for one session."""
    if (
        session_df.empty
        or "epc" not in session_df.columns
        or time_column not in session_df.columns
    ):
        return pd.DataFrame()

    rows = []

    for epc, group in session_df.groupby("epc"):
        group = group.copy()
        group[time_column] = pd.to_datetime(
            group[time_column],
            utc=True,
            errors="coerce",
        )
        group = group.dropna(subset=[time_column]).sort_values(time_column)

        if group.empty:
            continue

        first_time = group[time_column].iloc[0]
        last_time = group[time_column].iloc[-1]
        duration_sec = max(
            0.0,
            float((last_time - first_time).total_seconds()),
        )
        duration_min = duration_sec / 60.0

        # A one-reading session has zero measured duration; report N/A rather
        # than inventing a rate.
        reads_per_min = (
            None
            if duration_min <= 0.0
            else round(float(len(group) / duration_min), 2)
        )

        rssi = _safe_numeric(group.get("rssi"))

        rows.append(
            {
                "EPC": str(epc),
                "Readings": int(len(group)),
                "Duration (min)": round(duration_min, 2),
                "Reads/min": reads_per_min,
                "Strain BEST_ACC=1 (%)": _best_acc_percent(
                    group, "strain_best_acc"
                ),
                "Temp BEST_ACC=1 (%)": _best_acc_percent(
                    group, "temperature_best_acc"
                ),
                "Missing USER0 (%)": _missing_percent_fallback(
                    group,
                    ["w0", "user0_word", "user0_payload"],
                ),
                "Missing USER1 (%)": _missing_percent_fallback(
                    group,
                    ["w1", "user1_word", "user1_payload"],
                ),
                "RSSI mean (dBm)": (
                    None
                    if rssi.dropna().empty
                    else round(float(rssi.mean()), 2)
                ),
                "RSSI min (dBm)": (
                    None
                    if rssi.dropna().empty
                    else round(float(rssi.min()), 2)
                ),
                "RSSI max (dBm)": (
                    None
                    if rssi.dropna().empty
                    else round(float(rssi.max()), 2)
                ),
                "First reading": first_time,
                "Last reading": last_time,
            }
        )

    return pd.DataFrame(rows)

def session_metadata_integrity(session_df: pd.DataFrame):
    """Check whether locked-session metadata stays constant."""
    fields = [
        "session_id",
        "known_pressure_psi",
        "known_temperature_c",
        "test_condition",
        "operator_note",
        "session_locked",
    ]

    rows = []
    for field in fields:
        if field not in session_df.columns:
            rows.append(
                {
                    "Field": field,
                    "Unique non-null values": 0,
                    "Status": "NOT AVAILABLE",
                    "Observed values": "",
                }
            )
            continue

        values = (
            session_df[field]
            .dropna()
            .astype(str)
            .map(str.strip)
        )
        values = values[values != ""]
        unique_values = sorted(values.unique().tolist())

        if not unique_values:
            status = "MISSING"
        elif len(unique_values) == 1:
            status = "CONSISTENT"
        else:
            status = "MISMATCH"

        preview = " | ".join(unique_values[:4])
        if len(unique_values) > 4:
            preview += " | ..."

        rows.append(
            {
                "Field": field,
                "Unique non-null values": len(unique_values),
                "Status": status,
                "Observed values": preview,
            }
        )

    return pd.DataFrame(rows)

def sampling_imbalance_summary(quality_df: pd.DataFrame):
    if quality_df.empty or "Readings" not in quality_df.columns:
        return None

    counts = pd.to_numeric(quality_df["Readings"], errors="coerce").dropna()
    counts = counts[counts > 0]

    if len(counts) < 2:
        return None

    smallest = int(counts.min())
    largest = int(counts.max())
    ratio = float(largest / smallest) if smallest else None

    return {
        "smallest": smallest,
        "largest": largest,
        "ratio": ratio,
    }

def alignment_quality_summary(
    session_df: pd.DataFrame,
    time_column: str,
    metric_column: str,
    tag_a: str,
    tag_b: str,
    tolerance_ms: int,
):
    a_df = session_df[
        session_df["epc"].astype(str) == str(tag_a)
    ].copy()
    b_df = session_df[
        session_df["epc"].astype(str) == str(tag_b)
    ].copy()

    a_values = pd.to_numeric(
        a_df.get(metric_column),
        errors="coerce",
    ).dropna()
    b_values = pd.to_numeric(
        b_df.get(metric_column),
        errors="coerce",
    ).dropna()

    aligned = align_two_tags(
        a_df,
        b_df,
        time_column,
        metric_column,
        int(tolerance_ms),
    )

    reference_count = min(len(a_values), len(b_values))
    coverage = (
        0.0
        if reference_count == 0
        else float(len(aligned) / reference_count * 100.0)
    )

    return {
        "aligned": aligned,
        "tag_a_valid": int(len(a_values)),
        "tag_b_valid": int(len(b_values)),
        "reference_count": int(reference_count),
        "coverage_pct": round(coverage, 2),
        "mean_gap_ms": (
            None
            if aligned.empty
            else round(float(aligned["time_gap_ms"].mean()), 2)
        ),
        "median_gap_ms": (
            None
            if aligned.empty
            else round(float(aligned["time_gap_ms"].median()), 2)
        ),
        "max_gap_ms": (
            None
            if aligned.empty
            else round(float(aligned["time_gap_ms"].max()), 2)
        ),
    }
