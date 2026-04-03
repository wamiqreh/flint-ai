from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

import typer
from rich import print_json
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from .client import AsyncOrchestratorClient

console = Console()

app = typer.Typer(help="Flint CLI — spark your agent workflows")
workflows_app = typer.Typer(help="Workflow commands")
app.add_typer(workflows_app, name="workflows")
plugins_app = typer.Typer(help="Plugin marketplace commands")
app.add_typer(plugins_app, name="plugins")

# ---------------------------------------------------------------------------
# Template enum
# ---------------------------------------------------------------------------

TEMPLATE_CHOICES = ["basic", "multi-agent", "fan-out", "openai-pr-reviewer"]

# ---------------------------------------------------------------------------
# Existing commands
# ---------------------------------------------------------------------------


@app.command()
def submit(
    agent: str = typer.Option(..., "--agent", "-a", help="Agent type"),
    prompt: str = typer.Option(..., "--prompt", "-p", help="Task prompt"),
    base_url: str = typer.Option("http://localhost:5156", "--base-url"),
) -> None:
    async def run() -> None:
        client = AsyncOrchestratorClient(base_url)
        try:
            task_id = await client.submit_task(agent, prompt)
            typer.echo(task_id)
        finally:
            await client.close()

    asyncio.run(run())


@app.command()
def status(
    task_id: str,
    base_url: str = typer.Option("http://localhost:5156", "--base-url"),
) -> None:
    async def run() -> None:
        client = AsyncOrchestratorClient(base_url)
        try:
            task = await client.get_task(task_id)
            print_json(data=task.model_dump())
        finally:
            await client.close()

    asyncio.run(run())


@workflows_app.command("list")
def list_workflows(
    base_url: str = typer.Option("http://localhost:5156", "--base-url"),
) -> None:
    async def run() -> None:
        client = AsyncOrchestratorClient(base_url)
        try:
            workflows = await client.list_workflows()
            print_json(data=[w.model_dump(by_alias=True) for w in workflows])
        finally:
            await client.close()

    asyncio.run(run())


@workflows_app.command("start")
def start_workflow(
    workflow_id: str,
    base_url: str = typer.Option("http://localhost:5156", "--base-url"),
) -> None:
    async def run() -> None:
        client = AsyncOrchestratorClient(base_url)
        try:
            await client.start_workflow(workflow_id)
            typer.echo(f"started:{workflow_id}")
        finally:
            await client.close()

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Embedded templates for `flint init`
# ---------------------------------------------------------------------------

INIT_DOCKER_COMPOSE = """\
services:
  flint:
    image: flintai/orchestrator:latest
    ports:
      - "5156:5156"
    environment:
      - USE_INMEMORY_QUEUE=true
      - ASPNETCORE_URLS=http://+:5156
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5156/health"]
      interval: 10s
      timeout: 5s
      retries: 3
"""

INIT_ENV = """\
FLINT_API_URL=http://localhost:5156
# Uncomment to use real AI agents:
# OPENAI_API_KEY=sk-...
# CLAUDE_API_KEY=sk-ant-...
"""

INIT_REQUIREMENTS = """\
flint-ai>=0.3.0
"""


def _init_readme(name: str) -> str:
    return f"""\
# {name}

Built with [Flint](https://github.com/flintai/flint) 🔥

## Quick Start

1. Start Flint:
   ```bash
   docker compose up -d
   ```

2. Install SDK:
   ```bash
   pip install flint-ai
   ```

3. Run your workflow:
   ```bash
   python workflow.py
   ```

4. Open Dashboard: http://localhost:5156/dashboard/
"""


