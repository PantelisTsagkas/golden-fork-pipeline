# =============================================================================
# main.tf — Golden Fork Pipeline (three-Lambda architecture)
#
# Lambda 1 — Validator   : S3 /raw     → splits to /clean + /quarantine
# Lambda 2 — Loader      : S3 /clean   → writes to DynamoDB
# Lambda 3 — Alerter     : S3 /quarantine → publishes SNS alert
# =============================================================================

terraform {
  required_version = ">= 1.6.0"
  required_providers {
    aws     = { source = "hashicorp/aws", version = "~> 5.0" }
    archive = { source = "hashicorp/archive", version = "~> 2.0" }
  }
}

provider "aws" { region = var.aws_region }

locals {
  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# =============================================================================
# S3 Bucket
# =============================================================================

resource "aws_s3_bucket" "pipeline" {
  bucket        = var.bucket_name
  force_destroy = true
  tags          = local.common_tags
}

resource "aws_s3_bucket_versioning" "pipeline" {
  bucket = aws_s3_bucket.pipeline.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_public_access_block" "pipeline" {
  bucket                  = aws_s3_bucket.pipeline.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "pipeline" {
  bucket = aws_s3_bucket.pipeline.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

# =============================================================================
# SNS Topic — quarantine alerts
# =============================================================================

resource "aws_sns_topic" "quarantine_alerts" {
  name = "${var.project_name}-quarantine-alerts"
  tags = local.common_tags
}

resource "aws_sns_topic_subscription" "email_alert" {
  topic_arn = aws_sns_topic.quarantine_alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# =============================================================================
# DynamoDB Table
# =============================================================================

resource "aws_dynamodb_table" "orders" {
  name         = "${var.project_name}-orders"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "order_id"
  range_key    = "order_timestamp"

  attribute {
    name = "order_id"
    type = "S"
  }
  attribute {
    name = "order_timestamp"
    type = "S"
  }

  point_in_time_recovery { enabled = true }
  tags = local.common_tags
}

# =============================================================================
# IAM — shared assume-role doc
# =============================================================================

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "logs" {
  statement {
    effect    = "Allow"
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:*:*:*"]
  }
}

# =============================================================================
# Lambda 1 — Validator
# =============================================================================

data "archive_file" "validator_zip" {
  type        = "zip"
  output_path = "${path.module}/builds/validator.zip"
  source {
    content  = file("${path.module}/../lambda/validator/handler.py")
    filename = "handler.py"
  }
  source {
    content  = file("${path.module}/../lambda/shared/validators.py")
    filename = "validators.py"
  }
}

resource "aws_iam_role" "validator" {
  name               = "${var.project_name}-validator"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "validator_policy" {
  statement {
    effect    = "Allow"
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:*:*:*"]
  }
  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.pipeline.arn}/raw/*"]
  }
  statement {
    effect    = "Allow"
    actions   = ["s3:PutObject"]
    resources = [
      "${aws_s3_bucket.pipeline.arn}/clean/*",
      "${aws_s3_bucket.pipeline.arn}/quarantine/*",
    ]
  }
}

resource "aws_iam_role_policy" "validator" {
  name   = "${var.project_name}-validator-policy"
  role   = aws_iam_role.validator.id
  policy = data.aws_iam_policy_document.validator_policy.json
}

resource "aws_lambda_function" "validator" {
  function_name    = "${var.project_name}-validator"
  description      = "Validates CSV rows and splits into /clean and /quarantine"
  role             = aws_iam_role.validator.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.validator_zip.output_path
  source_code_hash = data.archive_file.validator_zip.output_base64sha256
  timeout          = 60
  memory_size      = 256
  environment {
    variables = { BUCKET_NAME = aws_s3_bucket.pipeline.id }
  }
  tags = local.common_tags
}

resource "aws_cloudwatch_log_group" "validator" {
  name              = "/aws/lambda/${aws_lambda_function.validator.function_name}"
  retention_in_days = 14
  tags              = local.common_tags
}

resource "aws_lambda_permission" "validator_s3" {
  statement_id  = "AllowS3InvokeValidator"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.validator.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.pipeline.arn
}

# =============================================================================
# Lambda 2 — Loader
# =============================================================================

data "archive_file" "loader_zip" {
  type        = "zip"
  output_path = "${path.module}/builds/loader.zip"
  source {
    content  = file("${path.module}/../lambda/loader/handler.py")
    filename = "handler.py"
  }
  source {
    content  = file("${path.module}/../lambda/shared/dynamodb.py")
    filename = "dynamodb.py"
  }
}

resource "aws_iam_role" "loader" {
  name               = "${var.project_name}-loader"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "loader_policy" {
  statement {
    effect    = "Allow"
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:*:*:*"]
  }
  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.pipeline.arn}/clean/*"]
  }
  statement {
    effect    = "Allow"
    actions   = ["dynamodb:BatchWriteItem"]
    resources = [aws_dynamodb_table.orders.arn]
  }
}

resource "aws_iam_role_policy" "loader" {
  name   = "${var.project_name}-loader-policy"
  role   = aws_iam_role.loader.id
  policy = data.aws_iam_policy_document.loader_policy.json
}

resource "aws_lambda_function" "loader" {
  function_name    = "${var.project_name}-loader"
  description      = "Reads /clean CSV and batch-writes rows to DynamoDB"
  role             = aws_iam_role.loader.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.loader_zip.output_path
  source_code_hash = data.archive_file.loader_zip.output_base64sha256
  timeout          = 60
  memory_size      = 256
  environment {
    variables = {
      BUCKET_NAME    = aws_s3_bucket.pipeline.id
      DYNAMODB_TABLE = aws_dynamodb_table.orders.name
    }
  }
  tags = local.common_tags
}

resource "aws_cloudwatch_log_group" "loader" {
  name              = "/aws/lambda/${aws_lambda_function.loader.function_name}"
  retention_in_days = 14
  tags              = local.common_tags
}

resource "aws_lambda_permission" "loader_s3" {
  statement_id  = "AllowS3InvokeLoader"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.loader.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.pipeline.arn
}

# =============================================================================
# Lambda 3 — Alerter
# =============================================================================

data "archive_file" "alerter_zip" {
  type        = "zip"
  output_path = "${path.module}/builds/alerter.zip"
  source {
    content  = file("${path.module}/../lambda/alerter/handler.py")
    filename = "handler.py"
  }
}

resource "aws_iam_role" "alerter" {
  name               = "${var.project_name}-alerter"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "alerter_policy" {
  statement {
    effect    = "Allow"
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:*:*:*"]
  }
  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.pipeline.arn}/quarantine/*"]
  }
  statement {
    effect    = "Allow"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.quarantine_alerts.arn]
  }
}

resource "aws_iam_role_policy" "alerter" {
  name   = "${var.project_name}-alerter-policy"
  role   = aws_iam_role.alerter.id
  policy = data.aws_iam_policy_document.alerter_policy.json
}

resource "aws_lambda_function" "alerter" {
  function_name    = "${var.project_name}-alerter"
  description      = "Reads /quarantine CSV and publishes SNS alert"
  role             = aws_iam_role.alerter.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.alerter_zip.output_path
  source_code_hash = data.archive_file.alerter_zip.output_base64sha256
  timeout          = 30
  memory_size      = 128
  environment {
    variables = {
      BUCKET_NAME   = aws_s3_bucket.pipeline.id
      SNS_TOPIC_ARN = aws_sns_topic.quarantine_alerts.arn
    }
  }
  tags = local.common_tags
}

resource "aws_cloudwatch_log_group" "alerter" {
  name              = "/aws/lambda/${aws_lambda_function.alerter.function_name}"
  retention_in_days = 14
  tags              = local.common_tags
}

resource "aws_lambda_permission" "alerter_s3" {
  statement_id  = "AllowS3InvokeAlerter"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.alerter.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.pipeline.arn
}

# =============================================================================
# S3 Bucket Notifications — three triggers, one notification resource
# =============================================================================

resource "aws_s3_bucket_notification" "pipeline_triggers" {
  bucket = aws_s3_bucket.pipeline.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.validator.arn
    events              = ["s3:ObjectCreated:Put"]
    filter_prefix       = "raw/"
    filter_suffix       = ".csv"
  }

  lambda_function {
    lambda_function_arn = aws_lambda_function.loader.arn
    events              = ["s3:ObjectCreated:Put"]
    filter_prefix       = "clean/"
    filter_suffix       = ".csv"
  }

  lambda_function {
    lambda_function_arn = aws_lambda_function.alerter.arn
    events              = ["s3:ObjectCreated:Put"]
    filter_prefix       = "quarantine/"
    filter_suffix       = ".csv"
  }

  depends_on = [
    aws_lambda_permission.validator_s3,
    aws_lambda_permission.loader_s3,
    aws_lambda_permission.alerter_s3,
  ]
}
