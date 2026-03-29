# -----------------------------------------------------------------------------
# Module: Redis — ElastiCache for Task Queue + Rate Limiting
# -----------------------------------------------------------------------------

variable "project_name"      { type = string }
variable "environment"       { type = string }
variable "subnet_ids"        { type = list(string) }
variable "security_group_id" { type = string }
variable "node_type"         { type = string }
variable "num_cache_nodes"   { type = number }
variable "engine_version"    { type = string }
variable "tags"              { type = map(string) }

locals {
  name_prefix = "${var.project_name}-${var.environment}"
}

# --- Subnet Group ---

resource "aws_elasticache_subnet_group" "main" {
  name       = "${local.name_prefix}-redis-subnet"
  subnet_ids = var.subnet_ids

  tags = var.tags
}

# --- Parameter Group ---

resource "aws_elasticache_parameter_group" "main" {
  name   = "${local.name_prefix}-redis-params"
  family = "redis7"

  # Enable keyspace notifications for rate-limit key expiry events
  parameter {
    name  = "notify-keyspace-events"
    value = "Ex"
  }

  tags = var.tags
}

# --- ElastiCache Cluster ---

resource "aws_elasticache_cluster" "main" {
  cluster_id           = "${local.name_prefix}-redis"
  engine               = "redis"
  engine_version       = var.engine_version
  node_type            = var.node_type
  num_cache_nodes      = var.num_cache_nodes
  parameter_group_name = aws_elasticache_parameter_group.main.name
  subnet_group_name    = aws_elasticache_subnet_group.main.name
  security_group_ids   = [var.security_group_id]
  port                 = 6379

  # Encryption
  at_rest_encryption_enabled = true
  transit_encryption_enabled = false # Enable for production (requires TLS client)

  # Maintenance
  maintenance_window       = "sun:05:00-sun:06:00"
  snapshot_retention_limit = var.environment == "production" ? 7 : 0

  tags = merge(var.tags, { Name = "${local.name_prefix}-redis" })
}

# --- Outputs ---

output "endpoint" {
  description = "Redis primary endpoint address"
  value       = aws_elasticache_cluster.main.cache_nodes[0].address
}

output "port" {
  description = "Redis port"
  value       = aws_elasticache_cluster.main.port
}
