"""
Flint + Claude (Anthropic) Agent Integration Example
=====================================================

This shows how to use Claude as a real coding/reasoning agent with Flint.
Claude supports tool use, multi-turn conversations, and complex reasoning.

Unlike the built-in ClaudeAgent (simple prompt→response), this runs Claude
as a full agent with tools via Flint's webhook pattern.

Setup:
  pip install anthropic fastapi uvicorn

Architecture:
  Flint (orchestrator) → webhook POST → Your Claude agent service
                       ← JSON response ←
"""

from fastapi import FastAPI, Request
from anthropic import Anthropic
import json
import uvicorn

app = FastAPI()
client = Anthropic()  # Uses ANTHROPIC_API_KEY env var

# ── Tools that Claude can use ────────────────────────────────────

tools = [
    {
        "name": "read_file",
        "description": "Read contents of a file",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to read"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "write_file",
        "description": "Write contents to a file",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"}
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "run_command",
        "description": "Execute a shell command",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string"}
            },
            "required": ["command"]
        }
    },
    {
        "name": "search_code",
        "description": "Search codebase for a pattern",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "path": {"type": "string", "description": "Directory to search in"}
            },
            "required": ["pattern"]
        }
    }
]

def execute_tool(name: str, input_data: dict) -> str:
    """Execute a tool and return the result."""
    import subprocess, os

    if name == "read_file":
        try:
            with open(input_data["path"]) as f:
                return f.read()
        except Exception as e:
            return f"Error: {e}"

    elif name == "write_file":
        try:
            os.makedirs(os.path.dirname(input_data["path"]), exist_ok=True)
            with open(input_data["path"], "w") as f:
                f.write(input_data["content"])
            return f"Written {len(input_data['content'])} chars to {input_data['path']}"
        except Exception as e:
            return f"Error: {e}"

    elif name == "run_command":
        try:
            result = subprocess.run(
                input_data["command"], shell=True,
                capture_output=True, text=True, timeout=30
            )
            return f"exit={result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        except Exception as e:
            return f"Error: {e}"

    elif name == "search_code":
        try:
            path = input_data.get("path", ".")
            result = subprocess.run(
                ["grep", "-rn", input_data["pattern"], path],
                capture_output=True, text=True, timeout=10
            )
            return result.stdout[:5000] or "No matches found"
        except Exception as e:
            return f"Error: {e}"

    return f"Unknown tool: {name}"


# ── Claude agent loop (multi-turn with tool use) ─────────────────

async def run_claude_agent(prompt: str, max_turns: int = 10) -> str:
    """Run Claude as a full agent with tool use in a loop."""
    messages = [{"role": "user", "content": prompt}]

    for turn in range(max_turns):
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system="You are an expert coding agent. Use your tools to accomplish tasks autonomously. "
                   "Think step by step, use tools as needed, and provide a clear final answer.",
            tools=tools,
            messages=messages,
        )

        # If Claude wants to use tools, execute them and continue
        if response.stop_reason == "tool_use":
            # Add Claude's response (with tool_use blocks)
            messages.append({"role": "assistant", "content": response.content})

            # Execute each tool call and build tool_result blocks
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result
                    })

            messages.append({"role": "user", "content": tool_results})
            continue

        # Claude is done — extract text response
        text_parts = [b.text for b in response.content if hasattr(b, "text")]
        return "\n".join(text_parts)

    return "Agent reached max turns without completing"


# ── Webhook endpoints ────────────────────────────────────────────

@app.post("/agents/claude-coder")
async def claude_coder(request: Request):
    """Claude as a coding agent — reads files, writes code, runs tests."""
    body = await request.json()
    prompt = body.get("prompt", "")
    task_id = body.get("task_id", "")

    output = await run_claude_agent(prompt)

    return {
        "task_id": task_id,
        "output": output,
        "success": True,
    }

@app.post("/agents/claude-reviewer")
async def claude_reviewer(request: Request):
    """Claude as a code reviewer — reads code and provides feedback."""
    body = await request.json()
    prompt = f"Review this code and provide actionable feedback:\n\n{body.get('prompt', '')}"
    task_id = body.get("task_id", "")

    output = await run_claude_agent(prompt, max_turns=5)

    return {
        "task_id": task_id,
        "output": output,
        "success": True,
    }


if __name__ == "__main__":
    print("🤖 Starting Claude Agent service on http://localhost:8001")
    print("   POST /agents/claude-coder    — Full coding agent with tool use")
    print("   POST /agents/claude-reviewer — Code review agent")
    print()
    print("Register with Flint:")
    print('  curl -X POST http://localhost:5156/agents/register -H "Content-Type: application/json" \\')
    print('    -d \'{"name":"claude-coder","url":"http://localhost:8001/agents/claude-coder"}\'')
    uvicorn.run(app, host="0.0.0.0", port=8001)
