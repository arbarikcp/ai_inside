"""Model config and factory — the single place that knows about providers."""

from .factory import chat_model, raw_client, resolve, MockChatModel
from .spec import ModelConfig, ModelSpec, load_config

__all__ = [
    "ModelConfig",
    "ModelSpec",
    "MockChatModel",
    "chat_model",
    "load_config",
    "raw_client",
    "resolve",
]
