"""Offline DataFrame adapter and real Dashboard analytics helpers.

Derived read-only values are deliberately separate from raw Session ZIP bytes.
Original reusable source modules in dashboard_components / dashboard_services
are imported without modification. No live MQTT, DB or Auth API in this module.
"""
from __future__ import annotations
import pandas as pd

from dashboard_services.readings import prepare_dataframe, add_s5_exploratory_interpretation
from dashboard_services.contract import normalize_canonical_fields
from offline_profiles import add_offline_temperature
from dashboard_services.metrics import align_two_tags, metric_options_for
from dashboard_services.quality import (
    build_session_quality_table, session_summary_table, session_metadata_integrity,
)


def word_to_int(value):
    """Pilot contract: hex must be 0x-prefixed; unprefixed words are decimal."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        number = int(raw, 16) if raw.lower().startswith("0x") else int(raw, 10)
        return number if 0 <= number <= 0xFFFF else None
    except (ValueError, TypeError):
        return None


def frame_from_parsed(parsed, tag_catalog=None, session_catalog=None):
    """Convert validated pilot session into original Dashboard's chart contract.

    Only conservatively infer T.5 display variant on a documented 192-bit/header
    combination; strict header format and USER5/USER6 allow diagnostic temperature
    calculation. No raw word is used as a physically verified pressure estimate.
    """
    frame = pd.DataFrame(parsed.rows)
    tag_catalog = tag_catalog or {}
    variants = {epc.upper(): meta.get("variant", "UNKNOWN") for epc, meta in tag_catalog.items()}
    aliases = {epc.upper(): meta.get("alias", "") for epc, meta in tag_catalog.items()}
    frame["tag_name"] = frame["epc"].str.upper().map(aliases).fillna(frame.get("tag_name", ""))
    # Explicit operator-maintained catalog assignments are passed to the original
    # exploratory S.5 calculation, but never overwrite underlying USER words.
    if variants:
        explicit = frame["epc"].str.upper().map(variants)
        if "tag_type" not in frame:
            frame["tag_type"] = ""
        frame["tag_type"] = explicit.where(explicit.isin(["AS3213S.5", "AS3213T.5"]), frame["tag_type"])
    # Session reference metadata is an append-only operator annotation.
    # Original nonempty reference values are NEVER overwritten.
    annotations=(session_catalog or {}).get(parsed.raw_sha256,{})
    for field in ("reference_pressure_psi","reference_temperature_c"):
        if field not in frame.columns: frame[field] = ""
        present = frame[field].fillna("").astype(str).str.strip().ne("")
        if annotations.get(field) is not None:
            frame.loc[~present,field] = annotations[field]
            frame[field+"_offline_annotation"] = (~present).map({True:"supplemental operator annotation",False:"original source"})
    for field in ("test_condition","operator_note"):
        if field not in frame.columns: frame[field]=""
        empty=frame[field].fillna("").astype(str).str.strip().eq("")
        if annotations.get(field):frame.loc[empty,field] = annotations[field]
    frame["time"] = pd.to_datetime(frame["timestamp_utc"], utc=True, errors="coerce")
    for field in ("user0", "user1", "user5", "user6"):
        if field in frame.columns:
            frame["raw_" + field] = frame[field]
            frame[field] = pd.to_numeric(frame[field].map(word_to_int), errors="coerce")
    frame["rssi"] = pd.to_numeric(frame["rssi"], errors="coerce")
    if "reference_pressure_psi" in frame.columns:
        frame["raw_reference_pressure_psi"] = frame["reference_pressure_psi"]
        frame["reference_pressure_psi"] = pd.to_numeric(frame["reference_pressure_psi"], errors="coerce")
        frame["known_pressure_psi"] = frame["reference_pressure_psi"]
    if "reference_temperature_c" in frame.columns:
        frame["raw_reference_temperature_c"] = frame["reference_temperature_c"]
        frame["reference_temperature_c"] = pd.to_numeric(frame["reference_temperature_c"], errors="coerce")
        frame["known_temperature_c"] = frame["reference_temperature_c"]
    frame = prepare_dataframe(frame, "time")
    for field in ("user0_word", "user1_word"):
        if field in frame.columns:
            num = pd.to_numeric(frame[field], errors="coerce")
            frame[field + "_header"] = num.map(
                lambda n: None if pd.isna(n) else format((int(n) >> 14) & 3, "02b")
            )
            frame[field + "_header_valid"] = num.map(
                lambda n: None if pd.isna(n) else ((int(n) >> 14) & 3) == 2
            )
    frame = add_offline_temperature(frame, variants)
    # Original Dashboard exploratory S.5 fields are *not* physically validated.
    frame = add_s5_exploratory_interpretation(frame)
    frame = normalize_canonical_fields(frame)
    return frame


def time_window(frame, minutes=None):
    """Relative to the session's last observation, not the wall clock."""
    if frame.empty or minutes is None:
        return frame.copy()
    last = frame["time"].max()
    return frame.loc[frame["time"] >= last - pd.Timedelta(minutes=minutes)].copy()


def describe_quality(frame):
    return {
        "by_tag": build_session_quality_table(frame, "time"),
        "summary": session_summary_table(frame, "time"),
        "metadata": session_metadata_integrity(frame),
    }


def metric_options(frame):
    options = metric_options_for(frame)
    # Original USER words, calibration diagnostics and independent references.
    # None of these values are a validated pressure prediction.
    additions = {
        "USER5 Tcal packed word (diagnostic)": ("user5_word", "USER5 packed word"),
        "USER6 temp-at-Tcal packed word (diagnostic)": ("user6_word", "USER6 packed word"),
        "Tcal (°C) — decoded calibration word": ("temperature_cal_tcal_c", "Tcal (°C)"),
        "Temperature-at-Tcal raw (diagnostic)": ("temperature_at_tcal_raw", "USER6 raw / 8"),
        "Strict S.5 strain raw — NOT pressure": ("strain_raw_strict", "S.5 strain raw"),
        "Reference temperature (°C) — lab input": ("known_temperature_c", "Reference temperature (°C)"),
        "Reference pressure (PSI) — lab input": ("known_pressure_psi", "Reference pressure (PSI)"),
    }
    options.update(additions)
    return {label: pair for label, pair in options.items()
            if pair[0] in frame.columns and
            pd.to_numeric(frame[pair[0]], errors="coerce").notna().any()}


def pair_tags(frame, first_epc, second_epc, column, tolerance_ms):
    return align_two_tags(
        frame.loc[frame["epc"] == first_epc],
        frame.loc[frame["epc"] == second_epc],
        "time", column, tolerance_ms,
    )
