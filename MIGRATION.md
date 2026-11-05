# Migration contract: Pilot S3 to lab server / InfluxDB 3

## Current assurances

- Original uploaded CSV/ZIP bytes are stored unchanged under content-addressed keys.
- Upload uses `IfNoneMatch='*'` to prevent accidental overwrites.
- The app never receives `DeleteObject` permission.
- Format checks validate one session/reader, timestamp timezone, values and ZIP structure.

## Known gaps that MUST be resolved before real experiments

- Unknown actual Android `Session Export` CSV/ZIP schema: map it without dropping fields.
- Actual raw acquisition fields beyond EPC, USER0, USER1, RSSI, timestamps (CONFIG, read index, session metadata, Tcal, etc.): extend schema.
- Record-level globally stable ID for repeated scans and replay/dedup.
- Validated sensor decoder, calibration plans, estimation and pressure decision modules not included in this starter.
- Cloud import acknowledgements and reconciliation versus on-device local exports.
- Explicit policy for shared file visibility among operators.

## Suggested importer order

1. List S3 under `sessions/` (use dedicated migration identity, not the deployed app credential).
2. Download raw original object, hash it, compare with SHA-256 from key and metadata.
3. Verify one Session+Reader and expected record count; create immutable import receipt.
4. Normalize to the production schema with a versioned adapter; preserve raw data and timestamps.
5. Apply idempotent record keys before writing to InfluxDB 3.
6. Trigger established decoder/calibration/decision pipeline **without overwriting raw values**.
7. Reconcile record counts, timestamps, session assignment, tag IDs, rejected records and derived results.
8. Archive audit report and backup; only then consider reducing temporary cloud usage.
