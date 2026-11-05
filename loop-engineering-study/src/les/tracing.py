"""LangSmith tracing setup for loop-engineering-study.

Call `configure_tracing()` once at startup to enable LangSmith tracing.
All LangChain/LangGraph calls will be automatically traced when enabled.
"""
from __future__ import annotations

import os


def configure_tracing(
    project: str | None = None,
    enabled: bool | None = None,
) -> bool:
    """Configure LangSmith tracing via environment variables.

    Args:
        project: LangSmith project name. Defaults to LANGSMITH_PROJECT env var
                 or "loop-engineering-study".
        enabled: Force enable/disable. Defaults to LANGSMITH_TRACING env var.

    Returns:
        True if tracing is enabled, False otherwise.
    """
    if enabled is None:
        enabled = os.getenv("LANGSMITH_TRACING", "false").lower() in ("true", "1")

    os.environ["LANGSMITH_TRACING"] = str(enabled).lower()

    if enabled:
        os.environ.setdefault("LANGSMITH_PROJECT", project or "loop-engineering-study")
        os.environ.setdefault("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")

    return enabled


def is_tracing_enabled() -> bool:
    """Check if LangSmith tracing is currently enabled."""
    return os.getenv("LANGSMITH_TRACING", "false").lower() in ("true", "1")
