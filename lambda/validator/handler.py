"""
validator/handler.py
--------------------
Lambda 1 of 3 — Validator

Trigger : S3 PutObject on /raw prefix
Does    : Reads the uploaded CSV, validates each row, splits output into
          /clean (valid rows) and /quarantine (invalid rows + failure reasons).

Does NOT write to DynamoDB or publish SNS — those are downstream concerns.
"""

import csv
import io
import json
import logging
import os

import boto3
from validators import validate_row
from metrics import publish_metrics

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")

PREFIX_RAW        = "raw/"
PREFIX_CLEAN      = "clean/"
PREFIX_QUARANTINE = "quarantine/"


def read_csv_from_s3(bucket: str, key: str) -> tuple[list[dict], list[str]]:
    response = s3.get_object(Bucket=bucket, Key=key)
    body     = response["Body"].read().decode("utf-8")
    reader   = csv.DictReader(io.StringIO(body))
    rows     = list(reader)
    return rows, reader.fieldnames or []


def write_csv_to_s3(bucket: str, key: str, rows: list[dict], fieldnames: list[str]) -> None:
    if not rows:
        logger.info("No rows to write for key: %s", key)
        return
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    s3.put_object(
        Bucket=bucket, Key=key,
        Body=buffer.getvalue().encode("utf-8"),
        ContentType="text/csv",
    )
    logger.info("Wrote %d rows → s3://%s/%s", len(rows), bucket, key)


def lambda_handler(event: dict, context) -> dict:
    bucket_name = os.environ["BUCKET_NAME"]

    record   = event["Records"][0]
    bucket   = record["s3"]["bucket"]["name"]
    key      = record["s3"]["object"]["key"]
    filename = key.split("/")[-1]

    logger.info("Validator triggered: s3://%s/%s", bucket, key)

    if not key.startswith(PREFIX_RAW):
        logger.warning("Key %s is not under /raw — skipping.", key)
        return {"statusCode": 200, "body": "skipped"}

    rows, fieldnames = read_csv_from_s3(bucket, key)
    total = len(rows)

    if total == 0:
        logger.warning("Empty file: %s", filename)
        return {"statusCode": 200, "body": "empty file"}

    clean_rows            = []
    quarantine_rows       = []
    failure_counts: dict  = {}
    quarantine_fieldnames = list(fieldnames) + ["validation_failures"]

    for row in rows:
        is_valid, failures = validate_row(row)
        if is_valid:
            clean_rows.append(row)
        else:
            row_copy = dict(row)
            row_copy["validation_failures"] = "; ".join(failures)
            quarantine_rows.append(row_copy)
            for reason in failures:
                category = reason.split(":")[0]
                failure_counts[category] = failure_counts.get(category, 0) + 1

    logger.info("Split — clean: %d | quarantine: %d", len(clean_rows), len(quarantine_rows))

    write_csv_to_s3(bucket, f"{PREFIX_CLEAN}{filename}",      clean_rows,      fieldnames)
    write_csv_to_s3(bucket, f"{PREFIX_QUARANTINE}{filename}",  quarantine_rows, quarantine_fieldnames)

    quarantine_rate = (len(quarantine_rows) / total * 100) if total else 0.0
    publish_metrics([
        {"name": "TotalRows", "value": total},
        {"name": "CleanRows", "value": len(clean_rows)},
        {"name": "QuarantineRows", "value": len(quarantine_rows)},
        {"name": "QuarantineRate", "value": quarantine_rate, "unit": "Percent"},
    ])

    summary = {
        "statusCode":        200,
        "file":              filename,
        "total_rows":        total,
        "clean_rows":        len(clean_rows),
        "quarantine_rows":   len(quarantine_rows),
        "failure_breakdown": failure_counts,
    }
    logger.info("Validator summary: %s", json.dumps(summary))
    return summary
