"""Ch 1 comparison spike: the Fix-the-function loop on the OpenAI Agents SDK.

The SDK's ``Runner.run`` *is* the inner loop: call the model, run any tool
calls, feed results back, and stop when the model returns plain text or
``max_turns`` is exceeded. As in the LangGraph build, we add a grounded
verifier and an outer adjustment step on top.

Runs offline: ``FixerSDKModel`` implements the SDK's ``Model`` interface on
top of the scratch ``FixerMock``, and SDK tracing is switched off so nothing
is sent to OpenAI.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from agents import Agent, FunctionTool, RunConfig, Runner
from agents.exceptions import MaxTurnsExceeded
from agents.items import ModelResponse
from agents.models.interface import Model
from agents.usage import Usage
from llm.base import LLMResponse, Message
from openai.types.responses import (
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
)

from les.contracts import LoopResult, StopReason, ToolSpec
from les.models import ModelSpec, resolve
from les.scratch.ch01.fixer_mock import FixerMock
from les.scratch.ch01.tasks import FIX_TASKS, FixTask
from les.scratch.ch01.tools import make_tools
from les.scratch.ch01.verifier import TestsPassVerifier
from les.scratch.ch01.workspace import SOLUTION_FILE, TaskWorkspace

SYSTEM_PROMPT = (
    "You are a Python bug fixer working in a loop. Use read_file, write_file "
    "and run_tests. Only reply without a tool call once run_tests prints PASSED."
)
VERIFY_PREFIX = "Verification failed:"
RUN_CONFIG = RunConfig(tracing_disabled=True)

Item = dict[str, Any]


# --- tools -------------------------------------------------------------------


def to_sdk_tool(spec: ToolSpec) -> FunctionTool:
    """Wrap a ToolSpec as an SDK ``FunctionTool`` (non-strict JSON schema)."""

    async def _invoke(_ctx: Any, args_json: str) -> str:
        args = json.loads(args_json or "{}")
        return spec.execute(**args).content

    return FunctionTool(
        name=spec.name,
        description=spec.description,
        params_json_schema=spec.schema(),
        on_invoke_tool=_invoke,
        strict_json_schema=False,
    )


# --- offline model -----------------------------------------------------------


def to_lab_messages(system: str | None, items: str | Sequence[Item]) -> list[Message]:
    """Convert SDK input items to lab ``Message`` objects for ``FixerMock``."""
    out = [Message("system", system)] if system else []
    if isinstance(items, str):
        return out + [Message("user", items)]
    for it in items:
        kind = it.get("type")
        if kind == "function_call_output":
            out.append(Message("tool", str(it["output"]), tool_call_id=it["call_id"]))
        elif kind == "function_call":
            continue  # the scratch loop doesn't store tool-call requests either
        elif it.get("role") == "user":
            out.append(Message("user", _content_text(it.get("content"))))
        elif it.get("role") == "assistant":
            out.append(Message("assistant", _content_text(it.get("content"))))
    return out


def to_model_response(resp: LLMResponse) -> ModelResponse:
    """Convert a lab ``LLMResponse`` to an SDK ``ModelResponse``."""
    output: list[Any] = [
        ResponseFunctionToolCall(
            arguments=json.dumps(tc.arguments),
            call_id=tc.id,
            name=tc.name,
            type="function_call",
            id=f"fc_{tc.id}",
            status="completed",
        )
        for tc in resp.tool_calls
    ]
    if not resp.tool_calls:
        output.append(
            ResponseOutputMessage(
                id="msg_final",
                content=[
                    ResponseOutputText(
                        text=resp.text, type="output_text", annotations=[]
                    )
                ],
                role="assistant",
                status="completed",
                type="message",
            )
        )
    usage = Usage(
        requests=1,
        input_tokens=resp.prompt_tokens,
        output_tokens=resp.completion_tokens,
        total_tokens=resp.total_tokens,
    )
    return ModelResponse(output=output, usage=usage, response_id=None)


class FixerSDKModel(Model):
    """SDK ``Model`` backed by the scripted ``FixerMock``."""

    def __init__(self) -> None:
        self.policy = FixerMock()

    async def get_response(  # type: ignore[override]
        self,
        system_instructions: str | None,
        input: str | list[Any],
        model_settings: Any,
        tools: list[Any],
        output_schema: Any,
        handoffs: list[Any],
        tracing: Any,
        **kwargs: Any,
    ) -> ModelResponse:
        schemas = [{"name": t.name} for t in tools] or None
        resp = self.policy.complete(
            to_lab_messages(system_instructions, input), schemas
        )
        return to_model_response(resp)

    def stream_response(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("FixerSDKModel does not stream")


def sdk_model(alias: str) -> Model | str:
    """Model for an alias in models.yaml: the mock, or a real provider."""
    spec = resolve(alias)
    if spec.family == "mock":
        return FixerSDKModel()
    if spec.family == "openai":
        return spec.name
    if spec.family in {"ollama", "vllm"}:
        from agents import OpenAIChatCompletionsModel
        from openai import AsyncOpenAI

        client = AsyncOpenAI(base_url=spec.base_url, api_key="local")
        return OpenAIChatCompletionsModel(model=spec.name, openai_client=client)
    raise ValueError(f"family '{spec.family}' not wired for the Agents SDK spike")


# --- runner ------------------------------------------------------------------


class SDKAgentLoop:
    """Fix-the-function loop on ``Agent`` + ``Runner.run_sync``."""

    def __init__(
        self,
        model: Model | str | None = None,
        task: FixTask | None = None,
        spec: ModelSpec | None = None,
        max_iterations: int = 8,
    ) -> None:
        self.model = model or FixerSDKModel()
        self.task = task or FIX_TASKS[0]
        self.spec = spec
        self.max_iterations = max_iterations
        self._state: dict[str, Any] = {}

    def run(self, goal: str, **kwargs: Any) -> LoopResult:
        task: FixTask = kwargs.get("task") or self.task
        stop = StopReason.BUDGET_ITERATIONS
        calls, p_tok, c_tok = 0, 0, 0
        with TaskWorkspace(task) as ws:
            agent = Agent(
                name="fixer",
                instructions=SYSTEM_PROMPT,
                tools=[to_sdk_tool(t) for t in make_tools(ws).values()],
                model=self.model,
            )
            verifier = TestsPassVerifier(ws)
            history: list[Item] = [
                {
                    "role": "user",
                    "content": f"Task id: {task.task_id}\nGoal: {goal}\n"
                    "Done when: run_tests prints PASSED.",
                },
                {
                    "role": "user",
                    "content": f"Workspace files: {', '.join(ws.list_files())}",
                },
            ]
            while (remaining := self.max_iterations - calls) > 0:
                try:
                    result = Runner.run_sync(
                        agent, history, max_turns=remaining, run_config=RUN_CONFIG
                    )
                except MaxTurnsExceeded as exc:
                    data = exc.run_data
                    if data is not None:
                        calls += len(data.raw_responses)
                        p_tok, c_tok = _add_usage(p_tok, c_tok, data.raw_responses)
                        history = list(data.input) + [
                            i.to_input_item() for i in data.new_items
                        ]  # type: ignore[arg-type]
                    break
                calls += len(result.raw_responses)
                p_tok, c_tok = _add_usage(p_tok, c_tok, result.raw_responses)
                history = result.to_input_list()  # type: ignore[assignment]
                verdict = verifier.verify(str(result.final_output))
                if verdict.passed:
                    stop = StopReason.SUCCESS
                    break
                history.append(
                    {"role": "user", "content": f"{VERIFY_PREFIX}\n{verdict.reason}"}
                )
            final_code = ws.read(SOLUTION_FILE)

        self._state = {
            "runner": "ch01_oai_sdk",
            "goal": goal,
            "task_id": task.task_id,
            "iteration": calls,
            "items": json.loads(json.dumps(history, default=str)),
        }
        ok = stop is StopReason.SUCCESS
        return LoopResult(
            success=ok,
            stop_reason=stop,
            final_output=final_code if ok else _last_text(history),
            iterations=calls,
            prompt_tokens=p_tok,
            completion_tokens=c_tok,
            total_tokens=p_tok + c_tok,
            cost_usd=self.spec.cost(p_tok, c_tok) if self.spec else 0.0,
            tool_calls=sum(
                1 for i in history if i.get("type") == "function_call_output"
            ),
            metadata={"task_id": task.task_id, "stages": anatomy_stages(history)},
        )

    def get_state(self) -> dict[str, Any]:
        return dict(self._state)


# --- helpers -----------------------------------------------------------------


def anatomy_stages(items: Sequence[Item]) -> list[str]:
    """Five-stage trace rebuilt from SDK items (same vocabulary as scratch)."""
    names = {i["call_id"]: i["name"] for i in items if i.get("type") == "function_call"}
    stages = ["intent", "context"] if items else []
    for it in items:
        if it.get("type") == "function_call_output":
            stages += ["action", "observation"]
            out = str(it.get("output", ""))
            if names.get(it["call_id"]) == "run_tests" and not (
                "PASSED" in out and "FAILED" not in out
            ):
                stages.append("adjustment")
        elif it.get("role") == "user" and _content_text(it.get("content")).startswith(
            VERIFY_PREFIX
        ):
            stages.append("adjustment")
    return stages


def _add_usage(p: int, c: int, responses: Sequence[ModelResponse]) -> tuple[int, int]:
    for r in responses:
        p += r.usage.input_tokens
        c += r.usage.output_tokens
    return p, c


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(part.get("text", "")) for part in content if isinstance(part, dict)
        )
    return "" if content is None else str(content)


def _last_text(items: Sequence[Item]) -> str:
    for it in reversed(items):
        if it.get("type") == "function_call_output":
            return str(it.get("output", ""))
        if "content" in it:
            return _content_text(it["content"])
    return ""
