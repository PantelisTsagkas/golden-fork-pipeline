"""
test_loader_handler.py — Lambda 2: Loader
Uses importlib to isolate module loading from other handler tests.
"""
import csv, io, importlib, importlib.util, sys, os
import boto3, pytest
from moto import mock_aws

REGION      = "eu-west-2"
BUCKET_NAME = "test-pipeline-bucket"
TABLE_NAME  = "test-orders"
LAMBDA_DIR  = os.path.join(os.path.dirname(__file__), "../lambda/loader")
SHARED_DIR  = os.path.join(os.path.dirname(__file__), "../lambda/shared")


def load_handler():
    import dynamodb as dm
    dm._dynamodb_client = None
    for mod in list(sys.modules):
        if mod in ("handler", "dynamodb"):
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
    monkeypatch.setenv("DYNAMODB_TABLE",         TABLE_NAME)


@pytest.fixture
def aws_resources():
    with mock_aws():
        s3  = boto3.client("s3",      region_name=REGION)
        ddb = boto3.client("dynamodb", region_name=REGION)
        s3.create_bucket(Bucket=BUCKET_NAME, CreateBucketConfiguration={"LocationConstraint": REGION})
        ddb.create_table(
            TableName=TABLE_NAME,
            KeySchema=[
                {"AttributeName": "order_id",        "KeyType": "HASH"},
                {"AttributeName": "order_timestamp",  "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "order_id",        "AttributeType": "S"},
                {"AttributeName": "order_timestamp",  "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        yield s3, ddb


def make_clean_csv(n=3):
    rows = [{
        "order_id": f"ORD-{i:05d}", "restaurant_id": "RES-001",
        "restaurant_name": "The Golden Fork", "customer_id": f"CUST-{1000+i}",
        "customer_name": "Jane Smith", "delivery_address": "10 Downing Street",
        "cuisine": "Italian", "item_count": "3", "subtotal_gbp": "45.00",
        "delivery_fee_gbp": "2.99", "total_gbp": "47.99", "payment_method": "card",
        "order_status": "delivered", "order_timestamp": f"2024-06-{i+1:02d}T10:00:00",
        "delivery_minutes": "30", "driver_rating": "4.5", "is_dirty": "False",
    } for i in range(n)]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=rows[0].keys())
    w.writeheader(); w.writerows(rows)
    return buf.getvalue()


def s3_event(bucket, key):
    return {"Records": [{"s3": {"bucket": {"name": bucket}, "object": {"key": key}}}]}


class TestLoaderHandler:
    def test_clean_rows_written_to_dynamodb(self, aws_resources):
        s3, _ = aws_resources
        with mock_aws():
            s3.put_object(Bucket=BUCKET_NAME, Key="clean/orders.csv", Body=make_clean_csv(5))
            h = load_handler()
            result = h.lambda_handler(s3_event(BUCKET_NAME, "clean/orders.csv"), None)
            assert result["dynamodb_written"] == 5 and result["dynamodb_failed"] == 0

    def test_non_clean_key_is_skipped(self, aws_resources):
        with mock_aws():
            h = load_handler()
            result = h.lambda_handler(s3_event(BUCKET_NAME, "raw/orders.csv"), None)
            assert result["body"] == "skipped"

    def test_returns_correct_row_count(self, aws_resources):
        s3, _ = aws_resources
        with mock_aws():
            s3.put_object(Bucket=BUCKET_NAME, Key="clean/orders.csv", Body=make_clean_csv(10))
            h = load_handler()
            result = h.lambda_handler(s3_event(BUCKET_NAME, "clean/orders.csv"), None)
            assert result["rows_read"] == 10 and result["dynamodb_written"] == 10

    def test_batch_count_reported(self, aws_resources):
        s3, _ = aws_resources
        with mock_aws():
            s3.put_object(Bucket=BUCKET_NAME, Key="clean/orders.csv", Body=make_clean_csv(30))
            h = load_handler()
            result = h.lambda_handler(s3_event(BUCKET_NAME, "clean/orders.csv"), None)
            assert result["dynamodb_batches"] == 2
