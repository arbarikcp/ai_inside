"""FixerChatModel: the scratch ``FixerMock`` exposed as a LangChain chat model.

``create_agent`` needs a ``BaseChatModel`` that supports ``bind_tools``. Rather
than writing a second scripted policy, this adapter converts LangChain
messages to the lab's ``Message`` type, asks ``FixerMock`` for the next move,
and converts the ``LLMResponse`` back into an ``AIMessage``. Scratch and
LangGraph builds therefore see the *same* model behaviour, so any difference
in results comes from the loop machinery, not the model.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool
from llm.base import LLMResponse, Message
from pydantic import Field, PrivateAttr

from les.scratch.ch01.fixer_mock import FixerMock


def to_lab_messages(messages: Sequence[BaseMessage]) -> list[Message]:
    """Convert LangChain messages to lab ``Message`` objects."""
    out: list[Message] = []
    for m in messages:
        text = m.content if isinstance(m.content, str) else str(m.content)
        if isinstance(m, SystemMessage):
            out.append(Message("system", text))
        elif isinstance(m, HumanMessage):
            out.append(Message("user", text))
        elif isinstance(m, ToolMessage):
            out.append(Message("tool", text, tool_call_id=m.tool_call_id))
        else:
            out.append(Message("assistant", text))
    return out


def to_ai_message(resp: LLMResponse) -> AIMessage:
    """Convert a lab ``LLMResponse`` to a LangChain ``AIMessage`` with usage."""
    return AIMessage(
        content=resp.text,
        tool_calls=[
            {"name": tc.name, "args": tc.arguments, "id": tc.id, "type": "tool_call"}
            for tc in resp.tool_calls
        ],
        usage_metadata={
            "input_tokens": resp.prompt_tokens,
            "output_tokens": resp.completion_tokens,
            "total_tokens": resp.total_tokens,
        },
    )


class FixerChatModel(BaseChatModel):
    """Scripted LangChain chat model backed by ``FixerMock``."""

    bound_tools: list[dict[str, Any]] = Field(default_factory=list)
    _policy: FixerMock = PrivateAttr(default_factory=FixerMock)

    @property
    def _llm_type(self) -> str:
        return "fixer-mock"

    @property
    def call_count(self) -> int:
        return self._policy.call_count

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> FixerChatModel:  # type: ignore[override]
        """Return a copy that 'knows' the tools, sharing the same policy."""
        bound = self.model_copy(
            update={"bound_tools": [convert_to_openai_tool(t) for t in tools]}
        )
        bound._policy = self._policy
        return bound

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        resp = self._policy.complete(
            to_lab_messages(messages), self.bound_tools or None
        )
        return ChatResult(generations=[ChatGeneration(message=to_ai_message(resp))])
