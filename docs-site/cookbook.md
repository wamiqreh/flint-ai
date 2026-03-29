# Cookbook / Recipes

Real-world workflow patterns you can copy-paste and adapt. Each recipe demonstrates a different DAG shape and orchestrator feature.

---

## Recipe 1: Code Generation Pipeline

### Use Case

You want an AI agent to generate code, then automatically lint it, run tests, get human sign-off, and deploy — all as a single pipeline. If tests fail, the test node retries before giving up.

### Architecture

```
generate-code → lint → run-tests → human-review → deploy
                       (retries=5)  (approval gate)
```

### Code

```python
from flint_ai import (
    OrchestratorClient,
    Workflow,
    Node,
)

# Build the pipeline
wf = (
    Workflow("code-gen-pipeline")
    .add(Node("generate-code", agent="openai",
              prompt="Write a Python function that {task_description}"))
    .add(Node("lint", agent="dummy",
              prompt="Run ruff/flake8 on the generated code and report issues")
         .depends_on("generate-code"))
    .add(Node("run-tests", agent="dummy",
              prompt="Execute the test suite against the generated code")
         .depends_on("lint")
         .with_retries(5))
    .add(Node("human-review", agent="dummy",
              prompt="Present code + test results to a reviewer for approval")
         .depends_on("run-tests")
         .requires_approval())
    .add(Node("deploy", agent="dummy",
              prompt="Deploy the approved code to the staging environment")
         .depends_on("human-review"))
    .build()
)

# Submit to the orchestrator
client = OrchestratorClient("http://localhost:5156")
client.create_workflow(wf)
client.start_workflow("code-gen-pipeline")
print("Pipeline started — waiting for human approval at 'human-review' node")
```

### Explanation

| Node | What It Does |
|---|---|
| `generate-code` | Calls OpenAI to produce source code from a task description. This is the entry node (no dependencies). |
| `lint` | A dummy agent simulating a linter. In production, swap for a real static-analysis agent. |
| `run-tests` | Runs the test suite. `.with_retries(5)` means if the tests fail (flaky tests, transient infra issues), the node retries up to 5 times before failing the workflow. |
| `human-review` | `.requires_approval()` pauses the workflow here. A human must call `POST /workflows/code-gen-pipeline/nodes/human-review/approve` to continue. |
| `deploy` | Only runs after human approval. Deploys the artifact to staging. |

!!! tip "Approving the gate"
    ```bash
    # Approve
    curl -X POST http://localhost:5156/workflows/code-gen-pipeline/nodes/human-review/approve

    # Or reject
    curl -X POST http://localhost:5156/workflows/code-gen-pipeline/nodes/human-review/reject
    ```

---

## Recipe 2: RAG Ingestion Pipeline

### Use Case

You're building a Retrieval-Augmented Generation system and need to scrape docs, chunk them, generate embeddings, and upsert into a vector database. If any step fails permanently, the task goes to the dead-letter queue for manual inspection.

### Architecture

```
scrape → chunk → embed → upsert-to-db
 (DLQ)   (DLQ)   (DLQ)     (DLQ)
```

### Code

```python
from flint_ai import Workflow, Node, OrchestratorClient

wf = (
    Workflow("rag-ingestion")
    .add(Node("scrape", agent="dummy",
              prompt="Scrape documentation from {source_url} and return raw text")
         .with_retries(3)
         .dead_letter_on_failure())
    .add(Node("chunk", agent="dummy",
              prompt="Split the scraped text into 512-token chunks with 50-token overlap")
         .depends_on("scrape")
         .with_retries(2)
         .dead_letter_on_failure())
    .add(Node("embed", agent="openai",
              prompt="Generate embeddings for each text chunk using text-embedding-3-small")
         .depends_on("chunk")
         .with_retries(3)
         .dead_letter_on_failure())
    .add(Node("upsert-to-db", agent="dummy",
              prompt="Upsert the embedding vectors into the Pinecone index {index_name}")
         .depends_on("embed")
         .with_retries(3)
         .dead_letter_on_failure())
    .build()
)

client = OrchestratorClient("http://localhost:5156")
client.create_workflow(wf)
client.start_workflow("rag-ingestion")
print("RAG ingestion pipeline started")
```

### Explanation

| Node | What It Does |
|---|---|
| `scrape` | Fetches raw content from a documentation URL. Retries handle transient HTTP errors. |
| `chunk` | Splits the scraped text into overlapping chunks suitable for embedding. |
| `embed` | Uses OpenAI's embedding model to vectorise each chunk. This is the most likely node to hit rate limits, so retries are important. |
| `upsert-to-db` | Writes vectors to the database. Dead-letter ensures partial failures are captured for replay. |

