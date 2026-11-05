"""Contract tests for protocol compliance.

These verify that the protocol types are well-formed and that
implementations satisfy the runtime-checkable protocols.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from les.contracts import (
    LoopResult,
    LoopRunner,
    ResumableRunner,
    StopReason,
    ToolInput,
    ToolOutput,
    ToolSpec,
    Verifier,
    VerifyResult,
)


# ---------------------------------------------------------------------------
# Value object tests
# ---------------------------------------------------------------------------

class TestStopReason:
    def test_all_reasons_are_strings(self) -> None:
        for reason in StopReason:
            assert isinstance(reason.value, str)

    def test_success_reason(self) -> None:
        assert StopReason.SUCCESS == "success"

    def test_budget_reasons_exist(self) -> None:
        budget_reasons = {
            StopReason.BUDGET_ITERATIONS,
            StopReason.BUDGET_TOKENS,
            StopReason.BUDGET_TIME,
            StopReason.BUDGET_COST,
        }
        assert len(budget_reasons) == 4


class TestLoopResult:
    def test_default_values(self) -> None:
        result = LoopResult(success=True, stop_reason=StopReason.SUCCESS)
        assert result.iterations == 0
        assert result.total_tokens == 0
        assert result.total_cost == 0.0

    def test_full_result(self) -> None:
        result = LoopResult(
            success=True,
            stop_reason=StopReason.SUCCESS,
            final_output="fixed the bug",
            iterations=3,
            prompt_tokens=1000,
            completion_tokens=500,
            total_tokens=1500,
            cost_usd=0.05,
            tool_calls=5,
            trace_id="abc-123",
        )
        assert result.success is True
        assert result.iterations == 3
        assert result.total_cost == 0.05


class TestToolIO:
    def test_tool_input(self) -> None:
        ti = ToolInput(name="read_file", arguments={"path": "/tmp/x.py"})
        assert ti.name == "read_file"

    def test_tool_output(self) -> None:
        to = ToolOutput(ok=True, content="file contents")
        assert to.ok is True

    def test_verify_result(self) -> None:
        vr = VerifyResult(passed=True, score=1.0)
        assert vr.passed is True
        assert vr.score == 1.0


# ---------------------------------------------------------------------------
# Protocol compliance tests (structural typing)
# ---------------------------------------------------------------------------

class TestProtocolCompliance:
    """Verify that concrete implementations satisfy the protocols."""

    def test_loop_runner_protocol(self) -> None:
        """A class with run() and get_state() satisfies LoopRunner."""

        class DummyRunner:
            def run(self, goal: str, **kwargs: Any) -> LoopResult:
                return LoopResult(success=True, stop_reason=StopReason.SUCCESS)
            def get_state(self) -> dict[str, Any]:
                return {}

        assert isinstance(DummyRunner(), LoopRunner)

    def test_resumable_runner_protocol(self) -> None:
        """A class with run(), get_state(), and resume() satisfies ResumableRunner."""

        class DummyResumable:
            def run(self, goal: str, **kwargs: Any) -> LoopResult:
                return LoopResult(success=True, stop_reason=StopReason.SUCCESS)
            def get_state(self) -> dict[str, Any]:
                return {}
            def resume(self, state: dict[str, Any], **kwargs: Any) -> LoopResult:
                return LoopResult(success=True, stop_reason=StopReason.SUCCESS)

        assert isinstance(DummyResumable(), ResumableRunner)

    def test_verifier_protocol(self) -> None:
        """A class with name property and verify() satisfies Verifier."""

        class DummyVerifier:
            @property
            def name(self) -> str:
                return "dummy"
            def verify(self, output: str, **context: Any) -> VerifyResult:
                return VerifyResult(passed=True)

        assert isinstance(DummyVerifier(), Verifier)

    def test_tool_spec_protocol(self) -> None:
        """A class with name, description, schema(), execute() satisfies ToolSpec."""

        class DummyTool:
            @property
            def name(self) -> str:
                return "dummy_tool"
            @property
            def description(self) -> str:
                return "A dummy tool"
            def schema(self) -> dict[str, Any]:
                return {"type": "object", "properties": {}}
            def execute(self, **kwargs: Any) -> ToolOutput:
                return ToolOutput(ok=True, content="done")

        assert isinstance(DummyTool(), ToolSpec)

    def test_plain_class_does_not_satisfy_runner(self) -> None:
        """A class missing methods should NOT satisfy LoopRunner."""

        class NotARunner:
            pass

        assert not isinstance(NotARunner(), LoopRunner)
