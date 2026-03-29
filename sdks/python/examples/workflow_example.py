import asyncio

from flint_ai import (
    AsyncOrchestratorClient,
    WorkflowDefinition,
    WorkflowEdge,
    WorkflowNode,
)


async def main() -> None:
    client = AsyncOrchestratorClient("http://localhost:5156")
    try:
        workflow = WorkflowDefinition(
            Id="wf-python-example",
            Nodes=[
                WorkflowNode(Id="n1", AgentType="dummy", PromptTemplate="Step 1"),
                WorkflowNode(Id="n2", AgentType="dummy", PromptTemplate="Step 2"),
            ],
            Edges=[WorkflowEdge(FromNodeId="n1", ToNodeId="n2")],
        )
        created = await client.create_workflow(workflow)
        await client.start_workflow(created.id)
        nodes = await client.get_workflow_nodes(created.id)
        print(nodes)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
