"""
dynamodb.py
-----------
Handles all DynamoDB interactions for the pipeline.

Table schema:
  PK  — order_id        (String)
  SK  — order_timestamp (String, ISO-8601)

BatchWriteItem supports a maximum of 25 items per request.
This module chunks clean rows into batches of 25 and handles
unprocessed items returned by DynamoDB with a simple retry loop.
"""

import logging
import boto3
from decimal import Decimal, ROUND_HALF_UP
from boto3.dynamodb.types import TypeSerializer

logger = logging.getLogger(__name__)

# DynamoDB BatchWriteItem hard limit
BATCH_SIZE = 25

# Fields that should be stored as numbers in DynamoDB, not strings
NUMERIC_FIELDS = {
    "item_count",
    "subtotal_gbp",
    "delivery_fee_gbp",
    "total_gbp",
    "delivery_minutes",
    "driver_rating",
}

# Fields to drop before writing — internal pipeline flags not useful in DynamoDB
EXCLUDED_FIELDS = {"is_dirty"}

_serializer = TypeSerializer()

# Lazy client — initialised on first use so moto can intercept during tests
_dynamodb_client = None


def _get_client():
    global _dynamodb_client
    if _dynamodb_client is None:
        _dynamodb_client = boto3.client("dynamodb")
    return _dynamodb_client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _coerce_row(row: dict) -> dict:
    """
    Prepare a CSV row dict for DynamoDB:
      - Drop internal pipeline fields
      - Cast numeric fields from string to float/int
      - Strip whitespace from string values
    """
    coerced = {}
    for key, value in row.items():
        if key in EXCLUDED_FIELDS:
            continue

        if value is None or value == "":
            # Skip empty/null values — DynamoDB doesn't store empty strings
            continue

        if key in NUMERIC_FIELDS:
            try:
                if key in ("item_count", "delivery_minutes"):
                    coerced[key] = int(value)
                else:
                    coerced[key] = Decimal(str(round(float(value), 2)))
            except (ValueError, TypeError):
                logger.warning("Could not coerce field %s value %r to number — skipping field", key, value)
        else:
            coerced[key] = str(value).strip()

    return coerced


def _to_dynamo_item(row: dict) -> dict:
    """Serialise a plain Python dict to DynamoDB AttributeValue format."""
    coerced = _coerce_row(row)
    return {k: _serializer.serialize(v) for k, v in coerced.items()}


def _chunk(lst: list, size: int):
    """Yield successive chunks of `size` from a list."""
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def batch_write_orders(rows: list[dict], table_name: str) -> dict:
    """
    Write a list of clean order rows to DynamoDB using BatchWriteItem.

    Chunks rows into batches of 25 (DynamoDB hard limit).
    Retries any unprocessed items returned by DynamoDB up to 3 times.

    Returns a summary dict:
        {
            "written":     int,   # rows successfully written
            "failed":      int,   # rows that could not be written after retries
            "batch_count": int,   # number of BatchWriteItem calls made
        }
    """
    if not rows:
        logger.info("No rows to write to DynamoDB.")
        return {"written": 0, "failed": 0, "batch_count": 0}

    client        = _get_client()
    total_written = 0
    total_failed  = 0
    batch_count   = 0
    max_retries   = 3

    for chunk in _chunk(rows, BATCH_SIZE):
        put_requests = [
            {"PutRequest": {"Item": _to_dynamo_item(row)}}
            for row in chunk
        ]

        unprocessed = put_requests
        attempt     = 0

        while unprocessed and attempt < max_retries:
            response = client.batch_write_item(
                RequestItems={table_name: unprocessed}
            )
            batch_count += 1

            unprocessed = response.get("UnprocessedItems", {}).get(table_name, [])

            if unprocessed:
                attempt += 1
                logger.warning(
                    "Batch had %d unprocessed items — retry %d/%d",
                    len(unprocessed), attempt, max_retries,
                )

        written_this_chunk = len(chunk) - len(unprocessed)
        total_written     += written_this_chunk
        total_failed      += len(unprocessed)

        if unprocessed:
            logger.error(
                "%d items could not be written after %d retries.",
                len(unprocessed), max_retries,
            )

    logger.info(
        "DynamoDB write complete — written: %d | failed: %d | batches: %d",
        total_written, total_failed, batch_count,
    )
    return {
        "written":     total_written,
        "failed":      total_failed,
        "batch_count": batch_count,
    }
