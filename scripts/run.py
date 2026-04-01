#!/usr/bin/env python3
"""Flint example runner — run any example in embedded or client-server mode.

Usage:
    # Embedded mode (default) — server starts automatically inside your process:
    python scripts/run.py examples/demo.py

    # Client-server mode — starts a standalone server, then runs the example:
    python scripts/run.py examples/demo.py --mode server

    # Just start the server (no example):
    python scripts/run.py --server-only

    # List available examples:
    python scripts/run.py --list
"""

import argparse
import os
import subprocess
import sys
import signal
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = ROOT / "examples"


def list_examples():
    """Print all available examples."""
    print("\n🔥 Flint — Available Examples\n")
    for f in sorted(EXAMPLES_DIR.glob("*.py")):
        # Read first docstring line
        desc = ""
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith('"""') or line.startswith("'''"):
                    desc = line.strip('"').strip("'").strip()
                    if not desc:
                        # multiline docstring — grab next line
                        desc = next(fh, "").strip().strip('"').strip("'")
                    break
        print(f"  {f.name:<30} {desc}")
    print()


def start_server(port: int = 5156, redis: str = "", postgres: str = ""):
    """Start the Flint server as a separate process."""
    cmd = [sys.executable, "-m", "flint_ai.server", "--host", "0.0.0.0", "--port", str(port)]
    if redis:
        cmd += ["--redis", redis]
    if postgres:
        cmd += ["--postgres", postgres]

    print(f"🚀 Starting Flint server on port {port}...")
    proc = subprocess.Popen(
        cmd, cwd=str(ROOT),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )

    # Wait for server to be ready
    import urllib.request
    for _ in range(30):
        try:
            urllib.request.urlopen(f"http://localhost:{port}/health", timeout=1)
            print(f"✅ Server ready at http://localhost:{port}")
            print(f"   Dashboard: http://localhost:{port}/ui/")
            print(f"   API docs:  http://localhost:{port}/docs")
            return proc
        except Exception:
            time.sleep(1)

    print("❌ Server failed to start. Output:")
    proc.terminate()
    out, _ = proc.communicate(timeout=5)
    print(out)
    sys.exit(1)


def run_example(example_path: str, mode: str, port: int):
    """Run an example file."""
    path = Path(example_path)
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        # Try looking in examples dir
        path = EXAMPLES_DIR / example_path
    if not path.exists():
        print(f"❌ Example not found: {example_path}")
        print(f"   Run with --list to see available examples.")
        sys.exit(1)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)

    if mode == "embedded":
        print(f"\n🔥 Running {path.name} (embedded mode — server starts automatically)\n")
        result = subprocess.run([sys.executable, str(path)], cwd=str(ROOT), env=env)
        return result.returncode
    else:
        print(f"\n🔥 Running {path.name} (client-server mode)\n")
        env["FLINT_SERVER_URL"] = f"http://localhost:{port}"
        result = subprocess.run([sys.executable, str(path)], cwd=str(ROOT), env=env)
        return result.returncode


def main():
    parser = argparse.ArgumentParser(
        description="Flint example runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  embedded  (default) Server starts automatically inside the example process.
                      No setup needed — just run and it works.

  server              Starts a standalone Flint server first, then runs the
                      example as a client connecting to it. Useful for:
                      - Viewing the dashboard while the example runs
                      - Running multiple examples against the same server
                      - Production-like testing

Examples:
  python scripts/run.py examples/demo.py
  python scripts/run.py examples/openai_workflow.py --mode server
  python scripts/run.py --server-only --port 8080
  python scripts/run.py --list
        """,
    )
    parser.add_argument("example", nargs="?", help="Path to example file")
    parser.add_argument("--mode", choices=["embedded", "server"], default="embedded",
                        help="Run mode (default: embedded)")
    parser.add_argument("--port", type=int, default=5156, help="Server port (default: 5156)")
    parser.add_argument("--redis", default="", help="Redis URL (optional)")
    parser.add_argument("--postgres", default="", help="Postgres URL (optional)")
    parser.add_argument("--list", action="store_true", help="List available examples")
    parser.add_argument("--server-only", action="store_true", help="Start server only (no example)")

    args = parser.parse_args()

    if args.list:
        list_examples()
        return

    server_proc = None

    if args.server_only:
        proc = start_server(args.port, args.redis, args.postgres)
        print("\nPress Ctrl+C to stop the server.")
        try:
            proc.wait()
        except KeyboardInterrupt:
            proc.terminate()
            print("\n🛑 Server stopped.")
        return

    if not args.example:
        parser.print_help()
        return

    try:
        if args.mode == "server":
            server_proc = start_server(args.port, args.redis, args.postgres)
            print()

        rc = run_example(args.example, args.mode, args.port)
        sys.exit(rc)

    except KeyboardInterrupt:
        print("\n🛑 Interrupted.")
    finally:
        if server_proc:
            print("🛑 Stopping server...")
            server_proc.terminate()
            try:
                server_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server_proc.kill()
            print("   Server stopped.")


if __name__ == "__main__":
    main()
