"""Safe, pure pressure estimation over explicitly decoded features.

No file writes, raw-word arithmetic, expression evaluation, or reference/target
pressure inputs. Current header-only backend decoders are intentionally ineligible.
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path

from jsonschema import Draft202012Validator

_SCHEMA = json.loads(Path(__file__).with_name("pressure_model_schema.json").read_text())
_VALIDATOR = Draft202012Validator(_SCHEMA)


class PressureModelError(ValueError):
    pass


def _finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def validate_model(model, *, importing=False):
    """JSON Schema plus finite-number/range checks; return an isolated copy."""
    errors = sorted(_VALIDATOR.iter_errors(model), key=lambda e: str(list(e.path)))
    if errors:
        raise PressureModelError(f"Invalid pressure model: {errors[0].message}")
    if type(model['version']) is not int:
        raise PressureModelError("Model version must be an integer")
    if importing and (model['status'] != 'DRAFT' or
                      'activated_at' in model or 'activated_by' in model):
        raise PressureModelError("Imports must be DRAFT without activation metadata")
    if model['scope'].get('profile_id', model['id']) != model['id']:
        raise PressureModelError("Profile scope must name this calibration profile ID")
    for value in model['parameters'].values():
        if not _finite(value):
            raise PressureModelError("Coefficients and reference temperature must be finite numbers")
    for name, bounds in model['operating_range'].items():
        if not all(_finite(v) for v in bounds) or bounds[0] >= bounds[1]:
            raise PressureModelError(f"Invalid operating range: {name}")
    if model['operating_range']['pressure_psi'][0] < 0:
        raise PressureModelError("Pressure range must be nonnegative PSI")
    if model['calibration_status'] == 'VALIDATED' and not model.get('provenance', '').strip():
        raise PressureModelError("VALIDATED models require validation evidence in provenance")
    if model['status'] == 'ACTIVE' and not (model.get('activated_at') and model.get('activated_by')):
        raise PressureModelError("ACTIVE model requires activation metadata")
    evidence = model.get('validation_evidence')
    if evidence:
        from datetime import datetime
        if (evidence['model_id'] != model['id'] or type(evidence['model_version']) is not int
                or evidence['model_version'] != model['version']
                or evidence['input_feature'] != model['input_feature']
                or evidence['input_units'] != model['input_units']
                or not evidence['reviewed_by'].strip()):
            raise PressureModelError('Validation evidence must match model revision and input contract')
        try:
            if datetime.fromisoformat(evidence['reviewed_at'].replace('Z', '+00:00')).tzinfo is None:
                raise ValueError('Missing timezone')
        except ValueError as exc:
            raise PressureModelError('Evidence review timestamp must include timezone') from exc
    return copy.deepcopy(model)


def resolve_active_model(epc, snapshot):
    """Resolve only the exact, explicit tag-to-calibration revision assignment."""
    from tag_registry import normalize_epc
    epc = normalize_epc(epc)
    catalog = snapshot['catalog']
    tag = catalog['tags'].get(epc)
    reg = snapshot['registry'].get(epc)
    if not isinstance(tag, dict) or not isinstance(reg, dict):
        return None
    if tag.get('enabled') is not True or reg.get('enabled') is not True:
        return None
    ref = tag.get('calibration_profile')
    if (not isinstance(ref, dict) or not isinstance(ref.get('id'), str)
            or type(ref.get('version')) is not int):
        return None
    versions = catalog['calibration_profiles'].get(ref['id'])
    if not isinstance(versions, dict):
        return None
    model = versions.get(str(ref['version']))
    if not isinstance(model, dict) or model.get('status') != 'ACTIVE':
        return None
    try:
        clean = validate_model(model)
    except PressureModelError:
        return None
    if clean['id'] != ref.get('id') or clean['version'] != ref.get('version'):
        return None
    if clean['scope'].get('epc', epc) != epc:
        return None
    return clean


def estimate_pressure(model, decoded, *, mode="production"):
    """Pure calculation for draft preview or active use; errors contain no PSI.

    Production requires a backend-approved physical decoder. Synthetic math must
    explicitly use mode='synthetic' and cannot be persisted as acquisition data.
    decoded must be a decoder-produced record with decode_status=VALID,
    sensor_format_valid/strain_format_valid booleans and feature_units metadata.
    Never pass original MQTT strain/temperature aliases as a decoded record.
    """
    if mode not in ('production', 'synthetic'):
        raise ValueError("Unknown pressure estimation mode")
    if model is None:
        return {'pressure_estimation_status': 'NO_MODEL', 'estimated_pressure_psi': None, 'pressure_mode': mode.upper()}
    try:
        model = validate_model(model)
    except (PressureModelError, TypeError, ValueError):
        return {'pressure_estimation_status': 'INVALID_MODEL', 'estimated_pressure_psi': None, 'pressure_mode': mode.upper()}
    base = {
        'estimated_pressure_psi': None,
        'pressure_model_id': model['id'], 'pressure_model_version': model['version'],
        'pressure_model_status': model['status'],
        'pressure_calibration_status': model['calibration_status'],
        'pressure_label': ('UNVALIDATED experimental prediction' if model['calibration_status'] == 'EXPERIMENTAL'
                           else 'UNVALIDATED model prediction — evidence not verified'),
        'pressure_input_feature': model['input_feature'], 'pressure_input_units': model['input_units'],
        'pressure_model_activated_at': model.get('activated_at', ''),
        'pressure_model_activated_by': model.get('activated_by', ''),
        'pressure_mode': mode.upper(),
        'physical_decoding_verified': False,
        'decoder_profile': decoded.get('decoder_profile', '') if isinstance(decoded, dict) else '',
        'physical_validation_id': decoded.get('physical_validation_id', '') if isinstance(decoded, dict) else '',
        'validation_evidence': copy.deepcopy(model.get('validation_evidence')),
        'pressure_validation_status': 'SYNTHETIC' if mode == 'synthetic' else 'UNVERIFIED',
    }
    def failed(status):
        return {**base, 'pressure_estimation_status': status}
    if model['status'] == 'RETIRED':
        return failed('RETIRED_MODEL')
    if mode == 'production' and model['status'] != 'ACTIVE':
        return failed('INACTIVE_MODEL')
    if not isinstance(decoded, dict) or decoded.get('decode_status') != 'VALID' or any(
            decoded.get(key) is not True for key in ('sensor_format_valid', 'strain_format_valid')):
        return failed('INVALID_SENSOR_DECODING')
    feature = model['input_feature']
    from pressure_validation import physical_decode_verified, validation_evidence_matches
    verified = physical_decode_verified(decoded, feature, model['input_units'],
        require_temperature='temperature_c' in model['operating_range'])
    base['physical_decoding_verified'] = verified
    if mode == 'production' and not verified:
        return failed('PHYSICAL_DECODING_UNVERIFIED')
    if mode == 'production':
        eligible = (model['calibration_status'] == 'VALIDATED'
                    and validation_evidence_matches(model.get('validation_evidence'), base))
        base['pressure_validation_status'] = 'VERIFIED' if eligible else 'UNVALIDATED'
        if eligible:
            base['pressure_label'] = 'Physically verified model prediction'
    else:
        base['pressure_label'] = 'SYNTHETIC test prediction — UNVALIDATED'
    evidence = model.get('validation_evidence') or {}
    for source, dest in [('evidence_id', 'pressure_validation_evidence_id'),
                         ('report_sha256', 'pressure_validation_report_sha256'),
                         ('reviewed_by', 'pressure_validation_reviewed_by'),
                         ('reviewed_at', 'pressure_validation_reviewed_at')]:
        base[dest] = evidence.get(source, '')
    units = decoded.get('feature_units')
    if not isinstance(units, dict) or units.get(feature) != model['input_units']:
        return failed('INPUT_UNITS_MISMATCH')
    strain = decoded.get(feature)
    if not _finite(strain):
        return failed('MISSING_OR_INVALID_STRAIN')
    ranges = model['operating_range']
    if not ranges['strain'][0] <= strain <= ranges['strain'][1]:
        return failed('STRAIN_OUT_OF_RANGE')
    params = model['parameters']
    pressure = params['intercept'] + params['slope'] * strain
    needs_temp = model['model_type'] == 'linear_temperature_compensated_v1'
    if needs_temp or 'temperature_c' in ranges:
        if decoded.get('temperature_format_valid') is not True:
            return failed('INVALID_TEMPERATURE_DECODING')
        temp = decoded.get('temperature_c')
        if units.get('temperature_c') != 'degC':
            return failed('INPUT_UNITS_MISMATCH')
        if not _finite(temp):
            return failed('MISSING_OR_INVALID_TEMPERATURE')
        if not ranges['temperature_c'][0] <= temp <= ranges['temperature_c'][1]:
            return failed('TEMPERATURE_OUT_OF_RANGE')
        if needs_temp:
            pressure += params['temperature_coefficient'] * (temp - params['temperature_reference_c'])
    if not _finite(pressure):
        return failed('NONFINITE_PREDICTION')
    if not ranges['pressure_psi'][0] <= pressure <= ranges['pressure_psi'][1]:
        return failed('PRESSURE_OUT_OF_RANGE')
    return {**base, 'pressure_estimation_status': 'OK', 'estimated_pressure_psi': pressure}


def estimate_for_tag(epc, decoded, snapshot, *, mode="production"):
    return estimate_pressure(resolve_active_model(epc, snapshot), decoded, mode=mode)
