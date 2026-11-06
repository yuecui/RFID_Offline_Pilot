# RFID Offline Pilot v0.3.1 — Advanced Diagnostics UI

## Scope

**Streamlit-only UI patch.** No changes to Android Offline Mode, MQTT, S3, AWS credentials, source ZIP bytes, decoder, calibration, charts, or persistent data schema.

- The prior `Inspect source/derived layer` selectbox listing `Read 1` ... `Read 100` is replaced by a collapsed **Advanced Diagnostics · Inspect individual readings** section.
- Select EPC first; each EPC's readings are ordered by recorded UTC timestamp.
- Navigate directly by **record number within the EPC** (1 to its full reading count), or search by **UTC time / reading ID**. Only the first 30 search hits are shown at once, with the total matches disclosed, avoiding huge dropdowns.
- Record detail labels include an abbreviated EPC, precise UTC timestamp, and abbreviated reading ID. The existing `build_layered_record()` output is preserved.
- It is read-only. Original archive files and derived values are untouched.

## Safe upgrade from existing v0.3

In the `RFID_Offline_Pilot` repository:

```bash
git status
git switch -c fix/compact-read-inspector
unzip -o ~/Downloads/RFID_Offline_Pilot_v0.3.1_Inspector_UI_PATCH.zip -d .
git diff --stat
git diff --check
```

The patch only adds/modifies:

- `offline_extended.py` (updated)
- `offline_inspector.py` (new helper)
- `tests/test_offline_inspector.py` (new tests)
- `UPGRADE_031.md` (this note)

**Do not override** `.streamlit/secrets.toml`, `s3_store.py`, existing Session ZIPs or any Android source.

Run local test using a working Python environment (e.g. 3.12; Homebrew 3.15 may have a broken Expat/ensurepip setup on this Mac):

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt pytest
PYTHONPATH=. python -m pytest -q tests
python -m streamlit run app.py
```

If Python 3.12 is unavailable, use another known working supported Python, rather than `--break-system-packages`.

Then:

```bash
git add offline_extended.py offline_inspector.py tests/test_offline_inspector.py UPGRADE_031.md
git commit -m "fix(offline): compact advanced reading inspection by EPC and time"
# merge/rebase the tested branch into main before pushing; don't force-push
```

On Streamlit Cloud, open **Session Library → Load selected session → Provenance & Export → Advanced Diagnostics**. Select a tag and record number, or search by UTC time/reading ID. Verify with a real session (e.g., the 1,145-read 2026-11-05 TC22R ZIP).

## Android Session Lock (existing v0.26.0)

`AcquisitionSession.kt` still sets `sessionLocked=true` when `RfidController.startScanVerified()` calls `onLockSession()`. The snapshot freezes Session ID, known pressure/temperature, condition, note, and operator identity during scanning. UI metadata fields are disabled while locked; `Stop Acquisition` calls `unlockSessionAfterScan()`. `OfflineSessionStore.beginSession()` separately refuses a Session ID already containing readings; stopping a scan does **not** erase or make previous readings editable. There is **no** separate permanent final-approval lock status in the Offline SQLite schema.
