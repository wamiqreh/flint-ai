# -----------------------------------------------------------------------------
# Module: PostgreSQL — RDS for Persistent Storage
# -----------------------------------------------------------------------------

variable "project_name"       { type = string }
variable "environment"        { type = string }
variable "subnet_ids"         { type = list(string) }
variable "security_group_id"  { type = string }
variable "instance_class"     { type = string }
variable "allocated_storage"  { type = number }
variable "engine_version"     { type = string }
variable "multi_az"           { type = bool }
variable "db_name"            { type = string }
variable "tags"               { type = map(string) }

locals {
  name_prefix = "${var.project_name}-${var.environment}"
}

# --- Subnet Group ---

resource "aws_db_subnet_group" "main" {
  name       = "${local.name_prefix}-pg-subnet"
  subnet_ids = var.subnet_ids

  tags = merge(var.tags, { Name = "${local.name_prefix}-pg-subnet" })
}

# --- Parameter Group ---

resource "aws_db_parameter_group" "main" {
  name   = "${local.name_prefix}-pg-params"
  family = "postgres15"

  parameter {
    name  = "log_min_duration_statement"
    value = "1000" # Log queries slower than 1 second
  }

  parameter {
    name  = "shared_preload_libraries"
    value = "pg_stat_statements"
  }

  tags = var.tags
}

# --- RDS Instance ---

resource "aws_db_instance" "main" {
  identifier = "${local.name_prefix}-pg"

  engine               = "postgres"
  engine_version       = var.engine_version
  instance_class       = var.instance_class
  allocated_storage    = var.allocated_storage
  storage_type         = "gp3"
  storage_encrypted    = true

  db_name  = var.db_name
  username = "orchestrator"
  # In production, use aws_secretsmanager_secret for the password
  manage_master_user_password = true

  multi_az               = var.multi_az
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [var.security_group_id]
  parameter_group_name   = aws_db_parameter_group.main.name
  publicly_accessible    = false

  # Backup
  backup_retention_period = 7
  backup_window           = "03:00-04:00"
  maintenance_window      = "sun:05:00-sun:06:00"

  # Protection
  deletion_protection       = var.environment == "production"
  skip_final_snapshot       = var.environment != "production"
  final_snapshot_identifier = var.environment == "production" ? "${local.name_prefix}-pg-final" : null

  # Monitoring
  performance_insights_enabled = var.environment == "production"

  tags = merge(var.tags, { Name = "${local.name_prefix}-pg" })
}

# --- Outputs ---

output "endpoint" {
  description = "RDS instance endpoint (hostname)"
  value       = aws_db_instance.main.address
}

output "port" {
  description = "RDS instance port"
  value       = aws_db_instance.main.port
}

output "database_name" {
  description = "Database name"
  value       = aws_db_instance.main.db_name
}