def _init_workflow(template: str) -> str:
    if template == "openai-pr-reviewer":
        return '''\
"""Flint + OpenAI PR Reviewer — native adapter example."""
from flint_ai import OrchestratorClient, Workflow, Node, tool
from flint_ai.adapters.openai import FlintOpenAIAgent


@tool
def check_security(code: str) -> str:
    """Scan code for security vulnerabilities."""
    issues = []
    if "eval(" in code:
        issues.append("\\u26a0\\ufe0f eval() detected — code injection risk")
    if "password" in code.lower() and "hash" not in code.lower():
        issues.append("\\u26a0\\ufe0f Plaintext password detected")
    return "\\n".join(issues) if issues else "\\u2705 No security issues"


@tool
def count_lines(code: str) -> str:
    """Count lines of code."""
    lines = code.strip().split("\\n")
    return f"Total: {len(lines)}, Non-empty: {sum(1 for l in lines if l.strip())}"


# Define agents with natural OpenAI-style code
generator = FlintOpenAIAgent(
    name="code_generator",
    model="gpt-4o-mini",
    instructions="Generate clean Python code with type hints and docstrings.",
    temperature=0.3,
)

reviewer = FlintOpenAIAgent(
    name="code_reviewer",
    model="gpt-4o",
    instructions="Review code for correctness, performance, and security.",
    tools=[check_security, count_lines],
    temperature=0.1,
)

summarizer = FlintOpenAIAgent(
    name="summarizer",
    model="gpt-4o-mini",
    instructions="Summarize the review: score, top 3 findings, go/no-go.",
)

# Build DAG with adapter objects
wf = (Workflow("pr-review")
    .add(Node("generate", agent=generator, prompt="Write a FastAPI auth endpoint"))
    .add(Node("review", agent=reviewer, prompt="Review this code")
         .depends_on("generate").requires_approval().with_retries(2))
    .add(Node("summarize", agent=summarizer, prompt="Summarize findings")
         .depends_on("review"))
)

# One call: register agents + create workflow + start
client = OrchestratorClient()
workflow_id = client.deploy_workflow(wf)
print(f"\\U0001f525 Pipeline running: {workflow_id}")
print(f"\\U0001f4ca Dashboard: http://localhost:5156/dashboard/index.html")
'''
    if template == "multi-agent":
        return '''\
"""My first Flint workflow \u2014 multi-agent."""
from flint_ai.client import FlintClient
from flint_ai.workflow_builder import Workflow, Node

client = FlintClient("http://localhost:5156")

# Fan-out to multiple agents in parallel, then merge
wf = (Workflow("my-workflow")
    .add(Node("research", agent="dummy", prompt="Research the topic"))
    .add(Node("writer", agent="dummy", prompt="Write content about this"))
    .add(Node("critic", agent="dummy", prompt="Review and critique the content"))
    .add(Node("merge", agent="dummy", prompt="Combine all perspectives", depends_on=["research", "writer", "critic"]))
    .build())

# Deploy and run
client.create_workflow(wf)
run = client.start_workflow("my-workflow")
print(f"\U0001f525 Workflow running! Check: http://localhost:5156/dashboard/")
'''
    if template == "fan-out":
        return '''\
"""My first Flint workflow \u2014 fan-out split/merge."""
from flint_ai.client import FlintClient
from flint_ai.workflow_builder import Workflow, Node

client = FlintClient("http://localhost:5156")

# Split -> [chunk1, chunk2, chunk3] -> merge
wf = (Workflow("my-workflow")
    .add(Node("split", agent="dummy", prompt="Split the work into chunks"))
    .add(Node("chunk1", agent="dummy", prompt="Process chunk 1", depends_on=["split"]))
    .add(Node("chunk2", agent="dummy", prompt="Process chunk 2", depends_on=["split"]))
    .add(Node("chunk3", agent="dummy", prompt="Process chunk 3", depends_on=["split"]))
    .add(Node("merge", agent="dummy", prompt="Merge all results", depends_on=["chunk1", "chunk2", "chunk3"]))
    .build())

# Deploy and run
client.create_workflow(wf)
run = client.start_workflow("my-workflow")
print(f"\U0001f525 Workflow running! Check: http://localhost:5156/dashboard/")
'''
    # default: basic
    return '''\
"""My first Flint workflow."""
from flint_ai.client import FlintClient
from flint_ai.workflow_builder import Workflow, Node

client = FlintClient("http://localhost:5156")

# Build a simple 3-step workflow
wf = (Workflow("my-workflow")
    .add(Node("generate", agent="dummy", prompt="Generate an idea"))
    .add(Node("expand", agent="dummy", prompt="Expand on this", depends_on=["generate"]))
    .add(Node("summarize", agent="dummy", prompt="Write a summary", depends_on=["expand"]))
    .build())

# Deploy and run
client.create_workflow(wf)
run = client.start_workflow("my-workflow")
print(f"\U0001f525 Workflow running! Check: http://localhost:5156/dashboard/")
'''


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

