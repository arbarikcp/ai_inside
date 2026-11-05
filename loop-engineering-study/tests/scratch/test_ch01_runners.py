"""Unit tests for Ch 1 FixerMock, SingleShotChain, AnatomyLoop and compare."""

from __future__ import annotations

import json

import pytest
from llm.base import LLMResponse, Message, ToolCall
from llm.mock import MockLLM, say

from les.contracts import StopReason
from les.models import ModelSpec
from les.scratch.ch01.chain import SingleShotChain, extract_code
from les.scratch.ch01.compare import build_runners, compare, main, render_markdown
from les.scratch.ch01.fixer_mock import FixerMock
from les.scratch.ch01.loop import AnatomyLoop
from les.scratch.ch01.tasks import FIX_TASKS, TASKS_BY_ID

ADD = TASKS_BY_ID["add"]
FACT = TASKS_BY_ID["factorial"]


class TestFixerMock:
    def test_requires_task_id(self) -> None:
        with pytest.raises(ValueError, match="Task id"):
            FixerMock().complete([Message("user", "fix it")])

    def test_chain_mode_returns_first_attempt(self) -> None:
        resp = FixerMock().complete([Message("user", "Task id: factorial")])
        assert not resp.wants_tool
        assert FACT.wrong_fix in resp.text

    def test_loop_mode_starts_by_reading(self) -> None:
        resp = FixerMock().complete([Message("user", "Task id: add")], tools=[{}])
        assert resp.tool_calls[0].name == "read_file"
        assert resp.tool_calls[0].id == "read_file-1"

    def test_loop_mode_fixes_after_failed_tests(self) -> None:
        msgs = [
            Message("user", "Task id: factorial"),
            Message("tool", "FAILED 1", tool_call_id="run_tests-1"),
        ]
        resp = FixerMock().complete(msgs, tools=[{}])
        call = resp.tool_calls[0]
        assert call.name == "write_file"
        assert call.arguments["content"] == FACT.correct_fix


class TestExtractCode:
    def test_fenced_block(self) -> None:
        assert extract_code("text\n```python\nx = 1\n```\nmore") == "x = 1\n"

    def test_plain_text_fallback(self) -> None:
        assert extract_code("x = 1\n") == "x = 1\n"


class TestSingleShotChain:
    def test_solves_easy_task(self) -> None:
        result = SingleShotChain(task=ADD).run(ADD.goal)
        assert result.success
        assert result.stop_reason is StopReason.SUCCESS
        assert result.iterations == 1
        assert result.tool_calls == 0

    def test_fails_when_first_answer_wrong(self) -> None:
        result = SingleShotChain().run(FACT.goal, task=FACT)
        assert not result.success
        assert result.stop_reason is StopReason.BUDGET_ITERATIONS
        assert "FAIL" in result.metadata["verdict"]

    def test_state_is_json_serializable(self) -> None:
        chain = SingleShotChain()
        chain.run(ADD.goal)
        state = chain.get_state()
        json.dumps(state)
        assert state["task_id"] == "add"
        assert state["messages"][-1]["role"] == "assistant"

    def test_cost_uses_spec_prices(self) -> None:
        spec = ModelSpec(alias="x", family="mock", price_in=1_000_000, price_out=0)
        result = SingleShotChain(spec=spec).run(ADD.goal)
        assert result.cost_usd == pytest.approx(result.prompt_tokens)


class TestAnatomyLoop:
    def test_solves_task_chain_cannot(self) -> None:
        result = AnatomyLoop().run(FACT.goal, task=FACT)
        assert result.success
        assert result.stop_reason is StopReason.SUCCESS
        assert result.final_output == FACT.correct_fix
        # read, write(wrong), test, write(correct), test, final answer
        assert result.iterations == 6
        assert result.tool_calls == 5

    def test_stages_follow_anatomy(self) -> None:
        result = AnatomyLoop().run(FACT.goal, task=FACT)
        stages = result.metadata["stages"]
        assert stages[:2] == ["intent", "context"]
        assert {"action", "observation", "adjustment"} <= set(stages)

    def test_no_adjustment_when_first_fix_right(self) -> None:
        result = AnatomyLoop(task=ADD).run(ADD.goal)
        assert result.success
        assert "adjustment" not in result.metadata["stages"]

    def test_iteration_budget(self) -> None:
        result = AnatomyLoop(max_iterations=2).run(FACT.goal, task=FACT)
        assert not result.success
        assert result.stop_reason is StopReason.BUDGET_ITERATIONS
        assert result.iterations == 2

    def test_unverified_claim_is_rejected(self) -> None:
        # Model claims success without fixing anything, then gives up.
        llm = MockLLM(responses=[say("done!"), say("really done")])
        result = AnatomyLoop(llm=llm, task=ADD, max_iterations=2).run(ADD.goal)
        assert not result.success
        assert "Verification failed" in result.final_output

    def test_unknown_tool_is_observed_not_raised(self) -> None:
        bad = LLMResponse(tool_calls=[ToolCall(id="x-1", name="rm_rf", arguments={})])
        llm = MockLLM(responses=[bad])
        loop = AnatomyLoop(llm=llm, task=ADD, max_iterations=1)
        result = loop.run(ADD.goal)
        assert not result.success
        tool_msgs = [m for m in loop.get_state()["messages"] if m["role"] == "tool"]
        assert "unknown tool" in tool_msgs[0]["content"]

    def test_state_is_json_serializable(self) -> None:
        loop = AnatomyLoop()
        loop.run(ADD.goal)
        state = loop.get_state()
        json.dumps(state)
        assert state["iteration"] >= 1


class TestCompare:
    def test_loop_beats_chain_on_mock(self) -> None:
        scores = {s.name: s for s in compare(build_runners("mock"), FIX_TASKS)}
        assert scores["chain"].solved == 5
        assert scores["loop"].solved == 10
        assert scores["loop"].total_tokens > scores["chain"].total_tokens
        assert scores["chain"].mean_iterations == 1.0

    def test_render_markdown(self) -> None:
        tasks = FIX_TASKS[:2]
        md = render_markdown(compare(build_runners("mock"), tasks), tasks)
        assert "| chain | 2/2 |" in md
        assert "| add | ✅ | ✅ |" in md

    def test_main_prints_report(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["--model", "mock"]) == 0
        out = capsys.readouterr().out
        assert "chain vs loop" in out
        assert "| loop | 10/10 |" in out
