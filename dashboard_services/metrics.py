"""Extracted metrics responsibilities; original calculations and widget behavior preserved."""
import pandas as pd

def history_metric_summary(frame, value_col):
    if frame.empty or value_col not in frame.columns:
        return pd.DataFrame()

    data = frame.copy()
    data[value_col] = pd.to_numeric(data[value_col], errors="coerce")
    data = data.dropna(subset=["epc", value_col])
    if data.empty:
        return pd.DataFrame()

    group_cols = []
    if "comparison_date" in data.columns:
        group_cols.append("comparison_date")
    group_cols.append("epc")

    return (
        data.groupby(group_cols)[value_col]
        .agg(["count", "mean", "min", "max"])
        .reset_index()
        .rename(
            columns={
                "count": "readings",
                "mean": "mean",
                "min": "min",
                "max": "max",
            }
        )
    )

def align_two_tags(
    tag_a_df: pd.DataFrame,
    tag_b_df: pd.DataFrame,
    time_column: str,
    value_column: str,
    tolerance_ms: int,
):
    left = tag_a_df[[time_column, value_column]].copy()
    right = tag_b_df[[time_column, value_column]].copy()

    left[value_column] = pd.to_numeric(left[value_column], errors="coerce")
    right[value_column] = pd.to_numeric(right[value_column], errors="coerce")

    left = left.dropna().sort_values(time_column)
    right = right.dropna().sort_values(time_column)
    if left.empty or right.empty:
        return pd.DataFrame()

    left = left.rename(columns={value_column: "tag_a", time_column: "time_a"})
    right = right.rename(columns={value_column: "tag_b", time_column: "time_b"})

    # merge_asof needs the same key name, but we keep a copy of B time so the
    # actual pair separation can be reported.
    left["pair_time"] = left["time_a"]
    right["pair_time"] = right["time_b"]

    aligned = pd.merge_asof(
        left.sort_values("pair_time"),
        right.sort_values("pair_time"),
        on="pair_time",
        direction="nearest",
        tolerance=pd.Timedelta(milliseconds=tolerance_ms),
        suffixes=("_a", "_b"),
    )

    aligned = aligned.dropna(subset=["tag_a", "tag_b", "time_b"])
    if aligned.empty:
        return aligned

    aligned["difference"] = aligned["tag_a"] - aligned["tag_b"]
    aligned["absolute_difference"] = aligned["difference"].abs()
    aligned["time_gap_ms"] = (
        aligned["time_a"] - aligned["time_b"]
    ).abs().dt.total_seconds() * 1000.0

    return aligned

def metric_options_for(df: pd.DataFrame):
    """Return user-facing metric names with meaning first, address second."""
    options = {}

    variants = set()
    for col in ["dashboard_tag_variant", "tag_type", "sensor_variant"]:
        if col in df.columns:
            variants.update(df[col].dropna().astype(str).tolist())

    has_t5 = any(v in {"AS3213T.5", "AS3213T5"} for v in variants)

    if (
        "temperature_c" in df.columns
        and pd.to_numeric(df["temperature_c"], errors="coerce").notna().any()
    ):
        options["Temperature (°C) — calculated from USER1 + USER5 + USER6"] = (
            "temperature_c",
            "Temperature (°C)",
        )

    if (
        has_t5
        and "temperature_raw" in df.columns
        and pd.to_numeric(df["temperature_raw"], errors="coerce").notna().any()
    ):
        options["Temperature raw — USER1<12:0> / 8"] = (
            "temperature_raw",
            "Temperature raw",
        )

    if (
        "s5_accepted_strain_raw" in df.columns
        and pd.to_numeric(df["s5_accepted_strain_raw"], errors="coerce").notna().any()
    ):
        options["Strain raw — USER0<11:0> / 4 (S.5 NON-VALIDATED)"] = (
            "s5_accepted_strain_raw",
            "S.5 accepted strain raw",
        )

    if (
        "s5_accepted_temperature_raw" in df.columns
        and pd.to_numeric(df["s5_accepted_temperature_raw"], errors="coerce").notna().any()
    ):
        options["Temperature raw — USER1<11:0> / 4 (S.5 NON-VALIDATED)"] = (
            "s5_accepted_temperature_raw",
            "S.5 accepted temperature raw",
        )

    if (
        "s5_accepted_temperature_c" in df.columns
        and pd.to_numeric(df["s5_accepted_temperature_c"], errors="coerce").notna().any()
    ):
        options["Temperature (°C) — USER1 + USER5 + USER6 (S.5 NON-VALIDATED)"] = (
            "s5_accepted_temperature_c",
            "S.5 calculated temperature (°C)",
        )

    if "user0_payload" in df.columns:
        options["USER0 payload — bits <11:0> (diagnostic)"] = (
            "user0_payload",
            "USER0 payload",
        )

    if "user1_payload" in df.columns:
        options["USER1 payload — bits <11:0> (diagnostic)"] = (
            "user1_payload",
            "USER1 payload",
        )

    if "user0_word" in df.columns:
        options["USER0 packed word — bits <15:0> (diagnostic)"] = (
            "user0_word",
            "USER0 packed word",
        )

    if "user1_word" in df.columns:
        options["USER1 packed word — bits <15:0> (diagnostic)"] = (
            "user1_word",
            "USER1 packed word",
        )

    options["Signal strength — RSSI"] = ("rssi", "RSSI (dBm)")
    return options