_DOCKER_COMPOSE_FILENAMES = ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")


def _find_compose_file() -> Path | None:
    """Return the first compose file found in the cwd, or None."""
    for name in _DOCKER_COMPOSE_FILENAMES:
        p = Path.cwd() / name
        if p.exists():
            return p
    return None


def _docker_bin() -> str:
    """Return the docker binary path, or raise if not found."""
    docker = shutil.which("docker")
    if docker is None:
        console.print("[bold red]Error:[/] Docker is not installed or not on PATH.")
        console.print("Install Docker: https://docs.docker.com/get-docker/")
        raise typer.Exit(1)
    return docker


def _compose_cmd(docker: str) -> list[str]:
    """Return the base compose command (docker compose or docker-compose)."""
    # Prefer `docker compose` (V2); fall back to standalone docker-compose
    try:
        subprocess.run(
            [docker, "compose", "version"],
            capture_output=True,
            check=True,
        )
        return [docker, "compose"]
    except (subprocess.CalledProcessError, FileNotFoundError):
        dc = shutil.which("docker-compose")
        if dc:
            return [dc]
        console.print(
            "[bold red]Error:[/] Neither `docker compose` (V2) nor "
            "`docker-compose` found."
        )
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# flint init
# ---------------------------------------------------------------------------


@app.command()
def init(
    name: str = typer.Argument(..., help="Project name (used as directory name)"),
    template: str = typer.Option(
        "basic",
        "--template",
        "-t",
        help="Workflow template: basic, multi-agent, fan-out",
    ),
    force: bool = typer.Option(
        False, "--force", help="Overwrite existing directory"
    ),
) -> None:
    """Scaffold a new Flint project."""

    if template not in TEMPLATE_CHOICES:
        console.print(
            f"[bold red]Error:[/] Unknown template [bold]{template}[/]. "
            f"Choose from: {', '.join(TEMPLATE_CHOICES)}"
        )
        raise typer.Exit(1)

    project_dir = Path.cwd() / name

    if project_dir.exists():
        if not force:
            console.print(
                f"[bold yellow]Warning:[/] Directory [bold]{name}/[/] already exists.\n"
                f"Use [bold]--force[/] to overwrite."
            )
            raise typer.Exit(1)
        shutil.rmtree(project_dir)

    # --- create project tree ---
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Scaffolding project…", total=None)

        project_dir.mkdir(parents=True)

        (project_dir / "docker-compose.yml").write_text(
            INIT_DOCKER_COMPOSE, encoding="utf-8"
        )
        (project_dir / ".env").write_text(INIT_ENV, encoding="utf-8")
        (project_dir / "workflow.py").write_text(
            _init_workflow(template), encoding="utf-8"
        )
        (project_dir / "README.md").write_text(
            _init_readme(name), encoding="utf-8"
        )
        (project_dir / "requirements.txt").write_text(
            INIT_REQUIREMENTS, encoding="utf-8"
        )

        progress.update(task, description="Done!")

    console.print()
    console.print(
        Panel.fit(
            f"[bold green]✔ Project created:[/] [bold]{name}/[/]\n\n"
            f"  [dim]Files:[/]\n"
            f"    docker-compose.yml\n"
            f"    .env\n"
            f"    workflow.py          [dim]({template} template)[/]\n"
            f"    README.md\n"
            f"    requirements.txt\n\n"
            f"  [dim]Next steps:[/]\n"
            f"    cd {name}\n"
            f"    docker compose up -d\n"
            f"    pip install flint-ai\n"
            f"    python workflow.py",
            title="🔥 Flint",
            border_style="green",
        )
    )


