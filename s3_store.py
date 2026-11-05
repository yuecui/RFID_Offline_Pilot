"""Least-privileged S3 backing store; no delete and no overwrite."""
import boto3
from botocore.exceptions import ClientError
from rfid_formats import make_object_key


class S3SessionStore:
    def __init__(self, aws_section):
        self.bucket = str(aws_section["bucket"])
        self.client = boto3.client(
            "s3", region_name=str(aws_section["region"]),
            aws_access_key_id=str(aws_section["access_key_id"]),
            aws_secret_access_key=str(aws_section["secret_access_key"]),
        )

    def put(self, parsed, raw):
        key = make_object_key(parsed)
        try:
            self.client.put_object(
                Bucket=self.bucket, Key=key, Body=raw,
                ContentType="application/zip" if parsed.extension == ".zip" else "text/csv",
                ServerSideEncryption="AES256", IfNoneMatch="*",
                Metadata={"schema-version": "1.0", "sha256": parsed.raw_sha256},
            )
            return key, True
        except ClientError as exc:
            if exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 412 or exc.response.get("Error", {}).get("Code") in {"PreconditionFailed", "412"}:
                return key, False
            raise

    def list(self):
        result = []
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix="sessions/"):
            for item in page.get("Contents", []):
                if item["Key"].endswith((".csv", ".zip")):
                    result.append({"key": item["Key"], "size": item["Size"], "uploaded": item["LastModified"]})
        return sorted(result, key=lambda x: x["uploaded"], reverse=True)

    def get(self, key):
        if not key.startswith("sessions/") or not key.endswith((".csv", ".zip")):
            raise ValueError("Invalid session key")
        obj = self.client.get_object(Bucket=self.bucket, Key=key)
        if obj["ContentLength"] > 25 * 1024 * 1024:
            raise ValueError("Session exceeds maximum size")
        return obj["Body"].read(25 * 1024 * 1024 + 1)
