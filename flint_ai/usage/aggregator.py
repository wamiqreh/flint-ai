"""Aggregation layer for AI usage events."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel

from .events import AIEvent


class ModelSummary(BaseModel):
    """Aggregated cost/usage summary for a specific model."""

    total_cost: float = 0.0
    total_tokens: int = 0
    call_count: int = 0
    estimated_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


class AgentTrace(BaseModel):
    """Full trace of an agent's AI usage across multiple steps."""

    agent_id: str
    steps: list[AIEvent]
    total_cost: float
    total_tokens: int
    estimated_events: int
    by_type: dict[str, ModelSummary]

    @classmethod
    def from_events(cls, agent_id: str, events: list[AIEvent]) -> AgentTrace:
        total_cost = sum(e.cost_usd or 0.0 for e in events)
        total_tokens = sum(e.total_tokens for e in events)
        estimated_count = sum(1 for e in events if e.is_estimated())

        by_type: dict[str, ModelSummary] = {}
        for event in events:
            type_key = event.type.value
            if type_key not in by_type:
                by_type[type_key] = ModelSummary()
            summary = by_type[type_key]
            summary.total_cost += event.cost_usd or 0.0
            summary.total_tokens += event.total_tokens
            summary.call_count += 1
            if event.is_estimated():
                summary.estimated_count += 1
            summary.input_tokens += event.input_tokens or 0
            summary.output_tokens += event.output_tokens or 0

        for s in by_type.values():
            s.total_cost = round(s.total_cost, 6)

        return cls(
            agent_id=agent_id,
            steps=events,
            total_cost=round(total_cost, 6),
            total_tokens=total_tokens,
            estimated_events=estimated_count,
            by_type=by_type,
        )


class RetryAwareCost(BaseModel):
    """Cost breakdown separating first-attempt from retry costs."""

    first_attempt_cost: float = 0.0
    retry_cost: float = 0.0
    total_cost: float = 0.0
    attempts: int = 0
    first_attempt_tokens: int = 0
    retry_tokens: int = 0

    @classmethod
    def from_events(cls, events: list[AIEvent]) -> RetryAwareCost:
        first_cost = 0.0
        retry_cost = 0.0
        first_tokens = 0
        retry_tokens = 0
        attempts = len(events)

        for i, event in enumerate(events):
            cost = event.cost_usd or 0.0
            tokens = event.total_tokens
            if i == 0:
                first_cost += cost
                first_tokens += tokens
            else:
                retry_cost += cost
                retry_tokens += tokens

        return cls(
            first_attempt_cost=round(first_cost, 6),
            retry_cost=round(retry_cost, 6),
            total_cost=round(first_cost + retry_cost, 6),
            attempts=attempts,
            first_attempt_tokens=first_tokens,
            retry_tokens=retry_tokens,
        )


