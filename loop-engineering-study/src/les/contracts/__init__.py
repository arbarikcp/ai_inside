"""Contract protocols — the shared interface between all builds."""

from .protocols import (
    LoopResult,
    LoopRunner,
    ResumableRunner,
    StopReason,
    ToolInput,
    ToolOutput,
    ToolSpec,
    Verifier,
    VerifyResult,
)

__all__ = [
    "LoopResult",
    "LoopRunner",
    "ResumableRunner",
    "StopReason",
    "ToolInput",
    "ToolOutput",
    "ToolSpec",
    "Verifier",
    "VerifyResult",
]
