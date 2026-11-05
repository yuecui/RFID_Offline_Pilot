import csv
import io
import json
import zipfile
import pytest
from rfid_formats import parse_session, make_object_key, SessionValidationError, SCHEMA


def test_valid_csv():
    raw = open("examples/sample_readings.csv", "rb").read()
    parsed = parse_session(raw,"sample.csv")
    assert len(parsed.rows) == 6
    assert parsed.manifest["session_id"] == "PILOT_TEST_001"
    assert make_object_key(parsed).startswith("sessions/PILOT_TEST_001/")


def test_valid_zip():
    raw = open("examples/sample_session.zip", "rb").read()
    parsed = parse_session(raw,"sample.zip")
    assert parsed.manifest["schema_version"] == SCHEMA
    assert parsed.manifest["record_count"] == len(parsed.rows) == 6


def test_no_time_zone():
    raw = open("examples/sample_readings.csv", "rb").read().replace(b"2026-11-05T16:00:00Z", b"2026-11-05T16:00:00")
    with pytest.raises(SessionValidationError):
        parse_session(raw,"x.csv")


def test_missing_required_column():
    raw = b"timestamp_utc,session_id,reader_id,epc,rssi\n2026-11-05T16:00:00Z,S1,R1,1,-50\n"
    with pytest.raises(SessionValidationError):
        parse_session(raw,"bad.csv")


def test_unsafe_zip_member():
    bio=io.BytesIO()
    with zipfile.ZipFile(bio,"w") as z:
        z.writestr("../bad.txt", b"bad")
        z.writestr("readings.csv",open("examples/sample_readings.csv","rb").read())
    with pytest.raises(SessionValidationError):
        parse_session(bio.getvalue(),"bad.zip")


def test_duplicate_csv_header():
    raw = b"timestamp_utc,session_id,reader_id,epc,user0,user1,rssi,rssi\n2026-11-05T16:00:00Z,S1,R1,1,0x2339,0x21EC,-50,-50\n"
    with pytest.raises(SessionValidationError):
        parse_session(raw,"bad.csv")
