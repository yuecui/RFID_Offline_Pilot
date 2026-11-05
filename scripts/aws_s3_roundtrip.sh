#!/usr/bin/env bash
# Run on your own machine after configuring AWS CLI with the restricted IAM identity.
set -euo pipefail
: "${RFID_S3_BUCKET:?Set RFID_S3_BUCKET to exact created bucket name}"
aws sts get-caller-identity --query Arn --output text
TMPDIR_PATH=$(mktemp -d)
trap 'rm -rf "$TMPDIR_PATH"' EXIT
printf 'rfid-pilot-s3-check\n' > "$TMPDIR_PATH/upload.txt"
KEY="healthchecks/$(date -u +%Y%m%dT%H%M%SZ)-$$.txt"
aws s3api put-object --bucket "$RFID_S3_BUCKET" --key "$KEY" --body "$TMPDIR_PATH/upload.txt" --server-side-encryption AES256 --if-none-match '*' >/dev/null
aws s3api get-object --bucket "$RFID_S3_BUCKET" --key "$KEY" "$TMPDIR_PATH/download.txt" >/dev/null
cmp "$TMPDIR_PATH/upload.txt" "$TMPDIR_PATH/download.txt"
echo "PASS: S3 upload/download byte-for-byte match: s3://$RFID_S3_BUCKET/$KEY"
echo "Test object intentionally retained: no delete permission in pilot policy."
