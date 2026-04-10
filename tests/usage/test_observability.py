"""Tests for ObservabilityHooks."""

from __future__ import annotations

import pytest

from flint_ai.usage.events import AIEvent, EventType
from flint_ai.usage.observability import ObservabilityHooks


class TestObservabilityHooks:
    @pytest.fixture
    def hooks(self) -> ObservabilityHooks:
        return ObservabilityHooks()

    @pytest.fixture
    def event(self) -> AIEvent:
        return AIEvent(
            provider="openai",
            model="gpt-4o",
            type=EventType.LLM_CALL,
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.01,
        )

    def test_add_listener(self, hooks: ObservabilityHooks) -> None:
        hooks.add_listener(lambda e: None)
        assert hooks.listener_count == 1

    def test_remove_listener(self, hooks: ObservabilityHooks) -> None:
        def callback(e):
            pass

        hooks.add_listener(callback)
        hooks.remove_listener(callback)
        assert hooks.listener_count == 0

    @pytest.mark.asyncio
    async def test_on_event_notifies_listeners(self, hooks: ObservabilityHooks, event: AIEvent) -> None:
        received = []
        hooks.add_listener(lambda e: received.append(e))
        await hooks.on_event(event)
        assert len(received) == 1
        assert received[0].id == event.id

    @pytest.mark.asyncio
    async def test_on_event_async_listener(self, hooks: ObservabilityHooks, event: AIEvent) -> None:
        received = []

        async def async_listener(e):
            received.append(e)

        hooks.add_listener(async_listener)
        await hooks.on_event(event)
        assert len(received) == 1

    def test_debug_log(self, hooks: ObservabilityHooks, event: AIEvent) -> None:
        log_line = hooks.debug_log(event)
        assert "[llm_call]" in log_line
        assert "provider=openai" in log_line
        assert "model=gpt-4o" in log_line
        assert "in=100" in log_line
        assert "out=50" in log_line
        assert "cost=" in log_line

    def test_debug_log_estimated(self, hooks: ObservabilityHooks) -> None:
        event = AIEvent(
            provider="openai",
            model="gpt-4o",
            type=EventType.LLM_CALL,
            estimated=True,
        )
        log_line = hooks.debug_log(event)
        assert "[ESTIMATED]" in log_line

    def test_log_event(self, hooks: ObservabilityHooks, event: AIEvent) -> None:
        hooks.log_event(event)

    @pytest.mark.asyncio
    async def test_listener_error_does_not_break_others(self, hooks: ObservabilityHooks, event: AIEvent) -> None:
        received = []
        hooks.add_listener(lambda e: 1 / 0)
        hooks.add_listener(lambda e: received.append(e))
        await hooks.on_event(event)
        assert len(received) == 1
