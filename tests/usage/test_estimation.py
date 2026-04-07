"""Tests for TokenEstimator."""

from __future__ import annotations

from flint_ai.usage.estimation import TokenEstimator, UsageInfo


class TestUsageInfo:
    def test_defaults(self) -> None:
        u = UsageInfo()
        assert u.input_tokens is None
        assert u.output_tokens is None
        assert u.cached_tokens is None
        assert u.total_tokens == 0

    def test_total_tokens(self) -> None:
        u = UsageInfo(input_tokens=100, output_tokens=50)
        assert u.total_tokens == 150

    def test_to_dict(self) -> None:
        u = UsageInfo(input_tokens=100, output_tokens=50, cached_tokens=20)
        d = u.to_dict()
        assert d["input_tokens"] == 100
        assert d["output_tokens"] == 50
        assert d["cached_tokens"] == 20
        assert d["total_tokens"] == 150


class TestTokenEstimator:
    def test_estimate_generic(self) -> None:
        estimator = TokenEstimator()
        result = estimator.estimate(
            provider="unknown",
            model="unknown-model",
            input_text="Hello world, this is a test.",
            output_text="This is a response.",
        )
        assert result.input_tokens is not None
        assert result.input_tokens > 0
        assert result.output_tokens is not None

    def test_estimate_generic_empty_output(self) -> None:
        estimator = TokenEstimator()
        result = estimator.estimate(
            provider="unknown",
            model="unknown-model",
            input_text="Hello",
            output_text=None,
        )
        assert result.input_tokens is not None
        assert result.output_tokens == 0

    def test_estimate_openai_fallback(self) -> None:
        estimator = TokenEstimator()
        result = estimator.estimate(
            provider="openai",
            model="gpt-4o",
            input_text="Hello world",
            output_text="Hi there",
        )
        assert result.input_tokens is not None
        assert result.input_tokens > 0

    def test_estimate_openai_unknown_model_fallback(self) -> None:
        estimator = TokenEstimator()
        result = estimator.estimate(
            provider="openai",
            model="unknown-gpt-future",
            input_text="Hello world",
        )
        assert result.input_tokens is not None
        assert result.input_tokens > 0
