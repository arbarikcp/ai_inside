"""Ch 1 cross-build report: scratch chain, scratch loop, LangGraph, Agents SDK.

Run:
    uv run python -m les.compare.ch01_report              # all offline (mock)
    uv run python -m les.compare.ch01_report --model local
    uv run python -m les.compare.ch01_report --graph      # print the LG graph
"""

from __future__ import annotations

import argparse

from les.compare.openai_agents.ch01 import SDKAgentLoop, sdk_model
from les.lg.ch01 import FixerChatModel, LGAgentLoop
from les.models import chat_model, resolve
from les.scratch.ch01.compare import (
    RunnerFactory,
    build_runners,
    compare,
    render_markdown,
)
from les.scratch.ch01.tasks import FIX_TASKS


def build_all_runners(model: str) -> dict[str, RunnerFactory]:
    """Factories for every Ch 1 build on one model alias."""
    spec = resolve(model)
    mock = spec.family == "mock"
    runners = build_runners(model)  # chain + scratch loop
    runners["langgraph"] = lambda: LGAgentLoop(
        model=FixerChatModel() if mock else chat_model(model), spec=spec
    )
    runners["openai_sdk"] = lambda: SDKAgentLoop(model=sdk_model(model), spec=spec)
    return runners


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ch 1: every build on 10 tasks")
    parser.add_argument("--model", default="mock", help="alias or role in models.yaml")
    parser.add_argument("--graph", action="store_true", help="print LG graph and exit")
    args = parser.parse_args(argv)
    if args.graph:
        print(LGAgentLoop().mermaid())
        return 0
    scores = compare(build_all_runners(args.model), FIX_TASKS)
    print(f"# Ch 1: all builds on {len(FIX_TASKS)} tasks (model: {args.model})\n")
    print(render_markdown(scores, FIX_TASKS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
