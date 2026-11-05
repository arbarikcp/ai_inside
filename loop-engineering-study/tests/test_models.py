"""Tests for the model config layer (Task 2)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from les.models.spec import ModelConfig, ModelSpec, load_config
from les.models.factory import (
    MockChatModel,
    chat_model,
    raw_client,
    resolve,
)

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "models.yaml"


# ---------------------------------------------------------------------------
# spec.py tests
# ---------------------------------------------------------------------------

class TestModelSpec:
    def test_cost_calculation(self) -> None:
        spec = ModelSpec(alias="test", family="openai", name="gpt-4", price_in=3.0, price_out=15.0)
        # 1000 prompt tokens at $3/M + 500 completion tokens at $15/M
        cost = spec.cost(prompt_tokens=1000, completion_tokens=500)
        assert cost == pytest.approx((1000 * 3.0 + 500 * 15.0) / 1_000_000)

    def test_cost_zero_for_free_models(self) -> None:
        spec = ModelSpec(alias="mock", family="mock")
        assert spec.cost(1000, 1000) == 0.0


class TestLoadConfig:
    def test_loads_config_file(self) -> None:
        cfg = load_config(CONFIG_PATH)
        assert isinstance(cfg, ModelConfig)
        assert "mock" in cfg.models
        assert "local" in cfg.models
        assert cfg.default == "mock"

    def test_roles_defined(self) -> None:
        cfg = load_config(CONFIG_PATH)
        assert "maker" in cfg.roles
        assert "checker" in cfg.roles
        assert "cheap" in cfg.roles
        assert "strong" in cfg.roles

    def test_model_specs_populated(self) -> None:
        cfg = load_config(CONFIG_PATH)
        mock = cfg.models["mock"]
        assert mock.family == "mock"
        local = cfg.models["local"]
        assert local.family == "ollama"
        assert local.base_url != ""


class TestModelConfig:
    def test_resolve_alias(self) -> None:
        cfg = load_config(CONFIG_PATH)
        spec = cfg.resolve("mock")
        assert spec.alias == "mock"
        assert spec.family == "mock"

    def test_resolve_role(self) -> None:
        cfg = load_config(CONFIG_PATH)
        spec = cfg.resolve("maker")
        # maker -> local (per config)
        assert spec.alias == "local"

    def test_resolve_unknown_raises(self) -> None:
        cfg = load_config(CONFIG_PATH)
        with pytest.raises(KeyError, match="Unknown model alias"):
            cfg.resolve("nonexistent")

    def test_resolve_default(self) -> None:
        cfg = load_config(CONFIG_PATH)
        spec = cfg.resolve_default()
        assert spec.alias == "mock"

    def test_les_model_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = load_config(CONFIG_PATH)
        monkeypatch.setenv("LES_MODEL", "local")
        spec = cfg.resolve_default()
        assert spec.alias == "local"


# ---------------------------------------------------------------------------
# factory.py tests
# ---------------------------------------------------------------------------

class TestResolve:
    def test_resolve_mock(self) -> None:
        spec = resolve("mock", config_path=CONFIG_PATH)
        assert spec.family == "mock"

    def test_resolve_role_to_spec(self) -> None:
        spec = resolve("checker", config_path=CONFIG_PATH)
        assert spec.family == "anthropic"


class TestChatModel:
    def test_mock_returns_mock_chat_model(self) -> None:
        model = chat_model("mock", config_path=CONFIG_PATH)
        assert isinstance(model, MockChatModel)

    def test_mock_chat_model_generates(self) -> None:
        model = MockChatModel()
        from langchain_core.messages import HumanMessage
        result = model.invoke([HumanMessage(content="hello")])
        assert result.content == "mock response"


class TestRawClient:
    def test_mock_returns_lab_mock(self) -> None:
        client = raw_client("mock", config_path=CONFIG_PATH)
        from llm.base import LLMClient
        assert isinstance(client, LLMClient)

    def test_mock_client_responds(self) -> None:
        client = raw_client("mock", config_path=CONFIG_PATH)
        from llm.base import Message
        response = client.complete([Message(role="user", content="hello")])
        assert response.text == "mock response"
