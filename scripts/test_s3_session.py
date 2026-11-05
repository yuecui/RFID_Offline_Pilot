"""Real AWS S3 roundtrip using the *synthetic sample Session ZIP*.

Requires restricted IAM credentials via AWS CLI profile / environment, not in source.
Usage: RFID_S3_BUCKET='exact-bucket' python scripts/test_s3_session.py
"""
from pathlib import Path
import hashlib
import os
import sys
import boto3
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rfid_formats import parse_session, make_object_key


def main():
    bucket = os.environ.get("RFID_S3_BUCKET")
    if not bucket:
        raise SystemExit("Set RFID_S3_BUCKET to your exact, already-created bucket name")
    region = os.environ.get("AWS_REGION", "us-east-2")
    client = boto3.client("s3", region_name=region)
    raw = (ROOT / "examples/sample_session.zip").read_bytes()
    parsed = parse_session(raw, "sample_session.zip")
    key = make_object_key(parsed)
    print(f"Test session: {parsed.manifest['session_id']} ({len(parsed.rows)} readings)")
    print("Target:", f"s3://{bucket}/{key}")
    try:
        client.put_object(
            Bucket=bucket, Key=key, Body=raw, ContentType="application/zip",
            ServerSideEncryption="AES256", IfNoneMatch="*",
            Metadata={"sha256": parsed.raw_sha256, "schema-version": "1.0"},
        )
        print("New immutable sample upload confirmed")
    except ClientError as exc:
        if exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 412:
            print("Already archived, checking original file without overwrite")
        else:
            raise
    result = client.get_object(Bucket=bucket, Key=key)
    received = result["Body"].read(25 * 1024 * 1024 + 1)
    assert len(received) == len(raw), "Download length mismatch"
    assert hashlib.sha256(received).hexdigest() == parsed.raw_sha256, "SHA256 mismatch"
    assert result.get("Metadata",{}).get("sha256") == parsed.raw_sha256, "S3 metadata hash mismatch"
    restored = parse_session(received, "sample_session.zip")
    assert len(restored.rows) == 6
    print("PASS: Real S3 sample Session upload/download; SHA256, bytes and records match")
    print("Object intentionally retained: restricted pilot app has no DeleteObject permission")


if __name__ == "__main__":
    main()
