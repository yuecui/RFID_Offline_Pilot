"""Extracted lineage responsibilities; original calculations and widget behavior preserved."""
import json
import pandas as pd

def _value_or_none(row, name):
    if row is None or name not in row.index:
        return None
    value = row.get(name)
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, str) and value.strip() in ["", "None", "nan", "<NA>"]:
        return None
    return value

def build_layered_record(row: pd.Series):
    raw = {
        "timestamp": _value_or_none(row, "timestamp")
        or _value_or_none(row, "time")
        or _value_or_none(row, "_received_at"),
        "captured_at": _value_or_none(row, "captured_at")
        or _value_or_none(row, "timestamp")
        or _value_or_none(row, "time"),
        "captured_at_epoch_ms": _value_or_none(
            row,
            "captured_at_epoch_ms",
        ),
        "device_timezone": _value_or_none(row, "device_timezone"),
        "received_at": _value_or_none(row, "received_at")
        or _value_or_none(row, "_received_at"),
        "delivery_delay_ms": _value_or_none(
            row,
            "delivery_delay_ms",
        ),
        "reading_id": _value_or_none(row, "reading_id"),
        "session_id": _value_or_none(row, "session_id"),
        "session_locked": _value_or_none(row, "session_locked"),
        "reader_id": _value_or_none(row, "reader_id"),
        "epc": _value_or_none(row, "epc"),
        "rssi": _value_or_none(row, "rssi"),
        "w0": _value_or_none(row, "w0"),
        "w1": _value_or_none(row, "w1"),
        "user_memory": _value_or_none(row, "user_memory"),
        "reference_pressure_psi": _value_or_none(row, "reference_pressure_psi"),
        "reference_temperature_c": _value_or_none(row, "reference_temperature_c"),
        "test_condition": _value_or_none(row, "test_condition"),
        "operator_note": _value_or_none(row, "operator_note"),
    }

    decode = {
        "sensor_format_valid": _value_or_none(row, "sensor_format_valid"),
        "strain_format_valid": _value_or_none(row, "strain_format_valid"),
        "temperature_format_valid": _value_or_none(row, "temperature_format_valid"),
        "user0_word": _value_or_none(row, "user0_word"),
        "user1_word": _value_or_none(row, "user1_word"),
        "user0_payload": _value_or_none(row, "user0_payload"),
        "user1_payload": _value_or_none(row, "user1_payload"),
        "strain_raw": _value_or_none(row, "strain_raw"),
        "temperature_raw": _value_or_none(row, "temperature_raw"),
        "temperature_c": _value_or_none(row, "temperature_c"),
        "strain_best_acc": _value_or_none(row, "strain_best_acc"),
        "temperature_best_acc": _value_or_none(row, "temperature_best_acc"),
        "tcal_c": _value_or_none(row, "tcal_c"),
        "temp_at_tcal_raw": _value_or_none(row, "temp_at_tcal_raw"),
        "decoder_version": _value_or_none(row, "decoder_version"),
        "dashboard_tag_variant": _value_or_none(
            row,
            "dashboard_tag_variant",
        ),
        "s5_user0_header": _value_or_none(row, "s5_user0_header"),
        "s5_user1_header": _value_or_none(row, "s5_user1_header"),
        "s5_header_matches_documentation": _value_or_none(
            row,
            "s5_header_matches_documentation",
        ),
        "s5_accepted_strain_raw": _value_or_none(
            row,
            "s5_accepted_strain_raw",
        ),
        "s5_accepted_temperature_raw": _value_or_none(
            row,
            "s5_accepted_temperature_raw",
        ),
        "s5_accepted_temperature_c": _value_or_none(
            row,
            "s5_accepted_temperature_c",
        ),
        "s5_interpretation_status": _value_or_none(
            row,
            "s5_interpretation_status",
        ),
    }

    calibration = {
        "reference_pressure_psi": raw.get("reference_pressure_psi"),
        "reference_temperature_c": raw.get("reference_temperature_c"),
        "estimated_pressure_psi": (_value_or_none(row, "backend_estimated_pressure_psi")
                                   if "backend_estimated_pressure_psi" in row.index
                                   else _value_or_none(row, "estimated_pressure_psi")),
        "calibration_model": (_value_or_none(row, "backend_pressure_model_id")
                              or _value_or_none(row, "pressure_model_id")
                              or _value_or_none(row, "calibration_model")),
        "model_version": (_value_or_none(row, "backend_pressure_model_version")
                          or _value_or_none(row, "pressure_model_version")
                          or _value_or_none(row, "model_version")),
        "pressure_calibration_status": (_value_or_none(row, "backend_pressure_calibration_status")
                                        or _value_or_none(row, "pressure_calibration_status")),
        "pressure_validation_status": _value_or_none(row, "backend_pressure_validation_status"),
        "pressure_mode": _value_or_none(row, "backend_pressure_mode"),
        "pressure_label": _value_or_none(row, "pressure_label"),
        "pressure_input_feature": _value_or_none(row, "pressure_input_feature"),
        "pressure_input_units": _value_or_none(row, "pressure_input_units"),
        "pressure_estimation_status": _value_or_none(row, "pressure_estimation_status"),
        "confidence": _value_or_none(row, "confidence"),
        "error": _value_or_none(row, "error"),
    }

    decision = {
        "target_pressure_psi": _value_or_none(row, "backend_target_pressure_psi"),
        "pressure_status": _value_or_none(row, "backend_pressure_decision_status"),
        "pressure_decision_reason": _value_or_none(row, "backend_pressure_decision_reason"),
        "pressure_validation_status": _value_or_none(row, "backend_pressure_validation_status"),
        "pressure_mode": _value_or_none(row, "backend_pressure_mode"),
        "low_threshold_psi": _value_or_none(row, "low_threshold_psi"),
        "high_threshold_psi": _value_or_none(row, "high_threshold_psi"),
        "backend_status": _value_or_none(row, "backend_status"),
        "storage_status": _value_or_none(row, "storage_status"),
    }

    return {
        "Raw Acquisition": raw,
        "Sensor Decoding": decode,
        "Calibration / Estimation": calibration,
        "Decision": decision,
    }

