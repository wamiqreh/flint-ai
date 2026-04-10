"""Claude vision example — analyze images with Anthropic's vision capabilities.

This example demonstrates how to use Claude with vision to analyze images.

Note: This is a placeholder example structure. To use real image analysis:
1. Install: pip install anthropic
2. Set ANTHROPIC_API_KEY environment variable
3. Update image_data with actual base64-encoded images or URLs

The FlintAnthropicAgent currently supports:
- Text input with tool calling
- Vision through Anthropic's message API (image_content blocks)
- Custom cost tracking for vision tokens

For production use with vision:
- Pass image content as base64 in messages
- Claude automatically counts image tokens
- Costs are calculated via FlintCostTracker.calculate_vision()
"""

import asyncio
import base64
from pathlib import Path

from flint_ai import Workflow, Node
from flint_ai.adapters.anthropic import FlintAnthropicAgent
from flint_ai.adapters.core.cost_tracker import FlintCostTracker
from flint_ai.adapters.openai import tool


@tool
def extract_metadata(content: str) -> str:
    """Extract structured metadata from image analysis.
    
    Args:
        content: The analysis text
    
    Returns:
        Structured metadata
    """
    return f"Extracted metadata: {content[:50]}..."


def encode_image_to_base64(image_path: str) -> str:
    """Encode an image file to base64 for API transmission.
    
    Args:
        image_path: Path to the image file
    
    Returns:
        Base64-encoded image data
    """
    with open(image_path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


async def main():
    """Run Claude vision analysis workflow."""
    
    # Initialize cost tracker with vision support
    cost_tracker = FlintCostTracker()
    
    agent = FlintAnthropicAgent(
        name="vision_analyzer",
        model="claude-3-5-sonnet-20241022",
        instructions=(
            "You are an expert image analyst. Analyze the provided image in detail. "
            "Describe what you see, identify objects, text, and any important details."
        ),
        tools=[extract_metadata],
        cost_tracker=cost_tracker,
        temperature=0.7,
    )

    # Example: Analyze an image
    # For a real implementation, you would pass actual image content
    
    print("Claude Vision Analysis Example")
    print("=" * 60)
    print("\nThis example demonstrates vision capabilities with Claude.")
    print("\nTo use real vision:")
    print("1. Prepare an image file (JPEG, PNG, GIF, or WebP)")
    print("2. Pass image_data in the prompt or extend FlintAnthropicAgent.run()")
    print("3. Claude will automatically count image tokens")
    print("4. Costs are tracked via FlintCostTracker.calculate_vision()")
    
    # Placeholder workflow for vision
    workflow = (
        Workflow("vision-analysis")
        .add(
            Node(
                "analyze_image",
                agent=agent,
                prompt=(
                    "Please analyze this image. "
                    "[In a real scenario, image data would be embedded here]"
                ),
            )
        )
        .build()
    )

    print("\nWorkflow created: vision-analysis")
    print("Ready for image analysis with cost tracking.")
    
    # To enable actual image processing, extend FlintAnthropicAgent to:
    # 1. Accept image_content blocks in the messages
    # 2. Track image_tokens separately in cost calculation
    # 3. Use calculate_vision() for proper pricing
    
    print("\nVision Cost Examples:")
    print("-" * 60)
    
    # Example cost calculations
    pricing = cost_tracker.get_pricing("claude-3-5-sonnet-20241022")
    if pricing:
        print(f"Claude 3.5 Sonnet pricing: {pricing}")
        
        # Estimate for 1000 image tokens (approx 1 high-res image)
        vision_cost = cost_tracker.calculate_vision(
            "claude-3-5-sonnet-20241022",
            image_tokens=1000,
            prompt_tokens=100,
            completion_tokens=500,
        )
        
        print(f"\nExample: 1 image (1000 tokens) + prompt")
        print(f"  Image cost: ${vision_cost.prompt_cost_usd:.6f}")
        print(f"  Completion cost: ${vision_cost.completion_cost_usd:.6f}")
        print(f"  Total: ${vision_cost.total_cost_usd:.6f}")


if __name__ == "__main__":
    asyncio.run(main())
