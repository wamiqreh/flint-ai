# 📄 Document Summarizer

A fan-out / fan-in workflow that splits a document into chunks, summarizes each
chunk in parallel, then merges the results — demonstrating Flint's parallel
execution and map-reduce pattern.

```
                    ┌─────────┐
               ┌───▶│ chunk-1 │───┐
               │    └─────────┘   │
┌───────┐      │    ┌─────────┐   │    ┌───────┐
│ split  │─────┼───▶│ chunk-2 │───┼───▶│ merge │
└───────┘      │    └─────────┘   │    └───────┘
               │    ┌─────────┐   │
               └───▶│ chunk-3 │───┘
                    └─────────┘
```

## What It Does

1. **split** — Breaks a long document into 3 logical sections.
2. **chunk-1 / chunk-2 / chunk-3** — Each chunk is summarized by a separate
   agent running **in parallel**.
3. **merge** — Combines all three summaries into a single coherent document
   summary.

This pattern scales to any number of parallel workers and is ideal for
large-document processing, batch analysis, or any map-reduce workload.

## Prerequisites

- Flint running locally: `docker compose -f docker-compose.dev.yml up -d`
- Python 3.10+: `pip install flint-ai`

## Run

```bash
python summarize.py
```

## What Happens

1. The script builds a 5-node DAG with the fan-out / fan-in topology.
2. After submission, `split` runs first.
3. When `split` completes, `chunk-1`, `chunk-2`, and `chunk-3` execute
   **concurrently** — you'll see them start at roughly the same time.
4. Once all three chunks finish, `merge` runs to produce the final summary.
5. Results are printed to the console with timing info.

## Try in the Visual Editor

1. Open **http://localhost:5156/editor/**
2. Click **Import JSON**
3. Load `workflow.json`
4. Click **Deploy**
