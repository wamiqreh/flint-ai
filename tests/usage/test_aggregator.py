"""Tests for Aggregator."""

from __future__ import annotations

import pytest

from flint_ai.usage.aggregator import AgentTrace, Aggregator, RetryAwareCost
from flint_ai.usage.events import AIEvent, EventType


class TestAggregator:
    @pytest.fixture
    def aggregator(self) -> Aggregator:
        return Aggregator()

    @pytest.fixture
    def events(self) -> list[AIEvent]:
        return [
            AIEvent(
                provider="openai",
                model="gpt-4o",
                type=EventType.LLM_CALL,
                input_tokens=100,
                output_tokens=50,
                cost_usd=0.01,
                metadata={"task_id": "t1", "agent_id": "a1"},
            ),
            AIEvent(
                provider="openai",
                model="gpt-4o",
                type=EventType.LLM_CALL,
                input_tokens=200,
                output_tokens=100,
                cost_usd=0.02,
                metadata={"task_id": "t1", "agent_id": "a1"},
            ),
            AIEvent(
                provider="openai",
                model="text-embedding-3-small",
                type=EventType.EMBEDDING,
                input_tokens=50,
                cost_usd=0.001,
                metadata={"task_id": "t2", "agent_id": "a2"},
            ),
        ]

    def test_add_event(self, aggregator: Aggregator) -> None:
        event = AIEvent(provider="openai", model="gpt-4o", type=EventType.LLM_CALL)
        aggregator.add_event(event)
        assert aggregator.event_count == 1

    def test_add_events(self, aggregator: Aggregator) -> None:
        events = [
            AIEvent(provider="openai", model="gpt-4o", type=EventType.LLM_CALL),
            AIEvent(provider="openai", model="gpt-4o", type=EventType.LLM_CALL),
        ]
        aggregator.add_events(events)
        assert aggregator.event_count == 2

    def test_by_task(self, aggregator: Aggregator, events: list[AIEvent]) -> None:
        aggregator.add_events(events)
        task_events = aggregator.by_task("t1")
        assert len(task_events) == 2

    def test_by_model(self, aggregator: Aggregator, events: list[AIEvent]) -> None:
        aggregator.add_events(events)
        by_model = aggregator.by_model()
        assert "openai:gpt-4o" in by_model
        assert "openai:text-embedding-3-small" in by_model
        assert by_model["openai:gpt-4o"].call_count == 2

    def test_by_provider(self, aggregator: Aggregator, events: list[AIEvent]) -> None:
        aggregator.add_events(events)
        by_provider = aggregator.by_provider()
        assert "openai" in by_provider
        assert by_provider["openai"].call_count == 3

    def test_total_cost(self, aggregator: Aggregator, events: list[AIEvent]) -> None:
        aggregator.add_events(events)
        total = aggregator.total_cost()
        assert total == pytest.approx(0.031, rel=1e-6)

    def test_total_tokens(self, aggregator: Aggregator, events: list[AIEvent]) -> None:
        aggregator.add_events(events)
        total = aggregator.total_tokens()
        assert total == 500

    def test_by_agent(self, aggregator: Aggregator, events: list[AIEvent]) -> None:
        aggregator.add_events(events)
        trace = aggregator.by_agent("a1")
        assert trace.agent_id == "a1"
        assert len(trace.steps) == 2
        assert trace.total_cost == pytest.approx(0.03, rel=1e-6)

    def test_by_step(self, aggregator: Aggregator, events: list[AIEvent]) -> None:
        aggregator.add_events(events)
        step_events = aggregator.by_step("w1", "n1")
        assert len(step_events) == 0

    def test_retry_aware_cost(self, aggregator: Aggregator, events: list[AIEvent]) -> None:
        aggregator.add_events(events)
        retry_cost = aggregator.retry_aware_cost("t1")
        assert retry_cost.first_attempt_cost == pytest.approx(0.01, rel=1e-6)
        assert retry_cost.retry_cost == pytest.approx(0.02, rel=1e-6)
        assert retry_cost.attempts == 2

    def test_timeline(self, aggregator: Aggregator, events: list[AIEvent]) -> None:
        aggregator.add_events(events)
        timeline = aggregator.timeline(bucket_minutes=60)
        assert len(timeline) > 0
        assert "timestamp" in timeline[0]
        assert "cost_usd" in timeline[0]

    def test_clear(self, aggregator: Aggregator, events: list[AIEvent]) -> None:
        aggregator.add_events(events)
        aggregator.clear()
        assert aggregator.event_count == 0

    def test_all_events(self, aggregator: Aggregator, events: list[AIEvent]) -> None:
        aggregator.add_events(events)
        all_events = aggregator.all_events()
        assert len(all_events) == 3


class TestAgentTrace:
    def test_from_events(self) -> None:
        events = [
            AIEvent(
                provider="openai",
                model="gpt-4o",
                type=EventType.LLM_CALL,
                input_tokens=100,
                output_tokens=50,
                cost_usd=0.01,
            ),
            AIEvent(
                provider="openai",
                model="gpt-4o",
                type=EventType.LLM_CALL,
                input_tokens=200,
                output_tokens=100,
                cost_usd=0.02,
                estimated=True,
            ),
        ]
        trace = AgentTrace.from_events("agent-1", events)
        assert trace.agent_id == "agent-1"
        assert len(trace.steps) == 2
        assert trace.total_cost == pytest.approx(0.03, rel=1e-6)
        assert trace.total_tokens == 450
        assert trace.estimated_events == 1


class TestRetryAwareCost:
    def test_from_events_single(self) -> None:
        events = [
            AIEvent(
                provider="openai",
                model="gpt-4o",
                type=EventType.LLM_CALL,
                input_tokens=100,
                output_tokens=50,
                cost_usd=0.01,
            ),
        ]
        result = RetryAwareCost.from_events(events)
        assert result.first_attempt_cost == pytest.approx(0.01, rel=1e-6)
        assert result.retry_cost == 0.0
        assert result.attempts == 1

    def test_from_events_multiple(self) -> None:
        events = [
            AIEvent(
                provider="openai",
                model="gpt-4o",
                type=EventType.LLM_CALL,
                input_tokens=100,
                output_tokens=50,
                cost_usd=0.01,
            ),
            AIEvent(
                provider="openai",
                model="gpt-4o",
                type=EventType.LLM_CALL,
                input_tokens=100,
                output_tokens=50,
                cost_usd=0.01,
            ),
        ]
        result = RetryAwareCost.from_events(events)
        assert result.first_attempt_cost == pytest.approx(0.01, rel=1e-6)
        assert result.retry_cost == pytest.approx(0.01, rel=1e-6)
        assert result.attempts == 2
