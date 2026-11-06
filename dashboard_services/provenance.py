"""Extracted provenance responsibilities; original calculations and widget behavior preserved."""
from dashboard_services.contract import canonical_export_columns
from dashboard_services.contract import normalize_canonical_fields
from dashboard_services.settings import VERSION
import hashlib
import io
import json
import pandas as pd
import zipfile

def _unique_nonempty_values(df: pd.DataFrame, column: str):
    if column not in df.columns:
        return []

    values = df[column].dropna().astype(str).map(str.strip)
    values = values[
        ~values.isin(["", "None", "nan", "<NA>"])
    ]

    return sorted(values.unique().tolist())

def _time_bounds(df: pd.DataFrame):
    for column in ["time", "_received_at", "timestamp"]:
        if column not in df.columns:
            continue

        values = pd.to_datetime(
            df[column],
            utc=True,
            errors="coerce",
        ).dropna()

        if not values.empty:
            return (
                values.min().isoformat(),
                values.max().isoformat(),
                column,
            )

    return None, None, None

def deterministic_session_hash(df: pd.DataFrame):
    """
    Hash a stable canonical snapshot of the selected session.

    The hash is a reproducibility fingerprint of the exported rows, not a
    cryptographic signature of the physical experiment.
    """
    if df.empty:
        return None, 0

    work = normalize_canonical_fields(df)

    columns = canonical_export_columns(work)

    # Exclude dashboard-generated diagnostic origin fields and use stable order.
    hash_df = work[columns].copy()

    sort_columns = [
        c
        for c in [
            "reading_id",
            "timestamp",
            "time",
            "_received_at",
            "epc",
        ]
        if c in hash_df.columns
    ]

    if sort_columns:
        hash_df = hash_df.sort_values(
            sort_columns,
            kind="mergesort",
        )

    for column in hash_df.columns:
        if pd.api.types.is_datetime64_any_dtype(hash_df[column]):
            hash_df[column] = hash_df[column].astype(str)

    csv_bytes = hash_df.to_csv(
        index=False,
        lineterminator="\n",
    ).encode("utf-8")

    return hashlib.sha256(csv_bytes).hexdigest(), len(csv_bytes)

def build_session_provenance_summary(df: pd.DataFrame):
    if df.empty:
        return {}

    work = normalize_canonical_fields(df)
    first_time, last_time, time_column = _time_bounds(work)

    reading_ids = _unique_nonempty_values(work, "reading_id")
    session_ids = _unique_nonempty_values(work, "session_id")
    readers = _unique_nonempty_values(work, "reader_id")
    epcs = _unique_nonempty_values(work, "epc")
    operators = _unique_nonempty_values(work, "operator_id")
    schema_versions = _unique_nonempty_values(work, "schema_version")
    decoder_versions = _unique_nonempty_values(work, "decoder_version")
    model_versions = _unique_nonempty_values(work, "model_version")
    lock_values = _unique_nonempty_values(work, "session_locked")

    reference_pressures = _unique_nonempty_values(
        work,
        "reference_pressure_psi",
    )
    reference_temperatures = _unique_nonempty_values(
        work,
        "reference_temperature_c",
    )
    test_conditions = _unique_nonempty_values(
        work,
        "test_condition",
    )

    pressure_origins = _unique_nonempty_values(
        work,
        "_reference_pressure_origin",
    )
    temperature_origins = _unique_nonempty_values(
        work,
        "_reference_temperature_origin",
    )
    schema_origins = _unique_nonempty_values(
        work,
        "_schema_version_origin",
    )

    dataset_sha256, canonical_bytes = deterministic_session_hash(work)

    duplicate_reading_ids = 0
    if "reading_id" in work.columns:
        ids = work["reading_id"].dropna().astype(str)
        duplicate_reading_ids = int(ids.duplicated().sum())

    return {
        "dashboard_version": VERSION,
        "provenance_manifest_version": "provenance-v1",
        "row_count": int(len(work)),
        "session_ids": session_ids,
        "reader_ids": readers,
        "epcs": epcs,
        "operator_ids": operators,
        "schema_versions": schema_versions,
        "schema_version_origins": schema_origins,
        "decoder_versions": decoder_versions,
        "model_versions": model_versions,
        "session_locked_values": lock_values,
        "reference_pressure_values": reference_pressures,
        "reference_temperature_values": reference_temperatures,
        "reference_pressure_origins": pressure_origins,
        "reference_temperature_origins": temperature_origins,
        "test_conditions": test_conditions,
        "first_timestamp": first_time,
        "last_timestamp": last_time,
        "time_column": time_column,
        "unique_reading_ids": len(reading_ids),
        "duplicate_reading_ids": duplicate_reading_ids,
        "canonical_dataset_sha256": dataset_sha256,
        "canonical_snapshot_bytes": canonical_bytes,
    }

