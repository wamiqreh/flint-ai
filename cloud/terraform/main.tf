# -----------------------------------------------------------------------------
# Flint — Cloud Deployment (AWS)
# -----------------------------------------------------------------------------
# This is the root Terraform configuration that wires together all modules
# to deploy a multi-tenant hosted version of the orchestrator.
#
# Usage:
#   terraform init
#   terraform plan  -var-file=environments/free-tier.tfvars
#   terraform apply -var-file=environments/free-tier.tfvars
# -----------------------------------------------------------------------------

terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Uncomment to use S3 backend for remote state
  # backend "s3" {
  #   bucket         = "orchestrator-terraform-state"
  #   key            = "cloud/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "orchestrator-terraform-locks"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = merge(var.tags, {
      Environment = var.environment
    })
  }
}

# -----------------------------------------------------------------------------
# Networking — VPC, subnets, ALB, security groups
# -----------------------------------------------------------------------------

module "networking" {
  source = "./modules/networking"

  project_name       = var.project_name
  environment        = var.environment
  vpc_cidr           = var.vpc_cidr
  availability_zones = var.availability_zones
  certificate_arn    = var.certificate_arn
  tags               = var.tags
}

# -----------------------------------------------------------------------------
# Redis — ElastiCache for task queue and rate limiting
# -----------------------------------------------------------------------------

module "redis" {
  source = "./modules/redis"

  project_name      = var.project_name
  environment       = var.environment
  subnet_ids        = module.networking.private_subnet_ids
  security_group_id = module.networking.redis_security_group_id
  node_type         = var.redis_node_type
  num_cache_nodes   = var.redis_num_cache_nodes
  engine_version    = var.redis_engine_version
  tags              = var.tags
}

# -----------------------------------------------------------------------------
# PostgreSQL — RDS for persistent storage
# -----------------------------------------------------------------------------

module "postgres" {
  source = "./modules/postgres"

  project_name       = var.project_name
  environment        = var.environment
  subnet_ids         = module.networking.private_subnet_ids
  security_group_id  = module.networking.postgres_security_group_id
  instance_class     = var.postgres_instance_class
  allocated_storage  = var.postgres_allocated_storage
  engine_version     = var.postgres_engine_version
  multi_az           = var.postgres_multi_az
  db_name            = var.postgres_db_name
  tags               = var.tags
}

# -----------------------------------------------------------------------------
# ECS — Fargate services for API and Worker
# -----------------------------------------------------------------------------

module "ecs" {
  source = "./modules/ecs"

  project_name  = var.project_name
  environment   = var.environment
  aws_region    = var.aws_region

  # Networking
  private_subnet_ids   = module.networking.private_subnet_ids
  ecs_security_group_id = module.networking.ecs_security_group_id
  alb_target_group_arn = module.networking.alb_target_group_arn

  # API service
  api_image         = var.api_image
  api_cpu           = var.api_cpu
  api_memory        = var.api_memory
  api_desired_count = var.api_desired_count
  api_max_count     = var.api_max_count

  # Worker service
  worker_image         = var.worker_image
  worker_cpu           = var.worker_cpu
  worker_memory        = var.worker_memory
  worker_desired_count = var.worker_desired_count
  worker_max_count     = var.worker_max_count

  # Dependencies
  redis_endpoint    = module.redis.endpoint
  postgres_endpoint = module.postgres.endpoint
  postgres_db_name  = var.postgres_db_name

  tags = var.tags
}