# ---------------------------------------------------------------------------
# flint dev
# ---------------------------------------------------------------------------


@app.command()
def dev(
    stop: bool = typer.Option(False, "--stop", help="Stop the local orchestrator"),
    base_url: str = typer.Option("http://localhost:5156", "--base-url"),
) -> None:
    """Start (or stop) the local development orchestrator via Docker Compose."""

    docker = _docker_bin()
    compose = _compose_cmd(docker)
    compose_file = _find_compose_file()

    if compose_file is None:
        console.print(
            "[bold red]Error:[/] No docker-compose.yml found in the current directory.\n"
            "Run [bold]flint init[/] first, then cd into the project folder."
        )
        raise typer.Exit(1)

    if stop:
        console.print("[bold]Stopping orchestrator…[/]")
        subprocess.run([*compose, "down"], check=True)
        console.print("[bold green]✔ Orchestrator stopped.[/]")
        return

    # --- start ---
    console.print("[bold]Starting orchestrator…[/]")
    result = subprocess.run([*compose, "up", "-d", "--build"])
    if result.returncode != 0:
        console.print("[bold red]Error:[/] docker compose up failed.")
        raise typer.Exit(1)

    # --- health-check loop ---
    health_url = f"{base_url}/health"
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task(
            f"Waiting for health check at {health_url}…", total=None
        )
        healthy = False
        for _ in range(30):
            try:
                import urllib.request

                with urllib.request.urlopen(health_url, timeout=2) as resp:
                    if resp.status == 200:
                        healthy = True
                        break
            except Exception:
                pass
            time.sleep(2)
        progress.update(task, description="Health check complete.")

    if not healthy:
        console.print(
            f"[bold yellow]Warning:[/] Health check at {health_url} "
            "did not return 200 within 60 s.\n"
            "The containers may still be starting — check [bold]flint logs[/]."
        )
    else:
        console.print("[bold green]✔ Orchestrator is healthy![/]")

    console.print()
    console.print(
        Panel.fit(
            f"[bold green]Local orchestrator is running[/]\n\n"
            f"  API:       {base_url}\n"
            f"  Swagger:   {base_url}/swagger\n"
            f"  Dashboard: {base_url}/dashboard/\n"
            f"  Health:    {health_url}\n\n"
            f"  Stop with: [bold]flint dev --stop[/]",
            title="🔥 Flint Dev",
            border_style="green",
        )
    )


# ---------------------------------------------------------------------------
# flint dashboard
# ---------------------------------------------------------------------------


@app.command()
def dashboard(
    base_url: str = typer.Option("http://localhost:5156", "--base-url"),
) -> None:
    """Open the Flint dashboard in the default browser."""
    url = f"{base_url}/dashboard/"
    console.print(f"Opening [bold]{url}[/] …")
    webbrowser.open(url)


# ---------------------------------------------------------------------------
# flint logs
# ---------------------------------------------------------------------------


@app.command()
def logs(
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow log output"),
) -> None:
    """Show Docker Compose logs for the local orchestrator."""

    docker = _docker_bin()
    compose = _compose_cmd(docker)
    compose_file = _find_compose_file()

    if compose_file is None:
        console.print(
            "[bold red]Error:[/] No docker-compose.yml found in the current directory.\n"
            "Run [bold]flint init[/] first, then cd into the project folder."
        )
        raise typer.Exit(1)

    cmd = [*compose, "logs"]
    if follow:
        cmd.append("-f")

    subprocess.run(cmd)


