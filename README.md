# RFID Offline Pilot v0.3 — Original Dashboard Offline Analysis

**Purpose:** make existing TC22R offline Session ZIP files usable in a **private** Streamlit Community Cloud app backed by immutable **private AWS S3** objects, while the lab's permanent server is pending. This is **not** the live RFID platform.

## What this release adds beyond v0.2

- **Temperature**: T.5 strict USER1 (`0b11`) + USER5/USER6 calibration formula, and S.5 strict USER0/USER1 (`0b10`, reserved-bit checks), ported from the uploaded Android `AsygnDecoder.kt`. Numeric temperature is marked `HEADER_VALID_CALCULATED_NOT_PHYSICALLY_VALIDATED`; it must not be portrayed as scientifically calibrated/validated. T.5-like 192-bit EPC plus matching USER1 header may be inferred for exploratory identification; confirm variant in Tag catalog. S.5 exploratory readings with nonconforming header are kept separate and labelled NON-VALIDATED.
- Full recorded trend menu: temperature °C (when format/calibration present), raw temperature, USER0/1/5/6 words, S.5 exploratory raw strain/temperature, RSSI, independent known reference pressure/temperature.
- Variant-aware tag/data-quality diagnostics with explicit support for unknown tags (no invented temperature).
- S3-backed **Tag name/variant annotations**, **Session reference-pressure, reference-temperature and condition annotations** via append-only JSON events. Raw uploads are never modified, and nonempty original reference values are never silently overwritten. Editors provide a *self-declared* name, **not authenticated identity**.
- Calibration condition coverage planning, candidate reference dataset ZIP, structural experiment Readiness evaluation/ZIP, layered record provenance and experiment package ZIP, reusing corresponding modules from the uploaded original Dashboard source.
- Recorded Session Replay with time-progress slider (not live MQTT); two-tag nearest-time alignment; historical multi-Session overlay and **two different Chicago-local-date** comparison; comprehensive derived CSV exports.
- Calibration Plan **archive and download**; validation of DRAFT pressure model schema and **SYNTHETIC-only** model preview using the original production code. Uploading a plan NEVER activates a model, and no raw USER values are misrepresented as verified PSI.

## Status and explicit limits

1. `19` offline Python logic / export tests passed in the authoring environment. A separate mocked UI import/render smoke test also passed. **The hosted Streamlit UI, S3 cloud writes, and deployment have NOT yet been verified with v0.3.** Redeploy and retest before laboratory use.
2. Your actual 1,145-reading TC22R ZIP was processed *privately* for local contract checks; **real measurements are not included in this release archive.** The repo contains synthetic samples only.
3. These functions **cannot be fully reproduced** in an offline, serverless Streamlit app: live MQTT data, broker ACL / Reader status, actual Android login/reader approval, collector ACK/Delivery Recovery, production pressure-model activation, and InfluxDB lifecycle operations. Those remain with the lab's Docker service.
4. The uploaded original backend currently uses a `header_only_v1` physical decoder contract. **Matching USER header bits alone does not validate an engineering strain or a pressure estimate.** Production estimated PSI and `LOW/NORMAL/HIGH` decisions remain intentionally unavailable until physically validated decoder and model evidence exists.
5. In the private Streamlit Cloud app, authorized *viewers of the app* can see the shared Sessions, annotations, and plans. There is currently **no per-user permission** or verified-editor authorization for these metadata operations. Do not make the app public.
6. S3 uploads: max 25 MiB original archive, max 200,000 rows, max 64 MiB decompressed ZIP. Large archives or large multi-Session comparisons may exceed free Streamlit memory. S3 is object storage, not a row-query engine.

## Files

- `app.py` — four top-level tabs (Upload Session, Session Library, Compare Sessions, Calibration Plans)
- `offline_views.py` — recorded trends, EPC, tag alignment, quality, replay, two-day/session comparison
- `offline_extended.py` — catalog/annotations, calibration planning, readiness, provenance, packages, pressure status
- `offline_profiles.py` — guarded S.5/T.5 temperature formula and variant diagnostics
- `offline_analysis.py` — adapter from TC22R Session ZIP/CSV to original Dashboard DataFrames
- `offline_metadata.py` — append-only S3 metadata event handling
- `dashboard_components/`, `dashboard_services/` — corresponding pure/plotting helpers from the uploaded original Dashboard `src/`
- `pressure_calibration.py`, `pressure_decision.py`, `pressure_validation.py`, `pressure_model_schema.json` — original strictly guarded model/schema and synthetic preview
- `s3_store.py` / `rfid_formats.py` — unchanged S3 immutable Session archive and input validation

