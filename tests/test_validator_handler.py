"""
test_validator_handler.py — Lambda 1: Validator
Uses importlib to isolate module loading from other handler tests.
"""
import csv, io, importlib, importlib.util, sys, os
import boto3, pytest
from moto import mock_aws

REGION      = "eu-west-2"
BUCKET_NAME = "test-pipeline-bucket"
LAMBDA_DIR  = os.path.join(os.path.dirname(__file__), "../lambda/validator")
SHARED_DIR  = os.path.join(os.path.dirname(__file__), "../lambda/shared")


def load_handler():
    """Load validator/handler.py in isolation via importlib."""
    for mod in list(sys.modules):
        if mod in ("handler", "validators", "dynamodb"):
            del sys.modules[mod]
    sys.path.insert(0, SHARED_DIR)
    sys.path.insert(0, LAMBDA_DIR)
    spec = importlib.util.spec_from_file_location("handler", f"{LAMBDA_DIR}/handler.py")
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(autouse=True)
def aws_env(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID",     "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION",     REGION)
    monkeypatch.setenv("BUCKET_NAME",            BUCKET_NAME)


@pytest.fixture
def s3_bucket():
    with mock_aws():
        client = boto3.client("s3", region_name=REGION)
        client.create_bucket(
            Bucket=BUCKET_NAME,
            CreateBucketConfiguration={"LocationConstraint": REGION},
        )
        yield client


def make_csv(rows):
    buf = io.StringIO()
    csv.DictWriter(buf, fieldnames=rows[0].keys()).writeheader() or \
    csv.DictWriter(buf, fieldnames=rows[0].keys()).writerows(rows)
    buf.seek(0); buf.truncate(0)
    w = csv.DictWriter(buf, fieldnames=rows[0].keys())
    w.writeheader(); w.writerows(rows)
    return buf.getvalue()


def make_row(order_id="ORD-00001", dirty=False):
    row = {
        "order_id": order_id, "restaurant_id": "RES-001",
        "restaurant_name": "The Golden Fork", "customer_id": "CUST-1234",
        "customer_name": "Jane Smith", "delivery_address": "10 Downing Street",
        "cuisine": "Italian", "item_count": "3", "subtotal_gbp": "45.00",
        "delivery_fee_gbp": "2.99", "total_gbp": "47.99", "payment_method": "card",
        "order_status": "delivered", "order_timestamp": "2024-06-15T14:30:00",
        "delivery_minutes": "35", "driver_rating": "4.5", "is_dirty": "False",
    }
    if dirty:
        row.update({"customer_id": "", "order_status": "INVALID", "is_dirty": "True"})
    return row


def s3_event(bucket, key):
    return {"Records": [{"s3": {"bucket": {"name": bucket}, "object": {"key": key}}}]}


class TestValidatorHandler:
    def test_clean_rows_written_to_clean_prefix(self, s3_bucket):
        with mock_aws():
            rows = [make_row("ORD-00001"), make_row("ORD-00002")]
            s3_bucket.put_object(Bucket=BUCKET_NAME, Key="raw/orders.csv", Body=make_csv(rows))
            h = load_handler()
            result = h.lambda_handler(s3_event(BUCKET_NAME, "raw/orders.csv"), None)
            assert result["clean_rows"] == 2 and result["quarantine_rows"] == 0
            resp = s3_bucket.get_object(Bucket=BUCKET_NAME, Key="clean/orders.csv")
            assert len(list(csv.DictReader(io.StringIO(resp["Body"].read().decode())))) == 2

    def test_dirty_rows_written_to_quarantine(self, s3_bucket):
        with mock_aws():
            rows = [make_row("ORD-00001"), make_row("ORD-00002", dirty=True)]
            s3_bucket.put_object(Bucket=BUCKET_NAME, Key="raw/orders.csv", Body=make_csv(rows))
            h = load_handler()
            result = h.lambda_handler(s3_event(BUCKET_NAME, "raw/orders.csv"), None)
            assert result["clean_rows"] == 1 and result["quarantine_rows"] == 1
            resp   = s3_bucket.get_object(Bucket=BUCKET_NAME, Key="quarantine/orders.csv")
            q_rows = list(csv.DictReader(io.StringIO(resp["Body"].read().decode())))
            assert len(q_rows) == 1 and "validation_failures" in q_rows[0]

    def test_quarantine_rows_have_failure_reasons(self, s3_bucket):
        with mock_aws():
            s3_bucket.put_object(Bucket=BUCKET_NAME, Key="raw/orders.csv", Body=make_csv([make_row(dirty=True)]))
            h = load_handler()
            h.lambda_handler(s3_event(BUCKET_NAME, "raw/orders.csv"), None)
            resp  = s3_bucket.get_object(Bucket=BUCKET_NAME, Key="quarantine/orders.csv")
            q_row = list(csv.DictReader(io.StringIO(resp["Body"].read().decode())))[0]
            assert q_row["validation_failures"] != ""

    def test_non_raw_key_is_skipped(self, s3_bucket):
        with mock_aws():
            h = load_handler()
            result = h.lambda_handler(s3_event(BUCKET_NAME, "clean/orders.csv"), None)
            assert result["body"] == "skipped"

    def test_returns_correct_split_counts(self, s3_bucket):
        with mock_aws():
            rows = [make_row(f"ORD-{i:05d}", dirty=(i % 3 == 0)) for i in range(9)]
            s3_bucket.put_object(Bucket=BUCKET_NAME, Key="raw/orders.csv", Body=make_csv(rows))
            h = load_handler()
            result = h.lambda_handler(s3_event(BUCKET_NAME, "raw/orders.csv"), None)
            assert result["total_rows"] == 9
            assert result["clean_rows"] + result["quarantine_rows"] == 9
