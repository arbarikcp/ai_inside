"""Contract test fixtures — parametrized over implementations.

Each chapter registers its scratch and LangGraph builds here.
Contract tests import the `runner` fixture and test against the protocol,
so both implementations must pass the same suite.
"""
from __future__ import annotations

import pytest

# Registry of LoopRunner implementations.
# Each chapter adds to this via conftest or registration functions.
# Format: {"ch01_scratch": <LoopRunner factory>, "ch01_lg": <LoopRunner factory>}
RUNNER_REGISTRY: dict[str, type] = {}


def register_runner(name: str, factory: type) -> None:
    """Register a LoopRunner implementation for contract testing."""
    RUNNER_REGISTRY[name] = factory


# --- Chapter registrations --------------------------------------------------
from les.scratch.ch01 import AnatomyLoop, SingleShotChain  # noqa: E402

register_runner("ch01_scratch_chain", SingleShotChain)
register_runner("ch01_scratch_loop", AnatomyLoop)

from les.lg.ch01 import LGAgentLoop  # noqa: E402

register_runner("ch01_lg", LGAgentLoop)

from les.compare.openai_agents.ch01 import SDKAgentLoop  # noqa: E402

register_runner("ch01_oai_sdk", SDKAgentLoop)


# The fixture is a placeholder until chapter implementations register.
# Usage in contract tests:
#   @pytest.mark.parametrize("runner_name", [...])
#   def test_something(runner_name, runner_factory):
#       runner = runner_factory(runner_name)
#       result = runner.run("some goal")
#       ...


@pytest.fixture
def runner_factory():
    """Returns a factory function to get a registered LoopRunner by name."""
    def _factory(name: str):
        if name not in RUNNER_REGISTRY:
            pytest.skip(f"Runner '{name}' not yet registered")
        return RUNNER_REGISTRY[name]()
    return _factory
