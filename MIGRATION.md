# Future lab server migration — RFID Offline Pilot v0.3

1. Enumerate `sessions/<session-id>/<raw-sha256>.zip|csv` and `sessions/_metadata/` in S3. Use a restricted AWS identity, never anonymous access.
2. Download files **without modification**; recompute SHA256; parse manifest and validate row count, Session ID, Reader ID, UTC timestamps and per-reading IDs.
3. Write raw records to the permanent system with an idempotent mapping using `(reader_id, session_id, reading_id)` (or an agreed stable fallback). Do not alter original captured timestamps or raw USER bytes.
4. Preserve append-only tag, Session and calibration-plan metadata events independently of raw records. Do not convert a self-declared editor identifier into a verified user identity.
5. Apply approved Decoder Profile and calibration/model **versions** in a derived layer. Do not interpret pilot synthetic predictions or header-valid temperatures as independent physical validation. Retain provenance.
6. Import reference metadata annotations only where absent in original raw records, with separate source attribution and reviewer approval.
7. Compare counts, SHA256 manifest and a selected set of derived results against cloud pilot; export a migration audit and back up before any S3 retention decision.
8. Do not delete the original S3 Session archives until the lab holds two verified separate copies. Keep the final IAM disabled/retired when cloud operations end.

Current S3 IAM policy covers `sessions/*`, so metadata events use `sessions/_metadata/tag/`, `sessions/_metadata/session/`, and `sessions/_metadata/plan/` without expanding privileges.
