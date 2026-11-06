# Update your existing Streamlit app from v0.2 to v0.3

**Scope:** Private Streamlit Community Cloud + private S3, offline analysis only. No new AWS services, IAM permissions, or secrets are required: the new tag catalog, annotations and plans live under `sessions/_metadata/*`, which is already allowed by the v0.2 least-privilege policy (`sessions/*`). Keep the app private.

## Safe update

```bash
cd ~/Developer/RFID_Offline_Pilot  # replace if your project lives elsewhere
git status                          # require clean working tree
git switch -c feat/offline-dashboard-v03
# Unzip v0.3_UPGRADE_ONLY.zip into THIS repository root
unzip -o ~/Downloads/RFID_Offline_Pilot_v0.3_UPGRADE_ONLY.zip -d .
git diff --stat
python3 -m pip install -r requirements.txt pytest
PYTHONPATH=. python3 -m pytest -q tests
python3 -m compileall -q app.py offline_analysis.py offline_profiles.py offline_metadata.py offline_extended.py offline_views.py
```

Review any local changes before applying this replacement. The ZIP contains neither `.streamlit/secrets.toml` nor AWS keys. `git diff --check` is recommended.

Run locally with `streamlit run app.py` and test the 13 tabs; on success commit, push the new branch, and choose whether to merge it into Streamlit Cloud's deployment branch `main`. Streamlit private app secrets remain unchanged.

## Real TC22R Session

```bash
python3 scripts/audit_offline_session.py ~/Downloads/OFF-*.zip
```

The temperature graph is offered only when USER1, USER5, USER6 and supported tag format checks permit it. When a 192-bit EPC and USER1 header infer T.5, the result is explicitly labelled *REVIEW* until its tag identity is confirmed. For S.5 tags, assign verified variant via **Tag identity / Rename**; original raw ZIP is never rewritten. Header-valid numerical temperature remains **not independently physically validated**.

## Acceptance

1. v0.2's archived original Session still loads byte-for-byte from S3.
2. Temperature metric appears for eligible readings, on Recorded trends, Replay, Two-tag alignment and multi-session comparison.
3. Tag identity edits and session references persist after reload; immutable Session ZIP SHA256 does not change.
4. Calibration Plans archive without activating a physical pressure model; reference dataset, readiness, package ZIP and derived CSV download work.
5. All unapproved physical pressure estimates and pressure decisions remain unavailable.
6. Online MQTT, Reader approval, real-time ACK and InfluxDB are not provided by this Streamlit+S3 deployment.

See `README.md`, `SOURCE_AUDIT.md`, `RELEASE_STATUS.md` and `MIGRATION.md` for full details.
