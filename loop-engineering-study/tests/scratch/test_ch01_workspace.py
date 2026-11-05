"""Unit tests for Ch 1 tasks, workspace, tools and verifier."""

from __future__ import annotations

import pytest

from les.contracts import ToolSpec, Verifier
from les.scratch.ch01.tasks import FIX_TASKS, TASKS_BY_ID
from les.scratch.ch01.tools import function_schemas, make_tools
from les.scratch.ch01.verifier import TestsPassVerifier
from les.scratch.ch01.workspace import SOLUTION_FILE, TEST_FILE, TaskWorkspace


class TestFixTasks:
    def test_ten_unique_tasks(self) -> None:
        assert len(FIX_TASKS) == 10
        assert len(TASKS_BY_ID) == 10

    def test_half_have_wrong_fix(self) -> None:
        assert sum(1 for t in FIX_TASKS if t.wrong_fix) == 5

    def test_first_attempt_falls_back_to_correct(self) -> None:
        add = TASKS_BY_ID["add"]
        assert add.first_attempt == add.correct_fix
        fact = TASKS_BY_ID["factorial"]
        assert fact.first_attempt == fact.wrong_fix

    def test_goal_mentions_function(self) -> None:
        assert "factorial" in TASKS_BY_ID["factorial"].goal


@pytest.mark.parametrize("task", FIX_TASKS, ids=lambda t: t.task_id)
class TestTaskSemantics:
    """Each task must be a real bug: buggy fails, correct passes, wrong fails."""

    def test_buggy_fails(self, task) -> None:
        with TaskWorkspace(task) as ws:
            assert not ws.run_tests().passed

    def test_correct_fix_passes(self, task) -> None:
        with TaskWorkspace(task) as ws:
            ws.write(SOLUTION_FILE, task.correct_fix)
            run = ws.run_tests()
            assert run.passed, run.output
            assert "PASSED" in run.output

    def test_wrong_fix_fails(self, task) -> None:
        if not task.wrong_fix:
            pytest.skip("no wrong fix")
        with TaskWorkspace(task) as ws:
            ws.write(SOLUTION_FILE, task.wrong_fix)
            assert not ws.run_tests().passed


class TestTaskWorkspace:
    def test_files_created_and_cleaned_up(self) -> None:
        with TaskWorkspace(FIX_TASKS[0]) as ws:
            root = ws.root
            assert ws.list_files() == [SOLUTION_FILE, TEST_FILE]
        assert not root.exists()

    def test_path_escape_rejected(self) -> None:
        with TaskWorkspace(FIX_TASKS[0]) as ws:
            with pytest.raises(ValueError, match="escapes"):
                ws.read("../../etc/passwd")

    def test_test_file_is_read_only(self) -> None:
        with TaskWorkspace(FIX_TASKS[0]) as ws:
            with pytest.raises(ValueError, match="read-only"):
                ws.write(TEST_FILE, "")

    def test_syntax_error_reported_not_raised(self) -> None:
        with TaskWorkspace(FIX_TASKS[0]) as ws:
            ws.write(SOLUTION_FILE, "def add(:\n")
            run = ws.run_tests()
            assert not run.passed
            assert "SyntaxError" in run.output

    def test_timeout(self) -> None:
        with TaskWorkspace(FIX_TASKS[0], timeout_s=0.5) as ws:
            ws.write(SOLUTION_FILE, "while True:\n    pass\n")
            run = ws.run_tests()
            assert not run.passed
            assert "TIMEOUT" in run.output


class TestTools:
    def test_tools_satisfy_toolspec(self) -> None:
        with TaskWorkspace(FIX_TASKS[0]) as ws:
            tools = make_tools(ws)
            assert set(tools) == {"read_file", "write_file", "run_tests"}
            for tool in tools.values():
                assert isinstance(tool, ToolSpec)

    def test_read_write_roundtrip(self) -> None:
        with TaskWorkspace(FIX_TASKS[0]) as ws:
            tools = make_tools(ws)
            assert tools["write_file"].execute(path=SOLUTION_FILE, content="x = 1\n").ok
            out = tools["read_file"].execute(path=SOLUTION_FILE)
            assert out.ok and out.content == "x = 1\n"

    def test_read_missing_file_is_soft_error(self) -> None:
        with TaskWorkspace(FIX_TASKS[0]) as ws:
            out = make_tools(ws)["read_file"].execute(path="nope.py")
            assert not out.ok
            assert "error" in out.content

    def test_write_escape_is_soft_error(self) -> None:
        with TaskWorkspace(FIX_TASKS[0]) as ws:
            out = make_tools(ws)["write_file"].execute(path="../x.py", content="")
            assert not out.ok

    def test_run_tests_reports_pass_flag(self) -> None:
        task = FIX_TASKS[0]
        with TaskWorkspace(task) as ws:
            tools = make_tools(ws)
            assert tools["run_tests"].execute().data["passed"] is False
            ws.write(SOLUTION_FILE, task.correct_fix)
            assert tools["run_tests"].execute().data["passed"] is True

    def test_function_schemas_format(self) -> None:
        with TaskWorkspace(FIX_TASKS[0]) as ws:
            schemas = function_schemas(make_tools(ws))
        assert {s["function"]["name"] for s in schemas} == {
            "read_file",
            "write_file",
            "run_tests",
        }
        assert all(s["type"] == "function" for s in schemas)


class TestTestsPassVerifier:
    def test_satisfies_protocol_and_judges_by_tests(self) -> None:
        task = FIX_TASKS[0]
        with TaskWorkspace(task) as ws:
            verifier = TestsPassVerifier(ws)
            assert isinstance(verifier, Verifier)
            assert verifier.name == "tests_pass"
            failed = verifier.verify("I fixed it, trust me")
            assert not failed.passed and failed.score == 0.0
            ws.write(SOLUTION_FILE, task.correct_fix)
            ok = verifier.verify("")
            assert ok.passed and ok.score == 1.0
