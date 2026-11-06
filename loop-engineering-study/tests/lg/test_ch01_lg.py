"""Unit tests for the Ch 1 LangGraph build (Task 5)."""

from __future__ import annotations

import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from llm.base import LLMResponse, ToolCall

from les.contracts import StopReason
from les.lg.ch01 import FixerChatModel, LGAgentLoop, anatomy_stages, to_lc_tool
from les.lg.ch01.chat_mock import to_ai_message, to_lab_messages
from les.scratch.ch01 import AnatomyLoop
from les.scratch.ch01.tasks import FIX_TASKS, TASKS_BY_ID
from les.scratch.ch01.tools import make_tools
from les.scratch.ch01.workspace import SOLUTION_FILE, TaskWorkspace

ADD = TASKS_BY_ID["add"]
FACT = TASKS_BY_ID["factorial"]


class TestMessageConversion:
    def test_to_lab_messages_roles(self) -> None:
        msgs = to_lab_messages(
            [
                SystemMessage("s"),
                HumanMessage("h"),
                AIMessage("a"),
                ToolMessage("t", tool_call_id="read_file-1"),
            ]
        )
        assert [m.role for m in msgs] == ["system", "user", "assistant", "tool"]
        assert msgs[3].tool_call_id == "read_file-1"

    def test_to_ai_message_tool_calls_and_usage(self) -> None:
        resp = LLMResponse(
            tool_calls=[ToolCall(id="run_tests-1", name="run_tests")],
            prompt_tokens=7,
            completion_tokens=3,
        )
        ai = to_ai_message(resp)
        assert ai.tool_calls[0]["name"] == "run_tests"
        assert ai.tool_calls[0]["id"] == "run_tests-1"
        assert ai.usage_metadata == {
            "input_tokens": 7,
            "output_tokens": 3,
            "total_tokens": 10,
        }


class TestFixerChatModel:
    def test_without_tools_behaves_like_chain(self) -> None:
        out = FixerChatModel().invoke([HumanMessage("Task id: factorial")])
        assert not out.tool_calls
        assert FACT.wrong_fix in out.content

    def test_bind_tools_switches_to_loop_and_shares_policy(self) -> None:
        base = FixerChatModel()
        with TaskWorkspace(ADD) as ws:
            bound = base.bind_tools([to_lc_tool(t) for t in make_tools(ws).values()])
        assert len(bound.bound_tools) == 3
        out = bound.invoke([HumanMessage("Task id: add")])
        assert out.tool_calls[0]["name"] == "read_file"
        assert base.call_count == 1  # same FixerMock behind both


class TestLcTools:
    def test_wraps_toolspec(self) -> None:
        with TaskWorkspace(ADD) as ws:
            tool = to_lc_tool(make_tools(ws)["read_file"])
            assert tool.name == "read_file"
            assert "def add" in tool.invoke({"path": SOLUTION_FILE})

    def test_soft_errors_pass_through(self) -> None:
        with TaskWorkspace(ADD) as ws:
            tool = to_lc_tool(make_tools(ws)["write_file"])
            assert "error" in tool.invoke({"path": "../x.py", "content": ""})


class TestLGAgentLoop:
    def test_solves_task_chain_cannot(self) -> None:
        result = LGAgentLoop().run(FACT.goal, task=FACT)
        assert result.success
        assert result.stop_reason is StopReason.SUCCESS
        assert result.final_output == FACT.correct_fix
        assert result.iterations == 6
        assert result.tool_calls == 5

    @pytest.mark.parametrize("task", FIX_TASKS, ids=lambda t: t.task_id)
    def test_parity_with_scratch_loop(self, task) -> None:
        """Same model policy → identical iterations, tools, tokens, stages."""
        lg = LGAgentLoop().run(task.goal, task=task)
        sc = AnatomyLoop().run(task.goal, task=task)
        assert (lg.success, lg.iterations, lg.tool_calls, lg.total_tokens) == (
            sc.success,
            sc.iterations,
            sc.tool_calls,
            sc.total_tokens,
        )
        assert lg.metadata["stages"] == sc.metadata["stages"]

    @pytest.mark.parametrize("budget", [1, 2, 3])
    def test_recursion_limit_enforces_iteration_budget(self, budget: int) -> None:
        result = LGAgentLoop(max_iterations=budget).run(FACT.goal, task=FACT)
        assert not result.success
        assert result.stop_reason is StopReason.BUDGET_ITERATIONS
        assert result.iterations == budget

    def test_verification_feedback_resumes_same_thread(self) -> None:
        # Model claims "done" with no fix; loop must feed back and keep going.
        class Liar(FixerChatModel):
            def _generate(self, messages, stop=None, run_manager=None, **kw):  # type: ignore[override]
                from langchain_core.outputs import ChatGeneration, ChatResult

                return ChatResult(
                    generations=[ChatGeneration(message=AIMessage("done!"))]
                )

        loop = LGAgentLoop(model=Liar(), task=ADD, max_iterations=3)
        result = loop.run(ADD.goal)
        assert not result.success
        assert result.iterations == 3
        humans = [m for m in loop.get_state()["messages"] if m["role"] == "human"]
        # 3 rejected claims, but only 2 feedbacks are *sent*: after the 3rd
        # rejection the budget is spent, so the graph is never resumed.
        assert sum(m["content"].startswith("Verification failed") for m in humans) == 2
        assert result.metadata["stages"].count("adjustment") == 2

    def test_state_is_json_serializable(self) -> None:
        loop = LGAgentLoop()
        loop.run(FACT.goal, task=FACT)
        state = loop.get_state()
        json.dumps(state)
        assert state["thread_id"].startswith("factorial-")
        ai_with_calls = [m for m in state["messages"] if m.get("tool_calls")]
        assert ai_with_calls[0]["tool_calls"][0]["name"] == "read_file"

    def test_mermaid_shows_model_tools_cycle(self) -> None:
        src = LGAgentLoop().mermaid()
        for edge in ("__start__ --> model", "model -.-> tools", "tools -.-> model"):
            assert edge in src
        assert "read_file, write_file, run_tests" in src


class TestAnatomyStages:
    def test_empty(self) -> None:
        assert anatomy_stages([]) == []

    def test_failed_tests_add_adjustment(self) -> None:
        msgs = [
            HumanMessage("Task id: x"),
            ToolMessage("FAILED 1", tool_call_id="c1", name="run_tests"),
            ToolMessage("PASSED", tool_call_id="c2", name="run_tests"),
        ]
        assert anatomy_stages(msgs) == [
            "intent",
            "context",
            "action",
            "observation",
            "adjustment",
            "action",
            "observation",
        ]
