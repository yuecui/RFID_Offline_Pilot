"""Extracted contract responsibilities; original calculations and widget behavior preserved."""
from dashboard_services.settings import VERSION
import pandas as pd

CANONICAL_FIELD_ALIASES = {
    "reference_pressure_psi": [
        "reference_pressure_psi",
        "known_pressure_psi",
    ],
    "reference_temperature_c": [
        "reference_temperature_c",
        "known_temperature_c",
    ],
    "estimated_pressure_psi": [
        "estimated_pressure_psi",
    ],
    "target_pressure_psi": [
        "target_pressure_psi",
    ],
    "operator_id": [
        "operator_id",
    ],
    "decoder_version": [
        "decoder_version",
    ],
    "model_version": [
        "model_version",
    ],
    "schema_version": [
        "schema_version",
    ],
}

CANONICAL_LAYERS = {
    "Raw Acquisition": [
        "timestamp",
        "captured_at",
        "captured_at_epoch_ms",
        "device_timezone",
        "received_at",
        "delivery_delay_ms",
        "reading_id",
        "session_id",
        "session_locked",
        "reader_id",
        "operator_id",
        "epc",
        "rssi",
        "w0",
        "w1",
        "user_memory",
        "reference_pressure_psi",
        "reference_temperature_c",
        "test_condition",
        "operator_note",
        "schema_version",
    ],
    "Sensor Decoding": [
        "user0_word",
        "user1_word",
        "user0_payload",
        "user1_payload",
        "strain_raw",
        "temperature_raw",
        "temperature_c",
        "strain_best_acc",
        "temperature_best_acc",
        "sensor_format_valid",
        "strain_format_valid",
        "temperature_format_valid",
        "tcal_c",
        "temp_at_tcal_raw",
        "decoder_version",
        "dashboard_tag_variant",
        "s5_user0_header",
        "s5_user1_header",
        "s5_header_matches_documentation",
        "s5_accepted_strain_raw",
        "s5_accepted_temperature_raw",
        "s5_accepted_temperature_c",
        "s5_tcal_c",
        "s5_temp_at_tcal_raw",
        "s5_interpretation_status",
    ],
    "Calibration / Estimation": [
        "reference_pressure_psi",
        "reference_temperature_c",
        "estimated_pressure_psi",
        "calibration_model",
        "model_version",
        "confidence",
        "error",
    ],
    "Decision": [
        "target_pressure_psi",
        "pressure_status",
        "low_threshold_psi",
        "high_threshold_psi",
        "backend_status",
        "storage_status",
    ],
}

