"""Tests for LangSmith tracing configuration."""
from __future__ import annotations

import os

import pytest

from les.tracing import configure_tracing, is_tracing_enabled


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove tracing env vars before each test."""
    for key in (
        "LANGSMITH_TRACING",
        "LANGSMITH_PROJECT",
        "LANGSMITH_ENDPOINT",
        "LANGSMITH_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)


class TestConfigureTracing:
    def test_disabled_by_default(self) -> None:
        result = configure_tracing()
        assert result is False
        assert os.environ["LANGSMITH_TRACING"] == "false"

    def test_enable_via_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LANGSMITH_TRACING", "true")
        result = configure_tracing()
        assert result is True

    def test_enable_via_parameter(self) -> None:
        result = configure_tracing(enabled=True)
        assert result is True
        assert os.environ["LANGSMITH_TRACING"] == "true"
        assert os.environ["LANGSMITH_PROJECT"] == "loop-engineering-study"
        assert os.environ["LANGSMITH_ENDPOINT"] == "https://api.smith.langchain.com"

    def test_custom_project_name(self) -> None:
        configure_tracing(project="my-custom-project", enabled=True)
        assert os.environ["LANGSMITH_PROJECT"] == "my-custom-project"

    def test_disable_via_parameter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LANGSMITH_TRACING", "true")
        result = configure_tracing(enabled=False)
        assert result is False


class TestIsTracingEnabled:
    def test_false_when_unset(self) -> None:
        assert is_tracing_enabled() is False

    def test_true_when_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LANGSMITH_TRACING", "true")
        assert is_tracing_enabled() is True

    def test_true_with_numeric(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LANGSMITH_TRACING", "1")
        assert is_tracing_enabled() is True
