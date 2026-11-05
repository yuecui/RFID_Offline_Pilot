# RFID Offline Pilot v0.1 — Streamlit Community Cloud + private S3

**Status: local sample parsing tested; AWS account resources NOT created; actual S3 upload NOT run.**

A small, isolated pilot for interim lab experiments. It does **not** replace the
existing `RFID_Dashboard` production stack. The current Android export format
and production decoder/calibration implementation were not provided. Therefore
this starter accepts the *pilot interchange format* below; mapping the actual
TC22R export and pressure estimation is a required integration step.

## Recommended production boundary

- A **private** Streamlit Community Cloud app handles uploads, analysis, and user access through invited viewers.
- A **private** Amazon S3 **general purpose** bucket in `us-east-2` stores *immutable original* CSV/ZIP files under `sessions/`.
- An IAM programmatic identity can only `ListBucket` for pilot prefixes and `GetObject`/`PutObject` for pilot objects. It **cannot delete** objects, manage IAM, create buckets, or access unrelated S3 buckets.
- No credentials, raw data, or passwords go into GitHub.
- Public access blocking and default SSE-S3 encryption stay enabled on the S3 bucket.
- S3 object keys include the raw SHA-256 hash. The application uses `If-None-Match: *` to refuse accidental overwrites. Retain separate offline backups for irreplaceable research data.

## 1. AWS Budget (do this first)

In the **AWS Console** (account owner/billing-permitted identity):

1. Open **Billing and Cost Management → Budgets → Create budget**.
2. Choose **Cost budget** (Monthly, recurring; custom budget if required) with a **USD $5 monthly budget** for this small pilot.
3. Configure actual-spend email alerts at **$1 (20%)**, **$3 (60%)**, **$5 (100%)**, and optionally forecasted spend approaching $5.
4. Enter the billing contact's email and **complete email recipient verification** if requested.
5. Check **Billing → Free Tier** separately; monitor gross resource consumption as credits may offset charges. Consider a free-tier usage alert if available to your account.
6. Remember: **Budgets are alerts, not a spending cap**; billing reports and alert emails can be delayed. Do not create EC2/RDS/NAT Gateway for this project.

AWS instructions: https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-create.html

## 2. S3 bucket and least-privileged identity

1. Finish bucket creation and copy its **EXACT final name** from the S3 Buckets list. If using *Account Regional namespace*, the final name may include an AWS-added suffix.
2. Keep **Block all public access** enabled; bucket owner enforced (ACLs disabled); SSE-S3 encryption; avoid public bucket policies.
3. In **IAM → Policies → Create policy → JSON**, paste `iam/rfid-s3-policy.template.json` and replace every `REPLACE_WITH_EXACT_BUCKET_NAME` with the exact bucket name; name the policy `RFIDOfflinePilotS3RW`. It covers only the `sessions/` and `healthchecks/` prefixes and gives no delete permission.
4. In **IAM → Users → Create user**, create `rfid-offline-streamlit` **without console access**, then attach only the new customer-managed policy. Use least privilege; do not attach `AmazonS3FullAccess`, `AdministratorAccess`, or an AWS root access key.
5. For Streamlit Community Cloud (an external host that does not automatically have an AWS role), create one **programmatic access key** for that restricted IAM user. Keep it only in a password manager or Streamlit **Secrets**; never in Git, chat, screenshots, or an Android APK. Consider more advanced short-lived credentials if an approved federation path is available.
6. Record which teammate owns the IAM user, and plan to disable the access key after migrating to the lab server.

AWS IAM example: https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_examples_s3_rw-bucket-console.html

## 3. Test a REAL S3 upload/download

On a computer with AWS CLI configured for **the restricted IAM user**:

```bash
aws sts get-caller-identity
export RFID_S3_BUCKET='EXACT-FINAL-BUCKET-NAME'
python scripts/test_s3_session.py
```

Expected: `PASS: Real S3 sample Session upload/download; SHA256, bytes and records match`.
The synthetic test Session is stored at `sessions/PILOT_TEST_001/<sha256>.zip`, and the uploaded bytes are downloaded and verified without overwriting any existing file. The application never uses a public bucket URL. **This step has not been executed on your AWS account by ChatGPT.**

If the test fails with AccessDenied, confirm the policy bucket ARN matches the *exact* bucket name, and that the correct IAM user credentials are active.

## 4. Streamlit Community Cloud deployment

