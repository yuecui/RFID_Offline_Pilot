"""Read-only navigation for inspecting a single RFID record in an offline Session.

This module is Streamlit-independent so selection/filtering can be tested without
running the UI. It does not alter raw source data or derived diagnostic fields.
"""
from __future__ import annotations

import pandas as pd


def readings_for_epc(frame: pd.DataFrame, epc: str) -> pd.DataFrame:
    """Return a stable acquisition-time-ordered view of reads for one EPC."""
    if frame.empty or "epc" not in frame:
        return frame.iloc[0:0].copy().reset_index(drop=True)
    scoped = frame.loc[frame["epc"].astype(str).eq(str(epc))].copy()
    fields = [col for col in ("time", "timestamp_utc", "reading_id") if col in scoped]
    if fields:
        scoped = scoped.sort_values(fields, kind="stable", na_position="last")
    return scoped.reset_index(drop=True)


def _utc_display(row: pd.Series) -> str:
    raw = row.get("time", None)
    if raw is None or pd.isna(raw):
        raw = row.get("timestamp_utc", None)
    try:
        t = pd.to_datetime(raw, errors="coerce", utc=True)
        if pd.notna(t):
            return t.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + " UTC"
    except (TypeError, ValueError, OverflowError):
        pass
    return str(raw) if raw is not None and not pd.isna(raw) else "Time unavailable"


def short_epc(epc: object) -> str:
    value = str(epc)
    return value if len(value) <= 18 else value[:8] + "…" + value[-8:]


def short_reading_id(read_id: object) -> str:
    if read_id is None or pd.isna(read_id) or not str(read_id).strip():
        return "ID unavailable"
    value = str(read_id)
    return value if len(value) <= 24 else value[:12] + "…" + value[-8:]


def reading_label(row: pd.Series, position: int) -> str:
    """A useful label: 1-based within-EPC index, timestamp, EPC, and reading ID."""
    return (f"#{position + 1} | {_utc_display(row)} | "
            f"{short_epc(row.get('epc', ''))} | {short_reading_id(row.get('reading_id', None))}")


def find_readings(rows: pd.DataFrame, query: str, limit: int = 30) -> tuple[list[int], int]:
    """Fast, case-insensitive substring search over time or reading ID.

    Returns zero-based positions (capped for a compact dropdown) and an
    uncapped count. The original DataFrame is never mutated.
    """
    query = str(query).strip().casefold()
    if not query or rows.empty:
        return [], 0

    def values(field: str) -> pd.Series:
        if field in rows:
            return rows[field].astype("string").fillna("").str.casefold()
        return pd.Series("", index=rows.index, dtype="string")

    matches = values("reading_id").str.contains(query, regex=False)
    matches |= values("timestamp_utc").str.contains(query, regex=False)
    if "time" in rows:
        matches |= values("time").str.contains(query, regex=False)

    positions = [int(i) for i, matching in enumerate(matches) if bool(matching)]
    return positions[:limit], len(positions)
