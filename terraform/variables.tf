# =============================================================================
# variables.tf — Input variables for the Golden Fork Pipeline
# =============================================================================

variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "eu-west-2"
}

variable "project_name" {
  description = "Project name used as prefix for resource names"
  type        = string
  default     = "golden-fork"
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "bucket_name" {
  description = "Name for the S3 pipeline bucket (must be globally unique)"
  type        = string
}

variable "alert_email" {
  description = "Email address to receive quarantine alerts via SNS"
  type        = string
}
