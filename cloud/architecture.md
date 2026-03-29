# Cloud Architecture Design

## Overview

Flint is deployed as a **multi-tenant SaaS** service on AWS.
All tiers (Free, Pro, Enterprise) share the same infrastructure; isolation and
limits are enforced at the application layer using API keys and Redis counters.

---

## Component Diagram

```
                         ┌──────────────┐
                         │   Route 53   │
                         │  DNS / TLS   │
                         └──────┬───────┘
                                │
                         ┌──────▼───────┐
                         │     ALB      │
                         │  (public)    │
                         └──────┬───────┘
                                │
              ┌─────────────────┼─────────────────┐
              │                 │                  │
     ┌────────▼───────┐ ┌──────▼───────┐ ┌───────▼────────┐
     │  ECS Fargate   │ │  ECS Fargate │ │  ECS Fargate   │
     │  API Service   │ │  API Service │ │  Worker Service│
     │  (2+ tasks)    │ │  (auto-scale)│ │  (auto-scale)  │
     └────────┬───────┘ └──────┬───────┘ └───────┬────────┘
              │                │                  │
              └────────────────┼──────────────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
     ┌────────▼───────┐ ┌─────▼──────┐ ┌───────▼────────┐
     │  ElastiCache   │ │    RDS     │ │  CloudWatch    │
     │  Redis 7       │ │ PostgreSQL │ │  + Prometheus  │
     │  (queue/rate)  │ │  15 (data) │ │  (observability│
     └────────────────┘ └────────────┘ └────────────────┘
```

---

## Multi-Tenant Architecture

### Isolation Model

Tenants share compute, queue, and database infrastructure. Isolation is
enforced by the application, not by separate cloud resources:

| Layer        | Isolation Mechanism                                |
|--------------|----------------------------------------------------|
| **API**      | API key in `X-API-Key` header → tenant ID lookup   |
| **Queue**    | Tasks tagged with `tenant_id`; consumer filters    |
| **Database** | Row-level: every table has a `tenant_id` column    |
| **Redis**    | Key prefix: `tenant:{id}:*` for rate-limit counters|

### Tenant Provisioning

1. User signs up via GitHub OAuth.
2. System generates an API key and inserts a row into `tenants` table.
3. Default tier is **Free** — limits are applied immediately.
4. Upgrade to Pro/Enterprise updates the `tier` column and Redis limit keys.

---

## Authentication & Authorization

```
Client → ALB → API
         │
         ├─ POST /auth/github  → Exchange GitHub OAuth code for JWT
         ├─ POST /auth/refresh  → Refresh JWT token
         └─ All other routes   → Validate JWT + resolve tenant
```

- **GitHub OAuth**: Primary sign-in method. OAuth app registered per environment.
- **JWT Tokens**: Short-lived (15 min) access tokens + long-lived refresh tokens.
- **API Keys**: For programmatic access (SDKs, CI/CD). Stored hashed in Postgres.
- **RBAC** (future): Role-based access within a tenant (admin, member, read-only).

---

## Free Tier Limits

| Resource             | Free Tier Limit          |
|----------------------|--------------------------|
| Tasks per day        | 1,000                    |
| Workflows            | 5 active                 |
| Concurrent tasks     | 2                        |
| Task payload size    | 64 KB                    |
| Workflow DAG depth   | 10 steps                 |
| Retention            | 7 days                   |
| Support              | Community (GitHub Issues) |

### Rate Limiting Strategy

Rate limits are enforced **per API key** using Redis:

```
Key:    ratelimit:{api_key}:daily_tasks
Type:   String (counter)
TTL:    Reset at midnight UTC (EXPIREAT)

Key:    ratelimit:{api_key}:concurrent
Type:   String (gauge)
TTL:    None (decremented on task completion)
```

**Algorithm**: Token bucket for burst allowance, sliding window for daily caps.

```
1. API receives request
2. MULTI/EXEC in Redis:
   a. INCR ratelimit:{key}:daily_tasks
   b. GET  ratelimit:{key}:concurrent
3. If daily > limit OR concurrent > limit → 429 Too Many Requests
4. Otherwise → enqueue task, INCR concurrent counter
5. On task completion → DECR concurrent counter
```

---

## Infrastructure Components

### Networking (VPC)

- **VPC**: `10.0.0.0/16` with DNS hostnames enabled.
- **Public subnets** (2 AZs): ALB, NAT Gateway.
- **Private subnets** (2 AZs): ECS tasks, RDS, ElastiCache.
- **Security groups**: ALB → ECS (port 5156), ECS → Redis (6379), ECS → Postgres (5432).

### ECS Fargate — API Service

