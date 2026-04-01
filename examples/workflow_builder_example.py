"""Example: building a workflow with the fluent DSL.

Run with:
    python -m examples.workflow_builder_example
"""

import asyncio
import json

from flint_ai import AsyncOrchestratorClient, Node, Workflow


def build_code_review_pipeline() -> None:
    """Build a 4-node code-review pipeline and print the JSON output."""

    wf = (
        Workflow("code-review-pipeline")
        .add(Node("generate", agent="openai", prompt="Write code for {task}"))
        .add(
            Node("lint", agent="dummy", prompt="Lint the output")
            .depends_on("generate")
        )
        .add(
            Node("test", agent="dummy", prompt="Run tests")
            .depends_on("lint")
        )
        .add(
            Node("review", agent="claude", prompt="Review this code")
            .depends_on("test")
            .requires_approval()
            .with_retries(3)
            .dead_letter_on_failure()
        )
    )

    # Inspect the builder
    print("Builder repr:", wf)
    print()

    # Serialise to JSON (alias-keyed, ready for the API)
    print("Workflow JSON:")
    print(wf.to_json(indent=2))
    print()

    # Build returns a WorkflowDefinition pydantic model
    definition = wf.build()
    print(f"WorkflowDefinition id : {definition.id}")
    print(f"  nodes: {[n.id for n in definition.nodes]}")
    print(f"  edges: {[(e.from_node_id, e.to_node_id) for e in definition.edges]}")


async def submit_to_server() -> None:
    """(Optional) Submit the built workflow to a running orchestrator."""

    wf_def = (
        Workflow("code-review-pipeline")
        .add(Node("generate", agent="openai", prompt="Write code for {task}"))
        .add(Node("lint", agent="dummy", prompt="Lint the output").depends_on("generate"))
        .add(Node("test", agent="dummy", prompt="Run tests").depends_on("lint"))
        .add(
            Node("review", agent="claude", prompt="Review this code")
            .depends_on("test")
            .requires_approval()
            .with_retries(3)
            .dead_letter_on_failure()
        )
        .build()
    )

    async with AsyncOrchestratorClient("http://localhost:5156") as client:
        created = await client.create_workflow(wf_def)
        print(f"Created workflow: {created.id}")
        await client.start_workflow(created.id)
        print("Workflow started!")


if __name__ == "__main__":
    build_code_review_pipeline()

    # Uncomment the lines below to submit to a running orchestrator:
    # asyncio.run(submit_to_server())
