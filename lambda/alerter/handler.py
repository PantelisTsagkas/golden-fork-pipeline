"""
alerter/handler.py
------------------
Lambda 3 of 3 — Alerter

Trigger : S3 PutObject on /quarantine prefix
Does    : Reads the quarantine CSV from S3 and publishes an SNS alert
          summarising the validation failures.
"""

import csv
import io
import json
import logging
import os

import boto3
from metrics import publish_metrics

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")
sns = boto3.client("sns")


def read_csv_from_s3(bucket: str, key: str) -> list[dict]:
    response = s3.get_object(Bucket=bucket, Key=key)
    body = response["Body"].read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(body))
    return list(reader)


def lambda_handler(event: dict, context) -> dict:
    bucket = os.environ["BUCKET_NAME"]
    topic_arn = os.environ["SNS_TOPIC_ARN"]

    record = event["Records"][0]
    key = record["s3"]["object"]["key"]
    filename = key.split("/")[-1]

    logger.info("Alerter triggered: s3://%s/%s", bucket, key)

    if not key.startswith("quarantine/"):
        logger.warning("Key %s is not under /quarantine — skipping.", key)
        return {"statusCode": 200, "body": "skipped"}

    rows = read_csv_from_s3(bucket, key)

    if not rows:
        logger.info("Quarantine file %s is empty — no alert needed.", filename)
        return {"statusCode": 200, "body": "empty quarantine"}

    # Build failure summary
    failure_counts: dict = {}
    for row in rows:
        reasons = row.get("validation_failures", "")
        for reason in reasons.split("; "):
            category = reason.split(":")[0]
            if category:
                failure_counts[category] = failure_counts.get(category, 0) + 1

    subject = f"[Golden Fork] {len(rows)} quarantined rows in {filename}"
    message = json.dumps(
        {
            "file": filename,
            "quarantined_rows": len(rows),
            "failure_summary": failure_counts,
        },
        indent=2,
    )

    sns.publish(
        TopicArn=topic_arn,
        Subject=subject[:100],  # SNS subject max 100 chars
        Message=message,
    )

    publish_metrics([
        {"name": "QuarantineAlertRows", "value": len(rows)},
    ])

    logger.info("Published SNS alert: %s", subject)

    return {
        "statusCode": 200,
        "file": filename,
        "alert_sent": True,
        "quarantined_rows": len(rows),
        "failure_summary": failure_counts,
    }
