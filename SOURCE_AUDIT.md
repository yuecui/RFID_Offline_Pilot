# Source audit — RFID_Dashboard (uploaded `src copy(2).zip`)

## Scope

Inspected 88 Python source files under the uploaded `src copy` tree. The full
production Dashboard depends on live MQTT, InfluxDB 3, Account/Reader API,
SQLite-backed services and server-side configuration data that were not part of
this source-only archive. Do not launch production `dashboard.py` on Streamlit
Community Cloud unchanged.

## Source functions reused in Offline Pilot v0.2

| File | Features |
|---|---|
| `dashboard_components/charts.py` | Original Altair multi-tag time-series builder |
| `dashboard_components/chicago.py` | America/Chicago display, UTC timeline |
| `dashboard_services/readings.py` | Original packed USER word, payload, BEST_ACC, exploratory tag logic |
| `dashboard_services/metrics.py` | Original metric selection and nearest-time alignment |
| `dashboard_services/quality.py` | Per-EPC quality and Session metadata checks |
| `dashboard_components/labels.py` / `colors.py` | EPC display/color logic |

Only a subset of source files was copied, without database credentials, keys,
recorded data, pycache or production state. No original code modules were
altered in this pilot; an adapter maps the pilot schema to the chart contract.

## Dashboard inventory — not yet all migrated

- `dashboard_pages/history.py`: calendar days, time filters, full trend,
  2-day overlay; offline v0.2 implements a recorded window and session overlays,
  not the full original calendar UI.
- `dashboard_pages/session.py`: Session metrics, temporal multi-tag,
  nearest-time comparison; many of these pure operations are reused.
- `dashboard_pages/compare.py`: paired tag difference and alignment; reused.
- `dashboard_pages/quality.py`, `readiness.py`: quality summaries, readiness;
  the basic acquisition table is reused; full readiness requires richer
  reference/session metadata.
- `dashboard_pages/calibration.py`, `reference.py`, `pressure_views.py`:
  reference datasets and physical calibration; **NOT** enabled, since actual
  physical validation and active model state are not in current CSV schema.
- `dashboard_pages/lineage.py`, `provenance.py`, `contract.py`, `package.py`:
  traceability and experiment packages; migration still needed.
- `dashboard_pages/live.py`, `dashboard_services/live.py`, `collector.py`:
  online MQTT and ingestion; not appropriate for always-on Streamlit Cloud.
- `dashboard_admin.py`, `rfid_accounts.py`, `dashboard_auth.py`: full auth and
  reader administration require durable backend and user-specific access rules.

## Data format limitations

Current ZIP/CSV v1.0 requires timestamp_utc, session_id, reader_id, epc,
user0, user1, rssi. There is no asserted equivalence to the current TC22R
Android Session Export. In the adapter `0x...` means hex and unprefixed words
mean decimal, per this pilot's explicit contract. Do not guess a different
production-export encoding. Additional fields (user5, user6, sensor_variant,
EPC configuration, calibration plan, known pressure and lab context) are needed
for full experimental interpretation.

The original pressure model code rejects invalid/unverified physical decoding.
S5 raw header mismatch and experimental calculations must remain labelled
UNVALIDATED; a valid-looking payload alone is **not** a calibrated pressure.

## Validation

- 12 local automated tests (original v0.1 format/store + new adapter/metrics)
  passed with pandas.
- Python syntax/bytecode compilation passed.
- The new Streamlit UI was not launched locally in this environment, because
  Streamlit and Altair were not installed and pip could not reach the package
  index. Check Streamlit Cloud build/runtime logs after deployment.
- Do not treat sample synthetic data as real research acquisitions.
