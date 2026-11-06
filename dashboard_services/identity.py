"""Extracted identity responsibilities; original calculations and widget behavior preserved."""
import pandas as pd

def normalize_hex_word(value):
    if value is None or pd.isna(value):
        return None
    text = str(value).strip().upper()
    if not text:
        return None
    if text.startswith("0X"):
        text = text[2:]
    try:
        return f"{int(text, 16) & 0xFFFF:04X}"
    except Exception:
        return None

def split_epc_identifier_words(epc):
    """Split the EPC identifier string into 16-bit words, left-to-right."""
    text = "".join(ch for ch in str(epc or "").upper() if ch in "0123456789ABCDEF")
    if not text:
        return []
    if len(text) % 4:
        text = text.ljust(((len(text) + 3) // 4) * 4, "0")
    return [text[i:i + 4] for i in range(0, len(text), 4)]

def latest_row_for_epc(df, epc, time_column):
    if df.empty or "epc" not in df.columns:
        return None
    rows = df[df["epc"].astype(str) == str(epc)].copy()
    if rows.empty:
        return None
    rows = rows.sort_values(time_column)
    return rows.iloc[-1]

def first_nonempty(row, names):
    if row is None:
        return None
    for name in names:
        if name in row.index:
            value = row.get(name)
            if value is not None and not pd.isna(value) and str(value).strip():
                return value
    return None

def build_epc_memory_table(row):
    if row is None:
        return pd.DataFrame(columns=["Offset", "Field", "Value", "Source"])

    epc = str(row.get("epc", "") or "")
    identifier_words = split_epc_identifier_words(epc)

    rows = []

    # CRC and PC are part of the EPC bank but are not present in the normal
    # inventory EPC string. Leave them explicitly unavailable unless future
    # Android payloads publish them.
    known = [
        (0x00, "STORED_CRC", first_nonempty(row, ["epc_stored_crc", "stored_crc"])),
        (0x01, "STORED_PC", first_nonempty(row, ["epc_stored_pc", "stored_pc"])),
    ]

    for offset, field, value in known:
        rows.append({
            "Offset": f"0x{offset:02X}",
            "Field": field,
            "Value": normalize_hex_word(value) or "Not available",
            "Source": "MQTT metadata" if value is not None else "Not read",
        })

    # Project ASYGN map reserves offsets 0x02-0x0D for EPC identifier words.
    # Fill as many words as are actually present in the EPC string.
    for i, offset in enumerate(range(0x02, 0x0E)):
        value = identifier_words[i] if i < len(identifier_words) else None
        rows.append({
            "Offset": f"0x{offset:02X}",
            "Field": f"EPC identifier word {i}",
            "Value": value or "Not present",
            "Source": "Inventory EPC" if value else "Not present",
        })

    mapped = [
        (0x0E, "SENS_REG_EPC", first_nonempty(row, ["epc_sens_reg", "sens_reg_epc"])),
        (0x0F, "TEMP_REG_EPC", first_nonempty(row, ["epc_temp_reg", "temp_reg_epc"])),
        (0x10, "CONFIG0", first_nonempty(row, ["epc_config0", "config0"])),
        (0x11, "CONFIG1", first_nonempty(row, ["epc_config1", "config1"])),
        (0x12, "CONFIG2", first_nonempty(row, ["epc_config2", "config2"])),
    ]

    for offset, field, value in mapped:
        rows.append({
            "Offset": f"0x{offset:02X}",
            "Field": field,
            "Value": normalize_hex_word(value) or "Not available",
            "Source": "Mapped EPC read" if value is not None else "Not read",
        })

    return pd.DataFrame(rows)