# ---------------------------------------------------------------------------
# flint plugins
# ---------------------------------------------------------------------------

_DEFAULT_REGISTRY_URL = (
    "https://raw.githubusercontent.com/flintai/flint"
    "/main/plugins/registry.json"
)

_PLUGINS_DIR = Path.home() / ".flint" / "plugins"


def _load_registry(
    registry: str | None,
) -> dict:
    """Load the plugin registry from a URL, local file, or the bundled default."""
    import urllib.request

    # Explicit path or URL provided by the caller
    source = registry or os.environ.get("FLINT_PLUGIN_REGISTRY")

    # 1. Try local file (explicit or bundled fallback)
    if source and not source.startswith(("http://", "https://")):
        p = Path(source)
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))

    # 2. Try bundled registry.json shipped with the repo
    bundled = Path(__file__).resolve().parents[3] / "plugins" / "registry.json"
    if not source and bundled.is_file():
        return json.loads(bundled.read_text(encoding="utf-8"))

    # 3. Fetch from URL
    url = source if source and source.startswith(("http://", "https://")) else _DEFAULT_REGISTRY_URL
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception as exc:
        # Last-resort: try bundled even if a URL was given but failed
        if bundled.is_file():
            console.print(
                f"[yellow]Warning:[/] Could not fetch registry from {url}, "
                "using bundled registry.json"
            )
            return json.loads(bundled.read_text(encoding="utf-8"))
        console.print(f"[bold red]Error:[/] Failed to load plugin registry: {exc}")
        raise typer.Exit(1)


@plugins_app.command("list")
def plugins_list(
    registry: str | None = typer.Option(
        None, "--registry", "-r", help="Registry URL or local path"
    ),
    plugin_type: str | None = typer.Option(
        None, "--type", "-t", help="Filter by type (agent, template, middleware)"
    ),
) -> None:
    """List all available plugins from the registry."""
    data = _load_registry(registry)
    plugins = data.get("plugins", [])

    if plugin_type:
        plugins = [p for p in plugins if p.get("type") == plugin_type]

    if not plugins:
        console.print("[yellow]No plugins found.[/]")
        return

    from rich.table import Table

    table = Table(title="Flint Plugin Registry", show_lines=False)
    table.add_column("Name", style="bold cyan", no_wrap=True)
    table.add_column("Type", style="magenta")
    table.add_column("Version")
    table.add_column("Description")

    for p in plugins:
        table.add_row(
            p.get("name", ""),
            p.get("type", ""),
            p.get("version", ""),
            p.get("description", ""),
        )

    console.print(table)


@plugins_app.command("search")
def plugins_search(
    query: str = typer.Argument(..., help="Search term"),
    registry: str | None = typer.Option(
        None, "--registry", "-r", help="Registry URL or local path"
    ),
) -> None:
    """Search plugins by name, description, or tags."""
    data = _load_registry(registry)
    plugins = data.get("plugins", [])
    q = query.lower()

    matches = [
        p
        for p in plugins
        if q in p.get("name", "").lower()
        or q in p.get("description", "").lower()
        or any(q in tag.lower() for tag in p.get("tags", []))
    ]

    if not matches:
        console.print(f"[yellow]No plugins matching '{query}'.[/]")
        return

    from rich.table import Table

    table = Table(title=f"Search results for '{query}'", show_lines=False)
    table.add_column("Name", style="bold cyan", no_wrap=True)
    table.add_column("Type", style="magenta")
    table.add_column("Version")
    table.add_column("Description")

    for p in matches:
        table.add_row(
            p.get("name", ""),
            p.get("type", ""),
            p.get("version", ""),
            p.get("description", ""),
        )

    console.print(table)


