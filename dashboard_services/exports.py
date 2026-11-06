"""Extracted exports responsibilities; original calculations and widget behavior preserved."""
from dashboard_services.quality import alignment_quality_summary
from dashboard_services.quality import build_session_quality_table
from dashboard_services.quality import session_metadata_integrity
from dashboard_services.settings import VERSION
import io
import json
import pandas as pd
import zipfile

def build_tag_identity_export(session_df: pd.DataFrame, time_column: str):
    """Return one latest metadata row per EPC for an experiment package."""
    if session_df.empty or "epc" not in session_df.columns:
        return pd.DataFrame()

    metadata_columns = [
        "epc",
        "tid_raw",
        "tid_mdid",
        "tid_tmn",
        "tag_manufacturer",
        "tag_chip_family",
        "tag_type",
        "epc_sens_reg",
        "epc_temp_reg",
        "epc_config0",
        "epc_config1",
        "epc_config2",
    ]

    available = [
        col for col in metadata_columns
        if col in session_df.columns
    ]

    if "epc" not in available:
        return pd.DataFrame()

    working = session_df.copy()
    if time_column in working.columns:
        working[time_column] = pd.to_datetime(
            working[time_column],
            utc=True,
            errors="coerce",
        )
        working = working.sort_values(time_column)

    latest = (
        working.groupby("epc", as_index=False)
        .tail(1)
    )

    return latest[available].reset_index(drop=True)

def build_experiment_package(
    session_df: pd.DataFrame,
    session_id: str,
    time_column: str,
    tolerance_ms: int,
    metric_label: str,
    metric_column: str,
    tag_a: str | None,
    tag_b: str | None,
):
    """Build a reproducible ZIP package entirely in memory."""
    quality_df = build_session_quality_table(
        session_df,
        time_column,
    )
    integrity_df = session_metadata_integrity(
        session_df
    )
    identity_df = build_tag_identity_export(
        session_df,
        time_column,
    )

    alignment_df = pd.DataFrame()
    alignment_summary_df = pd.DataFrame()

    if tag_a and tag_b:
        aq = alignment_quality_summary(
            session_df,
            time_column,
            metric_column,
            tag_a,
            tag_b,
            tolerance_ms,
        )
        alignment_df = aq["aligned"].copy()

        if not alignment_df.empty:
            alignment_df.insert(
                0, "session_id", session_id
            )
            alignment_df.insert(
                1, "tag_a_epc", tag_a
            )
            alignment_df.insert(
                2, "tag_b_epc", tag_b
            )

        alignment_summary_df = pd.DataFrame(
            [
                {
                    "session_id": session_id,
                    "tag_a_epc": tag_a,
                    "tag_b_epc": tag_b,
                    "metric": metric_label,
                    "tolerance_ms": tolerance_ms,
                    "tag_a_valid": aq["tag_a_valid"],
                    "tag_b_valid": aq["tag_b_valid"],
                    "aligned_pairs": len(aq["aligned"]),
                    "coverage_pct": aq["coverage_pct"],
                    "mean_gap_ms": aq["mean_gap_ms"],
                    "median_gap_ms": aq["median_gap_ms"],
                    "max_gap_ms": aq["max_gap_ms"],
                }
            ]
        )

    mismatch_count = 0
    if not integrity_df.empty:
        mismatch_count = int(
            (integrity_df["Status"] == "MISMATCH").sum()
        )

    tag_count = (
        int(session_df["epc"].astype(str).nunique())
        if "epc" in session_df.columns
        else 0
    )

    raw_count = int(len(session_df))

    checks = {
        "session_has_data": raw_count > 0,
        "at_least_one_tag": tag_count > 0,
        "metadata_no_mismatch": mismatch_count == 0,
        "quality_summary_created": not quality_df.empty,
    }

    if tag_a and tag_b:
        checks["alignment_summary_created"] = (
            not alignment_summary_df.empty
        )

    package_complete = all(checks.values())

    manifest = {
        "package_format": "RFID experiment package",
        "package_version": "1.0",
        "dashboard_version": VERSION,
        "generated_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "session_id": session_id,
        "source_time_column": time_column,
        "raw_reading_count": raw_count,
        "tag_count": tag_count,
        "alignment": {
            "metric": metric_label,
            "metric_column": metric_column,
            "tolerance_ms": tolerance_ms,
            "tag_a_epc": tag_a,
            "tag_b_epc": tag_b,
        },
        "software_checks": checks,
        "package_complete": package_complete,
        "scientific_validation_note": (
            "Package completeness is a software/data-integrity check only. "
            "It does not validate physical strain, temperature, pressure, "
            "or the scientific appropriateness of the selected alignment tolerance."
        ),
        "files": [
            "manifest.json",
            "session_raw.csv",
            "tag_quality.csv",
            "metadata_integrity.csv",
            "tag_identity.csv",
        ],
    }

    if not alignment_summary_df.empty:
        manifest["files"].append(
            "alignment_summary.csv"
        )
    if not alignment_df.empty:
        manifest["files"].append(
            "aligned_pairs.csv"
        )

    buffer = io.BytesIO()
    with zipfile.ZipFile(
        buffer,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(
                manifest,
                indent=2,
                default=str,
            ),
        )
        archive.writestr(
            "session_raw.csv",
            session_df.to_csv(index=False),
        )
        archive.writestr(
            "tag_quality.csv",
            quality_df.to_csv(index=False),
        )
        archive.writestr(
            "metadata_integrity.csv",
            integrity_df.to_csv(index=False),
        )
        archive.writestr(
            "tag_identity.csv",
            identity_df.to_csv(index=False),
        )

        if not alignment_summary_df.empty:
            archive.writestr(
                "alignment_summary.csv",
                alignment_summary_df.to_csv(index=False),
            )

        if not alignment_df.empty:
            archive.writestr(
                "aligned_pairs.csv",
                alignment_df.to_csv(index=False),
            )

    return {
        "bytes": buffer.getvalue(),
        "manifest": manifest,
        "quality": quality_df,
        "integrity": integrity_df,
        "identity": identity_df,
        "alignment_summary": alignment_summary_df,
        "aligned_pairs": alignment_df,
    }