def build_provenance_checks(df: pd.DataFrame):
    summary = build_session_provenance_summary(df)
    if not summary:
        return pd.DataFrame()

    rows = []

    def add_check(name, status, detail, category="Core"):
        rows.append(
            {
                "Category": category,
                "Check": name,
                "Status": status,
                "Detail": detail,
            }
        )

    # Core observation identity.
    add_check(
        "Single session ID",
        "PASS" if len(summary["session_ids"]) == 1 else "ATTENTION",
        ", ".join(summary["session_ids"]) or "Missing",
    )

    add_check(
        "Unique reading IDs",
        "PASS" if summary["duplicate_reading_ids"] == 0 else "ATTENTION",
        f"{summary['duplicate_reading_ids']} duplicate IDs",
    )

    add_check(
        "Reader identity",
        "PASS" if len(summary["reader_ids"]) >= 1 else "ATTENTION",
        ", ".join(summary["reader_ids"]) or "Missing",
    )

    add_check(
        "Tag identity",
        "PASS" if len(summary["epcs"]) >= 1 else "ATTENTION",
        f"{len(summary['epcs'])} unique EPC(s)",
    )

    # Session lock is expected to be one consistent true-like state for
    # observations belonging to an acquisition session.
    lock_values_lower = {
        value.lower()
        for value in summary["session_locked_values"]
    }
    lock_pass = (
        len(lock_values_lower) == 1
        and next(iter(lock_values_lower), "") in {"true", "1"}
    )

    add_check(
        "Session lock consistency",
        "PASS" if lock_pass else "ATTENTION",
        ", ".join(summary["session_locked_values"]) or "Missing",
    )

    # Schema/provenance.
    add_check(
        "Schema version available",
        "PASS" if summary["schema_versions"] else "ATTENTION",
        ", ".join(summary["schema_versions"]) or "Missing",
        category="Schema",
    )

    # Origin markers survive repeated normalization. A dashboard-added
    # schema_version must therefore remain "dashboard-normalized" and must
    # never be promoted to "source" merely because the column already exists.
    source_schema_present = "source" in summary["schema_version_origins"]
    normalized_only = (
        summary["schema_version_origins"]
        and not source_schema_present
    )

    add_check(
        "Acquisition-time schema version",
        "PASS" if source_schema_present else "INFO",
        (
            "At least one source record supplied schema_version"
            if source_schema_present
            else "Dashboard-normalized only; Android/backend payload does not yet provide schema_version"
        ),
        category="Schema",
    )

    # Reference metadata consistency.
    add_check(
        "Reference pressure consistency",
        (
            "PASS"
            if len(summary["reference_pressure_values"]) <= 1
            else "ATTENTION"
        ),
        (
            ", ".join(summary["reference_pressure_values"])
            if summary["reference_pressure_values"]
            else "Not provided"
        ),
        category="Reference metadata",
    )

    add_check(
        "Reference temperature consistency",
        (
            "PASS"
            if len(summary["reference_temperature_values"]) <= 1
            else "ATTENTION"
        ),
        (
            ", ".join(summary["reference_temperature_values"])
            if summary["reference_temperature_values"]
            else "Not provided"
        ),
        category="Reference metadata",
    )

    # Future provenance fields are informative, not release failures.
    add_check(
        "Operator ID",
        "PASS" if summary["operator_ids"] else "INFO",
        ", ".join(summary["operator_ids"]) or "Not yet provided",
        category="Future provenance",
    )

    add_check(
        "Decoder version",
        "PASS" if summary["decoder_versions"] else "INFO",
        ", ".join(summary["decoder_versions"]) or "Not yet provided",
        category="Future provenance",
    )

    add_check(
        "Model version",
        "PASS" if summary["model_versions"] else "INFO",
        ", ".join(summary["model_versions"]) or "Not yet applicable",
        category="Future provenance",
    )

    return pd.DataFrame(rows)

def provenance_release_status(checks_df: pd.DataFrame):
    if checks_df.empty:
        return "NO DATA"

    core = checks_df[
        checks_df["Category"].isin(
            ["Core", "Schema", "Reference metadata"]
        )
    ]

    if (core["Status"] == "ATTENTION").any():
        return "ATTENTION"

    return "CORE READY"

def build_provenance_manifest(df: pd.DataFrame):
    summary = build_session_provenance_summary(df)
    checks = build_provenance_checks(df)

    return {
        **summary,
        "generated_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "release_status": provenance_release_status(checks),
        "checks": checks.to_dict(orient="records"),
        "notes": {
            "hash_scope": (
                "SHA-256 is computed from the canonical CSV snapshot of the "
                "selected rows after deterministic sorting."
            ),
            "scientific_boundary": (
                "Provenance completeness does not validate ASYGN physical "
                "decoding, pressure calibration, or decision thresholds."
            ),
            "future_fields": (
                "operator_id, decoder_version, and model_version are tracked "
                "but are not required for the current diagnostic-only sensor state."
            ),
        },
    }

def build_provenance_zip(df: pd.DataFrame):
    work = normalize_canonical_fields(df)
    manifest = build_provenance_manifest(work)
    checks = build_provenance_checks(work)

    export_cols = canonical_export_columns(work)
    snapshot = work[export_cols].copy()

    buffer = io.BytesIO()
    with zipfile.ZipFile(
        buffer,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        archive.writestr(
            "provenance_manifest.json",
            json.dumps(
                manifest,
                indent=2,
                default=str,
            ),
        )
        archive.writestr(
            "provenance_checks.csv",
            checks.to_csv(index=False),
        )
        archive.writestr(
            "canonical_snapshot.csv",
            snapshot.to_csv(index=False),
        )

    return buffer.getvalue(), manifest, checks
