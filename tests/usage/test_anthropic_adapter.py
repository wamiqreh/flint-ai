"""Tests for Anthropic/Claude adapter in unified usage system."""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from flint_ai.usage import EventEmitter, PricingRegistry
from flint_ai.usage.adapters.anthropic import AnthropicAdapter


@pytest.fixture
def pricing_registry():
    """Pricing registry with Claude models."""
    return PricingRegistry()


@pytest.fixture
def event_emitter():
    """Event emitter for collecting events."""
    return EventEmitter()


@pytest.fixture
def anthropic_adapter(pricing_registry, event_emitter):
    """Claude adapter with mocked client."""
    return AnthropicAdapter(
        api_key="sk-ant-test-key",
        pricing=pricing_registry,
        emitter=event_emitter,
    )


@pytest.mark.asyncio
async def test_anthropic_adapter_init():
    """Test AnthropicAdapter initialization."""
    adapter = AnthropicAdapter(
        api_key="sk-ant-test",
        pricing=PricingRegistry(),
    )
    assert adapter.provider == "anthropic"
    assert adapter._api_key == "sk-ant-test"


@pytest.mark.asyncio
async def test_anthropic_adapter_claude_sonnet():
    """Test Claude Sonnet pricing is available."""
    registry = PricingRegistry()
    pricing = registry.get_pricing("anthropic", "claude-3-5-sonnet-20241022")
    assert pricing is not None
    assert pricing.input_per_1k == 0.003
    assert pricing.output_per_1k == 0.015


@pytest.mark.asyncio
async def test_anthropic_adapter_claude_opus():
    """Test Claude Opus pricing is available."""
    registry = PricingRegistry()
    pricing = registry.get_pricing("anthropic", "claude-3-opus-20250219")
    assert pricing is not None
    assert pricing.input_per_1k == 0.005
    assert pricing.output_per_1k == 0.025


@pytest.mark.asyncio
async def test_anthropic_adapter_claude_haiku():
    """Test Claude Haiku pricing is available."""
    registry = PricingRegistry()
    pricing = registry.get_pricing("anthropic", "claude-3-haiku-20240307")
    assert pricing is not None
    assert pricing.input_per_1k == 0.00080
    assert pricing.output_per_1k == 0.004


@pytest.mark.asyncio
async def test_anthropic_execute_llm_mocked(anthropic_adapter):
    """Test execute_llm with mocked Anthropic SDK."""
    # Mock the Anthropic client
    mock_response = MagicMock()
    mock_response.id = "msg-123"
    mock_response.usage.input_tokens = 100
    mock_response.usage.output_tokens = 50
    mock_response.stop_reason = "end_turn"
    mock_response.content = [MagicMock(text="Hello!")]

    with patch.dict(sys.modules, {"anthropic": MagicMock()}):
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        anthropic_adapter._client = mock_client

        result = await anthropic_adapter.execute_llm(
            model="claude-3-5-sonnet-20241022",
            messages=[{"role": "user", "content": "Hello"}],
        )

        assert result.content == "Hello!"
        assert result.usage.input_tokens == 100
        assert result.usage.output_tokens == 50


@pytest.mark.asyncio
async def test_anthropic_execute_llm_cost_calculation(anthropic_adapter):
    """Test cost calculation for Claude call."""
    # Sonnet: $0.003 input, $0.015 output per 1K
    # 1000 input tokens @ 0.003 = $3
    # 1000 output tokens @ 0.015 = $15
    # Total = $18 ($0.018 in decimal)

    mock_response = MagicMock()
    mock_response.id = "msg-456"
    mock_response.usage.input_tokens = 1000
    mock_response.usage.output_tokens = 1000
    mock_response.stop_reason = "end_turn"
    mock_response.content = [MagicMock(text="Output")]

    with patch.dict(sys.modules, {"anthropic": MagicMock()}):
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        anthropic_adapter._client = mock_client

        result = await anthropic_adapter.execute_llm(
            model="claude-3-5-sonnet-20241022",
            messages=[{"role": "user", "content": "Hello"}],
        )

        assert result.usage.input_tokens == 1000
        assert result.usage.output_tokens == 1000


@pytest.mark.asyncio
async def test_anthropic_embedding_not_supported(anthropic_adapter):
    """Test that embedding calls raise NotImplementedError."""
    with pytest.raises(NotImplementedError):
        await anthropic_adapter.execute_embedding(
            model="claude-3-haiku-20240307",
            texts=["Hello"],
        )


@pytest.mark.asyncio
async def test_anthropic_image_not_supported(anthropic_adapter):
    """Test that image calls raise NotImplementedError."""
    with pytest.raises(NotImplementedError):
        await anthropic_adapter.execute_image(
            model="claude-3-haiku-20240307",
            prompt="Draw something",
        )


@pytest.mark.asyncio
async def test_anthropic_audio_not_supported(anthropic_adapter):
    """Test that audio calls raise NotImplementedError."""
    with pytest.raises(NotImplementedError):
        await anthropic_adapter.execute_audio(
            model="claude-3-haiku-20240307",
            audio_path="test.mp3",
        )