1. Create a **new private GitHub repo**, e.g. `RFID_Offline_Pilot`. Put all files in this folder in the repo root. **Do not overwrite the existing RFID Dashboard repo.**
2. Run locally: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && streamlit run app.py`. Without secrets, uploads can be previewed but cannot be archived.
3. Optionally save *local* `.streamlit/secrets.toml` by copying `.streamlit/secrets.toml.example`, replacing the placeholders, and verifying it is ignored by Git. **Never commit the real file.**
4. At https://share.streamlit.io choose **Create app**, select the private GitHub repo, branch `main`, and entrypoint `app.py`.
5. In **Advanced settings → Secrets**, paste the same TOML keys using **the exact S3 bucket name**, AWS Region `us-east-2`, and the restricted IAM access key. Keep the app private and invite only the approved lab testers.
6. Deploy. Verify the app can list the S3 bucket without an AccessDenied exception, and run the sample upload test.
7. In a private pilot, use Streamlit's private-app **viewer permissions**. Do not publish the app publicly with an S3 upload credential attached. Restrict invitations to trusted lab members.

Streamlit docs:
- https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy
- https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management
- https://docs.streamlit.io/deploy/streamlit-community-cloud/share-your-app

### Important limits

- Streamlit Community Cloud's local filesystem is **not persistent storage**; save completed uploads to S3.
- This prototype lists S3 objects instead of maintaining a separate Sheets/DynamoDB index; simpler for a small lab pilot.
- Streamlit viewer control is at the **app level**. This first version does not implement per-operator Session ACLs; all invited viewers can read the archived sessions. If users must be isolated from each other's data, add authenticated per-user authorization before deployment.
- Streamlit's shared service has uptime, memory and upload-size constraints; retain session exports on the TC22R until confirmed archived.

## 5. Validate the example session (no AWS needed)

```bash
python -m pip install -r requirements.txt pytest
PYTHONPATH=. pytest -q tests
```

Upload `examples/sample_session.zip` or `examples/sample_readings.csv` to the Streamlit app. Validate:

- 6 readings and 2 EPCs are shown.
- Uploading the exact same file twice is idempotent: the second attempt reports "already archived", no overwrite.
- Session Library loads the original file and can download it byte-for-byte.
- Upload a second valid session with a **different Session ID**, then compare both sessions and export the comparison CSV.
- Open the S3 Console to confirm the object exists under `sessions/PILOT_TEST_001/` and is not publicly accessible.

`app.py` implements counts, mean RSSI, Session comparison, raw data table, CSV export and original file download. **It does NOT claim pressure or temperature estimation**, because the validated `RFID_Dashboard` decoder/calibration modules have not yet been integrated.

## Pilot session interchange schema

Accepted file types:

- CSV with headers: `timestamp_utc,session_id,reader_id,epc,user0,user1,rssi` and optional `operator_id,reference_pressure_psi,reference_temperature_c,tag_name`.
- ZIP containing exactly `manifest.json` and `readings.csv`. Manifest fields: `schema_version="rfid-offline-session/1.0"`, `session_id`, `reader_id`, `created_at_utc`, `record_count`, `operator_id` (optional).

One file contains **one Reader ID and one Session ID**. Timestamps must include timezone; UTF-8 text; USER0/USER1 are 16-bit raw words represented as decimal or `0x`-prefixed hex. Import parsing normalizes timestamps for analysis **but S3 stores the original upload bytes unchanged**. The sample is synthetic demo data only.

### Integrating ACTUAL TC22R exports and pressure processing

Before real researchers use this to calculate pressure:

1. Compare an actual exported TC22R Session to `examples/sample_session.zip` and implement an adapter in `rfid_formats.py` (or adjust Android export to match schema), preserving raw fields and collection timestamps.
2. Reuse the existing Decoder Profile, calibration plan, model version and decision pipeline from `RFID_Dashboard` rather than inventing equations from USER0/USER1.
3. Record `raw_record_id`, `session_id`, `decoder_version`, `calibration_version` and result provenance in the migrated data layer.
4. Ensure the backend import is idempotent per Session/record, and verifies expected record counts and raw SHA-256 hashes.
5. Do not discard Android local copies until the upload is confirmed, audited and backed up.

## 6. Migration when the lab server is ready

Objects are stored under:

```
s3://EXACT-BUCKET/sessions/<session-id>/<sha256>.csv
s3://EXACT-BUCKET/sessions/<session-id>/<sha256>.zip
```

For each object: download original raw bytes; verify S3 metadata SHA256 equals downloaded SHA256; parse `manifest.json`/CSV and preserve time, EPC, USER0, USER1, RSSI, Session IDs; deduplicate by `(session_id, record_id)` or a stable equivalent agreed in the production importer; **only then** pass into the established decoder/calibration/decision pipeline. Record import provenance. Do not delete the S3 originals until a separate verified backup exists. See `MIGRATION.md`.

## Security/cost checklist

- [ ] Private repository + private app with invited viewers only
- [ ] AWS Budget alerts $1 / $3 / $5 and verified recipient
- [ ] Exact bucket name & Region, Block Public Access, default encryption
- [ ] Only restricted IAM identity; no root keys, no delete permission
- [ ] End-to-end S3 test successful, sha256 checked
- [ ] Secure Streamlit Secrets configured, no credentials in Git
- [ ] Raw session export locally retained until S3 receipt
- [ ] Actual Android export adapter and validated decoder/calibration attached before real pressure reporting
- [ ] AWS Free Plan expiry date noted; regular off-cloud backups planned
