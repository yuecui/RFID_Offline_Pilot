"""Extracted readiness responsibilities; original calculations and widget behavior preserved."""
from dashboard_services.contract import canonical_export_columns
from dashboard_services.contract import normalize_canonical_fields
from dashboard_services.provenance import _unique_nonempty_values
from dashboard_services.provenance import deterministic_session_hash
from dashboard_services.settings import VERSION
import io
import json
import pandas as pd
import zipfile

READINESS_MODES = {
    "Diagnostic acquisition": {
        "require_reference_pressure": False,
        "require_reference_temperature": False,
    },
    "Calibration candidate": {
        "require_reference_pressure": True,
        "require_reference_temperature": True,
    },
}

def _single_nonempty_value(df: pd.DataFrame, column: str):
    values = _unique_nonempty_values(df, column)
    if len(values) == 1:
        return values[0]
    return None

def _bool_values(df: pd.DataFrame, column: str):
    if column not in df.columns:
        return set()

    values = set()
    for value in df[column].dropna().tolist():
        if isinstance(value, bool):
            values.add(value)
            continue

        text_value = str(value).strip().lower()
        if text_value in {"true", "1", "yes"}:
            values.add(True)
        elif text_value in {"false", "0", "no"}:
            values.add(False)

    return values

def _missing_pct_any(df: pd.DataFrame, columns):
    """
    Percentage of rows where no usable value exists across fallback columns.
    """
    available = [c for c in columns if c in df.columns]
    if not available or df.empty:
        return 100.0

    present = pd.Series(False, index=df.index)

    for column in available:
        series = df[column]
        valid = series.notna()

        if series.dtype == object:
            valid = valid & (
                series.astype(str).str.strip().isin(
                    ["", "None", "nan", "<NA>"]
                )
                == False
            )

        present = present | valid

    return round(float((~present).mean() * 100.0), 2)

def _best_acc_min_pct(df: pd.DataFrame):
    values = []

    for column in ["strain_best_acc", "temperature_best_acc"]:
        if column not in df.columns:
            continue

        numeric = pd.to_numeric(df[column], errors="coerce").dropna()
        if numeric.empty:
            continue

        values.append(float((numeric == 1).mean() * 100.0))

    if not values:
        return None

    return round(min(values), 2)

