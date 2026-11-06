"""Append-only mutable-looking catalog over immutable S3 event objects.

No overwrite or DeleteObject authorization is needed. Latest event by timestamp
wins for each key; provenance of all previous edits is retained. Avoid public
app access: shared users can see/edit shared metadata.
"""
from __future__ import annotations
import json
import re
import uuid
import math
from datetime import datetime, timezone

PREFIX = "sessions/_metadata/"
EPC = re.compile(r"^[0-9A-F]{8,64}$")
VARIANTS = {"UNKNOWN", "AS3213S.5", "AS3213T.5"}


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def validate_record(kind, value):
    if kind == "tag":
        if not isinstance(value, dict) or not EPC.fullmatch(str(value.get("epc", "")).upper()):
            raise ValueError("Tag EPC must be 8–64 uppercase hexadecimal characters")
        alias = str(value.get("alias", "")).strip()
        if len(alias) > 100 or any(ord(c) < 32 for c in alias):
            raise ValueError("Alias too long or contains control characters")
        variant = value.get("variant", "UNKNOWN")
        if variant not in VARIANTS:
            raise ValueError("Unsupported ASYGN variant")
        return {"epc": str(value["epc"]).upper(), "alias": alias, "variant": variant}
    if kind == "session":
        if not isinstance(value, dict):
            raise ValueError("Session annotation must be a JSON object")
        fingerprint = str(value.get("raw_sha256") or "").lower()
        if not re.fullmatch(r"[0-9a-f]{64}",fingerprint):
            raise ValueError("Session raw SHA-256 fingerprint required")
        out = {"raw_sha256": fingerprint}
        for field in ("reference_pressure_psi", "reference_temperature_c"):
            candidate=value.get(field)
            if candidate is None or str(candidate).strip()=="":
                out[field]=None
            else:
                f=float(candidate)
                if not math.isfinite(f) or abs(f)>10000 or (field=="reference_pressure_psi" and f<0):
                    raise ValueError("Reference value out of range")
                out[field]=f
        for field, limit in (("test_condition",128),("operator_note",1000)):
            v=str(value.get(field) or "").strip()
            if len(v)>limit or any(ord(c)<32 and c not in "\n\t" for c in v):
                raise ValueError("Invalid annotation text")
            out[field]=v
        return out
    if kind == "plan":
        if not isinstance(value, dict) or not isinstance(value.get("plan"), dict):
            raise ValueError("Plan must be a JSON object")
        raw = json.dumps(value["plan"], allow_nan=False)
        if len(raw.encode()) > 100_000:
            raise ValueError("Calibration plan exceeds 100 KiB")
        title = str(value.get("title") or "").strip()
        if not title or len(title)>100:
            raise ValueError("Calibration plan title required")
        return {"title": title, "plan": value["plan"]}
    raise ValueError("Unsupported metadata kind")


def save_event(store, kind, value, actor):
    payload = validate_record(kind, value)
    actor = str(actor).strip()
    if not actor or len(actor)>100:
        raise ValueError("Editor identifier required for audit log")
    event = {"version": 1, "kind": kind, "value": payload, "actor": actor,
             "timestamp_utc": utc_now(), "event_id": str(uuid.uuid4())}
    key = PREFIX + kind + "/" + event["timestamp_utc"].replace(":", "-") + "_" + event["event_id"] + ".json"
    store.client.put_object(Bucket=store.bucket, Key=key, Body=json.dumps(event, ensure_ascii=False).encode(),
                            IfNoneMatch="*", ServerSideEncryption="AES256", ContentType="application/json")
    return key


def load_events(store, kind=None, max_events=5000):
    prefix = PREFIX + (kind + "/" if kind else "")
    objects = []
    for page in store.client.get_paginator("list_objects_v2").paginate(Bucket=store.bucket, Prefix=prefix):
        objects.extend(o["Key"] for o in page.get("Contents", []) if o["Key"].endswith(".json"))
        if len(objects)>max_events:
            raise ValueError("Too many catalog events; export/compact using administrator tooling")
    events=[]
    for key in sorted(objects):
        response=store.client.get_object(Bucket=store.bucket, Key=key)
        data=json.loads(response["Body"].read(120_000))
        if data.get("kind") in {"tag", "plan", "session"}:
            events.append(data)
    return events


def tag_catalog(events):
    result={}
    for event in sorted(events, key=lambda e:(e.get("timestamp_utc", ""),e.get("event_id", ""))):
        if event.get("kind")=="tag":
            v=event.get("value", {})
            if "epc" in v:
                result[v["epc"].upper()] = dict(v)
    return result


def calibration_plans(events):
    return [event for event in events if event.get("kind")=="plan"]


def session_annotations(events):
    out={}
    for event in sorted(events, key=lambda e:(e.get("timestamp_utc", ""),e.get("event_id", ""))):
        if event.get("kind")=="session":
            v=event.get("value",{})
            if v.get("raw_sha256"):
                out[v["raw_sha256"]]=dict(v)
    return out
