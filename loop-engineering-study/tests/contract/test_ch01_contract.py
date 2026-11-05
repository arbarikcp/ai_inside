"""Ch 1 contract tests — every Ch 1 runner (scratch now, LangGraph in Task 5)."""

from __future__ import annotations

import json

import pytest

from les.contracts import LoopResult, LoopRunner, StopReason
from les.scratch.ch01.tasks import TASKS_BY_ID

CH01_RUNNERS = ["ch01_scratch_chain", "ch01_scratch_loop", "ch01_lg"]


@pytest.mark.parametrize("runner_name", CH01_RUNNERS)
class TestCh01Contract:
    def test_is_loop_runner(self, runner_name, runner_factory) -> None:
        assert isinstance(runner_factory(runner_name), LoopRunner)

    def test_run_returns_loop_result(self, runner_name, runner_factory) -> None:
        task = TASKS_BY_ID["add"]
        result = runner_factory(runner_name).run(task.goal, task=task)
        assert isinstance(result, LoopResult)
        assert isinstance(result.stop_reason, StopReason)
        assert result.success == (result.stop_reason is StopReason.SUCCESS)
        assert result.iterations >= 1
        assert result.total_tokens == result.prompt_tokens + result.completion_tokens

    def test_easy_task_succeeds(self, runner_name, runner_factory) -> None:
        task = TASKS_BY_ID["add"]
        assert runner_factory(runner_name).run(task.goal, task=task).success

    def test_failure_has_named_stop_reason(self, runner_name, runner_factory) -> None:
        task = TASKS_BY_ID["factorial"]
        result = runner_factory(runner_name).run(task.goal, task=task)
        if not result.success:
            assert result.stop_reason is not StopReason.SUCCESS

    def test_state_is_json_serializable(self, runner_name, runner_factory) -> None:
        runner = runner_factory(runner_name)
        task = TASKS_BY_ID["add"]
        runner.run(task.goal, task=task)
        state = runner.get_state()
        assert json.loads(json.dumps(state))["task_id"] == "add"