Every node uses `.dead_letter_on_failure()` — if a node exhausts all retries, the task is moved to the dead-letter queue instead of silently disappearing. You can inspect and replay dead-lettered tasks:

```bash
# View dead-lettered tasks
curl http://localhost:5156/dashboard/dlq | python -m json.tool
```

!!! note "Why dead-letter everything?"
    In data pipelines, silent failures are worse than loud ones. Dead-lettering guarantees you'll know when documents fail to ingest, so you can fix the source and replay.

---

## Recipe 3: Multi-Model Ensemble

### Use Case

You want to ask the same question to multiple LLMs in parallel, then merge and rank the responses. This fan-out/fan-in pattern lets you get diverse perspectives and pick the best answer.

### Architecture

```
             ┌→ ask-openai  ─┐
prompt-prep ─┤→ ask-claude   ├→ merge-and-rank
             └→ ask-copilot  ─┘
```

### Code

```python
from flint_ai import Workflow, Node, OrchestratorClient

wf = (
    Workflow("multi-model-ensemble")

    # Entry node: prepare and validate the prompt
    .add(Node("prompt-prep", agent="dummy",
              prompt="Validate and normalise the user question: {user_question}"))

    # Fan-out: ask three models in parallel
    .add(Node("ask-openai", agent="openai",
              prompt="Answer this question thoroughly: {user_question}")
         .depends_on("prompt-prep")
         .with_retries(2))
    .add(Node("ask-claude", agent="claude",
              prompt="Answer this question thoroughly: {user_question}")
         .depends_on("prompt-prep")
         .with_retries(2))
    .add(Node("ask-copilot", agent="copilot",
              prompt="Answer this question thoroughly: {user_question}")
         .depends_on("prompt-prep")
         .with_retries(2))

    # Fan-in: merge and rank all responses
    .add(Node("merge-and-rank", agent="openai",
              prompt="Compare these three answers and produce a ranked summary "
                     "with the best response first")
         .depends_on("ask-openai", "ask-claude", "ask-copilot"))
    .build()
)

client = OrchestratorClient("http://localhost:5156")
client.create_workflow(wf)
client.start_workflow("multi-model-ensemble")
print("Ensemble started — 3 models queried in parallel")
```

### Explanation

| Node | What It Does |
|---|---|
| `prompt-prep` | Sanitises and normalises the user's question. Acts as a single entry point. |
| `ask-openai` / `ask-claude` / `ask-copilot` | Three parallel branches. Each depends only on `prompt-prep`, so the orchestrator schedules them concurrently. Each has retries for transient API failures. |
| `merge-and-rank` | `.depends_on("ask-openai", "ask-claude", "ask-copilot")` — this node waits for **all three** to complete before running. It uses OpenAI to compare the answers and produce a ranked summary. |

!!! tip "Fan-out / Fan-in"
    The key pattern here is **multiple nodes depending on the same parent** (fan-out) and **one node depending on multiple parents** (fan-in). The orchestrator handles the synchronisation — `merge-and-rank` only fires when all three model responses are ready.

---

## Recipe 4: Customer Support Triage

### Use Case

Incoming support tickets are classified by an AI agent. Simple tickets get auto-responded to immediately. Complex tickets are escalated to a specialist agent and then require human review before sending the response.

### Architecture

```
classify → route ──┬→ auto-respond          (simple tickets)
                   └→ escalate → human-review → respond  (complex tickets)
```

### Code

```python
from flint_ai import Workflow, Node, OrchestratorClient

wf = (
    Workflow("support-triage")

    # Step 1: Classify the ticket
    .add(Node("classify", agent="openai",
              prompt="Classify this support ticket as 'simple' or 'complex': {ticket_body}"))

    # Step 2: Route based on classification
    .add(Node("route", agent="dummy",
              prompt="Read the classification result and forward to the correct branch")
         .depends_on("classify"))

    # Branch A: Auto-respond for simple tickets
    .add(Node("auto-respond", agent="openai",
              prompt="Draft a helpful response for this simple support ticket: {ticket_body}")
         .depends_on("route")
         .with_retries(2))

    # Branch B: Escalation path for complex tickets
    .add(Node("escalate", agent="claude",
              prompt="Research this complex issue and draft a detailed resolution: {ticket_body}")
         .depends_on("route")
         .with_retries(3))
    .add(Node("human-review", agent="dummy",
              prompt="Present the drafted resolution to a support manager for approval")
         .depends_on("escalate")
         .requires_approval())
    .add(Node("respond", agent="dummy",
              prompt="Send the approved resolution to the customer")
         .depends_on("human-review"))
    .build()
)

client = OrchestratorClient("http://localhost:5156")
client.create_workflow(wf)
client.start_workflow("support-triage")
print("Triage pipeline active — complex tickets require human approval")
```

