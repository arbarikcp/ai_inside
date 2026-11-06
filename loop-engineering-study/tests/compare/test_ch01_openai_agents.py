"""Unit tests for the Ch 1 OpenAI Agents SDK spike and the cross-build report."""

from __future__ import annotations

import asyncio
import json

import pytest
from llm.base import LLMResponse, ToolCall

from les.compare.ch01_report import build_all_runners, main
from les.compare.openai_agents.ch01 import (
    FixerSDKModel,
    SDKAgentLoop,
    anatomy_stages,
    sdk_model,
    to_lab_messages,
    to_model_response,
    to_sdk_tool,
)
from les.contracts import StopReason
from les.scratch.ch01 import AnatomyLoop
from les.scratch.ch01.compare import compare
from les.scratch.ch01.tasks import FIX_TASKS, TASKS_BY_ID
from les.scratch.ch01.tools import make_tools
from les.scratch.ch01.workspace import SOLUTION_FILE, TaskWorkspace

ADD = TASKS_BY_ID["add"]
FACT = TASKS_BY_ID["factorial"]


class TestConversion:
    def test_input_items_to_lab_messages(self) -> None:
        items = [
            {"role": "user", "content": "Task id: add"},
            {"type": "function_call", "call_id": "read_file-1", "name": "read_file"},
            {"type": "function_call_output", "call_id": "read_file-1", "output": "src"},
            {"role": "assistant", "content": [{"type": "output_text", "text": "ok"}]},
        ]
        msgs = to_lab_messages("sys", items)
        assert [m.role for m in msgs] == ["system", "user", "tool", "assistant"]
        assert msgs[2].tool_call_id == "read_file-1"
        assert msgs[3].content == "ok"

    def test_string_input(self) -> None:
        assert [m.role for m in to_lab_messages(None, "hi")] == ["user"]

    def test_tool_call_response(self) -> None:
        resp = LLMResponse(
            tool_calls=[
                ToolCall(id="write_file-1", name="write_file", arguments={"path": "a"})
            ],
            prompt_tokens=5,
            completion_tokens=2,
        )
        mr = to_model_response(resp)
        assert mr.output[0].type == "function_call"
        assert json.loads(mr.output[0].arguments) == {"path": "a"}
        assert mr.usage.total_tokens == 7

    def test_text_response(self) -> None:
        mr = to_model_response(LLMResponse(text="done"))
        assert mr.output[0].type == "message"
        assert mr.output[0].content[0].text == "done"


class TestSdkTool:
    def test_invokes_toolspec(self) -> None:
        with TaskWorkspace(ADD) as ws:
            tool = to_sdk_tool(make_tools(ws)["read_file"])
            assert tool.name == "read_file"
            out = asyncio.run(
                tool.on_invoke_tool(None, json.dumps({"path": SOLUTION_FILE}))
            )
            assert "def add" in out


class TestFixerSDKModel:
    def test_no_tools_gives_chain_answer(self) -> None:
        model = FixerSDKModel()
        mr = asyncio.run(
            model.get_response(None, "Task id: factorial", None, [], None, [], None)
        )
        assert FACT.wrong_fix in mr.output[0].content[0].text


class TestSDKAgentLoop:
    def test_solves_task_chain_cannot(self) -> None:
        result = SDKAgentLoop().run(FACT.goal, task=FACT)
        assert result.success
        assert result.final_output == FACT.correct_fix
        assert (result.iterations, result.tool_calls) == (6, 5)

    @pytest.mark.parametrize("task", FIX_TASKS, ids=lambda t: t.task_id)
    def test_parity_with_scratch_loop(self, task) -> None:
        sdk = SDKAgentLoop().run(task.goal, task=task)
        sc = AnatomyLoop().run(task.goal, task=task)
        assert (sdk.success, sdk.iterations, sdk.tool_calls, sdk.total_tokens) == (
            sc.success,
            sc.iterations,
            sc.tool_calls,
            sc.total_tokens,
        )
        assert sdk.metadata["stages"] == sc.metadata["stages"]

    @pytest.mark.parametrize("budget", [1, 2, 3])
    def test_max_turns_enforces_iteration_budget(self, budget: int) -> None:
        result = SDKAgentLoop(max_iterations=budget).run(FACT.goal, task=FACT)
        assert not result.success
        assert result.stop_reason is StopReason.BUDGET_ITERATIONS
        assert result.iterations == budget

    def test_state_is_json_serializable(self) -> None:
        loop = SDKAgentLoop()
        loop.run(ADD.goal, task=ADD)
        json.dumps(loop.get_state())
        assert loop.get_state()["runner"] == "ch01_oai_sdk"


class TestStagesAndModels:
    def test_stages_from_items(self) -> None:
        items = [
            {"role": "user", "content": "Task id: x"},
            {"type": "function_call", "call_id": "c1", "name": "run_tests"},
            {"type": "function_call_output", "call_id": "c1", "output": "FAILED 1"},
            {"role": "user", "content": "Verification failed:\nboom"},
        ]
        assert anatomy_stages(items) == [
            "intent",
            "context",
            "action",
            "observation",
            "adjustment",
            "adjustment",
        ]

    def test_sdk_model_for_mock_and_openai(self) -> None:
        assert isinstance(sdk_model("mock"), FixerSDKModel)
        assert sdk_model("gpt") == "gpt-4.1-mini"

    def test_sdk_model_rejects_unwired_family(self) -> None:
        with pytest.raises(ValueError, match="not wired"):
            sdk_model("claude")


class TestCh01Report:
    def test_all_builds_on_mock(self) -> None:
        scores = {s.name: s for s in compare(build_all_runners("mock"), FIX_TASKS)}
        assert set(scores) == {"chain", "loop", "langgraph", "openai_sdk"}
        assert scores["chain"].solved == 5
        for name in ("loop", "langgraph", "openai_sdk"):
            assert scores[name].solved == 10
            assert scores[name].total_tokens == scores["loop"].total_tokens

    def test_main_graph_flag(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["--graph"]) == 0
        assert "tools -.-> model" in capsys.readouterr().out
