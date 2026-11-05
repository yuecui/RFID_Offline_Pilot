"""Extracted readings responsibilities; original calculations and widget behavior preserved."""
import pandas as pd

def hex_or_number(value):
    if value is None or pd.isna(value):
        return pd.NA
    if isinstance(value, str):
        text = value.strip()
        try:
            return int(text, 16)
        except Exception:
            return pd.to_numeric(text, errors="coerce")
    return pd.to_numeric(value, errors="coerce")

def _word_series(df: pd.DataFrame, word_index: int):
    """
    Return a numeric 16-bit USER word from MQTT wN or persisted userN.
    """
    mqtt_col = f"w{word_index}"
    db_col = f"user{word_index}"

    if mqtt_col in df.columns:
        return df[mqtt_col].apply(hex_or_number)

    if db_col in df.columns:
        return pd.to_numeric(df[db_col], errors="coerce")

    return pd.Series(pd.NA, index=df.index, dtype="object")

def _tag_variant_series(df: pd.DataFrame):
    """
    Normalize Android tag_type / sensor_variant into AS3213S.5 / AS3213T.5.

    Fallback:
    AS3213S.5 and AS3213T.5 share MDID/TMN, so EPC word 0x10 bits <13:11>
    are used when explicit tag metadata is missing:
      011 -> AS3213S.5
      001 -> AS3213T.5
    """
    result = pd.Series("UNKNOWN", index=df.index, dtype="object")

    if "tag_type" in df.columns:
        tag_type = df["tag_type"].fillna("").astype(str).str.upper()
        result = result.where(~tag_type.eq("AS3213S.5"), "AS3213S.5")
        result = result.where(~tag_type.eq("AS3213T.5"), "AS3213T.5")

    if "sensor_variant" in df.columns:
        variant = df["sensor_variant"].fillna("").astype(str).str.upper()
        result = result.where(
            ~variant.isin(["AS3213S5", "AS3213S.5"]),
            "AS3213S.5",
        )
        result = result.where(
            ~variant.isin(["AS3213T5", "AS3213T.5"]),
            "AS3213T.5",
        )

    if "epc_word_10" in df.columns:
        def infer_from_word10(value):
            if value is None or pd.isna(value):
                return None
            try:
                raw = int(str(value).strip().replace("0x", "").replace("0X", ""), 16)
            except Exception:
                try:
                    raw = int(value)
                except Exception:
                    return None

            bits = (raw >> 11) & 0x7
            if bits == 0b011:
                return "AS3213S.5"
            if bits == 0b001:
                return "AS3213T.5"
            return None

        inferred = df["epc_word_10"].map(infer_from_word10)
        result = result.where(
            result.ne("UNKNOWN") | inferred.isna(),
            inferred,
        )

    # Final display fallback for the current T.5 inventory mode.
    # ASYGN documents a 192-bit EPC when ACQ_TEMP is embedded in inventory.
    # If explicit metadata is absent, a 192-bit EPC together with the
    # documented T.5 USER1 header 0b11 is sufficient for this dashboard to
    # classify the row as AS3213T.5 for presentation/calculation.
    if "epc" in df.columns:
        if "user1_word" in df.columns:
            u1_source = pd.to_numeric(df["user1_word"], errors="coerce")
        else:
            u1_source = pd.to_numeric(_word_series(df, 1), errors="coerce")

        epc_clean = (
            df["epc"]
            .fillna("")
            .astype(str)
            .str.replace(r"[^0-9A-Fa-f]", "", regex=True)
        )
        is_192_bit = epc_clean.str.len().eq(48)

        u1_header_11 = u1_source.map(
            lambda value: (
                False
                if pd.isna(value)
                else (((int(value) >> 14) & 0x03) == 0b11)
            )
        )

        t5_fallback = is_192_bit & u1_header_11
        result = result.where(
            result.ne("UNKNOWN") | ~t5_fallback,
            "AS3213T.5",
        )

    return result

