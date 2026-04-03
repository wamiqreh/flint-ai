"""Simple circuit breaker for backend connections (Redis, Postgres).

Prevents tight-loop hammering of dead backends. After N consecutive
failures, the breaker trips open and fails fast for a cooldown period
before allowing a single probe request through.
"""

from __future__ import annotations

import logging
import time
from enum import Enum

logger = logging.getLogger("flint.server.middleware.circuit_breaker")


class CircuitState(str, Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing fast
    HALF_OPEN = "half_open"  # Probing with single request


class CircuitBreaker:
    """Track consecutive failures and trip a circuit to prevent cascading load.

    Args:
        name: Identifier for logging (e.g., "redis", "postgres").
        failure_threshold: Consecutive failures before tripping open.
        recovery_timeout: Seconds to wait before probing again.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN and time.monotonic() - self._last_failure_time >= self.recovery_timeout:
            self._state = CircuitState.HALF_OPEN
            logger.info("Circuit breaker '%s' entering half-open state", self.name)
        return self._state

    def allow_request(self) -> bool:
        """Check if a request should be allowed through."""
        s = self.state
        return s in (CircuitState.CLOSED, CircuitState.HALF_OPEN)

    def record_success(self) -> None:
        """Record a successful operation — reset breaker to closed."""
        if self._state != CircuitState.CLOSED:
            logger.info("Circuit breaker '%s' recovered → closed", self.name)
        self._failure_count = 0
        self._state = CircuitState.CLOSED

    def record_failure(self) -> None:
        """Record a failed operation — may trip breaker open."""
        self._failure_count += 1
        self._last_failure_time = time.monotonic()

        if self._failure_count >= self.failure_threshold:
            if self._state != CircuitState.OPEN:
                logger.warning(
                    "Circuit breaker '%s' tripped OPEN after %d failures (cooldown %.0fs)",
                    self.name,
                    self._failure_count,
                    self.recovery_timeout,
                )
            self._state = CircuitState.OPEN

    def reset(self) -> None:
        """Force-reset the breaker to closed."""
        self._failure_count = 0
        self._state = CircuitState.CLOSED
        self._last_failure_time = 0.0
