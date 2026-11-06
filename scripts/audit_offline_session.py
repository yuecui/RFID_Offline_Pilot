"""Audit an Android Offline Session ZIP/CSV before uploading to Streamlit.

Usage (from project root):
    python scripts/audit_offline_session.py path/to/session.zip
    python scripts/audit_offline_session.py path/to/session.zip --variants variants.json

variants.json: {"HEX_EPC": "AS3213S.5", "OTHER_HEX_EPC": "AS3213T.5"}
Only assign a variant after confirming the tag identity. No pressure estimates.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Allow invocation from any working directory without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from offline_analysis import frame_from_parsed, metric_options
from rfid_formats import parse_session, SessionValidationError


def audit(path: Path, variants: dict[str, str] | None = None) -> dict:
    data = parse_session(path.read_bytes(), path.name)
    catalog = {epc.upper(): {"variant": variant} for epc, variant in (variants or {}).items()}
    frame = frame_from_parsed(data, catalog)
    tags = []
    for epc, group in frame.groupby("epc"):
        valid_t = int(group["temperature_c"].notna().sum())
        tags.append({
            "epc": epc,
            "readings": int(len(group)),
            "variant": str(group["offline_variant"].mode().iloc[0]),
            "variant_source": str(group["offline_variant_origin"].mode().iloc[0]),
            "temperature_rows_format_valid": valid_t,
            "temperature_statuses": group["temperature_calc_status"].value_counts().to_dict(),
        })
    return {
        "session_id": data.manifest["session_id"],
        "reader_id": data.manifest["reader_id"],
        "source_sha256": data.raw_sha256,
        "readings": len(frame),
        "unique_epcs": frame["epc"].nunique(),
        "temperature_rows_format_valid": int(frame["temperature_c"].notna().sum()),
        "temperature_is_physically_validated": False,
        "pressure_estimates": "UNAVAILABLE — physical validation/calibration required",
        "metric_labels": list(metric_options(frame)),
        "tags": tags,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit RFID offline Session import")
    parser.add_argument("session", type=Path)
    parser.add_argument("--variants", type=Path, help="JSON dictionary of verified EPC -> AS3213S.5 or AS3213T.5")
    args = parser.parse_args()
    variants = json.loads(args.variants.read_text()) if args.variants else None
    if variants and (not isinstance(variants, dict) or any(v not in {"AS3213S.5", "AS3213T.5"} for v in variants.values())):
        parser.error("variants must be JSON EPC -> AS3213S.5 or AS3213T.5")
    try:
        report = audit(args.session, variants)
    except (SessionValidationError, FileNotFoundError, ValueError) as exc:
        print(f"Validation error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