### Explanation

| Node | What It Does |
|---|---|
| `classify` | Uses OpenAI to label the ticket as simple or complex. |
| `route` | A routing node that reads the classification and determines which branch to activate. Both downstream branches are defined as edges from `route`. |
| `auto-respond` | For simple tickets: generates a response directly and sends it. No human involved. |
| `escalate` | For complex tickets: uses Claude to research and draft a thorough resolution. Retries handle transient failures. |
| `human-review` | `.requires_approval()` pauses for a support manager to approve the drafted resolution. |
| `respond` | Sends the approved response to the customer. |

!!! note "Conditional branching"
    Both `auto-respond` and `escalate` depend on `route`. The routing logic inside the `route` agent decides which path the data actually flows through. You can also use the `Condition` field on `WorkflowEdge` for server-side conditional evaluation:

    ```python
    from flint_ai.models import WorkflowEdge

    # When building edges manually:
    WorkflowEdge(FromNodeId="route", ToNodeId="auto-respond", Condition="simple")
    WorkflowEdge(FromNodeId="route", ToNodeId="escalate", Condition="complex")
    ```

---

## Recipe 5: Content Publishing Pipeline

### Use Case

An editorial team uses AI to draft articles, but every piece must pass through human review and explicit approval before it gets formatted and published. This is a classic human-in-the-loop workflow.

### Architecture

```
draft → review → approve → format → publish
         (AI)   (human)    (AI)     (agent)
```

### Code

```python
from flint_ai import Workflow, Node, OrchestratorClient

wf = (
    Workflow("content-publishing")
    .add(Node("draft", agent="openai",
              prompt="Write a 1000-word blog post about {topic}. "
                     "Use an engaging tone and include code examples where relevant."))
    .add(Node("review", agent="claude",
              prompt="Review this article for factual accuracy, grammar, and tone. "
                     "Return a list of suggested edits.")
         .depends_on("draft"))
    .add(Node("approve", agent="dummy",
              prompt="Present the article and review comments to the editorial team")
         .depends_on("review")
         .requires_approval())
    .add(Node("format", agent="dummy",
              prompt="Convert the approved article to HTML with proper headings, "
                     "syntax-highlighted code blocks, and meta tags")
         .depends_on("approve"))
    .add(Node("publish", agent="dummy",
              prompt="Publish the formatted article to the CMS at {publish_url}")
         .depends_on("format")
         .with_retries(3)
         .dead_letter_on_failure())
    .build()
)

client = OrchestratorClient("http://localhost:5156")
client.create_workflow(wf)
client.start_workflow("content-publishing")
print("Publishing pipeline started — article will pause at 'approve' for sign-off")

# Check workflow progress
nodes = client.get_workflow_nodes("content-publishing")
for node in nodes:
    print(f"  {node['Id']}: {node.get('State', 'pending')}")
```

### Explanation

| Node | What It Does |
|---|---|
| `draft` | OpenAI generates the initial article. The entry point of the pipeline. |
| `review` | Claude reviews the draft for accuracy and style. A different model provides independent editorial oversight. |
| `approve` | `.requires_approval()` pauses the workflow. The editorial team reads the draft + review notes and decides whether to proceed, request changes, or kill the article. |
| `format` | Converts the approved markdown into publish-ready HTML. Only runs after explicit human approval. |
| `publish` | Pushes to the CMS. `.with_retries(3)` handles transient CMS API errors. `.dead_letter_on_failure()` ensures a failed publish doesn't disappear silently — the team can inspect and retry from the DLQ. |

!!! tip "Human-in-the-loop pattern"
    The `approve` node is the safety gate. Nothing downstream of it executes until a human explicitly approves:

    ```bash
    curl -X POST http://localhost:5156/workflows/content-publishing/nodes/approve/approve
    ```

    This pattern is essential for any workflow where AI-generated content must be reviewed before it reaches end users.

---

## Recipe 6: Batch Document Processing (ETL)

### Use Case

You have a batch of documents that need to go through an extract-transform-load pipeline. Each step might fail (corrupt files, validation errors, schema mismatches), so every node has retries and dead-letter protection.

