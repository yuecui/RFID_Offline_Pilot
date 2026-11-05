"""RFID Offline Pilot v0.1: conservative session file validation.

Raw uploaded bytes are never rewritten. Parsed values are for preview/analysis only.
This is a pilot interchange format, not a claim of compatibility with the
existing Android exporter or InfluxDB data model.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO, StringIO, TextIOWrapper
import csv
import hashlib
import json
import re
import zipfile

MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
MAX_ROWS = 200_000
SCHEMA = "rfid-offline-session/1.0"
REQUIRED = ("timestamp_utc", "session_id", "reader_id", "epc", "user0", "user1", "rssi")
OPTIONAL = ("operator_id", "reference_pressure_psi", "reference_temperature_c", "tag_name")
SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,96}$")

class SessionValidationError(ValueError):
    pass

@dataclass
class ParsedSession:
    manifest: dict
    rows: list[dict]
    raw_sha256: str
    extension: str


def _utc_date(v: str) -> str:
    try:
        dt = datetime.fromisoformat(v.strip().replace("Z", "+00:00"))
        if dt.tzinfo is None or dt.utcoffset() is None:
            raise ValueError("timezone required")
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except (ValueError, AttributeError) as exc:
        raise SessionValidationError(f"Timestamp requires ISO8601 with timezone: {v!r}") from exc


def _parse_csv(content: bytes) -> list[dict]:
    try:
        stream = StringIO(content.decode("utf-8-sig"))
    except UnicodeDecodeError as exc:
        raise SessionValidationError("CSV must be UTF-8") from exc
    reader = csv.DictReader(stream)
    if reader.fieldnames is None or any(f not in reader.fieldnames for f in REQUIRED):
        raise SessionValidationError("Required columns: " + ", ".join(REQUIRED))
    if len(reader.fieldnames) != len(set(reader.fieldnames)):
        raise SessionValidationError("Duplicate column headers")
    rows = []
    for index, row in enumerate(reader, start=2):
        if len(rows) >= MAX_ROWS:
            raise SessionValidationError(f"More than {MAX_ROWS} readings; split by session")
        if None in row:
            raise SessionValidationError(f"Malformed CSV row {index}")
        if not any(str(x or "").strip() for x in row.values()):
            continue
        for field in REQUIRED:
            if not (row.get(field) or "").strip():
                raise SessionValidationError(f"Missing {field} in CSV row {index}")
        for field in ("session_id", "reader_id"):
            if not SAFE_ID.fullmatch(row[field].strip()):
                raise SessionValidationError(f"Invalid {field} in CSV row {index}")
        row["timestamp_utc"] = _utc_date(row["timestamp_utc"])
        try:
            val = float(row["rssi"])
            if not -200 <= val <= 30:
                raise ValueError()
        except ValueError:
            raise SessionValidationError(f"Invalid RSSI in CSV row {index}")
        for field in ("user0", "user1"):
            val = row[field].strip()
            try:
                numeric = int(val, 16) if val.lower().startswith("0x") else int(val, 10)
            except ValueError:
                raise SessionValidationError(f"Invalid {field} in CSV row {index}")
            if not 0 <= numeric <= 65535:
                raise SessionValidationError(f"{field} out of 16-bit range in CSV row {index}")
        rows.append(dict(row))
    if not rows:
        raise SessionValidationError("No readings in file")
    if len({r["session_id"] for r in rows}) != 1 or len({r["reader_id"] for r in rows}) != 1:
        raise SessionValidationError("One file must contain one session and one reader")
    return rows


def parse_session(raw: bytes, filename: str) -> ParsedSession:
    if not raw or len(raw) > MAX_FILE_BYTES:
        raise SessionValidationError("Upload must be 1 byte to 25 MiB")
    extension = ".zip" if filename.lower().endswith(".zip") else ".csv" if filename.lower().endswith(".csv") else None
    if extension is None:
        raise SessionValidationError("Only .zip or .csv files are supported")
    sha = hashlib.sha256(raw).hexdigest()
    if extension == ".zip":
        try:
            with zipfile.ZipFile(BytesIO(raw)) as archive:
                names = archive.namelist()
                if sorted(names) != ["manifest.json", "readings.csv"]:
                    raise SessionValidationError("ZIP must contain exactly manifest.json and readings.csv")
                if sum(info.file_size for info in archive.infolist()) > MAX_UNCOMPRESSED_BYTES:
                    raise SessionValidationError("Decompressed ZIP exceeds safety limit")
                manifest = json.loads(archive.read("manifest.json"))
                rows = _parse_csv(archive.read("readings.csv"))
        except (zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError, RuntimeError) as exc:
            raise SessionValidationError("Invalid Session ZIP/manifest") from exc
        if manifest.get("schema_version") != SCHEMA:
            raise SessionValidationError("Unsupported schema_version")
        for field in ("session_id", "reader_id"):
            if manifest.get(field) != rows[0][field]:
                raise SessionValidationError(f"Manifest {field} does not match readings")
        if manifest.get("record_count") != len(rows):
            raise SessionValidationError("Manifest record_count does not match readings")
        _utc_date(manifest.get("created_at_utc", ""))
    else:
        rows = _parse_csv(raw)
        manifest = {
            "schema_version": SCHEMA,
            "session_id": rows[0]["session_id"],
            "reader_id": rows[0]["reader_id"],
            "operator_id": rows[0].get("operator_id", "") or "not-provided",
            "created_at_utc": rows[0]["timestamp_utc"],
            "record_count": len(rows),
        }
    return ParsedSession(manifest=manifest, rows=rows, raw_sha256=sha, extension=extension)


def make_object_key(parsed: ParsedSession) -> str:
    return f"sessions/{parsed.manifest['session_id']}/{parsed.raw_sha256}{parsed.extension}"
