output "app_runner_url" {
  description = "Public URL of the App Runner service"
  value       = "https://${aws_apprunner_service.this.service_url}"
}

output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint (for running migrate_sqlite.py)"
  value       = aws_db_instance.postgres.address
}

output "database_url" {
  description = "Full DATABASE_URL (sensitive)"
  value       = "postgresql://${var.db_username}:${var.db_password}@${aws_db_instance.postgres.address}:5432/${var.db_name}"
  sensitive   = true
}

output "ecr_uri" {
  value = aws_ecr_repository.this.repository_url
}
