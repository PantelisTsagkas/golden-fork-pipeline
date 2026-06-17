"""Publish custom CloudWatch metrics for pipeline observability."""

import logging
import os

import boto3

logger = logging.getLogger(__name__)
_cloudwatch = None


def _client():
    global _cloudwatch
    if _cloudwatch is None:
        _cloudwatch = boto3.client("cloudwatch")
    return _cloudwatch


def publish_metrics(metrics: list[dict]) -> None:
    namespace = os.environ.get("METRICS_NAMESPACE", "GoldenFork/Pipeline")
    base_dimensions = [
        {"Name": "Project", "Value": os.environ.get("PROJECT_NAME", "golden-fork")},
        {"Name": "Environment", "Value": os.environ.get("ENVIRONMENT", "dev")},
    ]

    metric_data = []
    for metric in metrics:
        metric_data.append(
            {
                "MetricName": metric["name"],
                "Value": metric["value"],
                "Unit": metric.get("unit", "Count"),
                "Dimensions": base_dimensions + metric.get("dimensions", []),
            }
        )

    try:
        _client().put_metric_data(Namespace=namespace, MetricData=metric_data)
        logging.getLogger().info("Published %d CloudWatch metrics to %s", len(metric_data), namespace)
    except Exception as exc:
        logging.getLogger().warning("Failed to publish CloudWatch metrics: %s", exc)
