# =============================================================================
# SQS Dead Letter Queues — capture Lambda invocations that fail after retries
# =============================================================================

resource "aws_sqs_queue" "validator_dlq" {
  name                      = "${var.project_name}-validator-dlq"
  message_retention_seconds = 1209600 # 14 days
  tags                      = local.common_tags
}

resource "aws_sqs_queue" "loader_dlq" {
  name                      = "${var.project_name}-loader-dlq"
  message_retention_seconds = 1209600
  tags                      = local.common_tags
}

resource "aws_sqs_queue" "alerter_dlq" {
  name                      = "${var.project_name}-alerter-dlq"
  message_retention_seconds = 1209600
  tags                      = local.common_tags
}
