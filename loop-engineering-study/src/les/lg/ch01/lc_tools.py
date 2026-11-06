"""Adapter: our ``ToolSpec`` contract → LangChain ``StructuredTool``.

The tools themselves (read_file, write_file, run_tests) are reused from the
scratch build unchanged. Only the wrapper differs, which keeps tool behaviour
identical across builds.
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import StructuredTool

from les.contracts import ToolSpec


def to_lc_tool(spec: ToolSpec) -> StructuredTool:
    """Wrap a ToolSpec so LangChain / LangGraph can call it."""

    def _run(**kwargs: Any) -> str:
        return spec.execute(**kwargs).content

    return StructuredTool.from_function(
        func=_run,
        name=spec.name,
        description=spec.description,
        args_schema=spec.schema(),
    )


def to_lc_tools(specs: dict[str, ToolSpec]) -> list[StructuredTool]:
    """Wrap every ToolSpec in a name → spec mapping."""
    return [to_lc_tool(s) for s in specs.values()]
