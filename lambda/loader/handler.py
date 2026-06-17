"""
loader/handler.py
-----------------
Lambda 2 of 3 — Loader

Trigger : S3 PutObject on /clean prefix
Does    : Reads the clean CSV from S3 and batch-writes rows to DynamoDB.
"""

import csv
import io
import logging
import os

import boto3
from dynamodb import batch_write_orders
from metrics import publish_metrics

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")


def read_csv_from_s3(bucket: str, key: str) -> list[dict]:
    response = s3.get_object(Bucket=bucket, Key=key)
    body = response["Body"].read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(body))
    return list(reader)


def lambda_handler(event: dict, context) -> dict:
    bucket = os.environ["BUCKET_NAME"]
    table_name = os.environ["DYNAMODB_TABLE"]

    record = event["Records"][0]
    key = record["s3"]["object"]["key"]
    filename = key.split("/")[-1]

    logger.info("Loader triggered: s3://%s/%s", bucket, key)

    if not key.startswith("clean/"):
        logger.warning("Key %s is not under /clean — skipping.", key)
        return {"statusCode": 200, "body": "skipped"}

    rows = read_csv_from_s3(bucket, key)

    if not rows:
        logger.warning("Empty file: %s", filename)
        return {"statusCode": 200, "body": "empty file"}

    logger.info("Loading %d rows from %s into DynamoDB table %s", len(rows), filename, table_name)

    result = batch_write_orders(rows, table_name)

    publish_metrics([
        {"name": "LoadedRows", "value": result["written"]},
    ])

    summary = {
        "statusCode": 200,
        "file": filename,
        "rows_read": len(rows),
        "dynamodb_written": result["written"],
        "dynamodb_failed": result["failed"],
        "dynamodb_batches": result["batch_count"],
    }
    logger.info("Loader summary: %s", summary)
    return summary
