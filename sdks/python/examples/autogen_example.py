"""Example: Using Flint with AutoGen.

Prerequisites::

    pip install 'flint-ai[autogen]'

Make sure the orchestrator server is running on http://localhost:5156.
"""

from autogen import ConversableAgent

from flint_ai.autogen_adapter import OrchestratorAgent

# ── Create orchestrator-backed agent ───────────────────────────────────────

orch = OrchestratorAgent(
    name="orchestrator",
    base_url="http://localhost:5156",
    agent_type="claude",
    system_message="You are a helpful coding assistant.",
)

# ── Create a local user-proxy agent ────────────────────────────────────────

user = ConversableAgent(
    name="user",
    human_input_mode="NEVER",
    max_consecutive_auto_reply=0,
    llm_config=False,
)

# ── Option 1: Two-agent conversation via AutoGen ---------------------------

if __name__ == "__main__":
    # The user proxy initiates a chat with the orchestrator agent.
    user.initiate_chat(
        orch.agent,
        message="Write a Python function that merges two sorted lists.",
    )

    # ── Option 2: Direct (non-AutoGen-loop) usage --------------------------

    reply = orch.generate_reply("Explain the difference between a list and a tuple in Python.")
    print("\n── Direct Reply ──")
    print(reply)
