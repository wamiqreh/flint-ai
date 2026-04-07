"""Tests for Normalizer."""

from __future__ import annotations

import pytest

from flint_ai.usage.events import EventType
from flint_ai.usage.normalizer import Normalizer


class TestNormalizer:
    @pytest.fixture
    def normalizer(self) -> Normalizer:
        return Normalizer()

    def test_normalize_llm_with_usage(self, normalizer: Normalizer) -> None:
        event = normalizer.normalize_llm(
            provider="openai",
            model="gpt-4o",
            input_text="Hello",
            output_text="Hi there",
            usage={"prompt_tokens": 10, "completion_tokens": 5},
        )
        assert event.type == EventType.LLM_CALL
        assert event.input_tokens == 10
        assert event.output_tokens == 5
        assert not event.estimated

    def test_normalize_llm_without_usage(self, normalizer: Normalizer) -> None:
        event = normalizer.normalize_llm(
            provider="openai",
            model="gpt-4o",
            input_text="Hello world this is a test",
            output_text="This is a response to the test",
            usage=None,
        )
        assert event.type == EventType.LLM_CALL
        assert event.input_tokens is not None
        assert event.input_tokens > 0
        assert event.output_tokens is not None
        # When tiktoken is available, estimation is accurate so estimated=False
        # When tiktoken is not available, char heuristic is used so estimated=True
        if normalizer.estimator._tiktoken_available:
            assert not event.estimated
        else:
            assert event.estimated

    def test_normalize_llm_with_metadata(self, normalizer: Normalizer) -> None:
        event = normalizer.normalize_llm(
            provider="openai",
            model="gpt-4o",
            input_text="Hello",
            output_text="Hi",
            usage={"prompt_tokens": 10, "completion_tokens": 5},
            metadata={"task_id": "abc", "node_id": "n1"},
        )
        assert event.metadata["task_id"] == "abc"
        assert event.metadata["node_id"] == "n1"

    def test_normalize_embedding_with_usage(self, normalizer: Normalizer) -> None:
        event = normalizer.normalize_embedding(
            provider="openai",
            model="text-embedding-3-small",
            input_text="Sample text",
            usage={"prompt_tokens": 5},
        )
        assert event.type == EventType.EMBEDDING
        assert event.input_tokens == 5

    def test_normalize_embedding_without_usage(self, normalizer: Normalizer) -> None:
        event = normalizer.normalize_embedding(
            provider="openai",
            model="text-embedding-3-small",
            input_text="Sample text for embedding",
            usage=None,
        )
        assert event.type == EventType.EMBEDDING
        assert event.input_tokens is not None
        assert event.input_tokens > 0
        # When tiktoken is available, estimation is accurate so estimated=False
        # When tiktoken is not available, char heuristic is used so estimated=True
        if normalizer.estimator._tiktoken_available:
            assert not event.estimated
        else:
            assert event.estimated

    def test_normalize_image(self, normalizer: Normalizer) -> None:
        event = normalizer.normalize_image(
            provider="openai",
            model="dall-e-3",
            image_count=3,
            metadata={"prompt": "A cat"},
        )
        assert event.type == EventType.IMAGE
        assert event.metadata["image_count"] == 3

    def test_normalize_audio(self, normalizer: Normalizer) -> None:
        event = normalizer.normalize_audio(
            provider="openai",
            model="whisper-1",
            duration_seconds=15.5,
            input_text="",
            output_text="Transcribed text",
        )
        assert event.type == EventType.AUDIO
        assert event.metadata["audio_duration_seconds"] == 15.5

    def test_normalize_tool_call(self, normalizer: Normalizer) -> None:
        event = normalizer.normalize_tool_call(
            provider="openai",
            model="gpt-4o",
            tool_name="search_code",
            input_tokens=50,
            output_tokens=30,
            metadata={"round": 0},
        )
        assert event.type == EventType.TOOL_CALL
        assert event.metadata["tool_name"] == "search_code"
        assert event.input_tokens == 50
        assert event.output_tokens == 30
        assert not event.estimated

    def test_normalize_tool_call_no_tokens(self, normalizer: Normalizer) -> None:
        event = normalizer.normalize_tool_call(
            provider="openai",
            model="gpt-4o",
            tool_name="search_code",
        )
        assert event.estimated
