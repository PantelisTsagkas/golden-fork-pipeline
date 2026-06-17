# =============================================================================
# CloudWatch Dashboard — pipeline row counts and quarantine rate
# =============================================================================

resource "aws_cloudwatch_dashboard" "pipeline" {
  dashboard_name = "${var.project_name}-pipeline"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "text"
        x      = 0
        y      = 0
        width  = 24
        height = 2
        properties = {
          markdown = "# Golden Fork Pipeline\nMetrics appear after each CSV upload. Use **1h** or **3h** time range — each upload is a single data point."
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 2
        width  = 6
        height = 4
        properties = {
          title  = "Total rows"
          region = var.aws_region
          view   = "singleValue"
          stat   = "Maximum"
          period = 300
          metrics = [
            ["GoldenFork/Pipeline", "TotalRows", "Project", var.project_name, "Environment", var.environment],
          ]
        }
      },
      {
        type   = "metric"
        x      = 6
        y      = 2
        width  = 6
        height = 4
        properties = {
          title  = "Clean rows"
          region = var.aws_region
          view   = "singleValue"
          stat   = "Maximum"
          period = 300
          metrics = [
            ["GoldenFork/Pipeline", "CleanRows", "Project", var.project_name, "Environment", var.environment],
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 2
        width  = 6
        height = 4
        properties = {
          title  = "Quarantine rows"
          region = var.aws_region
          view   = "singleValue"
          stat   = "Maximum"
          period = 300
          metrics = [
            ["GoldenFork/Pipeline", "QuarantineRows", "Project", var.project_name, "Environment", var.environment],
          ]
        }
      },
      {
        type   = "metric"
        x      = 18
        y      = 2
        width  = 6
        height = 4
        properties = {
          title  = "Quarantine rate %"
          region = var.aws_region
          view   = "singleValue"
          stat   = "Maximum"
          period = 300
          metrics = [
            ["GoldenFork/Pipeline", "QuarantineRate", "Project", var.project_name, "Environment", var.environment],
          ]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "Row counts per upload (Validator)"
          region = var.aws_region
          view   = "timeSeries"
          stat   = "Maximum"
          period = 300
          metrics = [
            ["GoldenFork/Pipeline", "TotalRows", "Project", var.project_name, "Environment", var.environment],
            ["GoldenFork/Pipeline", "CleanRows", "Project", var.project_name, "Environment", var.environment],
            ["GoldenFork/Pipeline", "QuarantineRows", "Project", var.project_name, "Environment", var.environment],
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "Loader & Alerter"
          region = var.aws_region
          view   = "timeSeries"
          stat   = "Maximum"
          period = 300
          metrics = [
            ["GoldenFork/Pipeline", "LoadedRows", "Project", var.project_name, "Environment", var.environment],
            ["GoldenFork/Pipeline", "QuarantineAlertRows", "Project", var.project_name, "Environment", var.environment],
          ]
        }
      },
    ]
  })
}
