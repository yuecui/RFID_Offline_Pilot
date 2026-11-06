"""Pure backend decisions; synthetic previews cannot qualify as production results."""
from pressure_calibration import _finite, estimate_pressure, resolve_active_model
from pressure_validation import validation_evidence_matches

DECISION_FIELDS = {'target_pressure_psi', 'lower_tolerance_psi', 'upper_tolerance_psi'}


def validate_decision_settings(settings):
    if not isinstance(settings, dict) or set(settings) != DECISION_FIELDS:
        raise ValueError('Pressure decision requires target PSI and independent lower/upper tolerances')
    if not all(_finite(settings[k]) for k in DECISION_FIELDS):
        raise ValueError('Pressure target and tolerances must be finite numbers')
    if settings['target_pressure_psi'] <= 0 or any(settings[k] < 0 for k in
                                                 ('lower_tolerance_psi', 'upper_tolerance_psi')):
        raise ValueError('Target must be positive; tolerances must be nonnegative')
    if not all(_finite(settings['target_pressure_psi'] + sign * settings[k])
               for sign, k in ((-1, 'lower_tolerance_psi'), (1, 'upper_tolerance_psi'))):
        raise ValueError('Pressure decision thresholds must be finite')
    return dict(settings)


def decide_pressure(estimated_pressure_psi, target_pressure_psi, lower_tolerance_psi,
                    upper_tolerance_psi, metadata, *, mode='production'):
    """Inclusive NORMAL boundaries; no references or payload aliases are inputs.

    Priority: missing calibration, invalid/out-of-range estimate, invalid settings,
    unverified/experimental evidence, then comparison. Synthetic mode is explicit
    and all returned branches are marked SYNTHETIC, ineligible for persistence.
    """
    if mode not in ('production', 'synthetic'):
        raise ValueError('Unknown pressure decision mode')
    metadata = metadata if isinstance(metadata, dict) else {}
    base = {'pressure_mode': mode.upper(), 'production_decision_eligible': False}
    def result(status, reason):
        return {**base, 'pressure_decision_status': status, 'pressure_decision_reason': reason}
    estimation = metadata.get('pressure_estimation_status')
    if estimation in ('NO_MODEL', 'INVALID_MODEL', 'RETIRED_MODEL', 'INACTIVE_MODEL') or not metadata.get('pressure_model_id'):
        return result('UNCALIBRATED', 'No usable active calibration model')
    if estimation in ('STRAIN_OUT_OF_RANGE', 'TEMPERATURE_OUT_OF_RANGE', 'PRESSURE_OUT_OF_RANGE'):
        return result('OUT_OF_RANGE', estimation)
    if estimation != 'OK' or not _finite(estimated_pressure_psi) or estimated_pressure_psi < 0:
        return result('INVALID_INPUT', estimation or 'Missing or invalid pressure estimate')
    try:
        settings = validate_decision_settings({'target_pressure_psi': target_pressure_psi,
            'lower_tolerance_psi': lower_tolerance_psi, 'upper_tolerance_psi': upper_tolerance_psi})
    except ValueError as exc:
        return result('NOT_CONFIGURED', str(exc))
    if mode == 'production':
        if (metadata.get('pressure_model_status') != 'ACTIVE'
                or metadata.get('pressure_mode') != 'PRODUCTION'
                or metadata.get('physical_decoding_verified') is not True
                or metadata.get('pressure_calibration_status') != 'VALIDATED'
                or not validation_evidence_matches(metadata.get('validation_evidence'), metadata)):
            return result('UNVALIDATED', 'Production decisions require verified physical decoding and reviewed model evidence')
    elif metadata.get('pressure_mode') != 'SYNTHETIC':
        return result('INVALID_INPUT', 'Synthetic mode requires synthetic estimation')
    low = target_pressure_psi - lower_tolerance_psi
    high = target_pressure_psi + upper_tolerance_psi
    status = 'LOW' if estimated_pressure_psi < low else 'HIGH' if estimated_pressure_psi > high else 'NORMAL'
    return {**result(status, 'Synthetic test only' if mode == 'synthetic' else 'Verified production decision'),
            **settings, 'low_threshold_psi': low, 'high_threshold_psi': high,
            'difference_psi': estimated_pressure_psi - target_pressure_psi,
            'production_decision_eligible': mode == 'production'}


def evaluate_for_tag(epc, decoded, snapshot):
    """Production-only integration; never reads settings or validity from MQTT."""
    from tag_registry import normalize_epc
    model = resolve_active_model(epc, snapshot)
    estimate = estimate_pressure(model, decoded)
    settings = snapshot['catalog']['tags'].get(normalize_epc(epc), {}).get('pressure_decision')
    try:
        settings = validate_decision_settings(settings)
    except ValueError:
        settings = {}
    decision = decide_pressure(estimate.get('estimated_pressure_psi'),
        settings.get('target_pressure_psi'), settings.get('lower_tolerance_psi'),
        settings.get('upper_tolerance_psi'), estimate)
    return {**estimate, **settings, **decision,
            'pressure_settings_source': 'TAG' if settings else 'NONE'}


def simulate_pressure_decision(model, decoded_test_input, settings):
    """Explicit test/preview API. Results are never accepted by production serializer."""
    estimate = estimate_pressure(model, decoded_test_input, mode='synthetic')
    settings = settings if isinstance(settings, dict) else {}
    return {**estimate, **decide_pressure(estimate.get('estimated_pressure_psi'),
        settings.get('target_pressure_psi'), settings.get('lower_tolerance_psi'),
        settings.get('upper_tolerance_psi'), estimate, mode='synthetic')}
