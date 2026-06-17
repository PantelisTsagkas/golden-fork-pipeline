"""
generate_orders.py
------------------
Generates a synthetic food delivery orders CSV for a single restaurant.
Produces a mix of clean rows and intentionally dirty rows to exercise
Lambda validation logic.

Usage:
    python generate_orders.py              # outputs orders.csv (500 rows)
    python generate_orders.py --rows 1000  # custom row count
    python generate_orders.py --seed 99    # reproducible output
"""

import csv
import random
import argparse
from datetime import datetime, timedelta
from faker import Faker

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
TOTAL_ROWS    = 500
DIRTY_RATIO   = 0.18        # ~18% of rows will have at least one issue
OUTPUT_FILE   = "orders.csv"
RESTAURANT    = "The Golden Fork"
RESTAURANT_ID = "RES-001"

VALID_STATUSES   = ["delivered", "cancelled", "in_transit", "preparing"]
INVALID_STATUSES = ["DONE", "unknown", "null", "shipped", ""]   # bad values
CUISINES         = ["Italian", "American", "Mexican", "Indian", "Japanese", "Mediterranean"]
PAYMENT_METHODS  = ["card", "cash", "wallet", "voucher"]

fake = Faker("en_GB")   # UK locale — realistic UK addresses & names

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def random_timestamp(start_days_ago: int = 180) -> str:
    """Return a clean ISO-8601 timestamp within the last N days."""
    delta = timedelta(
        days=random.randint(0, start_days_ago),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
        seconds=random.randint(0, 59),
    )
    return (datetime.now() - delta).strftime("%Y-%m-%dT%H:%M:%S")


def dirty_timestamp() -> str:
    """Return a malformed timestamp string."""
    bad = [
        "not-a-date",
        "32/13/2024",
        "2024-99-01T25:00:00",
        "",
        "yesterday",
        "20240101",
    ]
    return random.choice(bad)


def clean_row(order_id: int) -> dict:
    """Generate a single clean order record."""
    order_time   = random_timestamp()
    delivery_min = random.randint(20, 75)
    item_count   = random.randint(1, 8)
    unit_price   = round(random.uniform(6.5, 22.0), 2)
    subtotal     = round(item_count * unit_price, 2)
    delivery_fee = round(random.uniform(1.5, 4.99), 2)
    total        = round(subtotal + delivery_fee, 2)
    rating       = round(random.uniform(1.0, 5.0), 1)

    return {
        "order_id":          f"ORD-{order_id:05d}",
        "restaurant_id":     RESTAURANT_ID,
        "restaurant_name":   RESTAURANT,
        "customer_id":       f"CUST-{random.randint(1000, 9999)}",
        "customer_name":     fake.name(),
        "delivery_address":  fake.address().replace("\n", ", "),
        "cuisine":           random.choice(CUISINES),
        "item_count":        item_count,
        "subtotal_gbp":      subtotal,
        "delivery_fee_gbp":  delivery_fee,
        "total_gbp":         total,
        "payment_method":    random.choice(PAYMENT_METHODS),
        "order_status":      random.choice(VALID_STATUSES),
        "order_timestamp":   order_time,
        "delivery_minutes":  delivery_min,
        "driver_rating":     rating,
        "is_dirty":          False,     # audit flag — useful for Lambda testing
    }


# ---------------------------------------------------------------------------
# Dirt injection strategies
# Each function takes a row dict and corrupts one or more fields.
# ---------------------------------------------------------------------------

def inject_null_customer(row: dict) -> dict:
    row["customer_id"]   = ""
    row["customer_name"] = None
    row["is_dirty"]      = True
    return row

def inject_negative_total(row: dict) -> dict:
    row["total_gbp"]    = round(random.uniform(-50, -0.01), 2)
    row["subtotal_gbp"] = round(random.uniform(-40, -0.01), 2)
    row["is_dirty"]     = True
    return row

def inject_invalid_status(row: dict) -> dict:
    row["order_status"] = random.choice(INVALID_STATUSES)
    row["is_dirty"]     = True
    return row

def inject_bad_timestamp(row: dict) -> dict:
    row["order_timestamp"] = dirty_timestamp()
    row["is_dirty"]        = True
    return row

def inject_out_of_range_rating(row: dict) -> dict:
    row["driver_rating"] = round(random.choice([
        random.uniform(-5, 0),   # below floor
        random.uniform(5.1, 10), # above ceiling
    ]), 1)
    row["is_dirty"] = True
    return row

def inject_zero_items(row: dict) -> dict:
    row["item_count"]   = 0
    row["subtotal_gbp"] = 0.0
    row["total_gbp"]    = row["delivery_fee_gbp"]
    row["is_dirty"]     = True
    return row

def inject_missing_address(row: dict) -> dict:
    row["delivery_address"] = ""
    row["is_dirty"]         = True
    return row

DIRT_INJECTORS = [
    inject_null_customer,
    inject_negative_total,
    inject_invalid_status,
    inject_bad_timestamp,
    inject_out_of_range_rating,
    inject_zero_items,
    inject_missing_address,
]

# ---------------------------------------------------------------------------
# Main generation logic
# ---------------------------------------------------------------------------

def generate(total_rows: int, seed: int | None = None) -> list[dict]:
    if seed is not None:
        random.seed(seed)
        Faker.seed(seed)

    dirty_count  = int(total_rows * DIRTY_RATIO)
    dirty_indices = set(random.sample(range(total_rows), dirty_count))

    rows = []
    for i in range(total_rows):
        row = clean_row(order_id=i + 1)
        if i in dirty_indices:
            injector = random.choice(DIRT_INJECTORS)
            row = injector(row)
        rows.append(row)

    return rows


def write_csv(rows: list[dict], path: str) -> None:
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate synthetic food delivery orders CSV.")
    parser.add_argument("--rows",   type=int,  default=TOTAL_ROWS,  help="Number of rows to generate (default: 500)")
    parser.add_argument("--seed",   type=int,  default=None,        help="Random seed for reproducibility")
    parser.add_argument("--output", type=str,  default=OUTPUT_FILE, help="Output file path (default: orders.csv)")
    args = parser.parse_args()

    print(f"Generating {args.rows} rows (dirty ratio: {DIRTY_RATIO:.0%})...")
    rows = generate(total_rows=args.rows, seed=args.seed)
    write_csv(rows, args.output)

    dirty_total = sum(1 for r in rows if r["is_dirty"])
    print(f"Done → {args.output}")
    print(f"  Total rows : {len(rows)}")
    print(f"  Clean rows : {len(rows) - dirty_total}")
    print(f"  Dirty rows : {dirty_total} ({dirty_total/len(rows):.1%})")
