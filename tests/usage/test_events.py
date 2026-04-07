"""Tests for AIEvent and EventEmitter."""

from __future__ import annotations

import pytest

from flint_ai.usage.events import AIEvent, EventEmitter, EventType


class TestAIEvent:
    def test_creates_with_defaults(self) -> None:
        event = AIEvent(provider="openai", model="gpt-4o", type=EventType.LLM_CALL)
        assert event.id
        assert event.timestamp > 0
        assert event.provider == "openai"
        assert event.model == "gpt-4o"
        assert event.type == EventType.LLM_CALL
        assert event.input_tokens is None
        assert event.output_tokens is None
        assert event.estimated is False
        assert event.cost_usd is None
        assert event.metadata == {}

    def test_total_tokens(self) -> None:
        event = AIEvent(
            provider="openai",
            model="gpt-4o",
            type=EventType.LLM_CALL,
            input_tokens=100,
            output_tokens=50,
        )
        assert event.total_tokens == 150

    def test_total_tokens_with_none(self) -> None:
        event = AIEvent(
            provider="openai",
            model="gpt-4o",
            type=EventType.LLM_CALL,
        )
        assert event.total_tokens == 0

    def test_with_cost(self) -> None:
        event = AIEvent(provider="openai", model="gpt-4o", type=EventType.LLM_CALL)
        new_event = event.with_cost(0.042)
        assert new_event.cost_usd == 0.042
        assert event.cost_usd is None

    def test_with_metadata(self) -> None:
        event = AIEvent(
            provider="openai",
            model="gpt-4o",
            type=EventType.LLM_CALL,
            metadata={"task_id": "abc"},
        )
        new_event = event.with_metadata(node_id="n1")
        assert new_event.metadata == {"task_id": "abc", "node_id": "n1"}
        assert event.metadata == {"task_id": "abc"}

    def test_is_estimated_true(self) -> None:
        event = AIEvent(
            provider="openai",
            model="gpt-4o",
            type=EventType.LLM_CALL,
            estimated=True,
        )
        assert event.is_estimated()

    def test_is_estimated_missing_input(self) -> None:
        event = AIEvent(
            provider="openai",
            model="gpt-4o",
            type=EventType.LLM_CALL,
            output_tokens=50,
        )
        assert event.is_estimated()

    def test_is_estimated_false(self) -> None:
        event = AIEvent(
            provider="openai",
            model="gpt-4o",
            type=EventType.LLM_CALL,
            input_tokens=100,
            output_tokens=50,
        )
        assert not event.is_estimated()

    def test_to_dict(self) -> None:
        event = AIEvent(
            provider="openai",
            model="gpt-4o",
            type=EventType.LLM_CALL,
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.042,
            metadata={"task_id": "abc"},
        )
        d = event.to_dict()
        assert d["provider"] == "openai"
        assert d["input_tokens"] == 100
        assert d["output_tokens"] == 50
        assert d["cost_usd"] == 0.042
        assert d["metadata"]["task_id"] == "abc"


class TestEventEmitter:
    def test_subscribe_and_emit(self) -> None:
        emitter = EventEmitter()
        received = []
        emitter.subscribe(lambda e: received.append(e))

        event = AIEvent(provider="openai", model="gpt-4o", type=EventType.LLM_CALL)
        emitter.emit(event)

        assert len(received) == 1
        assert received[0].id == event.id

    def test_unsubscribe(self) -> None:
        emitter = EventEmitter()
        received = []

        def callback(e):
            received.append(e)

        emitter.subscribe(callback)
        emitter.unsubscribe(callback)

        event = AIEvent(provider="openai", model="gpt-4o", type=EventType.LLM_CALL)
        emitter.emit(event)

        assert len(received) == 0

    def test_multiple_listeners(self) -> None:
        emitter = EventEmitter()
        r1, r2 = [], []
        emitter.subscribe(lambda e: r1.append(e))
        emitter.subscribe(lambda e: r2.append(e))

        event = AIEvent(provider="openai", model="gpt-4o", type=EventType.LLM_CALL)
        emitter.emit(event)

        assert len(r1) == 1
        assert len(r2) == 1

    def test_emit_records_history(self) -> None:
        emitter = EventEmitter()
        event = AIEvent(provider="openai", model="gpt-4o", type=EventType.LLM_CALL)
        emitter.emit(event)
        assert len(emitter.get_history()) == 1
        assert emitter.get_history()[0].id == event.id

    def test_get_history_limit(self) -> None:
        emitter = EventEmitter()
        for _ in range(5):
            emitter.emit(AIEvent(provider="openai", model="gpt-4o", type=EventType.LLM_CALL))
        assert len(emitter.get_history(limit=3)) == 3

    def test_clear_history(self) -> None:
        emitter = EventEmitter()
        emitter.emit(AIEvent(provider="openai", model="gpt-4o", type=EventType.LLM_CALL))
        emitter.clear_history()
        assert len(emitter.get_history()) == 0

    def test_listener_count(self) -> None:
        emitter = EventEmitter()
        assert emitter.listener_count == 0
        emitter.subscribe(lambda e: None)
        assert emitter.listener_count == 1

    @pytest.mark.asyncio
    async def test_emit_async(self) -> None:
        emitter = EventEmitter()
        received = []

        async def async_listener(event):
            received.append(event)

        emitter.subscribe(async_listener)
        event = AIEvent(provider="openai", model="gpt-4o", type=EventType.LLM_CALL)
        await emitter.emit_async(event)

        assert len(received) == 1

    def test_listener_error_does_not_break_others(self) -> None:
        emitter = EventEmitter()
        emitter.subscribe(lambda e: 1 / 0)
        r2 = []
        emitter.subscribe(lambda e: r2.append(e))

        event = AIEvent(provider="openai", model="gpt-4o", type=EventType.LLM_CALL)
        emitter.emit(event)

        assert len(r2) == 1
