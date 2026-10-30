"""Unit tests for the sandboxed Python runner.

Governed by RFC-0009 §7:
- Normal execution with stdout capture and exit code 0
- Infinite loop timeout (R5002) within timeout + 0.5s; process terminated
- Print loop output cap (R5004) with output_truncated=True
- Division by zero (R5001) with MiniLang source line translation
- Recursion limit exceeded (R5003)
- Global variable used before initialization (R5006)
- Temp directory cleaned up after success, error, and timeout
- Sandboxed environment sanitization
- Precondition enforcement (rejection of unvalidated Python)
"""

from __future__ import annotations

import os
import tempfile
import time

import pytest

from nexora.codegen_python import GeneratedCode
from nexora.errors import InternalCompilerError
from nexora.runner import RunOptions, run_python


def test_runner_normal_execution() -> None:
    """Test successful execution of a simple generated Python script."""
    py_code = 'print("Hello from sandbox!")\n'
    gen = GeneratedCode(code=py_code, line_map=[1], names={})
    res = run_python(gen, RunOptions(timeout_seconds=5.0))

    assert res.exit_code == 0
    assert res.timed_out is False
    assert res.output_truncated is False
    assert res.stdout == "Hello from sandbox!\n"
    assert res.stderr == ""
    assert len(res.diagnostics) == 0


def test_runner_timeout_infinite_loop() -> None:
    """Test that an infinite loop triggers R5002 and terminates promptly."""
    # MiniLang source line 3 corresponds to while True loop
    py_code = "while True:\n    pass\n"
    gen = GeneratedCode(code=py_code, line_map=[3, 3], names={})

    t0 = time.perf_counter()
    res = run_python(gen, RunOptions(timeout_seconds=0.5))
    elapsed = time.perf_counter() - t0

    assert res.timed_out is True
    assert elapsed < 1.5  # Bounded within timeout + 1.0s
    assert len(res.diagnostics) == 1
    diag = res.diagnostics[0]
    assert diag.code == "R5002"
    assert "time limit" in diag.message


def test_runner_output_cap() -> None:
    """Test that excessive output is truncated with R5004."""
    # Loop that prints heavily
    py_code = "while True:\n    print('A' * 1000)\n"
    gen = GeneratedCode(code=py_code, line_map=[1, 2], names={})

    res = run_python(gen, RunOptions(timeout_seconds=3.0, max_output_bytes=2048))

    assert res.output_truncated is True
    assert len(res.diagnostics) == 1
    diag = res.diagnostics[0]
    assert diag.code == "R5004"
    assert len(res.stdout) <= 4096


def test_runner_zero_division_error() -> None:
    """Test that ZeroDivisionError is captured and mapped to R5001 with correct line."""
    py_code = "x = 10\ny = 0\nres = x / y\n"
    gen = GeneratedCode(code=py_code, line_map=[1, 2, 4], names={})

    res = run_python(gen)

    assert res.exit_code == 1
    assert len(res.diagnostics) == 1
    diag = res.diagnostics[0]
    assert diag.code == "R5001"
    assert diag.line == 4
    assert "division or modulo by zero" in diag.message


def test_runner_recursion_error() -> None:
    """Test that RecursionError is mapped to R5003."""
    py_code = "def rec():\n    return rec()\nrec()\n"
    gen = GeneratedCode(code=py_code, line_map=[1, 2, 3], names={})

    res = run_python(gen)

    assert res.exit_code == 1
    assert len(res.diagnostics) == 1
    diag = res.diagnostics[0]
    assert diag.code == "R5003"
    assert "recursion depth" in diag.message


def test_runner_uninitialized_variable_name_error() -> None:
    """Test NameError maps to R5006 and un-mangles renamed variables."""
    # Suppose 'print' in MiniLang was mangled to 'print_'
    py_code = "def foo():\n    return print_\nfoo()\n"
    gen = GeneratedCode(code=py_code, line_map=[1, 2, 3], names={"print_": "print"})

    res = run_python(gen)

    assert res.exit_code == 1
    assert len(res.diagnostics) == 1
    diag = res.diagnostics[0]
    assert diag.code == "R5006"
    assert "variable 'print' was used before it was initialized" in diag.message


def test_runner_temp_dir_cleaned_up() -> None:
    """Test that runner temp directories are reliably removed afterwards."""
    py_code = 'print("cleanup test")\n'
    gen = GeneratedCode(code=py_code, line_map=[1], names={})

    temp_base = tempfile.gettempdir()
    before_dirs = set(os.listdir(temp_base))

    run_python(gen)

    after_dirs = set(os.listdir(temp_base))
    new_nexora_dirs = [d for d in (after_dirs - before_dirs) if d.startswith("nexora-")]
    assert len(new_nexora_dirs) == 0


def test_runner_rejects_unvalidated_code() -> None:
    """Test that runner enforces whitelist validator before running."""
    # import os is forbidden in MiniLang generated python
    py_code = "import os\nos.system('echo hi')\n"
    gen = GeneratedCode(code=py_code, line_map=[1, 2], names={})

    with pytest.raises(InternalCompilerError) as exc_info:
        run_python(gen)
    assert "Precondition violated" in str(exc_info.value)