## Deploy safely over the existing v0.2 repo

Do not remove your existing AWS secrets, change the S3 bucket, or overwrite the original Android/production Dashboard repo.

```bash
cd ~/Developer/RFID_Offline_Pilot
# Ensure tracked modifications are saved; the next unzip replaces project source.
git status
cp -R . ../RFID_Offline_Pilot_before_v03_backup
unzip -o ~/Downloads/RFID_Offline_Pilot_v0.3_Offline_Analysis.zip -d .
git diff --stat
python3 -m pytest -q  # optional local test env
# Verify no credentials or real experimental data are staged.
git add app.py offline_analysis.py offline_views.py offline_extended.py \
    offline_profiles.py offline_metadata.py dashboard_components dashboard_services \
    pressure_calibration.py pressure_validation.py pressure_decision.py \
    pressure_model_schema.json requirements.txt README.md MIGRATION.md \
    SOURCE_AUDIT.md CHANGELOG.md examples tests

git diff --cached --stat
git commit -m "feat(offline): restore extended RFID analysis, temperature and calibration planning"
git push origin main
```

If the GitHub `main` branch advanced, fetch/rebase safely while the tree is clean; do **not** force-push. Streamlit Community Cloud typically redeploys after `main` receives a commit. Existing `st.secrets["aws"]` fields stay the same.

## Acceptance test sequence

1. Open the **private** deployed App; confirm the new analysis tabs, **Calibration Plans** top-level tab and new `Temperature (°C)` metric for valid T.5 example.
2. Upload `examples/diagnostic_t5_sample.zip`; expect six synthetic records. The T.5-like tag has calculated temperature; unknown type has no calculated temperature. Check `Data quality → Variant-aware USER header diagnostics`.
3. Upload the **real** TC22R offline ZIP locally held by the user. Verify original record count/EPC count and strict T.5 diagnostics. Preserve invalid/unknown variants and read their raw words without inventing temperatures.
4. In `Tag identity / Rename`, save a friendly name and (only if independently confirmed) S.5/T.5 variant. Reload Session to see annotations. Original ZIP sha256 must not change.
5. In `Session details`, annotate **missing** reference pressure/temperature and condition; reload. Original nonempty reference fields remain unchanged. Do not treat user-entered references as physically independently validated.
6. Compare two tags (nearest timestamp) and two saved Sessions (elapsed time and Chicago-local-day overlay).
7. Download readiness report ZIP, reference dataset ZIP and experiment package ZIP; verify that **manifest.json** and CSV members open.
8. In `Calibration Plans`, upload a valid JSON research plan, then download it. A draft model can only run a clearly marked *synthetic preview*, not generate real pressure from RFID words.
9. Refresh browser; load Session from S3; download the **original** archive and verify SHA-256 equal to the original.
10. Verify old v0.2 Sessions still load; confirm the AWS Budget alert remains enabled.

## Security and data integrity

- **S3:** bucket remains private, Block Public Access enabled, SSE-S3. The IAM policy `iam/rfid-s3-policy.template.json` already permits `sessions/*`, including append-only metadata under `sessions/_metadata/`. Do not add `DeleteObject` or wildcard S3 account permissions.
- **Secrets:** only in Streamlit Cloud Secrets; not in Git, screenshots, or logs. Keep Streamlit App **private** with restricted invited viewers.
- **Metadata model:** each edit is a uniquely named new JSON object under `sessions/_metadata/tag/`, `/session/` or `/plan/`. Older edits are never deleted/overwritten. Metadata editor name is self-declared; use external access logs if verified attribution is required.
- **Scientific status:** recorded raw USER words, reference inputs, derived diagnostic temperature, synthetic model preview and physically verified PSI are different categories. No pressure determination from raw sensor words without validated model and decoder evidence.
- **Backup/migration:** maintain TC22R original ZIP and a second off-cloud backup; migrate S3 archived ZIPs and metadata events into the future lab-server importer. Preserve recording timestamps, EPC, original USER words, Session / Reading IDs, SHA256 and interpretation versions.

See `MIGRATION.md` for permanent-server data import and `SOURCE_AUDIT.md` for source-derived coverage.
