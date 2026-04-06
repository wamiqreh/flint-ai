import asyncio

from flint_ai import AsyncOrchestratorClient, LangChainOrchestratorRunnable


async def main() -> None:
    client = AsyncOrchestratorClient("http://localhost:5156")
    try:
        runnable = LangChainOrchestratorRunnable(client=client, agent_type="dummy")
        result = await runnable.ainvoke("Use LangChain adapter path")
        print(result.model_dump())
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
