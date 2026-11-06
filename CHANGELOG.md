# RFID Offline Pilot Changelog

## v0.3 — Extended Offline Analysis (2026-11-05)

- Calculated temperature for documented-format S.5/T.5 payloads with USER5/USER6; T.5 192-bit EPC inference flagged for operator review; no physical validation asserted.
- Raw and reference metric options including USER5/USER6 and independent lab reference conditions.
- Tag alias, tag variant and Session reference annotation events in immutable S3 metadata objects.
- Calibration coverage planning, reference datasets, readiness ZIP, provenance and experiment package ZIP from original Dashboard pure helpers.
- Session Replay, per-Tag pairing, multi-Session overlay and Chicago-local-date two-day comparison.
- Draft model schema checks and synthetic-only model preview. No real PSI estimate from unverified inputs.
- Regression tests expanded to 19 tests; package contains synthetic fixtures only.

## v0.2 — Original Dashboard Charts

- Original Dashboards multitag Altair plots, recorded time windows, USER word diagnostics, Session quality and comparison.

## v0.1 — Upload & Archive

- Private Streamlit Cloud to private S3, immutable Session files, SHA256 and upload/download.
