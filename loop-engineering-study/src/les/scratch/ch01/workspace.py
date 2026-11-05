"""TaskWorkspace: a throwaway directory holding one FixTask.

The workspace is the agent's "world". Tools read and write inside it, and the
verifier runs the tests inside it. Paths are confined to the directory so a
tool call can never touch files outside the sandbox.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

from .tasks import FixTask

SOLUTION_FILE = "solution.py"
TEST_FILE = "test_solution.py"

# Appended to every test file so tests run with plain `python`, no pytest needed.
_TEST_HARNESS = """

if __name__ == "__main__":
    import sys
    import traceback

    _failures = 0
    for _name, _fn in list(globals().items()):
        if _name.startswith("test_") and callable(_fn):
            try:
                _fn()
                print(f"PASS {_name}")
            except Exception:
                _failures += 1
                print(f"FAIL {_name}")
                traceback.print_exc(limit=2, file=sys.stdout)
    print("PASSED" if _failures == 0 else f"FAILED {_failures}")
    sys.exit(1 if _failures else 0)
"""


@dataclass
class TestRun:
    """Outcome of running the task's tests once."""

    __test__ = False  # stop pytest from collecting this as a test class

    passed: bool
    output: str


class TaskWorkspace:
    """Materialises a FixTask into a temp dir and runs its tests.

    Use as a context manager so the directory is always cleaned up.
    """

    def __init__(self, task: FixTask, timeout_s: float = 10.0) -> None:
        self.task = task
        self.timeout_s = timeout_s
        self._tmp: tempfile.TemporaryDirectory[str] | None = None
        self.root: Path = Path()

    # --- lifecycle ---------------------------------------------------------

    def __enter__(self) -> TaskWorkspace:
        self._tmp = tempfile.TemporaryDirectory(prefix=f"les-ch01-{self.task.task_id}-")
        self.root = Path(self._tmp.name)
        (self.root / SOLUTION_FILE).write_text(self.task.buggy_src)
        (self.root / TEST_FILE).write_text(self.task.test_src + _TEST_HARNESS)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._tmp is not None:
            self._tmp.cleanup()
            self._tmp = None

    # --- file access (sandboxed) ------------------------------------------

    def resolve(self, rel_path: str) -> Path:
        """Return an absolute path inside the workspace, or raise ValueError."""
        target = (self.root / rel_path).resolve()
        if not target.is_relative_to(self.root.resolve()):
            raise ValueError(f"path escapes workspace: {rel_path}")
        return target

    def read(self, rel_path: str) -> str:
        return self.resolve(rel_path).read_text()

    def write(self, rel_path: str, content: str) -> None:
        if Path(rel_path).name == TEST_FILE:
            raise ValueError("the test file is read-only")
        self.resolve(rel_path).write_text(content)

    def list_files(self) -> list[str]:
        return sorted(p.name for p in self.root.iterdir() if p.is_file())

    # --- test execution ----------------------------------------------------

    def run_tests(self) -> TestRun:
        """Run the test file in a subprocess; never raises."""
        try:
            proc = subprocess.run(
                [sys.executable, "-B", "-E", "-s", TEST_FILE],
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
            )
        except subprocess.TimeoutExpired:
            return TestRun(passed=False, output=f"TIMEOUT after {self.timeout_s}s")
        output = (proc.stdout + proc.stderr).strip()
        return TestRun(passed=proc.returncode == 0, output=output)
