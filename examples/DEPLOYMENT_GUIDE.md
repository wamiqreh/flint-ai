"""Quick Reference: Embedded vs Server Mode

Choose the right deployment mode for your use case.
"""

print("""
╔════════════════════════════════════════════════════════════════════════════╗
║                    FLINT DEPLOYMENT MODES COMPARISON                       ║
╚════════════════════════════════════════════════════════════════════════════╝

┌─ EMBEDDED MODE ──────────────────────────────────────────────────────────┐
│ Run Flint as a background thread in your Python app (like Hangfire)      │
│                                                                            │
│ ✓ PROS:                          │ ✗ CONS:                              │
│   • Zero setup                   │   • Only Python                      │
│   • Server + app in one process  │   • Single machine only              │
│   • Perfect for development      │   • State lost on restart            │
│   • Simpler debugging            │                                       │
│   • Use with Workflow DSL        │                                       │
│                                                                            │
│ CODE:                                                                      │
│   from flint_ai.server import FlintEngine, ServerConfig                   │
│                                                                            │
│   config = ServerConfig(port=5160)                                        │
│   engine = FlintEngine(config)                                            │
│   engine.start(blocking=False)  # ← Runs in background                   │
│                                                                            │
│   # Now use via HTTP:                                                     │
│   client = httpx.Client(base_url=engine.url)                              │
│   r = client.post("/tasks", json={...})                                   │
│                                                                            │
│ PERSISTENCE:                                                               │
│   Default: In-memory (state lost on restart)                              │
│   Optional: Add Redis + Postgres for persistence                          │
│                                                                            │
│ BEST FOR:                                                                  │
│   ✓ Development & testing                                                 │
│   ✓ Demos & POCs                                                          │
│   ✓ Local integration testing                                             │
│   ✓ Applications with integrated task queue                               │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘

┌─ SERVER MODE ────────────────────────────────────────────────────────────┐
│ Run Flint as a separate process (like Celery/RabbitMQ)                   │
│                                                                            │
│ ✓ PROS:                          │ ✗ CONS:                              │
│   • Scale across machines        │   • Separate process to manage       │
│   • Multi-language clients       │   • Network overhead                 │
│   • High availability            │   • More complex setup               │
│   • Persistent queues            │                                       │
│   • Multiple workers             │                                       │
│   • Production-ready             │                                       │
│                                                                            │
│ SETUP:                                                                     │
│   Terminal 1 - Start server:                                              │
│   $ python -m flint_ai.server.run --port 5160 \\                          │
│       --queue redis://localhost:6379 \\                                   │
│       --store postgres://localhost/flint_db \\                            │
│       --workers 4                                                          │
│                                                                            │
│   Terminal 2+ - Use from your app:                                        │
│   client = httpx.Client(base_url="http://localhost:5160")                │
│   r = client.post("/tasks", json={...})                                   │
│                                                                            │
│ PERSISTENCE:                                                               │
│   - Must use Redis (queue) + Postgres (store) for production              │
│   - Tasks survive server restarts                                         │
│   - Can share state across multiple servers                               │
│                                                                            │
│ BEST FOR:                                                                  │
│   ✓ Production deployments                                                │
│   ✓ Microservices architecture                                            │
│   ✓ Multi-language environments                                           │
│   ✓ Horizontal scaling                                                    │
│   ✓ High-availability requirements                                        │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘

┌─ RUNNING BOTH SIMULTANEOUSLY ────────────────────────────────────────────┐
│                                                                            │
│ You can run BOTH for development + testing:                               │
│                                                                            │
│ Terminal 1 - Server mode on port 5160:                                    │
│ $ python -m flint_ai.server.run --port 5160                               │
│                                                                            │
│ Terminal 2 - Your app with embedded mode on port 5161:                    │
│ from flint_ai.server import FlintEngine, ServerConfig                     │
│ engine = FlintEngine(ServerConfig(port=5161))                             │
│ engine.start(blocking=False)                                              │
│                                                                            │
│ Now you have:                                                              │
│   • http://localhost:5160/ui/  (Server mode)                              │
│   • http://localhost:5161/ui/  (Embedded mode)                            │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘

┌─ QUICK DECISION MATRIX ──────────────────────────────────────────────────┐
│                                                                            │
│ Question                           │ Embedded  │ Server  │ Both         │
│ ─────────────────────────────────────────────────────────────────────    │
│ Are you in development?            │   YES     │   -     │   YES       │
│ Do you need persistence?           │   NO      │   YES   │   BOTH      │
│ Is this for production?            │   NO      │   YES   │   -         │
│ Multiple machines?                 │   NO      │   YES   │   -         │
│ Simple demo/POC?                   │   YES     │   -     │   -         │
│ Need horizontal scaling?           │   NO      │   YES   │   -         │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘

EXAMPLES:

  1. Embedded mode (development):
     python examples/basics/embedded_demo.py
     python examples/basics/embedded_mode_guide.py

  2. Server mode (production):
     python examples/basics/server_mode_guide.py
     # Requires: python -m flint_ai.server.run

  3. Both with Workflow DSL:
     python examples/basics/demo.py  # Uses FlintOpenAIAgent (embedded mode)

  4. Multimodal cost tracking (embedded):
     python examples/usage_tracking/embedding_image_costs.py

═════════════════════════════════════════════════════════════════════════════
""")