def build_experiment_readiness_checks(
    session_df: pd.DataFrame,
    mode: str,
    min_readings_per_tag: int,
    max_missing_user_pct: float,
    min_best_acc_pct: float,
    max_sampling_ratio: float,
):
    """
    Build a conservative gate for whether a session is structurally suitable
    for downstream analysis.

    This gate checks data completeness, traceability, and acquisition quality.
    It does NOT validate the ASYGN physical conversion or a pressure model.
    """
    if session_df is None or session_df.empty:
        return pd.DataFrame()

    work = normalize_canonical_fields(session_df)
    rows = []

    def add(
        category,
        check,
        status,
        observed,
        criterion,
        blocking=True,
    ):
        rows.append(
            {
                "Category": category,
                "Check": check,
                "Status": status,
                "Observed": observed,
                "Criterion": criterion,
                "Blocking": bool(blocking),
            }
        )

    # -------------------- Identity / traceability --------------------
    session_ids = _unique_nonempty_values(work, "session_id")
    add(
        "Identity",
        "Single session ID",
        "PASS" if len(session_ids) == 1 else "FAIL",
        ", ".join(session_ids) or "Missing",
        "Exactly one non-empty session_id",
    )

    reader_ids = _unique_nonempty_values(work, "reader_id")
    add(
        "Identity",
        "Reader identity",
        "PASS" if len(reader_ids) >= 1 else "FAIL",
        ", ".join(reader_ids) or "Missing",
        "At least one reader_id",
    )

    epcs = _unique_nonempty_values(work, "epc")
    add(
        "Identity",
        "Tag identity",
        "PASS" if len(epcs) >= 1 else "FAIL",
        f"{len(epcs)} unique EPC(s)",
        "At least one EPC",
    )

    # Reading IDs.
    duplicate_ids = None
    missing_reading_ids = None
    if "reading_id" in work.columns:
        ids = work["reading_id"]
        missing_reading_ids = int(ids.isna().sum())
        non_null_ids = ids.dropna().astype(str)
        duplicate_ids = int(non_null_ids.duplicated().sum())

    reading_id_pass = (
        duplicate_ids is not None
        and duplicate_ids == 0
        and missing_reading_ids == 0
    )
    add(
        "Identity",
        "Reading ID integrity",
        "PASS" if reading_id_pass else "FAIL",
        (
            f"{duplicate_ids} duplicate, {missing_reading_ids} missing"
            if duplicate_ids is not None
            else "reading_id unavailable"
        ),
        "No missing or duplicate reading_id values",
    )

    # Session lock.
    lock_values = _bool_values(work, "session_locked")
    add(
        "Session",
        "Session lock consistency",
        "PASS" if lock_values == {True} else "FAIL",
        (
            ", ".join(sorted(str(v) for v in lock_values))
            if lock_values
            else "Missing"
        ),
        "All records session_locked=True",
    )

    # -------------------- Acquisition completeness --------------------
    tag_counts = (
        work.groupby("epc", dropna=True)
        .size()
        .astype(int)
        if "epc" in work.columns
        else pd.Series(dtype="int64")
    )

    smallest_tag_count = (
        int(tag_counts.min())
        if not tag_counts.empty
        else 0
    )
    largest_tag_count = (
        int(tag_counts.max())
        if not tag_counts.empty
        else 0
    )

    add(
        "Acquisition",
        "Minimum readings per tag",
        "PASS"
        if smallest_tag_count >= int(min_readings_per_tag)
        else "FAIL",
        str(smallest_tag_count),
        f">= {int(min_readings_per_tag)} readings/tag",
    )

    user0_missing = _missing_pct_any(
        work,
        ["w0", "user0_word", "user0_payload"],
    )
    user1_missing = _missing_pct_any(
        work,
        ["w1", "user1_word", "user1_payload"],
    )

    add(
        "Acquisition",
        "USER0 completeness",
        "PASS"
        if user0_missing <= float(max_missing_user_pct)
        else "FAIL",
        f"{user0_missing:.2f}% missing",
        f"<= {float(max_missing_user_pct):.2f}% missing",
    )
    add(
        "Acquisition",
        "USER1 completeness",
        "PASS"
        if user1_missing <= float(max_missing_user_pct)
        else "FAIL",
        f"{user1_missing:.2f}% missing",
        f"<= {float(max_missing_user_pct):.2f}% missing",
    )

    best_acc_min = _best_acc_min_pct(work)
    add(
        "Acquisition",
        "BEST_ACC quality",
        (
            "PASS"
            if best_acc_min is not None
            and best_acc_min >= float(min_best_acc_pct)
            else "FAIL"
        ),
        (
            f"{best_acc_min:.2f}% minimum"
            if best_acc_min is not None
            else "Not available"
        ),
        f">= {float(min_best_acc_pct):.2f}% for available channels",
    )

    sampling_ratio = None
    if smallest_tag_count > 0 and largest_tag_count > 0:
        sampling_ratio = float(largest_tag_count / smallest_tag_count)

    if len(tag_counts) <= 1:
        sampling_status = "INFO"
        sampling_observed = "Single-tag session"
    elif sampling_ratio is not None and sampling_ratio <= float(max_sampling_ratio):
        sampling_status = "PASS"
        sampling_observed = f"{sampling_ratio:.2f}x"
    else:
        sampling_status = "REVIEW"
        sampling_observed = (
            f"{sampling_ratio:.2f}x"
            if sampling_ratio is not None
            else "N/A"
        )

    add(
        "Acquisition",
        "Sampling balance",
        sampling_status,
        sampling_observed,
        f"<= {float(max_sampling_ratio):.2f}x largest/smallest",
        blocking=False,
    )

    # -------------------- Metadata --------------------
    mode_config = READINESS_MODES.get(
        mode,
        READINESS_MODES["Diagnostic acquisition"],
    )

    pressure_values = _unique_nonempty_values(
        work,
        "reference_pressure_psi",
    )
    temperature_values = _unique_nonempty_values(
        work,
        "reference_temperature_c",
    )

    pressure_required = bool(
        mode_config["require_reference_pressure"]
    )
    temperature_required = bool(
        mode_config["require_reference_temperature"]
    )

    if pressure_required:
        pressure_status = (
            "PASS" if len(pressure_values) == 1 else "FAIL"
        )
        pressure_criterion = (
            "Exactly one reference pressure for calibration candidate"
        )
    else:
        pressure_status = (
            "PASS" if len(pressure_values) <= 1 else "REVIEW"
        )
        pressure_criterion = (
            "Optional; if supplied, must be consistent"
        )

    add(
        "Reference metadata",
        "Reference pressure",
        pressure_status,
        ", ".join(pressure_values) or "Not provided",
        pressure_criterion,
        blocking=pressure_required,
    )

    if temperature_required:
        temperature_status = (
            "PASS" if len(temperature_values) == 1 else "FAIL"
        )
        temperature_criterion = (
            "Exactly one reference temperature for calibration candidate"
        )
    else:
        temperature_status = (
            "PASS" if len(temperature_values) <= 1 else "REVIEW"
        )
        temperature_criterion = (
            "Optional; if supplied, must be consistent"
        )

    add(
        "Reference metadata",
        "Reference temperature",
        temperature_status,
        ", ".join(temperature_values) or "Not provided",
        temperature_criterion,
        blocking=temperature_required,
    )

    # -------------------- Provenance --------------------
    schema_versions = _unique_nonempty_values(
        work,
        "schema_version",
    )
    add(
        "Provenance",
        "Schema version available",
        "PASS" if schema_versions else "FAIL",
        ", ".join(schema_versions) or "Missing",
        "At least one schema_version",
    )

    schema_origins = _unique_nonempty_values(
        work,
        "_schema_version_origin",
    )
    if "source" in schema_origins:
        schema_origin_status = "PASS"
    elif "dashboard-normalized" in schema_origins:
        schema_origin_status = "INFO"
    else:
        schema_origin_status = "REVIEW"

    add(
        "Provenance",
        "Acquisition-time schema provenance",
        schema_origin_status,
        ", ".join(schema_origins) or "Missing",
        "Source preferred; dashboard-normalized accepted for legacy data",
        blocking=False,
    )

    operator_ids = _unique_nonempty_values(work, "operator_id")
    add(
        "Provenance",
        "Operator ID",
        "PASS" if operator_ids else "INFO",
        ", ".join(operator_ids) or "Not yet provided",
        "Recommended for future controlled experiments",
        blocking=False,
    )

    # -------------------- Scientific state --------------------
    sensor_valid_values = _bool_values(
        work,
        "sensor_format_valid",
    )

    accepted_s5_present = False
    if "s5_interpretation_status" in work.columns:
        accepted_s5_present = (
            work["s5_interpretation_status"]
            .fillna("")
            .astype(str)
            .str.contains(
                "ACCEPTED FOR EXPLORATORY",
                regex=False,
            )
            .any()
        )

    if accepted_s5_present:
        sensor_state = "S.5 ACCEPTED / NON-DOCUMENTED"
        sensor_status = "REVIEW"
    elif sensor_valid_values == {True}:
        sensor_state = "VALIDATED FORMAT"
        sensor_status = "PASS"
    elif True in sensor_valid_values:
        sensor_state = "MIXED FORMAT STATE"
        sensor_status = "REVIEW"
    else:
        sensor_state = "DIAGNOSTIC ONLY"
        sensor_status = "INFO"

    add(
        "Scientific boundary",
        "Sensor interpretation state",
        sensor_status,
        sensor_state,
        (
            "Informational only; readiness does not validate physical "
            "strain, temperature, or pressure"
        ),
        blocking=False,
    )

    return pd.DataFrame(rows)

