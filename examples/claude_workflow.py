"""Basic Claude workflow example.

This example shows how to use Flint with Anthropic's Claude models.
No API keys required for this example — it uses inline mode.

Run: ANTHROPIC_API_KEY=your-key python examples/claude_workflow.py
"""

import asyncio

from flint_ai import Workflow, Node
from flint_ai.adapters.anthropic import FlintAnthropicAgent
from flint_ai.adapters.openai import tool


@tool
def fetch_weather(city: str) -> str:
    """Fetch current weather for a city.
    
    Args:
        city: The city name
    
    Returns:
        Weather description for the city
    """
    weather_data = {
        "New York": "Sunny, 72°F",
        "London": "Rainy, 55°F",
        "Tokyo": "Clear, 68°F",
        "Sydney": "Warm, 80°F",
    }
    return weather_data.get(city, "Unknown location")


async def main():
    """Run a simple Claude workflow."""
    agent = FlintAnthropicAgent(
        name="weather_assistant",
        model="claude-3-5-sonnet-20241022",
        instructions="You are a helpful weather assistant. Use the fetch_weather tool to get weather information.",
        tools=[fetch_weather],
        temperature=0.7,
    )

    workflow = (
        Workflow("weather-workflow")
        .add(
            Node(
                "get_weather",
                agent=agent,
                prompt="What's the weather like in London and Tokyo?",
            )
        )
        .build()
    )

    print("Running Claude workflow...")
    print("=" * 60)

    result = await workflow.run()

    print("Result:")
    print(result["output"])
    print("\nCost Breakdown:")
    if result.get("cost"):
        cost = result["cost"]
        print(f"  Model: {cost['model']}")
        print(f"  Prompt tokens: {cost['prompt_tokens']}")
        print(f"  Completion tokens: {cost['completion_tokens']}")
        print(f"  Total cost: ${cost['total_cost_usd']:.6f}")


if __name__ == "__main__":
    asyncio.run(main())
