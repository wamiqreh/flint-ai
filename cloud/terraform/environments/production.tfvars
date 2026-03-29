# environments/production.tfvars
# Production sizing for paid tiers (Pro + Enterprise)

environment = "production"
aws_region  = "us-east-1"

# Networking
vpc_cidr           = "10.0.0.0/16"
availability_zones = ["us-east-1a", "us-east-1b", "us-east-1c"]

# ECS — API (production capacity)
api_cpu           = 1024   # 1 vCPU
api_memory        = 2048   # 2 GB
api_desired_count = 3
api_max_count     = 20

# ECS — Worker (heavier compute for concurrent task execution)
worker_cpu           = 2048   # 2 vCPU
worker_memory        = 4096   # 4 GB
worker_desired_count = 3
worker_max_count     = 10

# Redis — production-grade instance
redis_node_type       = "cache.r6g.large"
redis_num_cache_nodes = 1

# PostgreSQL — production instance with HA
postgres_instance_class    = "db.r6g.large"
postgres_allocated_storage = 100
postgres_multi_az          = true

tags = {
  Project     = "flint-ai"
  ManagedBy   = "terraform"
  Environment = "production"
  Tier        = "production"
}
