"""SingleShotChain: prompt in, answer out, check once. No feedback.

A chain is a loop with an iteration budget of 1: the model never sees what
happened when its answer was applied. When the first answer is wrong, the
chain fails with ``BUDGET_ITERATIONS``.
"""

from __future__ import annotations

import re
from typing import Any

from llm.base import LLMClient, Message

from les.contracts import LoopResult, StopReason
from les.models import ModelSpec

from .fixer_mock import FixerMock
from .tasks import FIX_TASKS, FixTask
from .verifier import TestsPassVerifier
from .workspace import SOLUTION_FILE, TEST_FILE, TaskWorkspace

SYSTEM_PROMPT = (
    "You are a Python bug fixer. Reply with the complete corrected contents of "
    "solution.py in a single ```python code block. Do not change the tests."
)

_CODE_RE = re.compile(r"```(?:python)?\n(.*?)```", re.DOTALL)


def extract_code(text: str) -> str:
    """Return the first fenced code block, or the raw text if there is none."""
    match = _CODE_RE.search(text)
    return match.group(1) if match else text


class SingleShotChain:
    """One model call, one write, one verification."""

    def __init__(
        self,
        llm: LLMClient | None = None,
        task: FixTask | None = None,
        spec: ModelSpec | None = None,
    ) -> None:
        self.llm = llm or FixerMock()
        self.task = task or FIX_TASKS[0]
        self.spec = spec
        self._state: dict[str, Any] = {}

    def run(self, goal: str, **kwargs: Any) -> LoopResult:
        task: FixTask = kwargs.get("task") or self.task
        with TaskWorkspace(task) as ws:
            messages = [
                Message("system", SYSTEM_PROMPT),
                Message(
                    "user",
                    f"Task id: {task.task_id}\nGoal: {goal}\n\n"
                    f"--- {SOLUTION_FILE} ---\n{ws.read(SOLUTION_FILE)}\n"
                    f"--- {TEST_FILE} ---\n{task.test_src}",
                ),
            ]
            response = self.llm.complete(messages)
            messages.append(Message("assistant", response.text))
            code = extract_code(response.text)
            ws.write(SOLUTION_FILE, code)
            verdict = TestsPassVerifier(ws).verify(response.text)

        self._state = {
            "runner": "ch01_scratch_chain",
            "goal": goal,
            "task_id": task.task_id,
            "iteration": 1,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "verdict": verdict.reason,
        }
        cost = (
            self.spec.cost(response.prompt_tokens, response.completion_tokens)
            if self.spec
            else 0.0
        )
        return LoopResult(
            success=verdict.passed,
            stop_reason=StopReason.SUCCESS
            if verdict.passed
            else StopReason.BUDGET_ITERATIONS,
            final_output=code,
            iterations=1,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            total_tokens=response.total_tokens,
            cost_usd=cost,
            tool_calls=0,
            metadata={"task_id": task.task_id, "verdict": verdict.reason},
        )

    def get_state(self) -> dict[str, Any]:
        return dict(self._state)
