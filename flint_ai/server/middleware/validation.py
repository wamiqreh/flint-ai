"""Input validation helpers for API endpoints."""

from __future__ import annotations

import re
from typing import Any

MAX_PROMPT_BYTES = 1_048_576  # 1 MB
MAX_DAG_NODES = 500
MAX_METADATA_BYTES = 65_536  # 64 KB
AGENT_TYPE_RE = re.compile(r"^[a-zA-Z0-9_\-]{1,128}$")


class ValidationError(Exception):
    """Raised when input fails validation."""

    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")


def validate_prompt_length(prompt: str) -> None:
    """Raise ValidationError if prompt exceeds max size."""
    if len(prompt.encode("utf-8", errors="ignore")) > MAX_PROMPT_BYTES:
        raise ValidationError("prompt", f"Prompt exceeds maximum size of {MAX_PROMPT_BYTES // 1024}KB")


def validate_agent_type(agent_type: str) -> None:
    """Raise ValidationError if agent_type contains invalid characters."""
    if not AGENT_TYPE_RE.match(agent_type):
        raise ValidationError(
            "agent_type",
            "Must be 1-128 characters, alphanumeric, underscore, or hyphen only",
        )


def validate_metadata(metadata: dict[str, Any] | None) -> None:
    """Raise ValidationError if metadata exceeds max size."""
    if metadata is None:
        return
    import json

    size = len(json.dumps(metadata).encode("utf-8"))
    if size > MAX_METADATA_BYTES:
        raise ValidationError("metadata", f"Metadata exceeds maximum size of {MAX_METADATA_BYTES // 1024}KB")


def validate_dag_size(nodes: list[Any]) -> None:
    """Raise ValidationError if DAG exceeds max node count."""
    if len(nodes) > MAX_DAG_NODES:
        raise ValidationError("nodes", f"DAG exceeds maximum of {MAX_DAG_NODES} nodes")
