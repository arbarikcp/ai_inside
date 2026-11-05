"""AnatomyLoop: the five-stage loop from Ch 1, written out step by step.

    1. intent       state the goal and the success condition
    2. context      ground the model in the real workspace (file list)
    3. action       the model picks a tool call and we execute it
    4. observation  the tool result goes back into the conversation
    5. adjustment   failures (failed tests, rejected answers) feed the next turn

The loop stops on SUCCESS (the verifier passes) or BUDGET_ITERATIONS. The
model saying "done" is never enough on its own.
"""

from __future__ import annotations

from typing import Any

from llm.base import LLMClient, Message

from les.contracts import LoopResult, StopReason, ToolOutput, ToolSpec
from les.models import ModelSpec

from .fixer_mock import FixerMock
from .tasks import FIX_TASKS, FixTask
from .tools import function_schemas, make_tools
from .verifier import TestsPassVerifier
from .workspace import SOLUTION_FILE, TaskWorkspace

SYSTEM_PROMPT = (
    "You are a Python bug fixer working in a loop. Use read_file, write_file "
    "and run_tests. Only reply without a tool call once run_tests prints PASSED."
)


class AnatomyLoop:
    """A minimal intent → context → action → observation → adjustment loop."""

    def __init__(
        self,
        llm: LLMClient | None = None,
        task: FixTask | None = None,
        spec: ModelSpec | None = None,
        max_iterations: int = 8,
    ) -> None:
        self.llm = llm or FixerMock()
        self.task = task or FIX_TASKS[0]
        self.spec = spec
        self.max_iterations = max_iterations
        self._state: dict[str, Any] = {}

    # --- public API (LoopRunner) ------------------------------------------

    def run(self, goal: str, **kwargs: Any) -> LoopResult:
        task: FixTask = kwargs.get("task") or self.task
        self._state = {
            "runner": "ch01_scratch_loop",
            "goal": goal,
            "task_id": task.task_id,
            "iteration": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "tool_calls": 0,
            "stages": [],
            "messages": [],
        }
        with TaskWorkspace(task) as ws:
            tools = make_tools(ws)
            verifier = TestsPassVerifier(ws)
            messages = self._intent(goal, task)
            messages += self._context(ws)
            stop, final = self._iterate(messages, tools, verifier)
            final_code = ws.read(SOLUTION_FILE)

        self._state["messages"] = [
            {"role": m.role, "content": m.content, "tool_call_id": m.tool_call_id}
            for m in messages
        ]
        return self._result(stop, final, final_code, task)

    def get_state(self) -> dict[str, Any]:
        return dict(self._state)

    # --- the five stages ---------------------------------------------------

    def _intent(self, goal: str, task: FixTask) -> list[Message]:
        self._stage("intent")
        return [
            Message("system", SYSTEM_PROMPT),
            Message(
                "user",
                f"Task id: {task.task_id}\nGoal: {goal}\n"
                "Done when: run_tests prints PASSED.",
            ),
        ]

    def _context(self, ws: TaskWorkspace) -> list[Message]:
        self._stage("context")
        return [Message("user", f"Workspace files: {', '.join(ws.list_files())}")]

    def _iterate(
        self,
        messages: list[Message],
        tools: dict[str, ToolSpec],
        verifier: TestsPassVerifier,
    ) -> tuple[StopReason, str]:
        schemas = function_schemas(tools)
        while self._state["iteration"] < self.max_iterations:
            self._state["iteration"] += 1
            response = self.llm.complete(messages, tools=schemas)
            self._state["prompt_tokens"] += response.prompt_tokens
            self._state["completion_tokens"] += response.completion_tokens

            if response.wants_tool:
                for call in response.tool_calls:
                    self._stage("action")
                    out = self._execute(tools, call.name, call.arguments)
                    self._stage("observation")
                    messages.append(Message("tool", out.content, tool_call_id=call.id))
                    if call.name == "run_tests" and not out.ok:
                        self._stage("adjustment")
                continue

            # Final answer: check it before we believe it.
            messages.append(Message("assistant", response.text))
            verdict = verifier.verify(response.text)
            if verdict.passed:
                return StopReason.SUCCESS, response.text
            self._stage("adjustment")
            messages.append(Message("user", f"Verification failed:\n{verdict.reason}"))

        return StopReason.BUDGET_ITERATIONS, messages[-1].content

    # --- helpers -----------------------------------------------------------

    def _execute(
        self, tools: dict[str, ToolSpec], name: str, args: dict[str, Any]
    ) -> ToolOutput:
        self._state["tool_calls"] += 1
        tool = tools.get(name)
        if tool is None:
            return ToolOutput(
                ok=False, content=f"unknown tool '{name}'. Available: {sorted(tools)}"
            )
        return tool.execute(**args)

    def _stage(self, name: str) -> None:
        self._state["stages"].append(name)

    def _result(
        self, stop: StopReason, final: str, code: str, task: FixTask
    ) -> LoopResult:
        s = self._state
        p, c = s["prompt_tokens"], s["completion_tokens"]
        return LoopResult(
            success=stop is StopReason.SUCCESS,
            stop_reason=stop,
            final_output=code if stop is StopReason.SUCCESS else final,
            iterations=s["iteration"],
            prompt_tokens=p,
            completion_tokens=c,
            total_tokens=p + c,
            cost_usd=self.spec.cost(p, c) if self.spec else 0.0,
            tool_calls=s["tool_calls"],
            metadata={"task_id": task.task_id, "stages": list(s["stages"])},
        )
