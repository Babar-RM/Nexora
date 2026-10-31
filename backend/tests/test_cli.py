"""Tests for the Nexora CLI (backend/main.py).

Governed by RFC-0009 §3.2:
- Phase emission options (--emit)
- Execution option (--run)
- JSON output mode (--json)
- Exit code conventions (0: success, 1: compile error, 2: usage/IO, 3: runtime)
- Standard input support via '-'
"""

from __future__ import annotations

import io
import json
from unittest.mock import patch

from main import main


def test_cli_help_or_missing_file() -> None:
    """Test CLI error exit code 2 when no input file is given."""
    err_stream = io.StringIO()
    with patch("sys.stderr", err_stream):
        code = main([])
    assert code == 2
    assert "no input file provided" in err_stream.getvalue()


def test_cli_emit_python(tmp_path) -> None:
    """Test standard compilation emitting Python source to stdout."""
    mini_file = tmp_path / "test.mini"
    mini_file.write_text('show("CLI Test");\n', encoding="utf-8")

    out_stream = io.StringIO()
    with patch("sys.stdout", out_stream):
        code = main([str(mini_file), "--emit", "python"])

    assert code == 0
    output = out_stream.getvalue()
    assert "__nx_show('CLI Test')" in output or '__nx_show("CLI Test")' in output


def test_cli_run(tmp_path) -> None:
    """Test CLI running the program and outputting to stdout."""
    mini_file = tmp_path / "run_test.mini"
    mini_file.write_text("show(100 + 23);\n", encoding="utf-8")

    out_stream = io.StringIO()
    with patch("sys.stdout", out_stream):
        code = main([str(mini_file), "--run"])

    assert code == 0
    assert out_stream.getvalue() == "123\n"


def test_cli_compile_error(tmp_path) -> None:
    """Test CLI returning exit code 1 on compilation errors with diagnostics on stderr."""
    mini_file = tmp_path / "bad.mini"
    mini_file.write_text("make x = ;\n", encoding="utf-8")

    err_stream = io.StringIO()
    with patch("sys.stderr", err_stream):
        code = main([str(mini_file)])

    assert code == 1
    err_output = err_stream.getvalue()
    assert "error[E2001]" in err_output or "error[" in err_output


def test_cli_runtime_error(tmp_path) -> None:
    """Test CLI returning exit code 3 on runtime failure."""
    mini_file = tmp_path / "div_zero.mini"
    mini_file.write_text("make x = 10 / 0;\n", encoding="utf-8")

    err_stream = io.StringIO()
    with patch("sys.stderr", err_stream):
        code = main([str(mini_file), "--run"])

    assert code == 3
    err_output = err_stream.getvalue()
    assert "R5001" in err_output


def test_cli_json_mode(tmp_path) -> None:
    """Test CLI --json output parsing."""
    mini_file = tmp_path / "json_test.mini"
    mini_file.write_text("show(42);\n", encoding="utf-8")

    out_stream = io.StringIO()
    with patch("sys.stdout", out_stream):
        code = main([str(mini_file), "--json"])

    assert code == 0
    data = json.loads(out_stream.getvalue())
    assert data["ok"] is True
    assert data["python"] is not None


def test_cli_stdin_support() -> None:
    """Test CLI reading from standard input via '-'."""
    src = "show(777);\n"
    stdin_stream = io.StringIO(src)
    out_stream = io.StringIO()

    with patch("sys.stdin", stdin_stream), patch("sys.stdout", out_stream):
        code = main(["-", "--run"])

    assert code == 0
    assert out_stream.getvalue() == "777\n"
