"""Mini-lab tools: read_file, write_file, run_tests.

Each tool satisfies the ``ToolSpec`` contract and is bound to one
``TaskWorkspace``. Tools never raise: failures come back as
``ToolOutput(ok=False)`` so the loop can observe and adjust.
"""

from __future__ import annotations

from typing import Any

from les.contracts import ToolOutput, ToolSpec

from .workspace import TaskWorkspace


class ReadFileTool:
    """Read a file from the workspace."""

    name = "read_file"
    description = "Read a text file from the workspace."

    def __init__(self, ws: TaskWorkspace) -> None:
        self._ws = ws

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative file path"}
            },
            "required": ["path"],
        }

    def execute(self, **kwargs: Any) -> ToolOutput:
        path = str(kwargs.get("path", ""))
        try:
            return ToolOutput(ok=True, content=self._ws.read(path))
        except (OSError, ValueError) as exc:
            return ToolOutput(ok=False, content=f"read_file error: {exc}")


class WriteFileTool:
    """Overwrite a file in the workspace."""

    name = "write_file"
    description = "Overwrite a file in the workspace with new content."

    def __init__(self, ws: TaskWorkspace) -> None:
        self._ws = ws

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative file path"},
                "content": {"type": "string", "description": "Full new file content"},
            },
            "required": ["path", "content"],
        }

    def execute(self, **kwargs: Any) -> ToolOutput:
        path = str(kwargs.get("path", ""))
        content = str(kwargs.get("content", ""))
        try:
            self._ws.write(path, content)
            return ToolOutput(ok=True, content=f"wrote {len(content)} chars to {path}")
        except (OSError, ValueError) as exc:
            return ToolOutput(ok=False, content=f"write_file error: {exc}")


class RunTestsTool:
    """Run the workspace test file."""

    name = "run_tests"
    description = "Run the tests and return their output (PASSED or FAILED ...)."

    def __init__(self, ws: TaskWorkspace) -> None:
        self._ws = ws

    def schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    def execute(self, **kwargs: Any) -> ToolOutput:
        run = self._ws.run_tests()
        return ToolOutput(
            ok=run.passed, content=run.output, data={"passed": run.passed}
        )


def make_tools(ws: TaskWorkspace) -> dict[str, ToolSpec]:
    """Build the three mini-lab tools bound to a workspace, keyed by name."""
    tools: list[ToolSpec] = [ReadFileTool(ws), WriteFileTool(ws), RunTestsTool(ws)]
    return {t.name: t for t in tools}


def function_schemas(tools: dict[str, ToolSpec]) -> list[dict[str, Any]]:
    """Wrap ToolSpec schemas in the OpenAI function format LLMClient expects."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.schema(),
            },
        }
        for t in tools.values()
    ]
