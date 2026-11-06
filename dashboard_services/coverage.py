"""Extracted coverage responsibilities; original calculations and widget behavior preserved."""
from dashboard_services.references import build_reference_session_summary
import pandas as pd

def build_condition_coverage_table(
    df: pd.DataFrame,
    time_column: str,
):
    """
    Summarize available reference conditions by pressure/temperature pair.

    This is a planning/coverage tool only. It does not fit or validate a
    pressure model.
    """
    if (
        df.empty
        or "session_id" not in df.columns
        or "epc" not in df.columns
    ):
        return pd.DataFrame()

    work = df.copy()

    if time_column in work.columns:
        work[time_column] = pd.to_datetime(
            work[time_column],
            utc=True,
            errors="coerce",
        )

    work["known_pressure_psi_num"] = pd.to_numeric(
        work.get("known_pressure_psi"),
        errors="coerce",
    )
    work["known_temperature_c_num"] = pd.to_numeric(
        work.get("known_temperature_c"),
        errors="coerce",
    )

    rows = []

    grouped = work.groupby(
        ["known_pressure_psi_num", "known_temperature_c_num"],
        dropna=False,
    )

    for (pressure, temperature), group in grouped:
        session_count = int(
            group["session_id"]
            .dropna()
            .astype(str)
            .nunique()
        )
        tag_count = int(
            group["epc"]
            .dropna()
            .astype(str)
            .nunique()
        )
        reading_count = int(len(group))

        session_ids = sorted(
            group["session_id"]
            .dropna()
            .astype(str)
            .unique()
            .tolist()
        )

        if time_column in group.columns:
            times = group[time_column].dropna()
            first_time = (
                times.min()
                if not times.empty
                else pd.NaT
            )
            last_time = (
                times.max()
                if not times.empty
                else pd.NaT
            )
        else:
            first_time = pd.NaT
            last_time = pd.NaT

        rows.append(
            {
                "known_pressure_psi": pressure,
                "known_temperature_c": temperature,
                "sessions": session_count,
                "tags": tag_count,
                "readings": reading_count,
                "session_ids": ", ".join(session_ids),
                "first_reading": first_time,
                "last_reading": last_time,
            }
        )

    return pd.DataFrame(rows)

def build_session_reference_quality(
    df: pd.DataFrame,
    time_column: str,
    minimum_readings: int,
    minimum_best_acc_pct: float,
):
    """
    One row per session/tag with simple data-readiness checks for planning.
    """
    summary = build_reference_session_summary(
        df,
        time_column,
    )

    if summary.empty:
        return summary

    statuses = []

    for _, row in summary.iterrows():
        reasons = []

        if pd.isna(row.get("known_pressure_psi")):
            reasons.append("missing pressure")

        if pd.isna(row.get("known_temperature_c")):
            reasons.append("missing temperature")

        if int(row.get("readings", 0) or 0) < minimum_readings:
            reasons.append(
                f"readings < {minimum_readings}"
            )

        strain_best = row.get("strain_best_acc_pct")
        temp_best = row.get("temperature_best_acc_pct")

        if (
            strain_best is not None
            and not pd.isna(strain_best)
            and float(strain_best) < minimum_best_acc_pct
        ):
            reasons.append(
                f"strain BEST_ACC < {minimum_best_acc_pct:g}%"
            )

        if (
            temp_best is not None
            and not pd.isna(temp_best)
            and float(temp_best) < minimum_best_acc_pct
        ):
            reasons.append(
                f"temp BEST_ACC < {minimum_best_acc_pct:g}%"
            )

        statuses.append(
            (
                "READY" if not reasons else "ATTENTION",
                "; ".join(reasons),
            )
        )

    summary = summary.copy()
    summary["planning_status"] = [
        item[0] for item in statuses
    ]
    summary["planning_reason"] = [
        item[1] for item in statuses
    ]

    return summary

def build_expected_condition_grid(
    pressure_levels: list[float],
    temperature_levels: list[float],
):
    if not pressure_levels or not temperature_levels:
        return pd.DataFrame()

    rows = []
    for pressure in pressure_levels:
        for temperature in temperature_levels:
            rows.append(
                {
                    "known_pressure_psi": float(pressure),
                    "known_temperature_c": float(temperature),
                }
            )

    return pd.DataFrame(rows)

def compare_expected_to_observed_conditions(
    expected_df: pd.DataFrame,
    observed_df: pd.DataFrame,
    minimum_sessions_per_condition: int,
):
    if expected_df.empty:
        return pd.DataFrame()

    if observed_df.empty:
        result = expected_df.copy()
        result["sessions"] = 0
        result["tags"] = 0
        result["readings"] = 0
        result["coverage_status"] = "MISSING"
        return result

    obs = observed_df.copy()

    merged = expected_df.merge(
        obs[
            [
                "known_pressure_psi",
                "known_temperature_c",
                "sessions",
                "tags",
                "readings",
            ]
        ],
        on=[
            "known_pressure_psi",
            "known_temperature_c",
        ],
        how="left",
    )

    for col in ["sessions", "tags", "readings"]:
        merged[col] = (
            pd.to_numeric(
                merged[col],
                errors="coerce",
            )
            .fillna(0)
            .astype(int)
        )

    merged["coverage_status"] = merged["sessions"].apply(
        lambda count: (
            "READY"
            if count >= minimum_sessions_per_condition
            else (
                "PARTIAL"
                if count > 0
                else "MISSING"
            )
        )
    )

    return merged

def build_next_test_recommendations(
    coverage_df: pd.DataFrame,
):
    """
    Return missing/partial condition rows only.

    These are planning suggestions based on user-selected target levels, not
    scientific claims about the correct experimental design.
    """
    if coverage_df.empty:
        return pd.DataFrame()

    needs_work = coverage_df[
        coverage_df["coverage_status"].isin(
            ["MISSING", "PARTIAL"]
        )
    ].copy()

    if needs_work.empty:
        return needs_work

    needs_work["recommended_action"] = needs_work.apply(
        lambda row: (
            "Collect new session"
            if row["coverage_status"] == "MISSING"
            else "Collect additional replicate session"
        ),
        axis=1,
    )

    return needs_work.sort_values(
        [
            "coverage_status",
            "known_temperature_c",
            "known_pressure_psi",
        ]
    )
