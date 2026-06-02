"""
test_alerter_handler.py — Lambda 3: Alerter
Uses importlib to isolate module loading from other handler tests.
"""
import csv, io, importlib, importlib.util, sys, os, json
import boto3, pytest
from moto import mock_aws

REGION      = "eu-west-2"
BUCKET_NAME = "test-pipeline-bucket"
LAMBDA_DIR  = os.path.join(os.path.dirname(__file__), "../lambda/alerter")
SHARED_DIR  = os.path.join(os.path.dirname(__file__), "../lambda/shared")


def load_handler():
    for mod in list(sys.modules):
        if mod in ("handler",):
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
def aws_resources(monkeypatch):
    with mock_aws():
        s3  = boto3.client("s3",  region_name=REGION)
        sns = boto3.client("sns", region_name=REGION)
        sqs = boto3.client("sqs", region_name=REGION)

        s3.create_bucket(Bucket=BUCKET_NAME, CreateBucketConfiguration={"LocationConstraint": REGION})

        topic     = sns.create_topic(Name="test-alerts")
        topic_arn = topic["TopicArn"]
        monkeypatch.setenv("SNS_TOPIC_ARN", topic_arn)

        queue     = sqs.create_queue(QueueName="test-alert-queue")
        queue_url = queue["QueueUrl"]
        queue_arn = sqs.get_queue_attributes(QueueUrl=queue_url, AttributeNames=["QueueArn"])["Attributes"]["QueueArn"]
        sns.subscribe(TopicArn=topic_arn, Protocol="sqs", Endpoint=queue_arn)

        yield s3, sns, sqs, queue_url, topic_arn


def make_quarantine_csv(n=3, failure="missing_delivery_address"):
    rows = [{
        "order_id": f"ORD-{i:05d}", "customer_id": "",
        "order_status": "delivered", "order_timestamp": f"2024-06-{i+1:02d}T10:00:00",
        "is_dirty": "True", "validation_failures": failure,
    } for i in range(n)]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=rows[0].keys())
    w.writeheader(); w.writerows(rows)
    return buf.getvalue()


def s3_event(bucket, key):
    return {"Records": [{"s3": {"bucket": {"name": bucket}, "object": {"key": key}}}]}


class TestAlerterHandler:
    def test_sns_alert_published_on_quarantine_file(self, aws_resources):
        s3, _, sqs, queue_url, _ = aws_resources
        with mock_aws():
            s3.put_object(Bucket=BUCKET_NAME, Key="quarantine/orders.csv", Body=make_quarantine_csv(5))
            h = load_handler()
            result = h.lambda_handler(s3_event(BUCKET_NAME, "quarantine/orders.csv"), None)
            assert result["alert_sent"] is True and result["quarantined_rows"] == 5
            messages = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=1)
            assert "Messages" in messages

    def test_failure_summary_built_correctly(self, aws_resources):
        s3, _, _, _, _ = aws_resources
        with mock_aws():
            s3.put_object(Bucket=BUCKET_NAME, Key="quarantine/orders.csv", Body=make_quarantine_csv(4))
            h = load_handler()
            result = h.lambda_handler(s3_event(BUCKET_NAME, "quarantine/orders.csv"), None)
            assert result["failure_summary"]["missing_delivery_address"] == 4

    def test_non_quarantine_key_is_skipped(self, aws_resources):
        with mock_aws():
            h = load_handler()
            result = h.lambda_handler(s3_event(BUCKET_NAME, "clean/orders.csv"), None)
            assert result["body"] == "skipped"

    def test_empty_quarantine_file_sends_no_alert(self, aws_resources):
        s3, _, _, _, _ = aws_resources
        with mock_aws():
            s3.put_object(Bucket=BUCKET_NAME, Key="quarantine/orders.csv", Body="order_id,validation_failures\n")
            h = load_handler()
            result = h.lambda_handler(s3_event(BUCKET_NAME, "quarantine/orders.csv"), None)
            assert "empty quarantine" in result["body"]
