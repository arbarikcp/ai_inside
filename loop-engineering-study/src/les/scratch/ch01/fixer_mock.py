"""FixerMock: a scripted model that behaves like a careless but teachable fixer.

* **Chain mode** (no tools offered): replies once with the task's first
  attempt in a fenced code block. For tasks with a ``wrong_fix`` that answer
  is wrong, so the chain fails.
* **Loop mode** (tools offered): read the file, write the first attempt, run
  the tests, and if they fail write the correct fix and rerun. It finishes
  only after it observes ``PASSED``.

The mock finds the task from the ``Task id: <id>`` line in the prompt. Real
models ignore that line. Tool call ids encode the tool name
(``write_file-2``), so the policy can read its own history.
"""

from __future__ import annotations

import re
from typing import Any

from llm.base import LLMClient, LLMResponse, Message, ToolCall

from .tasks import TASKS_BY_ID, FixTask
from .workspace import SOLUTION_FILE

_TASK_RE = re.compile(r"Task id: (\S+)")


def _estimate_tokens(messages: list[Message]) -> int:
    return sum(len(m.content) for m in messages) // 4 + 1


def _find_task(messages: list[Message]) -> FixTask:
    for m in messages:
        match = _TASK_RE.search(m.content)
        if match and match.group(1) in TASKS_BY_ID:
            return TASKS_BY_ID[match.group(1)]
    raise ValueError("FixerMock: no 'Task id: <id>' line in the prompt")


class FixerMock(LLMClient):
    """Deterministic fixer model for hermetic Ch 1 runs."""

    def __init__(self) -> None:
        self.call_count = 0

    def complete(
        self, messages: list[Message], tools: list[dict[str, Any]] | None = None
    ) -> LLMResponse:
        self.call_count += 1
        task = _find_task(messages)
        prompt_tokens = _estimate_tokens(messages)
        if not tools:
            text = f"```python\n{task.first_attempt}```"
            return LLMResponse(
                text=text, prompt_tokens=prompt_tokens, completion_tokens=len(text) // 4
            )
        return self._next_loop_step(task, messages, prompt_tokens)

    # --- loop policy -------------------------------------------------------

    def _next_loop_step(
        self, task: FixTask, messages: list[Message], prompt_tokens: int
    ) -> LLMResponse:
        tool_msgs = [m for m in messages if m.role == "tool"]
        writes = sum(
            1 for m in tool_msgs if (m.tool_call_id or "").startswith("write_file")
        )
        tests = sum(
            1 for m in tool_msgs if (m.tool_call_id or "").startswith("run_tests")
        )
        last = messages[-1]
        last_tool = (
            (last.tool_call_id or "").split("-")[0] if last.role == "tool" else ""
        )

        def call(name: str, n: int, **args: str) -> LLMResponse:
            tc = ToolCall(id=f"{name}-{n}", name=name, arguments=dict(args))
            return LLMResponse(
                tool_calls=[tc], prompt_tokens=prompt_tokens, completion_tokens=20
            )

        if not tool_msgs:
            return call("read_file", 1, path=SOLUTION_FILE)
        if last_tool == "read_file":
            return call(
                "write_file", writes + 1, path=SOLUTION_FILE, content=task.first_attempt
            )
        if last_tool == "write_file":
            return call("run_tests", tests + 1)
        if (
            last_tool == "run_tests"
            and "PASSED" in last.content
            and "FAILED" not in last.content
        ):
            return LLMResponse(
                text=f"Fixed `{task.function}`; tests pass.",
                prompt_tokens=prompt_tokens,
                completion_tokens=10,
            )
        # Tests failed, or the verifier rejected a final answer: adjust.
        return call(
            "write_file", writes + 1, path=SOLUTION_FILE, content=task.correct_fix
        )
