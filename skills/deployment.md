# Skill: Deployment

Load when: working on Docker, Kubernetes, Helm, Terraform, or deployment configuration.

## Docker

### Dockerfile
```
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir .[server-full]
EXPOSE 5156
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:5156/health || exit 1
ENTRYPOINT ["python", "-m", "flint_ai.server"]
```

### Docker Compose

**Base** (`docker-compose.yml`):
- `flint-api` :5156 → FastAPI server
- `redis` :6379 → Redis 7
- `postgres` :5432 → Postgres 16
- Healthchecks, volume persistence

**HA** (`docker-compose.ha.yml`):
- Redis master + 2 replicas + 3 sentinels
- 2x Flint API instances
- JSON logging

**Monitoring** (`docker-compose.monitoring.yml`):
- Prometheus v2.53 + Grafana 10.4.2
- Pre-provisioned dashboards and alert rules

```bash
docker compose up -d
docker compose -f docker-compose.yml -f docker-compose.ha.yml up -d
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d
```

## Kubernetes

### Files
| File | Purpose |
|------|---------|
| `k8s/worker-deployment.yaml` | Worker Deployment (2 replicas, resource limits, probes) |
| `k8s/pdb.yaml` | PodDisruptionBudget |
| `k8s/secret.example.yaml` | Secret template |

### Worker Deployment Spec
```yaml
replicas: 2
resources:
  requests: {cpu: 100m, memory: 256Mi}
  limits: {cpu: 500m, memory: 512Mi}
readinessProbe: httpGet {path: /ready, port: 5156}
livenessProbe: httpGet {path: /live, port: 5156}
annotations:
  prometheus.io/scrape: "true"
```

## Helm

### Chart: `helm/orchestrator/`

| Template | Purpose |
|----------|---------|
| `api-deployment.yaml` | API Deployment |
| `worker-deployment.yaml` | Worker Deployment |
| `service.yaml` | Service |
| `configmap.yaml` | ConfigMap |
| `secret.yaml` | Secret |
| `servicemonitor.yaml` | Prometheus ServiceMonitor |
| `prometheusrule.yaml` | Alerting rules |

### Values (defaults)
```yaml
api:
  replicaCount: 2
  image:
    repository: ghcr.io/wamiqreh/flint-ai
    tag: latest
  resources:
    requests: {cpu: 200m, memory: 512Mi}
    limits: {cpu: 1000m, memory: 1Gi}

worker:
  replicaCount: 2
  concurrency: 4

config:
  redisUrl: "redis://redis:6379"
  postgresUrl: "postgresql://postgres:postgres@postgres:5432/flint"
  logFormat: "json"

monitoring:
  enabled: true
  serviceMonitor:
    enabled: true
```

### Install
```bash
helm install flint ./helm/orchestrator -f values.yaml
helm upgrade flint ./helm/orchestrator --set api.replicaCount=4
```

## Terraform (AWS)

### Modules
| Module | Purpose |
|--------|---------|
| `cloud/terraform/modules/redis/` | ElastiCache Redis |
| `cloud/terraform/modules/postgres/` | RDS PostgreSQL |
| `cloud/terraform/modules/networking/` | VPC, subnets, security groups |
| `cloud/terraform/modules/ecs/` | ECS Fargate tasks |

### Variables
```hcl
variable "environment" { default = "production" }
variable "redis_node_type" { default = "cache.t3.micro" }
variable "postgres_instance_class" { default = "db.t3.micro" }
variable "ecs_task_cpu" { default = 512 }
variable "ecs_task_memory" { default = 1024 }
```

## Environment Variables

| Variable | Purpose | Required for |
|----------|---------|--------------|
| `REDIS_URL` | Redis connection | Redis queue |
| `POSTGRES_URL` | Postgres connection | Postgres store |
| `SQS_QUEUE_URL` | SQS queue URL | SQS queue |
| `FLINT_LOG_FORMAT` | `text` or `json` | Production logging |
| `FLINT_WORKER_COUNT` | Internal worker count | Server mode |
| `FLINT_PORT` | Server port | Server mode |

## Probes

| Endpoint | Type | Behavior |
|----------|------|----------|
| `/health` | Health | 200 if queue + store connected |
| `/ready` | Readiness | 503 if deps down — removes from LB |
| `/live` | Liveness | Always 200 — restart if down |
| `/metrics` | Prometheus | Metrics endpoint |

## CI/CD

| Workflow | Trigger | What |
|----------|---------|------|
| `ci.yml` | PR/push to main | Lint + typecheck + tests (3.9-3.12) |
| `docker-publish.yml` | push to main, tags, dispatch | Build multi-arch Docker, push to GHCR |
| `pypi-publish.yml` | tag `sdk-python-v*` | Build + upload to PyPI |

## Scaling Guidelines

- **API replicas:** Scale based on HTTP throughput (stateless)
- **Worker replicas:** Scale based on queue depth
- **Redis:** Use sentinel for HA, cluster for sharding
- **Postgres:** Read replicas for dashboard queries, connection pooling