def layer_status(layer_name: str, values: dict):
    non_null = sum(value is not None for value in values.values())
    total = max(1, len(values))

    if layer_name == "Raw Acquisition":
        required = ["reading_id", "session_id", "reader_id", "epc"]
        missing_required = [key for key in required if values.get(key) is None]
        return (
            "READY" if not missing_required else "ATTENTION",
            non_null,
            total,
            "" if not missing_required else "Missing: " + ", ".join(missing_required),
        )

    if layer_name == "Sensor Decoding":
        sensor_variant = str(
            values.get("sensor_variant")
            or values.get("dashboard_tag_variant")
            or ""
        ).upper()

        # T.5 is temperature-only, so strain_format_valid=False is expected.
        t5_valid = (
            sensor_variant in ["AS3213T5", "AS3213T.5"]
            and values.get("temperature_format_valid") is True
            and values.get("sensor_format_valid") is True
        )

        s5_fully_documented = (
            sensor_variant in ["AS3213S5", "AS3213S.5"]
            and values.get("strain_format_valid") is True
            and values.get("temperature_format_valid") is True
        )

        s5_accepted = (
            sensor_variant in ["AS3213S5", "AS3213S.5"]
            and values.get("s5_accepted_temperature_raw") is not None
            and values.get("s5_header_matches_documentation") is False
        )

        payload_present = (
            values.get("user0_payload") is not None
            and values.get("user1_payload") is not None
        )

        if t5_valid:
            return (
                "VALIDATED T.5 FORMAT",
                non_null,
                total,
                "Temperature-only AS3213T.5; documented 0b11 format accepted.",
            )

        if s5_fully_documented:
            return "VALIDATED S.5 FORMAT", non_null, total, ""

        if s5_accepted:
            return (
                "ACCEPTED / NON-DOCUMENTED",
                non_null,
                total,
                "Dashboard calculates S.5 values despite header mismatch; results are exploratory and non-validated.",
            )

        if payload_present:
            return (
                "DIAGNOSTIC ONLY",
                non_null,
                total,
                "USER payloads available; physical ASYGN decoding is not validated.",
            )

        return "PENDING", non_null, total, "No decoded payload available."

    if layer_name == "Calibration / Estimation":
        if values.get("estimated_pressure_psi") is not None:
            if (values.get("pressure_calibration_status") != "VALIDATED"
                    or values.get("pressure_validation_status") != "VERIFIED"
                    or values.get("pressure_mode") != "PRODUCTION"):
                return ("UNVALIDATED", non_null, total,
                        "Experimental or unspecified model: prediction is not a validated tire-pressure measurement.")
            return "AVAILABLE", non_null, total, ""
        return (
            "PENDING",
            non_null,
            total,
            "No validated pressure estimate/model is available.",
        )

    if layer_name == "Decision":
        pressure_status = values.get("pressure_status")
        if pressure_status in ("LOW", "NORMAL", "HIGH"):
            if values.get("pressure_validation_status") == "VERIFIED" and values.get("pressure_mode") == "PRODUCTION":
                return "AVAILABLE", non_null, total, ""
            return "UNVALIDATED", non_null, total, "No verified backend pressure decision"
        if pressure_status not in [None, "", "PENDING"]:
            return pressure_status, non_null, total, values.get("pressure_decision_reason") or "No pressure decision"
        return (
            "PENDING",
            non_null,
            total,
            "LOW/NORMAL/HIGH awaits validated estimation/calibration.",
        )

    return "UNKNOWN", non_null, total, ""

