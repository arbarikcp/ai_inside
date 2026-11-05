"""Model factory — the single place that knows about providers.

Every build (scratch, LangGraph, comparison) calls one of these functions.
Loop code never imports a provider SDK directly.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel

from llm.base import LLMClient, LLMResponse, Message, ToolCall
from llm.mock import MockLLM

from .spec import ModelConfig, ModelSpec, load_config

_config: ModelConfig | None = None

OPENAI_COMPAT_FAMILIES = {"ollama", "vllm"}


def _get_config(config_path: Path | str | None = None) -> ModelConfig:
    global _config
    if _config is None or config_path is not None:
        _config = load_config(config_path)
    return _config


def resolve(alias_or_role: str | None = None, config_path: Path | str | None = None) -> ModelSpec:
    """Resolve an alias, role, or LES_MODEL env var to a ModelSpec."""
    cfg = _get_config(config_path)
    if alias_or_role:
        return cfg.resolve(alias_or_role)
    return cfg.resolve_default()


# ---------------------------------------------------------------------------
# LangChain chat model (used by LangGraph builds)
# ---------------------------------------------------------------------------

def chat_model(
    alias_or_role: str | None = None,
    config_path: Path | str | None = None,
    **overrides: Any,
) -> BaseChatModel:
    """Return a LangChain chat model for the given alias or role.

    For mock: returns a MockChatModel wrapping the lab's MockLLM.
    For ollama/vllm: uses init_chat_model with openai provider + base_url.
    For openai/anthropic: uses init_chat_model with native provider.
    """
    spec = resolve(alias_or_role, config_path)

    if spec.family == "mock":
        return MockChatModel()

    if spec.family in OPENAI_COMPAT_FAMILIES:
        return init_chat_model(
            spec.name,
            model_provider="openai",
            base_url=spec.base_url,
            api_key="local",
            **overrides,
        )

    return init_chat_model(
        spec.name,
        model_provider=spec.family,
        **overrides,
    )


# ---------------------------------------------------------------------------
# Raw LLMClient (used by scratch builds — the lab's own protocol)
# ---------------------------------------------------------------------------

def raw_client(
    alias_or_role: str | None = None,
    config_path: Path | str | None = None,
) -> LLMClient:
    """Return a lab-protocol LLMClient for scratch builds.

    Mock returns the lab's MockLLM with a default policy.
    Others return an OpenAIAdapter pointed at the right endpoint.
    """
    spec = resolve(alias_or_role, config_path)

    if spec.family == "mock":
        return MockLLM(
            policy=lambda msgs: LLMResponse(text="mock response", completion_tokens=4)
        )

    if spec.family in OPENAI_COMPAT_FAMILIES:
        from llm.openai_adapter import OpenAIAdapter
        import os
        os.environ.setdefault("OPENAI_API_KEY", "local")
        adapter = OpenAIAdapter(model=spec.name, api_key="local")
        adapter._client.base_url = spec.base_url  # type: ignore[attr-defined]
        return adapter

    if spec.family == "openai":
        from llm.openai_adapter import OpenAIAdapter
        return OpenAIAdapter(model=spec.name)

    if spec.family == "anthropic":
        from llm.openai_adapter import OpenAIAdapter
        return OpenAIAdapter(model=spec.name)

    raise ValueError(f"Unsupported family '{spec.family}' for raw_client")


# ---------------------------------------------------------------------------
# MockChatModel — LangChain-compatible wrapper around the lab's mock
# ---------------------------------------------------------------------------

class MockChatModel(BaseChatModel):
    """A LangChain BaseChatModel that returns canned responses.

    Used for hermetic, free test runs. Produces a simple text response.
    """

    model_name: str = "mock"

    @property
    def _llm_type(self) -> str:
        return "mock"

    def _generate(
        self,
        messages: list[Any],
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> Any:
        from langchain_core.messages import AIMessage
        from langchain_core.outputs import ChatGeneration, ChatResult

        content = "mock response"
        message = AIMessage(content=content)
        generation = ChatGeneration(message=message)
        return ChatResult(generations=[generation])
