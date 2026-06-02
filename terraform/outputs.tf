output "bucket_name"            { value = aws_s3_bucket.pipeline.id }
output "dynamodb_table_name"    { value = aws_dynamodb_table.orders.name }
output "sns_topic_arn"          { value = aws_sns_topic.quarantine_alerts.arn }
output "lambda_validator_name"  { value = aws_lambda_function.validator.function_name }
output "lambda_loader_name"     { value = aws_lambda_function.loader.function_name }
output "lambda_alerter_name"    { value = aws_lambda_function.alerter.function_name }
output "upload_command"         { value = "aws s3 cp orders.csv s3://${aws_s3_bucket.pipeline.id}/raw/orders.csv" }