@plugins_app.command("info")
def plugins_info(
    name: str = typer.Argument(..., help="Plugin name"),
    registry: str | None = typer.Option(
        None, "--registry", "-r", help="Registry URL or local path"
    ),
) -> None:
    """Show detailed information about a plugin."""
    data = _load_registry(registry)
    plugins = data.get("plugins", [])
    plugin = next((p for p in plugins if p.get("name") == name), None)

    if plugin is None:
        console.print(f"[bold red]Error:[/] Plugin '{name}' not found in registry.")
        raise typer.Exit(1)

    # Check if installed locally
    installed_path = _PLUGINS_DIR / name
    installed = installed_path.is_dir()

    from rich.table import Table

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Field", style="bold")
    table.add_column("Value")

    table.add_row("Name", plugin.get("name", ""))
    table.add_row("Type", plugin.get("type", ""))
    table.add_row("Version", plugin.get("version", ""))
    table.add_row("Description", plugin.get("description", ""))
    table.add_row("Author", plugin.get("author", ""))
    table.add_row("Repository", plugin.get("repository", ""))
    table.add_row("Tags", ", ".join(plugin.get("tags", [])))
    table.add_row(
        "Installed",
        f"[green]Yes[/] ({installed_path})" if installed else "[dim]No[/]",
    )

    console.print(Panel(table, title=f"🔌 {name}", border_style="cyan"))


@plugins_app.command("install")
def plugins_install(
    name: str = typer.Argument(..., help="Plugin name to install"),
    registry: str | None = typer.Option(
        None, "--registry", "-r", help="Registry URL or local path"
    ),
) -> None:
    """Install a plugin from the registry (clones its git repository)."""
    data = _load_registry(registry)
    plugins = data.get("plugins", [])
    plugin = next((p for p in plugins if p.get("name") == name), None)

    if plugin is None:
        console.print(f"[bold red]Error:[/] Plugin '{name}' not found in registry.")
        raise typer.Exit(1)

    repo_url = plugin.get("repository", "")
    if not repo_url:
        console.print(f"[bold red]Error:[/] Plugin '{name}' has no repository URL.")
        raise typer.Exit(1)

    dest = _PLUGINS_DIR / name

    if dest.is_dir():
        console.print(
            f"[yellow]Plugin '{name}' is already installed at {dest}.[/]\n"
            f"To reinstall, remove the directory first:\n"
            f"  rm -rf {dest}"
        )
        raise typer.Exit(1)

    # Ensure parent directory exists
    _PLUGINS_DIR.mkdir(parents=True, exist_ok=True)

    git_bin = shutil.which("git")
    if git_bin is None:
        console.print(
            "[bold red]Error:[/] Git is not installed or not on PATH.\n"
            "Install Git: https://git-scm.com/downloads"
        )
        raise typer.Exit(1)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task(
            f"Installing {name} from {repo_url}…", total=None
        )

        result = subprocess.run(
            [git_bin, "clone", "--depth", "1", repo_url, str(dest)],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            progress.update(task, description="Failed!")
            console.print(
                f"[bold red]Error:[/] git clone failed:\n{result.stderr.strip()}"
            )
            raise typer.Exit(1)

        # Install Python dependencies if plugin.json lists them
        manifest_path = dest / "plugin.json"
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            deps = manifest.get("dependencies", {})
            if deps:
                progress.update(task, description="Installing dependencies…")
                dep_specs = [
                    f"{pkg}{ver}" if ver else pkg for pkg, ver in deps.items()
                ]
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", *dep_specs],
                    capture_output=True,
                )

        progress.update(task, description="Done!")

    console.print(
        Panel.fit(
            f"[bold green]✔ Installed:[/] {name} v{plugin.get('version', '?')}\n"
            f"  Location: {dest}\n"
            f"  Type:     {plugin.get('type', '?')}",
            title="🔌 Plugin Installed",
            border_style="green",
        )
    )