def readiness_overall_status(checks_df: pd.DataFrame):
    if checks_df is None or checks_df.empty:
        return "NO DATA"

    blocking = checks_df[
        checks_df["Blocking"].fillna(False).astype(bool)
    ]

    if (blocking["Status"] == "FAIL").any():
        return "NOT READY"

    if checks_df["Status"].isin(["REVIEW"]).any():
        return "READY WITH REVIEW"

    return "READY"

def readiness_summary(checks_df: pd.DataFrame):
    if checks_df is None or checks_df.empty:
        return {
            "pass": 0,
            "fail": 0,
            "review": 0,
            "info": 0,
        }

    counts = checks_df["Status"].value_counts().to_dict()
    return {
        "pass": int(counts.get("PASS", 0)),
        "fail": int(counts.get("FAIL", 0)),
        "review": int(counts.get("REVIEW", 0)),
        "info": int(counts.get("INFO", 0)),
    }

def build_readiness_manifest(
    session_df: pd.DataFrame,
    mode: str,
    min_readings_per_tag: int,
    max_missing_user_pct: float,
    min_best_acc_pct: float,
    max_sampling_ratio: float,
):
    work = normalize_canonical_fields(session_df)

    checks = build_experiment_readiness_checks(
        work,
        mode=mode,
        min_readings_per_tag=min_readings_per_tag,
        max_missing_user_pct=max_missing_user_pct,
        min_best_acc_pct=min_best_acc_pct,
        max_sampling_ratio=max_sampling_ratio,
    )

    summary = readiness_summary(checks)
    dataset_sha256, canonical_bytes = deterministic_session_hash(work)

    return {
        "dashboard_version": VERSION,
        "readiness_manifest_version": "readiness-v1",
        "generated_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "mode": mode,
        "session_ids": _unique_nonempty_values(work, "session_id"),
        "reader_ids": _unique_nonempty_values(work, "reader_id"),
        "epcs": _unique_nonempty_values(work, "epc"),
        "row_count": int(len(work)),
        "criteria": {
            "min_readings_per_tag": int(min_readings_per_tag),
            "max_missing_user_pct": float(max_missing_user_pct),
            "min_best_acc_pct": float(min_best_acc_pct),
            "max_sampling_ratio": float(max_sampling_ratio),
        },
        "status": readiness_overall_status(checks),
        "summary": summary,
        "canonical_dataset_sha256": dataset_sha256,
        "canonical_snapshot_bytes": canonical_bytes,
        "checks": checks.to_dict(orient="records"),
        "scientific_boundary": (
            "Readiness indicates structural suitability for downstream "
            "analysis under the selected mode. It does not validate ASYGN "
            "physical decoding, pressure calibration, or decision thresholds."
        ),
    }

