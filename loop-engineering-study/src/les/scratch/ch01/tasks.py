"""Fix-the-function task set for the Ch 1 mini-lab.

Each ``FixTask`` is a tiny buggy module plus a test file. Half the tasks also
carry a *plausible but wrong* first fix: the kind of answer a model gives when
it pattern-matches the bug without checking its work. The scripted mock uses
it to show why a loop (which observes test output) beats a single-shot chain.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FixTask:
    """One buggy function, its tests, and reference fixes."""

    task_id: str
    function: str
    buggy_src: str
    test_src: str
    correct_fix: str
    wrong_fix: str = ""  # optional plausible-but-wrong first attempt

    @property
    def goal(self) -> str:
        return (
            f"Fix `{self.function}` in solution.py "
            "so that all tests in test_solution.py pass."
        )

    @property
    def first_attempt(self) -> str:
        """What a careless fixer writes first (used by the mock)."""
        return self.wrong_fix or self.correct_fix


FIX_TASKS: list[FixTask] = [
    FixTask(
        task_id="add",
        function="add",
        buggy_src="def add(a, b):\n    return a - b\n",
        test_src=(
            "from solution import add\n\n"
            "def test_add():\n    assert add(2, 3) == 5\n    assert add(-1, 1) == 0\n"
        ),
        correct_fix="def add(a, b):\n    return a + b\n",
    ),
    FixTask(
        task_id="is_even",
        function="is_even",
        buggy_src="def is_even(n):\n    return n % 2 == 1\n",
        test_src=(
            "from solution import is_even\n\n"
            "def test_is_even():\n    assert is_even(4)\n    assert not is_even(7)\n"
        ),
        correct_fix="def is_even(n):\n    return n % 2 == 0\n",
    ),
    FixTask(
        task_id="factorial",
        function="factorial",
        buggy_src=(
            "def factorial(n):\n    result = 1\n    for i in range(1, n):\n"
            "        result *= i\n    return result\n"
        ),
        test_src=(
            "from solution import factorial\n\n"
            "def test_factorial():\n    assert factorial(0) == 1\n"
            "    assert factorial(5) == 120\n"
        ),
        correct_fix=(
            "def factorial(n):\n    result = 1\n    for i in range(1, n + 1):\n"
            "        result *= i\n    return result\n"
        ),
        wrong_fix=(
            "def factorial(n):\n    result = 1\n    for i in range(n):\n"
            "        result *= i\n    return result\n"
        ),
    ),
    FixTask(
        task_id="reverse",
        function="reverse_string",
        buggy_src="def reverse_string(s):\n    return s[::1]\n",
        test_src=(
            "from solution import reverse_string\n\n"
            "def test_reverse():\n    assert reverse_string('abc') == 'cba'\n"
            "    assert reverse_string('') == ''\n"
        ),
        correct_fix="def reverse_string(s):\n    return s[::-1]\n",
    ),
    FixTask(
        task_id="max_of",
        function="max_of",
        buggy_src=(
            "def max_of(xs):\n    best = 0\n    for x in xs:\n        if x > best:\n"
            "            best = x\n    return best\n"
        ),
        test_src=(
            "from solution import max_of\n\n"
            "def test_max_of():\n    assert max_of([1, 7, 3]) == 7\n"
            "    assert max_of([-5, -2, -9]) == -2\n"
        ),
        correct_fix=(
            "def max_of(xs):\n    best = xs[0]\n"
            "    for x in xs:\n        if x > best:\n"
            "            best = x\n    return best\n"
        ),
        wrong_fix=(
            "def max_of(xs):\n    best = 0\n    for x in xs:\n        if x >= best:\n"
            "            best = x\n    return best\n"
        ),
    ),
    FixTask(
        task_id="fizzbuzz",
        function="fizzbuzz",
        buggy_src=(
            "def fizzbuzz(n):\n    if n % 3 == 0:\n        return 'Fizz'\n"
            "    if n % 5 == 0:\n        return 'Buzz'\n    if n % 15 == 0:\n"
            "        return 'FizzBuzz'\n    return str(n)\n"
        ),
        test_src=(
            "from solution import fizzbuzz\n\n"
            "def test_fizzbuzz():\n    assert fizzbuzz(3) == 'Fizz'\n"
            "    assert fizzbuzz(10) == 'Buzz'\n    assert fizzbuzz(30) == 'FizzBuzz'\n"
            "    assert fizzbuzz(7) == '7'\n"
        ),
        correct_fix=(
            "def fizzbuzz(n):\n    if n % 15 == 0:\n        return 'FizzBuzz'\n"
            "    if n % 3 == 0:\n        return 'Fizz'\n    if n % 5 == 0:\n"
            "        return 'Buzz'\n    return str(n)\n"
        ),
        wrong_fix=(
            "def fizzbuzz(n):\n    if n % 5 == 0:\n        return 'Buzz'\n"
            "    if n % 3 == 0:\n        return 'Fizz'\n    if n % 15 == 0:\n"
            "        return 'FizzBuzz'\n    return str(n)\n"
        ),
    ),
    FixTask(
        task_id="count_vowels",
        function="count_vowels",
        buggy_src=(
            "def count_vowels(s):\n    return sum(1 for c in s if c in 'aeio')\n"
        ),
        test_src=(
            "from solution import count_vowels\n\n"
            "def test_count_vowels():\n    assert count_vowels('hello') == 2\n"
            "    assert count_vowels('AEIOU') == 5\n"
            "    assert count_vowels('sun') == 1\n"
        ),
        correct_fix=(
            "def count_vowels(s):\n"
            "    return sum(1 for c in s.lower() if c in 'aeiou')\n"
        ),
        wrong_fix=(
            "def count_vowels(s):\n"
            "    return sum(1 for c in s.lower() if c in 'aeio')\n"
        ),
    ),
    FixTask(
        task_id="mean",
        function="mean",
        buggy_src="def mean(xs):\n    return sum(xs) / len(xs)\n",
        test_src=(
            "from solution import mean\n\n"
            "def test_mean():\n    assert mean([1, 2, 3]) == 2\n"
            "    assert mean([]) == 0.0\n"
        ),
        correct_fix=(
            "def mean(xs):\n    if not xs:\n        return 0.0\n"
            "    return sum(xs) / len(xs)\n"
        ),
    ),
    FixTask(
        task_id="palindrome",
        function="is_palindrome",
        buggy_src="def is_palindrome(s):\n    return s == s[::-1]\n",
        test_src=(
            "from solution import is_palindrome\n\n"
            "def test_palindrome():\n    assert is_palindrome('Racecar')\n"
            "    assert is_palindrome('A man, a plan, a canal: Panama')\n"
            "    assert not is_palindrome('hello')\n"
        ),
        correct_fix=(
            "def is_palindrome(s):\n"
            "    t = ''.join(c.lower() for c in s if c.isalnum())\n"
            "    return t == t[::-1]\n"
        ),
        wrong_fix=(
            "def is_palindrome(s):\n    t = s.lower()\n    return t == t[::-1]\n"
        ),
    ),
    FixTask(
        task_id="clamp",
        function="clamp",
        buggy_src="def clamp(x, lo, hi):\n    return max(lo, min(x, lo))\n",
        test_src=(
            "from solution import clamp\n\n"
            "def test_clamp():\n    assert clamp(5, 0, 10) == 5\n"
            "    assert clamp(-3, 0, 10) == 0\n    assert clamp(42, 0, 10) == 10\n"
        ),
        correct_fix="def clamp(x, lo, hi):\n    return max(lo, min(x, hi))\n",
    ),
]

TASKS_BY_ID: dict[str, FixTask] = {t.task_id: t for t in FIX_TASKS}
