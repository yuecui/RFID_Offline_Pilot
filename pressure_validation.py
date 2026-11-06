"""Backend-owned physical decoder approvals; uploaded flags cannot enroll decoders."""
from datetime import datetime

# Intentionally empty. Add only after hardware validation and code review of a
# decoder that emits this exact feature/unit contract and validation identifier.
PHYSICAL_DECODER_VALIDATIONS = {}


def physical_decode_verified(decoded, feature, units, *, require_temperature=False):
    if not isinstance(decoded, dict) or decoded.get('pressure_data_origin') != 'BACKEND_DECODED':
        return False
    approval = PHYSICAL_DECODER_VALIDATIONS.get(decoded.get('decoder_profile'))
    return bool(approval and decoded.get('physical_validation_id') == approval['validation_id']
                and approval['feature_units'].get(feature) == units
                and decoded.get('decode_status') == 'VALID'
                and decoded.get('sensor_format_valid') is True
                and decoded.get('strain_format_valid') is True
                and (not require_temperature or (
                    approval['feature_units'].get('temperature_c') == 'degC'
                    and decoded.get('temperature_format_valid') is True)))


def validation_evidence_matches(evidence, metadata):
    if not isinstance(evidence, dict):
        return False
    required = {'evidence_id', 'report_sha256', 'reviewed_by', 'reviewed_at', 'model_id',
                'model_version', 'decoder_profile', 'decoder_validation_id', 'input_feature', 'input_units'}
    if set(evidence) != required:
        return False
    import re
    if not all(isinstance(evidence[k], str) and evidence[k].strip() for k in required - {'model_version'}):
        return False
    if not re.fullmatch(r'[0-9a-fA-F]{64}', evidence['report_sha256']):
        return False
    try:
        if datetime.fromisoformat(evidence['reviewed_at'].replace('Z', '+00:00')).tzinfo is None:
            return False
    except ValueError:
        return False
    approval = PHYSICAL_DECODER_VALIDATIONS.get(evidence['decoder_profile'])
    return bool(approval and type(evidence['model_version']) is int
                and evidence['model_id'] == metadata.get('pressure_model_id')
                and evidence['model_version'] == metadata.get('pressure_model_version')
                and evidence['decoder_profile'] == metadata.get('decoder_profile')
                and evidence['decoder_validation_id'] == approval['validation_id']
                and evidence['decoder_validation_id'] == metadata.get('physical_validation_id')
                and evidence['input_feature'] == metadata.get('pressure_input_feature')
                and evidence['input_units'] == metadata.get('pressure_input_units')
                and approval['feature_units'].get(evidence['input_feature']) == evidence['input_units'])
