"""Input sanitization for tool execution logging."""

from __future__ import annotations

import re
from typing import Any

_SECRET_PATTERNS = [
    "api_key",
    "api-key",
    "apikey",
    "token",
    "password",
    "passwd",
    "secret",
    "authorization",
    "access_token",
    "refresh_token",
    "private_key",
    "client_secret",
]

_MAX_STRING_LENGTH = 500


def sanitize_input(data: Any, max_string_length: int = _MAX_STRING_LENGTH) -> Any:
    """Sanitize input data for logging.

    - Truncates strings longer than max_string_length
    - Redacts values for keys matching secret patterns
    - Recursively processes dicts and lists
    """
    if isinstance(data, dict):
        return {k: _sanitize_value(k, v, max_string_length) for k, v in data.items()}
    if isinstance(data, list):
        return [sanitize_input(item, max_string_length) for item in data]
    if isinstance(data, str):
        if len(data) > max_string_length:
            return data[:max_string_length] + f"... [{len(data)} chars total]"
        return data
    return data


def _sanitize_value(key: str, value: Any, max_length: int) -> Any:
    key_lower = key.lower().replace("_", "-").replace(" ", "-")
    for pattern in _SECRET_PATTERNS:
        if pattern in key_lower:
            return "[REDACTED]"
    if isinstance(value, str) and len(value) > max_length:
        return value[:max_length] + f"... [{len(value)} chars total]"
    if isinstance(value, dict):
        return {k: _sanitize_value(k, v, max_length) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_input(item, max_length) for item in value]
    return value


def truncate_string(s: str, max_length: int = _MAX_STRING_LENGTH) -> str:
    """Truncate a string for display."""
    if len(s) <= max_length:
        return s
    return s[:max_length] + f"... [{len(s)} chars total]"
