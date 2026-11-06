"""LGAgentLoop: the Ch 1 fixer loop built with LangChain ``create_agent``.
``create_agent`` compiles to a LangGraph ``StateGraph`` with two nodes:

    __start__ → model ⇄ tools → __end__

That graph *is* the inner loop: stages 3 (action) and 4 (observation). We add
the parts the prebuilt agent doesn't do for us, so it matches the scratch
``AnatomyLoop``:

* **intent + context**: the first two ``HumanMessage``s.
* **grounded success**: after the agent stops, ``TestsPassVerifier`` runs. On
  failure the output is fed back (stage 5, adjustment) and the agent resumes
  on the same checkpointed thread.
* **iteration budget**: ``max_iterations`` model calls in total, enforced with
  LangGraph's ``recursion_limit`` (k model calls = 2k − 1 graph steps).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import GraphRecursionError

from les.contracts import LoopResult, StopReason
from les.models import ModelSpec
from les.scratch.ch01.tasks import FIX_TASKS, FixTask
from les.scratch.ch01.tools import make_tools
from les.scratch.ch01.verifier import TestsPassVerifier
from les.scratch.ch01.workspace import SOLUTION_FILE, TaskWorkspace

from .chat_mock import FixerChatModel
from .lc_tools import to_lc_tools

SYSTEM_PROMPT = (
    "You are a Python bug fixer working in a loop. Use read_file, write_file "
    "and run_tests. Only reply without a tool call once run_tests prints PASSED."
)
VERIFY_PREFIX = "Verification failed:"


class LGAgentLoop:
    """Fix-the-function loop on a ``create_agent`` graph."""

    def __init__(
        self,
        model: BaseChatModel | None = None,
        task: FixTask | None = None,
        spec: ModelSpec | None = None,
        max_iterations: int = 8,
    ) -> None:
        self.model = model or FixerChatModel()
        self.task = task or FIX_TASKS[0]
        self.spec = spec
        self.max_iterations = max_iterations
        self._state: dict[str, Any] = {}

    # --- graph -------------------------------------------------------------

    def build(self, ws: TaskWorkspace) -> Any:
        """Compile the agent graph with tools bound to ``ws``."""
        return create_agent(
            self.model,
            to_lc_tools(make_tools(ws)),
            system_prompt=SYSTEM_PROMPT,
            checkpointer=InMemorySaver(),
        )

    def mermaid(self) -> str:
        """Mermaid source of the compiled graph (``get_graph().draw_mermaid()``)."""
        with TaskWorkspace(self.task) as ws:
            return str(self.build(ws).get_graph().draw_mermaid())

    # --- LoopRunner --------------------------------------------------------

    def run(self, goal: str, **kwargs: Any) -> LoopResult:
        task: FixTask = kwargs.get("task") or self.task
        config: dict[str, Any] = {
            "configurable": {"thread_id": f"{task.task_id}-{uuid.uuid4().hex[:8]}"}
        }
        stop = StopReason.BUDGET_ITERATIONS
        with TaskWorkspace(task) as ws:
            agent = self.build(ws)
            verifier = TestsPassVerifier(ws)
            pending: list[BaseMessage] = [
                HumanMessage(  # 1. intent
                    f"Task id: {task.task_id}\nGoal: {goal}\n"
                    "Done when: run_tests prints PASSED."
                ),
                HumanMessage(f"Workspace files: {', '.join(ws.list_files())}"),  # 2.
            ]
            messages: list[BaseMessage] = []
            while (remaining := self.max_iterations - _model_calls(messages)) > 0:
                try:  # 3 + 4: action / observation, inside the graph
                    agent.invoke(
                        {"messages": pending},
                        {**config, "recursion_limit": 2 * remaining - 1},
                    )
                except GraphRecursionError:
                    messages = agent.get_state(config).values["messages"]
                    break
                messages = agent.get_state(config).values["messages"]
                verdict = verifier.verify(_text(messages[-1]))
                if verdict.passed:
                    stop = StopReason.SUCCESS
                    break
                # 5. adjustment: feed the real test output back in
                pending = [HumanMessage(f"{VERIFY_PREFIX}\n{verdict.reason}")]
            final_code = ws.read(SOLUTION_FILE)

        self._state = {
            "runner": "ch01_lg",
            "goal": goal,
            "task_id": task.task_id,
            "thread_id": config["configurable"]["thread_id"],
            "iteration": _model_calls(messages),
            "messages": [_to_dict(m) for m in messages],
        }
        return self._result(stop, messages, final_code, task)

    def get_state(self) -> dict[str, Any]:
        return dict(self._state)

    # --- helpers -----------------------------------------------------------

    def _result(
        self,
        stop: StopReason,
        messages: Sequence[BaseMessage],
        code: str,
        task: FixTask,
    ) -> LoopResult:
        ai = [m for m in messages if isinstance(m, AIMessage)]
        p = sum((m.usage_metadata or {}).get("input_tokens", 0) for m in ai)
        c = sum((m.usage_metadata or {}).get("output_tokens", 0) for m in ai)
        ok = stop is StopReason.SUCCESS
        return LoopResult(
            success=ok,
            stop_reason=stop,
            final_output=code if ok else (_text(messages[-1]) if messages else ""),
            iterations=len(ai),
            prompt_tokens=p,
            completion_tokens=c,
            total_tokens=p + c,
            cost_usd=self.spec.cost(p, c) if self.spec else 0.0,
            tool_calls=sum(1 for m in messages if isinstance(m, ToolMessage)),
            metadata={"task_id": task.task_id, "stages": anatomy_stages(messages)},
        )


# --- module helpers ----------------------------------------------------------


def anatomy_stages(messages: Sequence[BaseMessage]) -> list[str]:
    """Rebuild the five-stage trace from the message history.

    Same vocabulary as the scratch ``AnatomyLoop`` so the two can be compared.
    """
    stages = ["intent", "context"] if messages else []
    for m in messages:
        if isinstance(m, ToolMessage):
            stages += ["action", "observation"]
            if m.name == "run_tests" and not _tests_passed(_text(m)):
                stages.append("adjustment")
        elif isinstance(m, HumanMessage) and _text(m).startswith(VERIFY_PREFIX):
            stages.append("adjustment")
    return stages


def _model_calls(messages: Sequence[BaseMessage]) -> int:
    return sum(1 for m in messages if isinstance(m, AIMessage))


def _tests_passed(output: str) -> bool:
    return "PASSED" in output and "FAILED" not in output


def _text(m: BaseMessage) -> str:
    return m.content if isinstance(m.content, str) else str(m.content)


def _to_dict(m: BaseMessage) -> dict[str, Any]:
    d: dict[str, Any] = {"role": m.type, "content": _text(m)}
    if isinstance(m, ToolMessage):
        d["tool_call_id"] = m.tool_call_id
        d["name"] = m.name
    if isinstance(m, AIMessage) and m.tool_calls:
        d["tool_calls"] = [
            {"name": tc["name"], "args": tc["args"], "id": tc["id"]}
            for tc in m.tool_calls
        ]
    return d
