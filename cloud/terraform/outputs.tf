# -----------------------------------------------------------------------------
# Cloud Deployment — Outputs
# -----------------------------------------------------------------------------

output "alb_dns_name" {
  description = "DNS name of the Application Load Balancer"
  value       = module.networking.alb_dns_name
}

output "api_url" {
  description = "Base URL for the Orchestrator API"
  value       = var.domain_name != "" ? "https://${var.domain_name}" : "http://${module.networking.alb_dns_name}"
}

output "ecs_cluster_name" {
  description = "Name of the ECS cluster"
  value       = module.ecs.cluster_name
}

output "api_service_name" {
  description = "Name of the API ECS service"
  value       = module.ecs.api_service_name
}

output "worker_service_name" {
  description = "Name of the Worker ECS service"
  value       = module.ecs.worker_service_name
}

output "redis_endpoint" {
  description = "ElastiCache Redis primary endpoint"
  value       = module.redis.endpoint
}

output "postgres_endpoint" {
  description = "RDS PostgreSQL endpoint"
  value       = module.postgres.endpoint
}

output "postgres_database" {
  description = "PostgreSQL database name"
  value       = var.postgres_db_name
}

output "vpc_id" {
  description = "VPC ID"
  value       = module.networking.vpc_id
}

output "private_subnet_ids" {
  description = "Private subnet IDs"
  value       = module.networking.private_subnet_ids
}
