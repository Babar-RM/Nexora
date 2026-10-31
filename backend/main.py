"""Nexora Command-Line Interface (CLI).

Governed by RFC-0009 §3.2:
Usage: python main.py <file.mini> [options]

  --emit {tokens,ast,symbols,tac,opt-tac,cfg,python}   print one phase output (default: python)
  --run                run the generated Python in the sandbox and print its output
  --no-opt             disable optimization
  --json               print the full CompileResult as JSON
  --timeout SECONDS    runner timeout (default 5.0)
  --no-color           disable ANSI colors
  -                    read source from standard input

Exit codes:
  0: success
  1: compile error (diagnostics printed in RFC-0004 §3.6 format to stderr)
  2: usage / IO error
  3: runtime error when --run is used
  70: internal compiler error
"""

from __future__ import annotations

import argparse
import json
import sys

from nexora.errors import InternalCompilerError, render
from nexora.pipeline import CompileOptions, CompileResult, compile_source

# Valid phase choices for --emit
EMIT_CHOICES = ["tokens", "ast", "symbols", "tac", "opt-tac", "cfg", "python"]


def _format_phase_output(result: CompileResult, emit_phase: str) -> str:
    """Format the chosen phase output for standard output."""
    if emit_phase == "tokens":
        return json.dumps(result.tokens, indent=2)
    elif emit_phase == "ast":
        return json.dumps(result.ast, indent=2)
    elif emit_phase == "symbols":
        return json.dumps(result.symbols, indent=2)
    elif emit_phase == "tac":
        return "\n".join(result.tac) if result.tac else ""
    elif emit_phase == "opt-tac":
        return "\n".join(result.optimized_tac) if result.optimized_tac else ""
    elif emit_phase == "cfg":
        return json.dumps(result.cfg, indent=2)
    elif emit_phase == "python":
        return result.python if result.python is not None else ""
    return ""


def main(args: list[str] | None = None) -> int:
    """CLI entry point. Returns exit code."""
    parser = argparse.ArgumentParser(
        prog="nexora",
        description="Nexora MiniLang compiler and runner CLI.",
    )
    parser.add_argument(
        "file",
        nargs="?",
        default=None,
        help="Path to .mini source file, or '-' to read from standard input.",
    )
    parser.add_argument(
        "--emit",
        choices=EMIT_CHOICES,
        default="python",
        help="Phase output to emit (default: python).",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Run the generated Python in the sandbox and print its output.",
    )
    parser.add_argument(
        "--no-opt",
        action="store_true",
        help="Disable AST and TAC optimization.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full CompileResult as JSON to stdout.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        metavar="SECONDS",
        help="Runner timeout in seconds (default: 5.0).",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI color codes in diagnostic output.",
    )

    parsed_args = parser.parse_args(args)

    # 1. Check file argument presence
    if not parsed_args.file:
        sys.stderr.write("error: no input file provided\n")
        parser.print_usage(sys.stderr)
        return 2

    # 2. Read source code
    source: str
    if parsed_args.file == "-":
        try:
            source = sys.stdin.read()
        except OSError as exc:
            sys.stderr.write(f"error reading standard input: {exc}\n")
            return 2
    else:
        try:
            with open(parsed_args.file, encoding="utf-8") as f:
                source = f.read()
        except OSError as exc:
            sys.stderr.write(f"error reading file '{parsed_args.file}': {exc}\n")
            return 2

    # 3. Configure options and invoke pipeline
    mapped_emit: str = (
        "optimized_tac" if parsed_args.emit == "opt-tac" else parsed_args.emit
    )
    # If not full JSON, emit list can include the requested phase (+ python if running)
    emit_list = None
    if not parsed_args.json:
        phases = {mapped_emit}
        if parsed_args.run:
            phases.add("python")
        emit_list = list(phases)

    options = CompileOptions(
        run=parsed_args.run,
        optimize=not parsed_args.no_opt,
        emit=emit_list,
        timeout_seconds=parsed_args.timeout,
    )

    try:
        result = compile_source(source, options)
    except InternalCompilerError as ice:
        sys.stderr.write(f"internal compiler error: {ice}\n")
        return 70
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"internal unexpected error: {exc}\n")
        return 70

    # 4. Handle JSON output mode
    if parsed_args.json:
        sys.stdout.write(json.dumps(result.to_dict(), indent=2) + "\n")
        if not result.ok:
            return 1
        if result.run is not None and result.run.diagnostics:
            return 3
        return 0

    # 5. Handle compilation errors
    if not result.ok:
        for diag in result.diagnostics:
            rendered = render(diag, source)
            sys.stderr.write(rendered + "\n")
        err_count = sum(1 for d in result.diagnostics if d.severity == "error")
        warn_count = sum(1 for d in result.diagnostics if d.severity == "warning")
        sys.stderr.write(
            f"compilation failed with {err_count} error(s) and {warn_count} warning(s)\n"
        )
        return 1

    # Print any compiler warnings to stderr
    for diag in result.diagnostics:
        if diag.severity == "warning":
            sys.stderr.write(render(diag, source) + "\n")

    # 6. Handle Execution mode
    if parsed_args.run:
        if result.run is None:
            sys.stderr.write("error: execution result missing\n")
            return 70

        # Print standard output of user program to stdout
        sys.stdout.write(result.run.stdout)

        # Print runtime errors to stderr
        if result.run.diagnostics:
            for r_diag in result.run.diagnostics:
                sys.stderr.write(render(r_diag, source) + "\n")
            return 3
        return 0

    # 7. Normal Phase Emission
    phase_output = _format_phase_output(result, parsed_args.emit)
    if phase_output:
        if not phase_output.endswith("\n"):
            phase_output += "\n"
        sys.stdout.write(phase_output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
