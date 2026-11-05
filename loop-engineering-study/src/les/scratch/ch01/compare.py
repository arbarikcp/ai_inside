"""Chain vs loop comparison on the 10 Fix-the-function tasks.

Run:
    uv run python -m les.scratch.ch01.compare              # scripted mock
    uv run python -m les.scratch.ch01.compare --model local  # alias in models.yaml
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass, field

from llm.base import LLMClient

from les.contracts import LoopResult, LoopRunner
from les.models import ModelSpec, raw_client, resolve

from .chain import SingleShotChain
from .fixer_mock import FixerMock
from .loop import AnatomyLoop
from .tasks import FIX_TASKS, FixTask

RunnerFactory = Callable[[], LoopRunner]


@dataclass
class RunnerScore:
    """Aggregate results for one runner across all tasks."""

    name: str
    results: dict[str, LoopResult] = field(default_factory=dict)

    @property
    def solved(self) -> int:
        return sum(1 for r in self.results.values() if r.success)

    @property
    def total_tokens(self) -> int:
        return sum(r.total_tokens for r in self.results.values())

    @property
    def total_cost(self) -> float:
        return sum(r.cost_usd for r in self.results.values())

    @property
    def mean_iterations(self) -> float:
        n = len(self.results)
        return sum(r.iterations for r in self.results.values()) / n if n else 0.0


def compare(
    runners: dict[str, RunnerFactory], tasks: list[FixTask]
) -> list[RunnerScore]:
    """Run every runner on every task (fresh runner per task)."""
    scores = []
    for name, factory in runners.items():
        score = RunnerScore(name)
        for task in tasks:
            score.results[task.task_id] = factory().run(task.goal, task=task)
        scores.append(score)
    return scores


def render_markdown(scores: list[RunnerScore], tasks: list[FixTask]) -> str:
    """Render a summary table and a per-task table."""
    lines = [
        "| Runner | Solved | Mean iterations | Tokens | Cost (USD) |",
        "|---|---|---|---|---|",
    ]
    for s in scores:
        lines.append(
            f"| {s.name} | {s.solved}/{len(s.results)} | {s.mean_iterations:.1f} "
            f"| {s.total_tokens} | {s.total_cost:.4f} |"
        )
    lines += ["", "| Task | " + " | ".join(s.name for s in scores) + " |"]
    lines.append("|---" * (len(scores) + 1) + "|")
    for t in tasks:
        cells = [("✅" if s.results[t.task_id].success else "❌") for s in scores]
        lines.append(f"| {t.task_id} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def build_runners(model: str) -> dict[str, RunnerFactory]:
    """Runner factories for a model alias. 'mock' uses the scripted FixerMock."""
    spec: ModelSpec = resolve(model)

    def llm() -> LLMClient:
        return FixerMock() if spec.family == "mock" else raw_client(model)

    return {
        "chain": lambda: SingleShotChain(llm=llm(), spec=spec),
        "loop": lambda: AnatomyLoop(llm=llm(), spec=spec),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ch 1: single-shot chain vs loop")
    parser.add_argument(
        "--model", default="mock", help="alias or role from models.yaml"
    )
    args = parser.parse_args(argv)
    scores = compare(build_runners(args.model), FIX_TASKS)
    print(f"# Ch 1 — chain vs loop on {len(FIX_TASKS)} tasks (model: {args.model})\n")
    print(render_markdown(scores, FIX_TASKS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
