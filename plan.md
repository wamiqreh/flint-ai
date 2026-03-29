# Flint — Project Plan

## Completed (v0.2.0)

### Core Runtime
- .NET 10 runtime with ASP.NET Core Minimal APIs
- Queue-driven task execution (In-memory, Redis Streams)
- DAG workflow engine with retries, DLQ, human approval
- Agent adapters: Dummy, OpenAI, Claude, Copilot
- PostgreSQL + in-memory persistence
- Prometheus metrics, Serilog logging, OpenTelemetry tracing

### SDKs & Integrations
- Python SDK v0.2.0: async/sync clients, retry, typed errors, workflow builder DSL, CLI (aqo init/dev/submit/plugins), LangChain/CrewAI/AutoGen/FastAPI adapters
- TypeScript SDK v0.1.0: typed client, workflow builder, SSE/WebSocket streaming, Vercel AI/Express/Next.js adapters  
- C# SDK v0.2.0: typed client, workflow builder, NuGet-ready

### Developer Experience
- Visual DAG editor (/editor/)
- Monitoring dashboard (/dashboard/)
- Docker Compose: dev/prod/monitoring
- CLI scaffolding (aqo init, aqo dev)
- Plugin system with registry

### Infrastructure
- GitHub Actions CI/CD (build, test, Docker publish, PyPI publish)
- Kubernetes manifests + Helm chart + HPA/PDB/Ingress
- Terraform cloud scaffolding (AWS ECS/Redis/Postgres)
- Benchmark suite

### Community
- CONTRIBUTING.md, Code of Conduct
- Issue templates, PR template, Discussion templates
- Blog posts, content calendar
- Branding research (recommended: "Flint")

## Next Phase: Production Hardening & Launch

### Phase 1: Rebrand to Flint (2 weeks)
- Secure package names on PyPI/npm/NuGet/Docker Hub
- Rename CLI from `aqo` to `flint`
- Update all imports, docs, references
- Publish deprecation notice on old packages
- New logo and brand assets

### Phase 2: Production Hardening (4 weeks)  
- JWT/OIDC authentication (replace shared API key)
- RBAC with per-tenant isolation
- Complete PostgresWorkflowStore with migrations
- Real Kafka adapter (consumer groups)
- Real SQS adapter
- Circuit breakers for agent API calls
- gRPC API (compile and serve task.proto)
- Agent streaming (provider-native SSE)

### Phase 3: Launch & Growth (4 weeks)
- Publish Python SDK to PyPI
- Publish TypeScript SDK to npm
- Publish C# SDK to NuGet
- Publish Docker image to GHCR
- Deploy docs site (MkDocs Material on GitHub Pages or Vercel)
- Write launch blog post: "Introducing Flint"
- Submit to Hacker News, Reddit r/MachineLearning, r/LocalLLaMA
- Launch Discord server
- Tweet/post launch thread

### Phase 4: SaaS Hosted Tier (8 weeks)
- Deploy free tier on AWS (Terraform)
- Multi-tenant API with rate limiting
- GitHub OAuth signup
- Usage dashboard
- Billing integration (Stripe) for Pro/Enterprise tiers
- Landing page / marketing site

### Phase 5: Ecosystem Growth (ongoing)
- Community plugin contributions (Gemini, Ollama, Mistral, Groq, Together)
- Workflow template gallery (20+ templates)
- Conference talks (PyCon, KubeCon, AI Engineer Summit)
- Case studies and benchmarks
- Grafana dashboard templates
- VS Code extension (workflow editor)
- Mobile dashboard app

## Key Metrics to Track
| Metric | 3-month Target | 6-month Target |
|---|---|---|
| PyPI weekly downloads | 500 | 2,000 |
| npm weekly downloads | 200 | 1,000 |
| GitHub stars | 500 | 2,500 |
| Docker pulls | 1,000 | 10,000 |
| Discord members | 100 | 500 |
| Community plugins | 5 | 15 |

## Decision Log
- **Name**: Flint (recommended). Alternatives: Aqo, Convoy. Final decision pending registry availability check.
- **Primary SDK**: Python (largest AI dev audience)
- **Cloud provider**: AWS (Terraform ready). Azure/GCP as fast-follow.
- **Auth strategy**: API key (current) → JWT/OIDC (next) → OAuth + RBAC (SaaS)