### Architecture

```
ingest → extract → validate → transform → load
 (DLQ)    (DLQ)     (DLQ)      (DLQ)     (DLQ)
          retry=3   retry=2    retry=3   retry=5
```

### Code

```python
from flint_ai import Workflow, Node, OrchestratorClient

wf = (
    Workflow("document-etl")
    .add(Node("ingest", agent="dummy",
              prompt="Fetch documents from {source_bucket} and stage them for processing")
         .with_retries(3)
         .dead_letter_on_failure()
         .with_metadata(source="s3", batch_size=100))
    .add(Node("extract", agent="openai",
              prompt="Extract structured fields (title, date, author, body) "
                     "from each raw document using GPT-4")
         .depends_on("ingest")
         .with_retries(3)
         .dead_letter_on_failure())
    .add(Node("validate", agent="dummy",
              prompt="Validate extracted fields against the schema: "
                     "title (string, required), date (ISO 8601), author (string), "
                     "body (string, min 100 chars)")
         .depends_on("extract")
         .with_retries(2)
         .dead_letter_on_failure())
    .add(Node("transform", agent="dummy",
              prompt="Normalise dates to UTC, clean HTML from body, "
                     "generate document IDs, and prepare the insert payload")
         .depends_on("validate")
         .with_retries(3)
         .dead_letter_on_failure())
    .add(Node("load", agent="dummy",
              prompt="Bulk-insert the transformed documents into {target_database}")
         .depends_on("transform")
         .with_retries(5)
         .dead_letter_on_failure()
         .with_metadata(target="postgresql", table="documents"))
    .build()
)

client = OrchestratorClient("http://localhost:5156")
client.create_workflow(wf)
client.start_workflow("document-etl")
print("ETL pipeline started")

# Monitor the pipeline
nodes = client.get_workflow_nodes("document-etl")
for node in nodes:
    print(f"  {node['Id']}: {node.get('State', 'pending')}")
```

### Explanation

| Node | What It Does |
|---|---|
| `ingest` | Pulls raw documents from an S3 bucket. `.with_metadata()` attaches operational context (source system, batch size) that downstream agents or monitoring tools can read. |
| `extract` | Uses OpenAI to parse unstructured documents into structured fields. This is the most compute-intensive step. |
| `validate` | Checks that extracted data matches the expected schema. Fewer retries here because validation failures are usually deterministic — if a document is malformed, retrying won't help. |
| `transform` | Normalises and cleans the data for insertion. |
| `load` | Bulk-inserts into PostgreSQL. Has the most retries (5) because database transient errors (connection resets, lock timeouts) are common in batch writes. |

!!! note "DLQ as a safety net"
    Every node in this pipeline uses `.dead_letter_on_failure()`. This means:

    - If `extract` fails on a corrupt PDF, that task goes to the DLQ — but the pipeline definition remains intact for the next batch.
    - You can inspect dead-lettered tasks at `GET /dashboard/dlq` and replay them after fixing the issue.
    - This is the ETL equivalent of an error table — nothing is silently dropped.

---

## Pattern Summary

| Recipe | DAG Shape | Key Features |
|---|---|---|
| **Code Generation** | Linear chain | Human approval gate, retries on flaky step |
| **RAG Ingestion** | Linear chain | Dead-letter on every node, different agent types |
| **Multi-Model Ensemble** | Fan-out / Fan-in | Parallel branches, multi-dependency join |
| **Customer Support Triage** | Conditional branching | Routing node, mixed auto/human paths |
| **Content Publishing** | Linear with gate | Human-in-the-loop, multi-model review |
| **Batch Document ETL** | Linear chain | Retries + DLQ on every node, metadata |

---

## Tips

- **Start with `dummy` agents** during development — swap to `openai`, `claude`, or `copilot` when you're ready for real AI.
- **Use `.with_retries()`** generously on nodes that call external APIs. Transient failures are normal.
- **Use `.dead_letter_on_failure()`** on any node where silent failure would be costly.
- **Use `.requires_approval()`** before any irreversible action (deploy, publish, send email).
- **Fan-out/fan-in** works by having multiple nodes share the same parent (`depends_on`) and a single node depend on all of them.

## What's Next?

- **[Quickstart](getting-started.md)** — Set up the server and run your first task
- **[Python SDK Reference](python-sdk.md)** — Full API docs for the client, workflow builder, and models
- **[Architecture](architecture.md)** — How the orchestrator engine executes DAGs
