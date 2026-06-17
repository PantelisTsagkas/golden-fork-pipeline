output "bucket_name"            { value = aws_s3_bucket.pipeline.id }
output "dynamodb_table_name"    { value = aws_dynamodb_table.orders.name }
output "sns_topic_arn"          { value = aws_sns_topic.quarantine_alerts.arn }
output "lambda_validator_name"  { value = aws_lambda_function.validator.function_name }
output "lambda_loader_name"     { value = aws_lambda_function.loader.function_name }
output "lambda_alerter_name"    { value = aws_lambda_function.alerter.function_name }
output "upload_command"         { value = "aws s3 cp orders.csv s3://${aws_s3_bucket.pipeline.id}/raw/orders.csv" }

output "cloudwatch_dashboard_name" { value = aws_cloudwatch_dashboard.pipeline.dashboard_name }
output "cloudwatch_dashboard_url" {
  value = "https://${var.aws_region}.console.aws.amazon.com/cloudwatch/home?region=${var.aws_region}#dashboards/dashboard/${aws_cloudwatch_dashboard.pipeline.dashboard_name}"
}

output "athena_workgroup"   { value = aws_athena_workgroup.pipeline.name }
output "athena_database"    { value = aws_glue_catalog_database.pipeline.name }
output "athena_table"       { value = aws_glue_catalog_table.quarantine_orders.name }
output "validator_dlq_url"  { value = aws_sqs_queue.validator_dlq.url }
output "loader_dlq_url"     { value = aws_sqs_queue.loader_dlq.url }
output "alerter_dlq_url"    { value = aws_sqs_queue.alerter_dlq.url }

output "athena_sample_queries" {
  value = <<-EOT
    -- Failure breakdown (run in Athena console, workgroup: ${aws_athena_workgroup.pipeline.name})
    SELECT validation_failures, COUNT(*) AS row_count
    FROM ${aws_glue_catalog_database.pipeline.name}.${aws_glue_catalog_table.quarantine_orders.name}
    GROUP BY validation_failures
    ORDER BY row_count DESC;

    -- Sample quarantined orders
    SELECT order_id, customer_id, order_status, validation_failures
    FROM ${aws_glue_catalog_database.pipeline.name}.${aws_glue_catalog_table.quarantine_orders.name}
    LIMIT 20;
  EOT
}