- **Image**: `{ecr_repo}/orchestrator-api:latest`
- **CPU/Memory**: 256 / 512 (free tier) → 1024 / 2048 (production)
- **Desired count**: 2 (minimum for HA)
- **Health check**: `GET /ready` on port 5156
- **Auto-scaling**: Target tracking on ALB request count per target

### ECS Fargate — Worker Service

- **Image**: `{ecr_repo}/orchestrator-worker:latest`
- **CPU/Memory**: 512 / 1024 (free tier) → 2048 / 4096 (production)
- **Desired count**: 1 (free tier) → 3+ (production)
- **Auto-scaling**: Target tracking on custom CloudWatch metric `QueueDepth`
  - Scale out when queue depth > 100 for 2 minutes
  - Scale in when queue depth < 10 for 5 minutes

### ElastiCache Redis

- **Engine**: Redis 7.x
- **Node type**: `cache.t3.micro` (free tier) → `cache.r6g.large` (production)
- **Cluster mode**: Disabled (single node for free tier)
- **Usage**: Task queue (Redis Streams), rate-limit counters, caching

### RDS PostgreSQL

- **Engine**: PostgreSQL 15
- **Instance**: `db.t3.micro` (free tier) → `db.r6g.large` (production)
- **Storage**: 20 GB gp3 (free tier) → 100 GB+ gp3 (production)
- **Multi-AZ**: No (free tier) → Yes (production)
- **Backups**: 7-day retention, daily snapshots

---

## Auto-Scaling

### API Service Scaling

```
Metric:    ALBRequestCountPerTarget
Target:    1000 requests per target per minute
Min:       2 tasks
Max:       20 tasks (free tier ceiling: 4)
Cooldown:  Scale-out 60s, Scale-in 300s
```

### Worker Service Scaling

```
Metric:    Custom CloudWatch — QueueDepth (published by API)
Target:    Keep queue depth below 50
Min:       1 task
Max:       10 tasks (free tier ceiling: 2)
Cooldown:  Scale-out 120s, Scale-in 300s
```

### Scaling by Tier

| Tier       | API max | Worker max | Redis           | Postgres        |
|------------|---------|------------|-----------------|-----------------|
| Free       | 4       | 2          | cache.t3.micro  | db.t3.micro     |
| Pro        | 10      | 5          | cache.r6g.large | db.r6g.large    |
| Enterprise | 20+     | 10+        | Cluster mode    | Multi-AZ r6g.xl |

---

## Monitoring & Observability

### CloudWatch

- ECS task metrics: CPU, memory, running count
- ALB metrics: request count, latency, 5xx rate
- RDS metrics: connections, IOPS, replication lag
- Custom metrics: `QueueDepth`, `TasksProcessed`, `TasksFailed`

### Prometheus + Grafana

- API exposes `/metrics` endpoint (already implemented)
- Prometheus scrapes ECS tasks via service discovery
- Grafana dashboards for task throughput, latency percentiles, error rates
- Defined in `monitoring/` directory (existing)

### Alerting

| Alert                        | Condition                       | Action        |
|------------------------------|---------------------------------|---------------|
| High error rate              | 5xx > 5% for 5 min             | PagerDuty     |
| Queue depth spike            | Depth > 500 for 5 min          | Scale workers |
| Database connections exhaust | Connections > 80% max           | Alert + scale |
| Redis memory pressure        | Memory > 80%                    | Alert         |

---

## Cost Estimate — Free Tier Infrastructure

Estimated monthly cost to run the free-tier infrastructure on AWS (us-east-1):

| Component              | Specification          | Est. Monthly Cost |
|------------------------|------------------------|-------------------|
| ECS Fargate (API ×2)   | 0.25 vCPU, 0.5 GB     | ~$15              |
| ECS Fargate (Worker ×1)| 0.5 vCPU, 1 GB         | ~$15              |
| ElastiCache Redis      | cache.t3.micro         | ~$13              |
| RDS PostgreSQL         | db.t3.micro, 20 GB     | ~$15              |
| ALB                    | 1 ALB + LCUs           | ~$18              |
| NAT Gateway            | 1 AZ                   | ~$32              |
| CloudWatch             | Metrics + logs         | ~$5               |
| **Total**              |                        | **~$113/month**   |

> **Note**: Costs can be reduced by using Spot Fargate for workers (~40% savings)
> and scheduling scale-to-zero during low-traffic hours.

---

## Security

- **TLS everywhere**: ALB terminates TLS; internal traffic uses private subnets.
- **Secrets**: AWS Secrets Manager for DB passwords, API keys, OAuth secrets.
- **Network**: Private subnets for all compute and data; no public IPs on tasks.
- **Encryption**: RDS and ElastiCache encryption at rest (AWS managed keys).
- **WAF** (optional): AWS WAF on ALB for IP-based and rate-based rules.
