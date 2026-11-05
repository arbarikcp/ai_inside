"""Contract protocols for the study builds.

Both the scratch and LangGraph implementations must satisfy these protocols.
Contract tests are parametrized over every implementation, so adding a new
backend means registering it in conftest — the tests stay the same.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Shared value objects
# ---------------------------------------------------------------------------

class StopReason(str, Enum):
    """Named stop reasons — every loop exit must use one of these."""

    SUCCESS = "success"
    BUDGET_ITERATIONS = "budget_iterations"
    BUDGET_TOKENS = "budget_tokens"
    BUDGET_TIME = "budget_time"
    BUDGET_COST = "budget_cost"
    NO_PROGRESS = "no_progress"
    BLOCKED = "blocked"
    HUMAN_REQUESTED = "human_requested"
    KILL_SWITCH = "kill_switch"
    ERROR = "error"


@dataclass
class LoopResult:
    """The outcome of a finished loop run.

    Every implementation (scratch, LangGraph, comparison) must produce this.
    """

    success: bool
    stop_reason: StopReason
    final_output: str = ""
    iterations: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    tool_calls: int = 0
    trace_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def total_cost(self) -> float:
        return self.cost_usd


@dataclass
class ToolInput:
    """A tool call request to be validated and executed."""

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    call_id: str = ""


@dataclass
class ToolOutput:
    """The result of executing a tool."""

    ok: bool
    content: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class VerifyResult:
    """The outcome of a verification check."""

    passed: bool
    reason: str = ""
    score: float = 0.0


# ---------------------------------------------------------------------------
# Protocols — the contracts that scratch and LangGraph builds must satisfy
# ---------------------------------------------------------------------------

@runtime_checkable
class LoopRunner(Protocol):
    """Protocol for running an agent loop.

    Both scratch and LangGraph builds expose this interface. Contract tests
    are parametrized over implementations of this protocol.
    """

    def run(self, goal: str, **kwargs: Any) -> LoopResult:
        """Run the loop to completion and return a LoopResult."""
        ...

    def get_state(self) -> dict[str, Any]:
        """Return the current serializable state of the loop."""
        ...


@runtime_checkable
class ResumableRunner(LoopRunner, Protocol):
    """A LoopRunner that can be resumed from a saved state."""

    def resume(self, state: dict[str, Any], **kwargs: Any) -> LoopResult:
        """Resume a loop from a previously saved state."""
        ...


@runtime_checkable
class Verifier(Protocol):
    """Protocol for verification checks (Ch 8)."""

    @property
    def name(self) -> str:
        """Human-readable name for this verifier."""
        ...

    def verify(self, output: str, **context: Any) -> VerifyResult:
        """Check output against criteria and return a VerifyResult."""
        ...


@runtime_checkable
class ToolSpec(Protocol):
    """Protocol for tool definitions (Ch 6)."""

    @property
    def name(self) -> str:
        """The tool name as exposed to the model."""
        ...

    @property
    def description(self) -> str:
        """Short description for the model."""
        ...

    def schema(self) -> dict[str, Any]:
        """JSON schema for the tool parameters."""
        ...

    def execute(self, **kwargs: Any) -> ToolOutput:
        """Execute the tool with validated arguments."""
        ...
