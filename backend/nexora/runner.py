"""Sandboxed Python code runner for MiniLang programs.

Governed by RFC-0009 §3.1 and RFC-0008 §3.8.
Executes generated Python in an isolated subprocess with:
- Dedicated temporary directory created with prefix "nexora-", deleted afterwards.
- Subprocess: [sys.executable, "-I", "-S", "-B", "-X", "utf8", "harness.py", "program.py"]
- Polling supervision (every 20ms) enforcing wall-clock timeout and output cap.
- Strict mapping of runtime exceptions to R5001..R5006 diagnostics with MiniLang line tracking.
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from typing import Any

from .codegen_python import GeneratedCode, validate_generated_python
from .errors import Diagnostic, InternalCompilerError

# =============================================================================
# 1. Trusted In-Process Harness (RFC-0009 §3.1.2)
# =============================================================================

_HARNESS_SRC: str = """import json, sys
src = open(sys.argv[1], encoding="utf-8").read()
code = compile(src, "<generated>", "exec")
try:
    exec(code, {"__name__": "__nx_main__"})
except BaseException as exc:
    tb, line = exc.__traceback__, 0
    while tb is not None:
        if tb.tb_frame.f_code.co_filename == "<generated>":
            line = tb.tb_lineno
        tb = tb.tb_next
    with open("error.json", "w", encoding="utf-8") as f:
        json.dump({"type": type(exc).__name__, "message": str(exc)[:200], "line": line}, f)
    sys.exit(1)