def normalize_canonical_fields(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add canonical fields without overwriting original/raw columns.

    Legacy names remain intact. Canonical columns are additive aliases so
    historical data continue to work while new code can use stable names.

    v0.22 also records where normalized reference/schema values came from.
    """
    if df is None or df.empty:
        return df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()

    out = df.copy()

    # Record origin before aliases are filled.
    #
    # IMPORTANT: normalization can be applied more than once while the
    # dashboard builds research views. If provenance-origin columns already
    # exist, preserve them exactly instead of re-inferring origin from
    # canonical columns that may have been created by an earlier normalization.
    original_columns = set(out.columns)

    if "_reference_pressure_origin" in original_columns:
        pressure_origin = out["_reference_pressure_origin"].copy()
    else:
        if "reference_pressure_psi" in original_columns:
            pressure_origin = out["reference_pressure_psi"].notna().map(
                {True: "canonical-source", False: "missing"}
            )
        else:
            pressure_origin = pd.Series(
                "missing",
                index=out.index,
                dtype="object",
            )

        if "known_pressure_psi" in original_columns:
            pressure_origin = pressure_origin.where(
                pressure_origin != "missing",
                out["known_pressure_psi"].notna().map(
                    {True: "legacy-known_pressure_psi", False: "missing"}
                ),
            )

    if "_reference_temperature_origin" in original_columns:
        temperature_origin = out["_reference_temperature_origin"].copy()
    else:
        if "reference_temperature_c" in original_columns:
            temperature_origin = out["reference_temperature_c"].notna().map(
                {True: "canonical-source", False: "missing"}
            )
        else:
            temperature_origin = pd.Series(
                "missing",
                index=out.index,
                dtype="object",
            )

        if "known_temperature_c" in original_columns:
            temperature_origin = temperature_origin.where(
                temperature_origin != "missing",
                out["known_temperature_c"].notna().map(
                    {True: "legacy-known_temperature_c", False: "missing"}
                ),
            )

    if "_schema_version_origin" in original_columns:
        schema_origin = out["_schema_version_origin"].copy()
    else:
        if "schema_version" in original_columns:
            schema_origin = out["schema_version"].notna().map(
                {True: "source", False: "dashboard-normalized"}
            )
        else:
            schema_origin = pd.Series(
                "dashboard-normalized",
                index=out.index,
                dtype="object",
            )

    for canonical, aliases in CANONICAL_FIELD_ALIASES.items():
        if canonical in out.columns:
            canonical_series = out[canonical].copy()
        else:
            canonical_series = pd.Series(pd.NA, index=out.index, dtype="object")

        for alias in aliases:
            if alias not in out.columns:
                continue

            source = out[alias]

            # Fill only missing canonical values; never overwrite.
            try:
                missing_mask = canonical_series.isna()
            except Exception:
                missing_mask = pd.Series(True, index=out.index)

            canonical_series = canonical_series.where(
                ~missing_mask,
                source,
            )

        out[canonical] = canonical_series

    # Add explicit schema version for normalized dashboard views.
    if "schema_version" not in out.columns:
        out["schema_version"] = "dashboard-canonical-v1"
    else:
        out["schema_version"] = out["schema_version"].fillna(
            "dashboard-canonical-v1"
        )

    out["_reference_pressure_origin"] = pressure_origin
    out["_reference_temperature_origin"] = temperature_origin
    out["_schema_version_origin"] = schema_origin

    return out

def schema_field_status(df: pd.DataFrame):
    rows = []

    for layer, fields in CANONICAL_LAYERS.items():
        for field in fields:
            present = field in df.columns

            if present:
                non_null = int(df[field].notna().sum())
                total = int(len(df))
                populated_pct = (
                    round(non_null / total * 100.0, 1)
                    if total > 0
                    else 0.0
                )
            else:
                non_null = 0
                total = int(len(df))
                populated_pct = 0.0

            legacy_source = ""
            if field in CANONICAL_FIELD_ALIASES:
                aliases = [
                    a
                    for a in CANONICAL_FIELD_ALIASES[field]
                    if a in df.columns and a != field
                ]
                legacy_source = ", ".join(aliases)

            rows.append(
                {
                    "Layer": layer,
                    "Canonical field": field,
                    "Column present": present,
                    "Populated rows": non_null,
                    "Population (%)": populated_pct,
                    "Legacy source available": legacy_source,
                }
            )

    return pd.DataFrame(rows)

def build_contract_summary(df: pd.DataFrame):
    status = schema_field_status(df)

    if status.empty:
        return {
            "fields": 0,
            "present": 0,
            "fully_populated": 0,
            "legacy_aliases": 0,
        }

    return {
        "fields": int(len(status)),
        "present": int(status["Column present"].sum()),
        "fully_populated": int((status["Population (%)"] == 100.0).sum()),
        "legacy_aliases": int(
            (status["Legacy source available"].astype(str).str.len() > 0).sum()
        ),
    }

def canonical_contract_manifest(df: pd.DataFrame):
    summary = build_contract_summary(df)

    return {
        "dashboard_version": VERSION,
        "contract_version": "canonical-v1",
        "generated_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "row_count": int(len(df)),
        "summary": summary,
        "legacy_aliases": CANONICAL_FIELD_ALIASES,
        "layers": CANONICAL_LAYERS,
        "compatibility_note": (
            "Legacy known_pressure_psi / known_temperature_c remain preserved. "
            "Canonical reference_pressure_psi / reference_temperature_c are added "
            "without overwriting historical/raw fields."
        ),
        "scientific_note": (
            "Canonical naming does not validate ASYGN physical decoding or "
            "pressure calibration."
        ),
    }

def canonical_export_columns(df: pd.DataFrame):
    preferred = [
        "time",
        "_received_at",
        "timestamp",
        "reading_id",
        "session_id",
        "session_locked",
        "reader_id",
        "operator_id",
        "epc",
        "rssi",
        "w0",
        "w1",
        "user_memory",
        "reference_pressure_psi",
        "reference_temperature_c",
        "test_condition",
        "operator_note",
        "schema_version",
        "user0_word",
        "user1_word",
        "user0_payload",
        "user1_payload",
        "strain_raw",
        "temperature_raw",
        "temperature_c",
        "strain_best_acc",
        "temperature_best_acc",
        "sensor_format_valid",
        "strain_format_valid",
        "temperature_format_valid",
        "decoder_version",
        "estimated_pressure_psi",
        "calibration_model",
        "model_version",
        "confidence",
        "error",
        "target_pressure_psi",
        "pressure_status",
        "low_threshold_psi",
        "high_threshold_psi",
        "backend_status",
        "storage_status",
        # preserved legacy aliases for traceability:
        "known_pressure_psi",
        "known_temperature_c",
    ]

    return [c for c in preferred if c in df.columns]
