"""TestsPassVerifier: ground truth for the Fix-the-function lab.

The model's claim ("I fixed it") is never trusted. Success is decided by
running the tests in the workspace. This is the grounding idea from Ch 1.
"""

from __future__ import annotations

from typing import Any

from les.contracts import VerifyResult

from .workspace import TaskWorkspace


class TestsPassVerifier:
    """Passes only when the workspace tests pass."""

    __test__ = False  # stop pytest from collecting this as a test class

    def __init__(self, ws: TaskWorkspace) -> None:
        self._ws = ws

    @property
    def name(self) -> str:
        return "tests_pass"

    def verify(self, output: str, **context: Any) -> VerifyResult:
        run = self._ws.run_tests()
        if run.passed:
            return VerifyResult(passed=True, reason="all tests passed", score=1.0)
        return VerifyResult(passed=False, reason=run.output, score=0.0)