def add_s5_exploratory_interpretation(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add dashboard-only AS3213S.5 calculations.

    IMPORTANT:
    ASYGN documents USER0<15:14> = 0b10 and USER1<15:14> = 0b10.
    Our tested S.5 tags commonly report 0b00 instead.

    At the user's request, the dashboard still performs the documented
    payload/calibration arithmetic on those readings, but stores the results
    in explicitly non-validated fields. Strict Android/backend validity fields
    are NOT overwritten.
    """
    if df.empty:
        return df

    out = df.copy()
    out["dashboard_tag_variant"] = _tag_variant_series(out)

    u0 = pd.to_numeric(_word_series(out, 0), errors="coerce")
    u1 = pd.to_numeric(_word_series(out, 1), errors="coerce")
    u5 = pd.to_numeric(_word_series(out, 5), errors="coerce")
    u6 = pd.to_numeric(_word_series(out, 6), errors="coerce")

    s5_mask = out["dashboard_tag_variant"].eq("AS3213S.5")

    out["s5_user0_header"] = pd.NA
    out["s5_user1_header"] = pd.NA
    out["s5_header_matches_documentation"] = pd.NA
    out["s5_accepted_strain_raw"] = pd.NA
    out["s5_accepted_temperature_raw"] = pd.NA
    out["s5_accepted_temperature_c"] = pd.NA
    out["s5_tcal_c"] = pd.NA
    out["s5_temp_at_tcal_raw"] = pd.NA
    out["s5_interpretation_status"] = pd.NA

    valid_words = s5_mask & u0.notna() & u1.notna()

    if valid_words.any():
        u0_int = u0[valid_words].astype(int)
        u1_int = u1[valid_words].astype(int)

        header0 = u0_int.map(
            lambda value: (int(value) >> 14) & 0x03
        )
        header1 = u1_int.map(
            lambda value: (int(value) >> 14) & 0x03
        )

        out.loc[valid_words, "s5_user0_header"] = header0.map(
            lambda v: format(int(v), "02b")
        )
        out.loc[valid_words, "s5_user1_header"] = header1.map(
            lambda v: format(int(v), "02b")
        )

        header_match = (header0 == 0b10) & (header1 == 0b10)
        out.loc[
            valid_words,
            "s5_header_matches_documentation",
        ] = header_match.values

        # Apply the documented S.5 payload arithmetic even when the header
        # is non-conforming. Results are deliberately stored as "accepted"
        # exploratory values, not validated physical measurements.
        strain_raw = (u0_int & 0x0FFF) / 4.0
        temp_raw = (u1_int & 0x0FFF) / 4.0

        out.loc[
            valid_words,
            "s5_accepted_strain_raw",
        ] = strain_raw.values

        out.loc[
            valid_words,
            "s5_accepted_temperature_raw",
        ] = temp_raw.values

        out.loc[
            valid_words & out["s5_header_matches_documentation"].eq(True),
            "s5_interpretation_status",
        ] = "DOCUMENTED HEADER"

        out.loc[
            valid_words & ~out["s5_header_matches_documentation"].eq(True),
            "s5_interpretation_status",
        ] = (
            "ACCEPTED FOR EXPLORATORY CALCULATION — "
            "HEADER DOES NOT MATCH DOCUMENTATION"
        )

    calibration_mask = s5_mask & u5.notna() & u6.notna()

    if calibration_mask.any():
        u5_int = u5[calibration_mask].astype(int)
        u6_int = u6[calibration_mask].astype(int)

        magnitude = (u5_int & 0x7FFF) / 100.0
        sign = ((u5_int & 0x8000) != 0).map(
            lambda negative: -1.0 if negative else 1.0
        )
        tcal = magnitude * sign
        temp_at_tcal = (u6_int & 0x1FFF) / 8.0

        out.loc[calibration_mask, "s5_tcal_c"] = tcal.values
        out.loc[
            calibration_mask,
            "s5_temp_at_tcal_raw",
        ] = temp_at_tcal.values

    calc_mask = (
        s5_mask
        & pd.to_numeric(
            out["s5_accepted_temperature_raw"],
            errors="coerce",
        ).notna()
        & pd.to_numeric(out["s5_tcal_c"], errors="coerce").notna()
        & pd.to_numeric(
            out["s5_temp_at_tcal_raw"],
            errors="coerce",
        ).notna()
    )

    if calc_mask.any():
        accepted_temp = pd.to_numeric(
            out.loc[calc_mask, "s5_accepted_temperature_raw"],
            errors="coerce",
        )
        tcal = pd.to_numeric(
            out.loc[calc_mask, "s5_tcal_c"],
            errors="coerce",
        )
        temp_at_tcal = pd.to_numeric(
            out.loc[calc_mask, "s5_temp_at_tcal_raw"],
            errors="coerce",
        )

        out.loc[
            calc_mask,
            "s5_accepted_temperature_c",
        ] = (
            tcal +
            (accepted_temp - temp_at_tcal) / 2.99
        ).values

    return out

def prepare_dataframe(df: pd.DataFrame, time_column: str) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    out = df.copy()
    out[time_column] = pd.to_datetime(out[time_column], errors="coerce", utc=True)
    out = out.dropna(subset=[time_column]).sort_values(time_column)

    if "epc" not in out.columns:
        out["epc"] = "UNKNOWN"
    else:
        out["epc"] = out["epc"].fillna("UNKNOWN").astype(str)

    if "reader_id" not in out.columns:
        out["reader_id"] = "UNKNOWN"

    # MQTT uses w0/w1; InfluxDB typically stores user0/user1.
    # Keep the full 16-bit word for diagnostics, but also extract the
    # lower 12-bit sensor payload. The upper bits contain status/header
    # information, so plotting the full word can create artificial
    # ~8192-count jumps whenever BEST_ACC (bit 13) changes.
    if "w0" in out.columns:
        out["user0_word"] = out["w0"].apply(hex_or_number)
    elif "user0" in out.columns:
        out["user0_word"] = pd.to_numeric(out["user0"], errors="coerce")

    if "w1" in out.columns:
        out["user1_word"] = out["w1"].apply(hex_or_number)
    elif "user1" in out.columns:
        out["user1_word"] = pd.to_numeric(out["user1"], errors="coerce")

    if "user0_word" in out.columns:
        u0 = pd.to_numeric(out["user0_word"], errors="coerce")
        out["user0_payload"] = u0.apply(
            lambda v: pd.NA if pd.isna(v) else int(v) & 0x0FFF
        )
        if "strain_best_acc" not in out.columns:
            out["strain_best_acc"] = u0.apply(
                lambda v: pd.NA if pd.isna(v) else (int(v) >> 13) & 0x01
            )

    if "w5" in out.columns:
        out["user5_word"] = out["w5"].apply(hex_or_number)
    elif "user5" in out.columns:
        out["user5_word"] = pd.to_numeric(
            out["user5"],
            errors="coerce",
        )

    if "w6" in out.columns:
        out["user6_word"] = out["w6"].apply(hex_or_number)
    elif "user6" in out.columns:
        out["user6_word"] = pd.to_numeric(
            out["user6"],
            errors="coerce",
        )

    if "user1_word" in out.columns:
        u1 = pd.to_numeric(out["user1_word"], errors="coerce")
        out["user1_payload"] = u1.apply(
            lambda v: pd.NA if pd.isna(v) else int(v) & 0x0FFF
        )
        if "temperature_best_acc" not in out.columns:
            out["temperature_best_acc"] = u1.apply(
                lambda v: pd.NA if pd.isna(v) else (int(v) >> 13) & 0x01
            )

    for col in ["rssi", "strain_raw", "temperature_c"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    # v0.23 timing diagnostics:
    # Android v0.19+ publishes one observation time as both timestamp and
    # captured_at, plus captured_at_epoch_ms and device_timezone.
    #
    # Keep timestamp for backward compatibility, but prefer captured_at when
    # available. received_at can come from the backend/collector for persisted
    # data; _received_at is the dashboard's own live MQTT receive time.
    for col in ["timestamp", "captured_at", "received_at", "_received_at"]:
        if col in out.columns:
            out[col] = pd.to_datetime(
                out[col],
                errors="coerce",
                utc=True,
            )

    if "captured_at" not in out.columns:
        if "timestamp" in out.columns:
            out["captured_at"] = out["timestamp"]
        elif time_column in out.columns:
            out["captured_at"] = out[time_column]

    if "captured_at_epoch_ms" in out.columns:
        out["captured_at_epoch_ms"] = pd.to_numeric(
            out["captured_at_epoch_ms"],
            errors="coerce",
        )

    receive_col = None

    if "received_at" in out.columns:
        receive_col = "received_at"
    elif "_received_at" in out.columns:
        receive_col = "_received_at"

    if receive_col is not None and "captured_at" in out.columns:
        out["delivery_delay_ms"] = (
            (
                out[receive_col] -
                out["captured_at"]
            ).dt.total_seconds() * 1000.0
        )

        # Negative delay generally means the device/server clocks are not
        # synchronized. Preserve the raw value for diagnostics rather than
        # silently clipping it to zero.
        out["delivery_delay_source"] = receive_col

    # Dashboard-only interpretation layer for AS3213S.5 tags whose header
    # bits do not match the vendor's documented 0b10 requirement.
    out = add_s5_exploratory_interpretation(out)

    return out
