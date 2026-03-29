# environments/free-tier.tfvars
# Minimal sizing for the free hosted tier (~$113/month AWS cost)

environment = "free-tier"
aws_region  = "us-east-1"

# Networking
vpc_cidr           = "10.0.0.0/16"
availability_zones = ["us-east-1a", "us-east-1b"]

# ECS — API (small footprint)
api_cpu           = 256   # 0.25 vCPU
api_memory        = 512   # 512 MB
api_desired_count = 2
api_max_count     = 4

# ECS — Worker (slightly larger for task execution)
worker_cpu           = 512    # 0.5 vCPU
worker_memory        = 1024   # 1 GB
worker_desired_count = 1
worker_max_count     = 2

# Redis — single micro node
redis_node_type       = "cache.t3.micro"
redis_num_cache_nodes = 1

# PostgreSQL — smallest instance
postgres_instance_class    = "db.t3.micro"
postgres_allocated_storage = 20
postgres_multi_az          = false

tags = {
  Project     = "flint-ai"
  ManagedBy   = "terraform"
  Environment = "free-tier"
  Tier        = "free"
}
