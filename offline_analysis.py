"""Offline DataFrame adapter and real Dashboard analytics helpers.

Derived read-only values are deliberately separate from raw Session ZIP bytes.
Original reusable source modules in dashboard_components / dashboard_services
are imported without modification. No live MQTT, DB or Auth API in this module.
"""
from __future__ import annotations
import pandas as pd

from dashboard_services.readings import prepare_dataframe
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


def frame_from_parsed(parsed):
    """Convert validated pilot session into original Dashboard's chart contract.

    This intentionally does NOT infer a physical tag variant or calculate
    pressure/temperature from undocumented or unvalidated header words.
    """
    frame = pd.DataFrame(parsed.rows)
    frame["time"] = pd.to_datetime(frame["timestamp_utc"], utc=True, errors="coerce")
    for field in ("user0", "user1", "user5", "user6"):
        if field in frame.columns:
            frame["raw_" + field] = frame[field]
            frame[field] = pd.to_numeric(frame[field].map(word_to_int), errors="coerce")
    frame["rssi"] = pd.to_numeric(frame["rssi"], errors="coerce")
    if "reference_pressure_psi" in frame.columns:
        frame["known_pressure_psi"] = frame["reference_pressure_psi"]
    if "reference_temperature_c" in frame.columns:
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
    return {label: pair for label, pair in options.items()
            if pair[0] in frame.columns and
            pd.to_numeric(frame[pair[0]], errors="coerce").notna().any()}


def pair_tags(frame, first_epc, second_epc, column, tolerance_ms):
    return align_two_tags(
        frame.loc[frame["epc"] == first_epc],
        frame.loc[frame["epc"] == second_epc],
        "time", column, tolerance_ms,
    )