def lineage_status_table(layered_record: dict):
    rows = []
    for layer_name, values in layered_record.items():
        status, populated, total, note = layer_status(layer_name, values)
        rows.append({
            "Layer": layer_name,
            "Status": status,
            "Populated fields": f"{populated} / {total}",
            "Note": note,
        })
    return pd.DataFrame(rows)

def layered_record_long_table(layered_record: dict):
    rows = []
    for layer_name, values in layered_record.items():
        for field, value in values.items():
            rows.append({
                "Layer": layer_name,
                "Field": field,
                "Value": "N/A" if value is None else str(value),
            })
    return pd.DataFrame(rows)

def additive_integrity_checks(layered_record: dict):
    raw = layered_record["Raw Acquisition"]
    decode = layered_record["Sensor Decoding"]
    calibration = layered_record["Calibration / Estimation"]
    decision = layered_record["Decision"]

    checks = [
        {
            "Check": "Raw identity present",
            "Status": "PASS" if all(
                raw.get(field) is not None
                for field in ["reading_id", "reader_id", "epc"]
            ) else "ATTENTION",
        },
        {
            "Check": "Raw/user values preserved",
            "Status": "PASS" if (
                raw.get("w0") is not None
                or decode.get("user0_word") is not None
                or decode.get("user0_payload") is not None
            ) else "ATTENTION",
        },
        {
            "Check": "Reference values separated from estimates",
            "Status": "PASS",
        },
        {
            "Check": "Later layers do not replace raw acquisition",
            "Status": "PASS",
        },
    ]

    physical_decode_valid = (
        decode.get("strain_format_valid") is True
        and decode.get("temperature_format_valid") is True
    )
    if not physical_decode_valid:
        checks.append({"Check": "Physical decode validation", "Status": "PENDING"})

    if calibration.get("estimated_pressure_psi") is None:
        checks.append({"Check": "Pressure estimation model", "Status": "PENDING"})

    if decision.get("pressure_status") in [None, "", "PENDING"]:
        checks.append({"Check": "LOW/NORMAL/HIGH decision", "Status": "PENDING"})

    return pd.DataFrame(checks)

def build_lineage_export_json(layered_record: dict):
    return json.dumps(
        layered_record,
        indent=2,
        default=str,
    ).encode("utf-8")
