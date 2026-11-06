# v0.3 acceptance and limits

## Verified in build container
- Unit tests: 19 passed (synthetic session fixture; no real lab Session bundled).
- Python source compiles.
- Temperature option appears when T.5-like record has matching format, USER1/USER5/USER6; explicit S.5 has separate nonvalidated exploratory output.
- Reused production readyness, reference dataset and experiment ZIP interfaces tested against return types.

## Must validate in user's deployment
- Streamlit Cloud startup and all 13 tabs on actual hardware Session.
- S3 tag alias, variant and Session annotation writes with IAM prefix restrictions; reload uses latest event.
- Calibration plan archive and synthetic preview; *no physical pressure claims*.
- Original GitHub repo v0.2 upgrade, secrets handling and limited viewers.
- Compare two archived sessions, exports and migration.

## Not feasible on Streamlit + S3 alone
- Live MQTT, Reader Management/Auth API, delivery ACK, continuous Collector ingestion, live pressure result return.
- Production verified PSI or pressure decision without signed physical validation and active calibrated model.
