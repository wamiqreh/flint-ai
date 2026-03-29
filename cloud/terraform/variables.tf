# -----------------------------------------------------------------------------
# Cloud Deployment — Input Variables
# -----------------------------------------------------------------------------

variable "environment" {
  description = "Deployment environment name"
  type        = string
  default     = "free-tier"

  validation {
    condition     = contains(["free-tier", "production"], var.environment)
    error_message = "Environment must be 'free-tier' or 'production'."
  }
}

variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name used for resource naming and tagging"
  type        = string
  default     = "orchestrator"
}

# --- Networking ---

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "List of AZs to deploy into (minimum 2 for HA)"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

variable "domain_name" {
  description = "Custom domain for the ALB (optional, leave empty to skip)"
  type        = string
  default     = ""
}

variable "certificate_arn" {
  description = "ACM certificate ARN for TLS termination on ALB"
  type        = string
  default     = ""
}

# --- ECS ---

variable "api_image" {
  description = "Docker image URI for the API service"
  type        = string
  default     = "ghcr.io/flint-ai/api:latest"
}

variable "worker_image" {
  description = "Docker image URI for the Worker service"
  type        = string
  default     = "ghcr.io/flint-ai/worker:latest"
}

variable "api_cpu" {
  description = "CPU units for API Fargate tasks (256 = 0.25 vCPU)"
  type        = number
  default     = 256
}

variable "api_memory" {
  description = "Memory (MiB) for API Fargate tasks"
  type        = number
  default     = 512
}

variable "api_desired_count" {
  description = "Desired number of API tasks"
  type        = number
  default     = 2
}

variable "api_max_count" {
  description = "Maximum number of API tasks for auto-scaling"
  type        = number
  default     = 4
}

variable "worker_cpu" {
  description = "CPU units for Worker Fargate tasks"
  type        = number
  default     = 512
}

variable "worker_memory" {
  description = "Memory (MiB) for Worker Fargate tasks"
  type        = number
  default     = 1024
}

variable "worker_desired_count" {
  description = "Desired number of Worker tasks"
  type        = number
  default     = 1
}

variable "worker_max_count" {
  description = "Maximum number of Worker tasks for auto-scaling"
  type        = number
  default     = 2
}

# --- Redis ---

variable "redis_node_type" {
  description = "ElastiCache Redis node type"
  type        = string
  default     = "cache.t3.micro"
}

variable "redis_num_cache_nodes" {
  description = "Number of cache nodes (1 for single-node, >1 for cluster)"
  type        = number
  default     = 1
}

variable "redis_engine_version" {
  description = "Redis engine version"
  type        = string
  default     = "7.0"
}

# --- PostgreSQL ---

variable "postgres_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.micro"
}

variable "postgres_allocated_storage" {
  description = "Allocated storage in GB"
  type        = number
  default     = 20
}

variable "postgres_engine_version" {
  description = "PostgreSQL engine version"
  type        = string
  default     = "15"
}

variable "postgres_multi_az" {
  description = "Enable Multi-AZ deployment for RDS"
  type        = bool
  default     = false
}

variable "postgres_db_name" {
  description = "Name of the default database"
  type        = string
  default     = "orchestrator"
}

# --- Tags ---

variable "tags" {
  description = "Common tags applied to all resources"
  type        = map(string)
  default = {
    Project   = "flint-ai"
    ManagedBy = "terraform"
  }
}