"""


# =============================================================================
# 2. Options and Result Data Structures (RFC-0009 §3.1)
# =============================================================================


@dataclass(frozen=True)
class RunOptions:
    """Execution options for running generated Python code."""

    timeout_seconds: float = 5.0
    max_output_bytes: int = 64 * 1024
    max_memory_mb: int = 256  # Enforced on POSIX only (RFC-0009 §3.1.4)


@dataclass(frozen=True)
class RunResult:
    """Outcome of sandboxed execution."""

    stdout: str
    stderr: str  # Always "" in v1 (RFC-0009 §3.1.3)
    exit_code: int | None
    timed_out: bool
    output_truncated: bool
    duration_ms: int
    diagnostics: list[Diagnostic]  # R5xxx, at most one

    def to_dict(self) -> dict[str, Any]:
        """Convert result to JSON-serializable dictionary."""
        return {
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "output_truncated": self.output_truncated,
            "duration_ms": self.duration_ms,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
        }


# =============================================================================
# 3. Environment Sanitization & Subprocess Configuration
# =============================================================================


def _build_minimal_env() -> dict[str, str]:
    """Build a minimal, sanitized environment dictionary for the subprocess."""
    clean_env: dict[str, str] = {"PATH": ""}
    if platform.system() == "Windows":
        # Windows Python requires specific environment variables to initialize
        for var in (
            "SYSTEMROOT",
            "COMSPEC",
            "PATHEXT",
            "TEMP",
            "TMP",
            "SystemDrive",
            "WINDIR",
        ):
            val = os.environ.get(var)
            if val is not None:
                clean_env[var] = val
    return clean_env


def _make_preexec_fn(options: RunOptions):
    """Create a preexec_fn for POSIX systems enforcing resource limits (RFC-0009 §3.1.4)."""
    if platform.system() == "Windows":
        return None

    try:
        import math
        import resource

        def preexec() -> None:
            # RLIMIT_CPU = ceil(timeout) + 1
            cpu_limit = math.ceil(options.timeout_seconds) + 1
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, cpu_limit))

            # RLIMIT_AS = max_memory_mb * 1024 * 1024
            mem_bytes = options.max_memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))

            # RLIMIT_FSIZE = max_output_bytes + 4096
            file_limit = options.max_output_bytes + 4096
            resource.setrlimit(resource.RLIMIT_FSIZE, (file_limit, file_limit))

            # RLIMIT_CORE = 0
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

        return preexec
    except ImportError:
        return None


# =============================================================================
# 4. Error Mapping (RFC-0009 §3.1.6, RFC-0008 §3.8)
# =============================================================================


def _translate_line(harness_line: int, line_map: list[int]) -> int:
    """Translate 1-based Python line from harness to original MiniLang source line."""
    if 1 <= harness_line <= len(line_map):
        return line_map[harness_line - 1]
    return 0


def _map_runtime_error(
    err_type: str,
    err_msg: str,
    harness_line: int,
    generated: GeneratedCode,
) -> Diagnostic:
    """Map a runtime exception from error.json to an R5xxx Diagnostic."""
    line = _translate_line(harness_line, generated.line_map)
    line_or_none = line if line > 0 else None

    if err_type == "ZeroDivisionError":
        return Diagnostic(
            phase="Runtime Error",
            code="R5001",
            severity="error",
            message="division or modulo by zero",
            line=line_or_none,
            column=1,
            hint="ensure the denominator is not zero before dividing or taking modulo",
        )
    if err_type == "RecursionError":
        return Diagnostic(
            phase="Runtime Error",
            code="R5003",
            severity="error",
            message="maximum recursion depth exceeded",
            line=line_or_none,
            column=1,
            hint="check for a missing base case or infinite recursion in tasks",
        )
    if err_type == "NameError":
        # Unmangle variable name if possible
        # Python NameError message typically: "name 'foo_' is not defined" or "name 'foo' is not defined"
        import re

        m = re.search(r"name '([^']+)' is not defined", err_msg)
        if m:
            py_name = m.group(1)
            orig_name = generated.names.get(py_name, py_name)
            msg = f"variable '{orig_name}' was used before it was initialized"
        else:
            msg = "variable was used before it was initialized"

        return Diagnostic(
            phase="Runtime Error",
            code="R5006",
            severity="error",
            message=msg,
            line=line_or_none,
            column=1,
            hint="ensure variables are initialized before use",
        )

    # General / unexpected exception
    clean_msg = err_msg.strip() if err_msg.strip() else err_type
    return Diagnostic(
        phase="Runtime Error",
        code="R5005",
        severity="error",
        message=f"the program failed while running: {clean_msg}",
        line=line_or_none,
        column=1,
    )


# =============================================================================
# 5. Core Runner Function (RFC-0009 §3.1)
# =============================================================================


def run_python(
    generated: GeneratedCode,
    options: RunOptions | None = None,
) -> RunResult:
    """Execute generated Python code in an isolated subprocess.

    Args:
        generated: Generated Python code and mappings produced by PythonGenerator.
        options: Execution resource constraints (timeout, output cap, memory).

    Returns:
        RunResult containing stdout, exit code, timing, and any R5xxx diagnostic.

    Raises:
        InternalCompilerError: Only if runner infrastructure fails (e.g. tempdir or spawn error),
                               never for user code errors.
    """
    if options is None:
        options = RunOptions()
    # 0. Structural Whitelist Check (RFC-0009 §3.1, RFC-0008 §3.9)
    try:
        validate_generated_python(generated.code)
    except Exception as exc:
        raise InternalCompilerError(
            f"Precondition violated: unvalidated or invalid Python submitted to runner: {exc}"
        ) from exc

    start_time = time.perf_counter()

    # 1. Create fresh temporary directory
    try:
        temp_dir = tempfile.mkdtemp(prefix="nexora-")
    except Exception as exc:
        raise InternalCompilerError(
            f"Failed to create temporary runner directory: {exc}"
        ) from exc

    try:
        # 2. Write program.py and harness.py
        prog_path = os.path.join(temp_dir, "program.py")
        harness_path = os.path.join(temp_dir, "harness.py")
        stdout_path = os.path.join(temp_dir, "stdout.txt")
        error_json_path = os.path.join(temp_dir, "error.json")

        with open(prog_path, "w", encoding="utf-8") as f:
            f.write(generated.code)
        with open(harness_path, "w", encoding="utf-8") as f:
            f.write(_HARNESS_SRC)

        cmd = [
            sys.executable,
            "-I",
            "-S",
            "-B",
            "-X",
            "utf8",
            "harness.py",
            "program.py",
        ]
        clean_env = _build_minimal_env()
        preexec = _make_preexec_fn(options)

        # 3. Spawn subprocess
        with open(stdout_path, "wb") as stdout_file:
            try:
                proc = subprocess.Popen(
                    cmd,
                    cwd=temp_dir,
                    stdin=subprocess.DEVNULL,
                    stdout=stdout_file,
                    stderr=subprocess.DEVNULL,
                    env=clean_env,
                    close_fds=platform.system() != "Windows",
                    preexec_fn=preexec,  # noqa: PLW1509 - Required for POSIX RLIMIT resource bounds per RFC-0009 §3.1.4
                )
            except OSError as exc:
                raise InternalCompilerError(
                    f"Failed to spawn runner subprocess: {exc}"
                ) from exc

            # 4. Supervise with 20ms polling loop
            timed_out = False
            output_truncated = False
            diagnostics: list[Diagnostic] = []

            while True:
                ret = proc.poll()
                elapsed = time.perf_counter() - start_time

                # Check timeout
                if elapsed > options.timeout_seconds:
                    timed_out = True
                    try:
                        proc.kill()
                    except OSError:
                        pass
                    proc.wait()
                    diagnostics.append(
                        Diagnostic(
                            phase="Runtime Error",
                            code="R5002",
                            severity="error",
                            message=f"time limit of {int(options.timeout_seconds) if options.timeout_seconds.is_integer() else options.timeout_seconds} s exceeded",
                            hint="check for an infinite loop in during statements",
                        )
                    )
                    break

                # Check output cap
                try:
                    stdout_file.flush()
                    out_size = os.path.getsize(stdout_path)
                except OSError:
                    out_size = 0

                if out_size > options.max_output_bytes:
                    output_truncated = True
                    try:
                        proc.kill()
                    except OSError:
                        pass
                    proc.wait()
                    diagnostics.append(
                        Diagnostic(
                            phase="Runtime Error",
                            code="R5004",
                            severity="error",
                            message=f"output limit of {options.max_output_bytes // 1024} KB exceeded",
                        )
                    )
                    break

                if ret is not None:
                    break

                time.sleep(0.02)

        # 5. Read captured stdout
        try:
            with open(stdout_path, "rb") as f:
                raw_bytes = f.read(options.max_output_bytes)
                stdout_str = (
                    raw_bytes.decode("utf-8", errors="replace")
                    .replace("\r\n", "\n")
                    .replace("\r", "\n")
                )
        except OSError:
            stdout_str = ""

        duration_ms = max(0, int((time.perf_counter() - start_time) * 1000))

        # 6. Read error.json if present
        exit_code = proc.returncode
        if not timed_out and not output_truncated:
            if os.path.exists(error_json_path):
                import json

                try:
                    with open(error_json_path, encoding="utf-8") as f:
                        err_data = json.load(f)
                    err_type = str(err_data.get("type", "Error"))
                    err_msg = str(err_data.get("message", ""))
                    h_line = int(err_data.get("line", 0))
                    diagnostics.append(
                        _map_runtime_error(err_type, err_msg, h_line, generated)
                    )
                except (OSError, json.JSONDecodeError):
                    diagnostics.append(
                        Diagnostic(
                            phase="Runtime Error",
                            code="R5005",
                            severity="error",
                            message="the program failed while running",
                        )
                    )
            elif exit_code is not None and exit_code != 0:
                # Killed by OS resource limits (e.g. RLIMIT_AS) or abnormal termination
                diagnostics.append(
                    Diagnostic(
                        phase="Runtime Error",
                        code="R5005",
                        severity="error",
                        message="the program was stopped by the system (resource limit)",
                    )
                )

        return RunResult(
            stdout=stdout_str,
            stderr="",
            exit_code=exit_code,
            timed_out=timed_out,
            output_truncated=output_truncated,
            duration_ms=duration_ms,
            diagnostics=diagnostics,
        )

    finally:
        # Cleanup temporary directory (RFC-0009 §3.1.1)
        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)