def build_readiness_zip(
    session_df: pd.DataFrame,
    mode: str,
    min_readings_per_tag: int,
    max_missing_user_pct: float,
    min_best_acc_pct: float,
    max_sampling_ratio: float,
):
    work = normalize_canonical_fields(session_df)

    checks = build_experiment_readiness_checks(
        work,
        mode=mode,
        min_readings_per_tag=min_readings_per_tag,
        max_missing_user_pct=max_missing_user_pct,
        min_best_acc_pct=min_best_acc_pct,
        max_sampling_ratio=max_sampling_ratio,
    )

    manifest = build_readiness_manifest(
        work,
        mode=mode,
        min_readings_per_tag=min_readings_per_tag,
        max_missing_user_pct=max_missing_user_pct,
        min_best_acc_pct=min_best_acc_pct,
        max_sampling_ratio=max_sampling_ratio,
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(
        buffer,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        archive.writestr(
            "readiness_manifest.json",
            json.dumps(manifest, indent=2, default=str),
        )
        archive.writestr(
            "readiness_checks.csv",
            checks.to_csv(index=False),
        )
        archive.writestr(
            "canonical_snapshot.csv",
            work[
                canonical_export_columns(work)
            ].to_csv(index=False),
        )

    return buffer.getvalue(), manifest, checks
