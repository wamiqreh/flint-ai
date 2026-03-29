import asyncio

from flint_ai import AsyncOrchestratorClient


async def main() -> None:
    client = AsyncOrchestratorClient("http://localhost:5156")
    try:
        ids = []
        for i in range(10):
            task_id = await client.submit_task("dummy", f"Batch task {i}")
            ids.append(task_id)

        for task_id in ids:
            task = await client.wait_for_task(task_id)
            print(task_id, task.state)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
