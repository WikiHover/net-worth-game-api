output "service_url" {
  description = "ALB URL for the net-worth-game service"
  value       = "https://networth.wikihover.com"
}

output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint"
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
