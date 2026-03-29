import asyncio

from flint_ai import AsyncOrchestratorClient


async def main() -> None:
    client = AsyncOrchestratorClient("http://localhost:5156")
    try:
        task_id = await client.submit_task("dummy", "Stream this task until completion")
        async for update in client.stream_task(task_id):
            print(update.model_dump())
            if update.state in {"Succeeded", "Failed", "DeadLetter"}:
                break
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
