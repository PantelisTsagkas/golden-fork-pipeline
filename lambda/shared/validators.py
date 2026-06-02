"""
validators.py
-------------
One validation function per dirty pattern.
Each function returns (is_valid: bool, reason: str | None).
"""

from datetime import datetime

VALID_STATUSES    = {"delivered", "cancelled", "in_transit", "preparing"}
VALID_PAYMENTS    = {"card", "cash", "wallet", "voucher"}
RATING_MIN        = 1.0
RATING_MAX        = 5.0
DELIVERY_FEE_MAX  = 20.0
TOTAL_MAX         = 1000.0


# ---------------------------------------------------------------------------
# Individual field validators
# ---------------------------------------------------------------------------

def validate_customer(row: dict) -> tuple[bool, str | None]:
    if not (row.get("customer_id") or "").strip():
        return False, "missing_customer_id"
    if not (row.get("customer_name") or "").strip():
        return False, "missing_customer_name"
    return True, None


def validate_address(row: dict) -> tuple[bool, str | None]:
    if not row.get("delivery_address", "").strip():
        return False, "missing_delivery_address"
    return True, None


def validate_status(row: dict) -> tuple[bool, str | None]:
    status = row.get("order_status", "").strip()
    if status not in VALID_STATUSES:
        return False, f"invalid_order_status:{status!r}"
    return True, None


def validate_timestamp(row: dict) -> tuple[bool, str | None]:
    raw = row.get("order_timestamp", "").strip()
    if not raw:
        return False, "missing_order_timestamp"
    try:
        datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S")
        return True, None
    except ValueError:
        return False, f"malformed_timestamp:{raw!r}"


def validate_financials(row: dict) -> tuple[bool, str | None]:
    try:
        subtotal     = float(row.get("subtotal_gbp", 0))
        delivery_fee = float(row.get("delivery_fee_gbp", 0))
        total        = float(row.get("total_gbp", 0))
    except (ValueError, TypeError):
        return False, "non_numeric_financials"

    if subtotal < 0:
        return False, f"negative_subtotal:{subtotal}"
    if delivery_fee < 0 or delivery_fee > DELIVERY_FEE_MAX:
        return False, f"invalid_delivery_fee:{delivery_fee}"
    if total < 0:
        return False, f"negative_total:{total}"
    if total > TOTAL_MAX:
        return False, f"total_exceeds_max:{total}"
    return True, None


def validate_item_count(row: dict) -> tuple[bool, str | None]:
    try:
        count = int(row.get("item_count", 0))
    except (ValueError, TypeError):
        return False, "non_integer_item_count"
    if count <= 0:
        return False, f"invalid_item_count:{count}"
    return True, None


def validate_rating(row: dict) -> tuple[bool, str | None]:
    raw = row.get("driver_rating", "")
    if raw == "" or raw is None:
        return True, None          # rating is optional — driver may not be rated yet
    try:
        rating = float(raw)
    except (ValueError, TypeError):
        return False, f"non_numeric_rating:{raw!r}"
    if not (RATING_MIN <= rating <= RATING_MAX):
        return False, f"rating_out_of_range:{rating}"
    return True, None


# ---------------------------------------------------------------------------
# Composite validator — runs all checks against a single row
# ---------------------------------------------------------------------------

ALL_VALIDATORS = [
    validate_customer,
    validate_address,
    validate_status,
    validate_timestamp,
    validate_financials,
    validate_item_count,
    validate_rating,
]


def validate_row(row: dict) -> tuple[bool, list[str]]:
    """
    Run all validators against a row.
    Returns (is_valid, [failure_reasons]).
    A row is clean only if ALL validators pass.
    """
    failures = []
    for validator in ALL_VALIDATORS:
        ok, reason = validator(row)
        if not ok:
            failures.append(reason)
    return len(failures) == 0, failures
