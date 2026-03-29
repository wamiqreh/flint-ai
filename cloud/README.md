# Cloud Deployment

This directory contains infrastructure-as-code and design documents for deploying
Flint as a hosted multi-tenant service.

## Directory Structure

```
cloud/
├── README.md              ← You are here
├── architecture.md        ← Cloud architecture design document
├── pricing.md             ← Tier pricing model (Free / Pro / Enterprise)
└── terraform/
    ├── main.tf            ← Root module wiring all components
    ├── variables.tf       ← Input variables (region, sizing, domain)
    ├── outputs.tf         ← Exported URLs and endpoints
    ├── modules/
    │   ├── networking/    ← VPC, subnets, ALB, security groups
    │   ├── ecs/           ← Fargate task definitions (API + Worker)
    │   ├── redis/         ← ElastiCache Redis
    │   └── postgres/      ← RDS PostgreSQL
    └── environments/
        ├── free-tier.tfvars    ← Minimal sizing for free tier
        └── production.tfvars   ← Production sizing
```

## Quick Start

```bash
cd cloud/terraform

# Initialize Terraform
terraform init

# Preview free-tier deployment
terraform plan -var-file=environments/free-tier.tfvars

# Apply (creates real AWS resources — costs money!)
terraform apply -var-file=environments/free-tier.tfvars
```

## Deployment Targets

| Target     | Description                                  | Status     |
|------------|----------------------------------------------|------------|
| AWS ECS    | Primary target — Fargate, ElastiCache, RDS   | Scaffold   |
| Kubernetes | Helm chart + raw manifests in `k8s/` & `helm/` | Starter  |

## Key Design Decisions

- **AWS-first**: Terraform modules target AWS. GCP/Azure can be added as
  alternative module implementations behind the same variable interface.
- **Fargate**: No EC2 instances to manage — pay per vCPU-second.
- **Multi-tenant**: Single deployment serves all tiers; isolation is enforced
  at the application layer via API keys and Redis rate-limit counters.
- **Secrets**: Stored in AWS Secrets Manager, injected into ECS tasks at runtime.

## Related Docs

- [Architecture Design](architecture.md) — component diagram, scaling, auth
- [Pricing Tiers](pricing.md) — Free / Pro / Enterprise definitions
- [Kubernetes Manifests](../k8s/README.md) — raw K8s deployment
- [Helm Chart](../helm/) — Helm-based deployment