class Aggregator:
    """Utilities for aggregating AI usage events at multiple levels.

    Usage:
        agg = Aggregator()
        agg.add_event(event)
        trace = agg.by_agent("my-agent")
        summary = agg.by_model()
    """

    def __init__(self) -> None:
        self._events: list[AIEvent] = []

    def add_event(self, event: AIEvent) -> None:
        self._events.append(event)

    def add_events(self, events: list[AIEvent]) -> None:
        self._events.extend(events)

    def by_request(self, request_id: str) -> list[AIEvent]:
        """All events for a single request."""
        return [e for e in self._events if e.metadata.get("request_id") == request_id]

    def by_task(self, task_id: str) -> list[AIEvent]:
        """All events for a specific task."""
        return [e for e in self._events if e.metadata.get("task_id") == task_id]

    def by_agent(self, agent_id: str, window: timedelta | None = None) -> AgentTrace:
        """Full trace for an agent."""
        events = self._filter_by_agent(agent_id, window)
        return AgentTrace.from_events(agent_id, events)

    def by_step(self, workflow_run_id: str, node_id: str) -> list[AIEvent]:
        """Events for a specific workflow step."""
        return [
            e
            for e in self._events
            if e.metadata.get("workflow_run_id") == workflow_run_id and e.metadata.get("node_id") == node_id
        ]

    def by_model(self, window: timedelta | None = None) -> dict[str, ModelSummary]:
        """Cost breakdown by model."""
        events = self._filter_by_window(window)
        summaries: dict[str, ModelSummary] = {}

        for event in events:
            key = f"{event.provider}:{event.model}"
            if key not in summaries:
                summaries[key] = ModelSummary()
            s = summaries[key]
            s.total_cost += event.cost_usd or 0.0
            s.total_tokens += event.total_tokens
            s.call_count += 1
            if event.is_estimated():
                s.estimated_count += 1
            s.input_tokens += event.input_tokens or 0
            s.output_tokens += event.output_tokens or 0

        for s in summaries.values():
            s.total_cost = round(s.total_cost, 6)

        return summaries

    def by_provider(self, window: timedelta | None = None) -> dict[str, ModelSummary]:
        """Cost breakdown by provider."""
        events = self._filter_by_window(window)
        summaries: dict[str, ModelSummary] = {}

        for event in events:
            key = event.provider
            if key not in summaries:
                summaries[key] = ModelSummary()
            s = summaries[key]
            s.total_cost += event.cost_usd or 0.0
            s.total_tokens += event.total_tokens
            s.call_count += 1
            if event.is_estimated():
                s.estimated_count += 1
            s.input_tokens += event.input_tokens or 0
            s.output_tokens += event.output_tokens or 0

        for s in summaries.values():
            s.total_cost = round(s.total_cost, 6)

        return summaries

    def retry_aware_cost(self, task_id: str) -> RetryAwareCost:
        """Separate first-attempt cost from retry cost."""
        events = self.by_task(task_id)
        return RetryAwareCost.from_events(events)

    def timeline(self, window: timedelta | None = None, bucket_minutes: int = 60) -> list[dict[str, Any]]:
        """Cost over time in time buckets."""
        events = self._filter_by_window(window)
        if not events:
            return []

        buckets: dict[str, dict[str, Any]] = {}
        for event in events:
            ts = datetime.fromtimestamp(event.timestamp, tz=timezone.utc)
            bucket_ts = ts.replace(minute=(ts.minute // bucket_minutes) * bucket_minutes, second=0, microsecond=0)
            key = bucket_ts.isoformat()

            if key not in buckets:
                buckets[key] = {
                    "timestamp": key,
                    "cost_usd": 0.0,
                    "tokens": 0,
                    "event_count": 0,
                }
            buckets[key]["cost_usd"] += event.cost_usd or 0.0
            buckets[key]["tokens"] += event.total_tokens
            buckets[key]["event_count"] += 1

        for b in buckets.values():
            b["cost_usd"] = round(b["cost_usd"], 6)

        return sorted(buckets.values(), key=lambda x: x["timestamp"])

    def total_cost(self, window: timedelta | None = None) -> float:
        """Total cost across all events."""
        events = self._filter_by_window(window)
        return round(sum(e.cost_usd or 0.0 for e in events), 6)

    def total_tokens(self, window: timedelta | None = None) -> int:
        """Total tokens across all events."""
        events = self._filter_by_window(window)
        return sum(e.total_tokens for e in events)

    def all_events(self, window: timedelta | None = None) -> list[AIEvent]:
        """All events, optionally filtered by time window."""
        return self._filter_by_window(window)

    def _filter_by_window(self, window: timedelta | None) -> list[AIEvent]:
        if window is None:
            return list(self._events)
        cutoff = datetime.now(timezone.utc) - window
        cutoff_ts = cutoff.timestamp()
        return [e for e in self._events if e.timestamp >= cutoff_ts]

    def _filter_by_agent(self, agent_id: str, window: timedelta | None) -> list[AIEvent]:
        events = self._filter_by_window(window)
        return [e for e in events if e.metadata.get("agent_id") == agent_id or e.metadata.get("task_id") == agent_id]

    def clear(self) -> None:
        self._events.clear()

    @property
    def event_count(self) -> int:
        return len(self._events)
