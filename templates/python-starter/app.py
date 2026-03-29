import asyncio

from flint_ai import AsyncOrchestratorClient


async def main() -> None:
    client = AsyncOrchestratorClient("http://localhost:5156")
    try:
        task_id = await client.submit_task("dummy", "hello from python starter template")
        task = await client.wait_for_task(task_id)
        print(task.model_dump())
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
