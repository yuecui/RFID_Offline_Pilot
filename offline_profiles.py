"""Non-destructive offline tag variant/temperature diagnostics.

ASYGN formulas and conditions are ported from the uploaded Android AsygnDecoder.kt.
A calculated temperature is NOT evidence of physical validation. Pressure is never
calculated from RFID words by this module.
"""
from __future__ import annotations
import pandas as pd


def _num(value):
    try:
        if value is None or pd.isna(value):
            return None
        i = int(value)
        return i if 0 <= i <= 0xffff else None
    except (TypeError, ValueError, OverflowError):
        return None


def _variant(value):
    s = str(value or "").upper().replace(" ", "")
    if "AS3213S.5" in s or "AS3213S5" in s:
        return "AS3213S.5"
    if "AS3213T.5" in s or "AS3213T5" in s:
        return "AS3213T.5"
    return "UNKNOWN"


def _diagnose(row, overrides):
    epc = str(row.get("epc") or "").upper()
    selected = _variant(overrides.get(epc))
    origin = "explicit offline tag catalog" if selected != "UNKNOWN" else ""
    if selected == "UNKNOWN":
        for name in ("tag_type", "sensor_variant", "dashboard_tag_variant"):
            found = _variant(row.get(name))
            if found != "UNKNOWN":
                selected = found
                origin = ("Dashboard variant inference — REVIEW tag identity"
                          if name == "dashboard_tag_variant" else f"record {name}")
                break
    u0, u1, u5, u6 = (_num(row.get(f"user{i}_word")) for i in (0, 1, 5, 6))
    if selected == "UNKNOWN" and len(epc) == 48 and u1 is not None and (u1 >> 14) == 3:
        selected, origin = "AS3213T.5", "192-bit EPC + USER1 header inference (review)"
    base = {"offline_variant": selected, "offline_variant_origin": origin,
            "temperature_calc_status": "VARIANT_UNKNOWN", "temperature_c": None,
            "temperature_raw": None, "temperature_cal_tcal_c": None,
            "temperature_at_tcal_raw": None,
            "strain_raw_strict": None, "sensor_header_status": "UNKNOWN"}
    if selected == "UNKNOWN":
        return base
    if u1 is None:
        base["temperature_calc_status"] = "MISSING_USER1"
        return base
    if u5 is None or u6 is None:
        base["temperature_calc_status"] = "MISSING_USER5_OR_USER6"
        return base
    tcal = (-1 if u5 & 0x8000 else 1) * ((u5 & 0x7fff) / 100.0)
    temp_tcal = (u6 & 0x1fff) / 8.0
    base["temperature_cal_tcal_c"] = tcal
    base["temperature_at_tcal_raw"] = temp_tcal
    if selected == "AS3213T.5":
        h_ok = (u1 >> 14) == 3
        base["sensor_header_status"] = "T5_USER1_MATCH" if h_ok else "T5_USER1_MISMATCH"
        if not h_ok:
            base["temperature_calc_status"] = "HEADER_MISMATCH"
            return base
        raw = (u1 & 0x1fff) / 8.0
    else:
        h_ok = (u0 is not None and (u0 >> 14) == 2 and ((u0 >> 12) & 1) == 0
                and (u1 >> 14) == 2 and ((u1 >> 12) & 1) == 0)
        base["sensor_header_status"] = "S5_USER01_MATCH" if h_ok else "S5_USER01_MISMATCH"
        if not h_ok:
            base["temperature_calc_status"] = "HEADER_MISMATCH"
            return base
        base["strain_raw_strict"] = (u0 & 0x0fff) / 4.0
        raw = (u1 & 0x0fff) / 4.0
    base["temperature_raw"] = raw
    base["temperature_c"] = tcal + (raw - temp_tcal) / 2.99
    base["temperature_calc_status"] = "HEADER_VALID_CALCULATED_NOT_PHYSICALLY_VALIDATED"
    return base


def add_offline_temperature(frame, tag_variants=None):
    """Tag variants are explicit or conservatively inferred for T.5 only.

    Results are derived from a copy; original raw bytes are never modified.
    """
    if frame.empty:
        return frame.copy()
    ov = {str(k).upper(): v for k, v in (tag_variants or {}).items()}
    rows = frame.apply(lambda row: _diagnose(row, ov), axis=1).to_list()
    derived = pd.DataFrame(rows, index=frame.index)
    out = frame.copy()
    for col in derived.columns:
        out[col] = derived[col]
    out["temperature_c"] = pd.to_numeric(out["temperature_c"], errors="coerce")
    out["temperature_raw"] = pd.to_numeric(out["temperature_raw"], errors="coerce")
    out["strain_raw_strict"] = pd.to_numeric(out["strain_raw_strict"], errors="coerce")
    return out
