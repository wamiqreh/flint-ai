# Pricing Tiers

## Overview

Flint is offered in three tiers. All tiers run on shared
infrastructure — limits are enforced at the application layer via API keys and
Redis rate-limit counters.

---

## Tier Comparison

| Feature                    | Free              | Pro ($49/mo)          | Enterprise (Custom)       |
|----------------------------|-------------------|-----------------------|---------------------------|
| **Tasks per day**          | 1,000             | 50,000                | Unlimited                 |
| **Active workflows**       | 5                 | Unlimited             | Unlimited                 |
| **Concurrent tasks**       | 2                 | 20                    | Unlimited                 |
| **Task payload size**      | 64 KB             | 1 MB                  | 10 MB                     |
| **Workflow DAG depth**     | 10 steps          | 50 steps              | Unlimited                 |
| **Data retention**         | 7 days            | 90 days               | Custom (up to unlimited)  |
| **API rate limit**         | 60 req/min        | 600 req/min           | Custom                    |
| **Agent types**            | All supported     | All supported         | All + custom adapters     |
| **Queue backends**         | Redis Streams     | Redis Streams         | Redis / Kafka / SQS       |
| **Redis**                  | Shared             | Dedicated instance    | Dedicated cluster         |
| **Support**                | Community (GitHub) | Priority email (24h) | Dedicated Slack + SLA     |
| **SSO / SAML**             | —                 | —                     | ✓                         |
| **Audit logs**             | —                 | Basic                 | Full + export             |
| **VPC peering**            | —                 | —                     | ✓                         |
| **Custom domain**          | —                 | ✓                     | ✓                         |
| **SLA**                    | —                 | 99.5% uptime          | 99.9%+ uptime             |

---

## Free Tier

**$0/month** — Get started at no cost.

Best for: Individual developers, side projects, evaluating the platform.

### Limits

- 1,000 tasks/day (resets at midnight UTC)
- 5 active workflows
- 2 concurrent task executions
- 64 KB max payload per task
- 10-step max workflow DAG depth
- 7-day data retention
- 60 API requests/minute

### What's Included

- Full API access (REST + gRPC when available)
- Python SDK + CLI
- All built-in agent adapters (Copilot, Claude, OpenAI, Custom)
- Redis Streams queue backend
- Basic metrics dashboard
- Community support via GitHub Issues and Discussions

### Fair Use

Free tier is intended for development and evaluation. Automated abuse (e.g.,
creating multiple accounts to bypass limits) will result in account suspension.

---

## Pro Tier

**$49/month** per workspace — For teams shipping AI-powered products.

Best for: Startups, small teams, production workloads.

### Everything in Free, plus:

- 50,000 tasks/day
- Unlimited active workflows
- 20 concurrent task executions
- 1 MB max payload per task
- 50-step max workflow DAG depth
- 90-day data retention
- 600 API requests/minute
- **Dedicated Redis instance** (no noisy neighbors)
- Priority email support (24-hour response time)
- Basic audit logs (API access, task lifecycle events)
- Custom domain support (CNAME to your subdomain)
- 99.5% uptime SLA

### Add-ons (Pro)

| Add-on                 | Price        |
|------------------------|--------------|
| Extra 50K tasks/day    | $29/mo       |
| Additional workspace   | $49/mo       |
| Extended retention (1y)| $19/mo       |

---

## Enterprise Tier

**Custom pricing** — For organizations with advanced requirements.

Best for: Large teams, regulated industries, high-throughput workloads.

### Everything in Pro, plus:

- Unlimited tasks, workflows, and concurrency
- 10 MB max payload per task
- Unlimited workflow DAG depth
- Custom data retention (up to unlimited)
- Custom API rate limits
- **Dedicated infrastructure** (isolated ECS cluster, RDS, Redis)
- All queue backends (Redis Streams, Kafka, SQS)
- Custom agent adapter support
- SSO / SAML integration
- Full audit logs with export (S3, SIEM integration)
- VPC peering for private network access
- Dedicated Slack channel for support
- 99.9%+ uptime SLA with credits
- Quarterly architecture reviews

### Contact

Email **enterprise@example.com** or [schedule a call](https://example.com/demo)
for custom pricing.

---

## Infrastructure Cost Basis

Estimated AWS infrastructure cost per tier (us-east-1):

| Component          | Free Tier         | Pro Tier           | Enterprise Tier      |
|--------------------|-------------------|--------------------|----------------------|
| ECS (API)          | 2× 0.25 vCPU     | 4× 1 vCPU         | 8× 2 vCPU           |
| ECS (Worker)       | 1× 0.5 vCPU      | 3× 1 vCPU         | 10× 2 vCPU          |
| Redis              | cache.t3.micro    | cache.r6g.large    | cache.r6g.xl cluster |
| PostgreSQL         | db.t3.micro       | db.r6g.large       | db.r6g.xlarge HA     |
| **Est. infra cost**| ~$113/mo          | ~$450/mo           | ~$2,000+/mo          |
| **Margin**         | Subsidized        | ~89%               | Negotiated           |

> Free tier is subsidized by Pro and Enterprise revenue. Break-even at
> approximately 10 Pro subscribers per hosted region.

---

## Billing & Usage

- **Billing cycle**: Monthly, charged on the 1st.
- **Usage tracking**: Real-time via `/dashboard` and API (`GET /usage`).
- **Overages** (Pro): Soft limit — email notification at 80%, hard cap at 120%.
- **Downgrades**: Effective at end of billing cycle. Data beyond retention
  window is archived for 30 days, then deleted.
