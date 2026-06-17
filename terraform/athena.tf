# =============================================================================
# Athena + Glue — SQL queries over quarantine CSV files in S3
# =============================================================================

resource "aws_glue_catalog_database" "pipeline" {
  name = "${var.project_name}_pipeline"
}

locals {
  quarantine_columns = [
    { name = "order_id", type = "string" },
    { name = "restaurant_id", type = "string" },
    { name = "restaurant_name", type = "string" },
    { name = "customer_id", type = "string" },
    { name = "customer_name", type = "string" },
    { name = "delivery_address", type = "string" },
    { name = "cuisine", type = "string" },
    { name = "item_count", type = "string" },
    { name = "subtotal_gbp", type = "string" },
    { name = "delivery_fee_gbp", type = "string" },
    { name = "total_gbp", type = "string" },
    { name = "payment_method", type = "string" },
    { name = "order_status", type = "string" },
    { name = "order_timestamp", type = "string" },
    { name = "delivery_minutes", type = "string" },
    { name = "driver_rating", type = "string" },
    { name = "is_dirty", type = "string" },
    { name = "validation_failures", type = "string" },
  ]
}

resource "aws_glue_catalog_table" "quarantine_orders" {
  name          = "quarantine_orders"
  database_name = aws_glue_catalog_database.pipeline.name

  table_type = "EXTERNAL_TABLE"

  parameters = {
    EXTERNAL                 = "TRUE"
    "skip.header.line.count" = "1"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.pipeline.id}/quarantine/"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      name                  = "opencsv"
      serialization_library = "org.apache.hadoop.hive.serde2.OpenCSVSerde"
      parameters = {
        "separatorChar" = ","
        "quoteChar"     = "\""
        "escapeChar"    = "\\"
      }
    }

    dynamic "columns" {
      for_each = local.quarantine_columns
      content {
        name = columns.value.name
        type = columns.value.type
      }
    }
  }
}

resource "aws_athena_workgroup" "pipeline" {
  name = "${var.project_name}-pipeline"

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true

    result_configuration {
      output_location = "s3://${aws_s3_bucket.pipeline.id}/athena-results/"
    }
  }

  tags = local.common_tags
}
