# Source coverage audit — v0.3

**Input basis:** user-provided RFID Dashboard `src copy(2).zip` plus TC22R Android `AsygnDecoder.kt` and the Offline Pilot v0.2 artifact. Not a hypothetical replacement implementation.

## Source reuse

| Source | Offline adaptation |
|---|---|
| `dashboard_components/charts.py`, `colors.py`, `chicago.py`, `labels.py` | Multitag Altair charts, EPC and local time formatting |
| `dashboard_services/readings.py`, `metrics.py`, `quality.py` | USER payloads, T.5/S.5 diagnostic fields, pairing and read quality |
| `dashboard_services/coverage.py`, `references.py` | Calibration reference-condition planning and export |
| `dashboard_services/readiness.py`, `contract.py` | Structural readiness and canonical fields |
| `dashboard_services/provenance.py`, `lineage.py`, `exports.py`, `identity.py` | Provenance, record layers, experiment package |
| `pressure_calibration.py`, `pressure_decision.py`, `pressure_validation.py`, `pressure_model_schema.json` | Draft model validation and **synthetic preview only**; *not* live model activation |
| TC22R `AsygnDecoder.kt` | S.5/T.5 strict temperature calculation, USER5/USER6 calibration, explicit statuses |

## Feature coverage

Implemented or adapted for S3: immutable Session upload/library, EPC statistics, raw word trends, strict-format temperature chart, exploratory S.5 nonvalidated plots, multiple Tags, signal strength, nearest-time comparisons, two-day comparison, Session historical time windows, Tag aliases, Session metadata annotations, quality, reference datasets, calibration coverage, readiness, provenance, experiment packages, replay, exports, calibration plan archive and draft model synthetic preview.

**Not replicable without always-on backend:** actual live RFID reads and MQTT, backend Collector queue/ACK, delivery recovery, device provisioning/Reader approval, logged-in admin users/roles, InfluxDB queries/migrations, active pressure-model transition, or true production pressure decision when physical-validation prerequisites are missing.

**Limitations of hosted v0.3:** annotations shared at app scope, not personal; no verified identities for editors, no cross-user permission isolation, and no actual cloud UI acceptance or managed-service smoke test yet. Any broad-access deployment needs further security work.
