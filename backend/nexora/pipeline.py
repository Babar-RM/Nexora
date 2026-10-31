"""Nexora Compiler Pipeline orchestrator.

Governed by RFC-0002 §3.5-§3.7 and RFC-0009 §3.3.
This module is the single public entry point for compiling MiniLang source code.
It orchestrates:
1. Lexical analysis (lexer.py)
2. Syntactic analysis (parser.py)
3. Semantic analysis and type checking (symbols.py, semantic.py)
4. Intermediate representation generation (ir.py)
5. Optimization (optimizer.py)
6. Python code generation (codegen_python.py)
7. Sandboxed execution (runner.py, optional)
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .ast_nodes import Program, node_to_dict
from .codegen_python import generate_python
from .errors import Diagnostic, LexerError
from .ir import CFG, IRGenerator, TACInstr, build_all_cfgs, format_tac
from .lexer import tokenize
from .optimizer import OptimizationReport, optimize_program, optimize_tac
from .parser import parse
from .runner import RunOptions, RunResult, run_python
from .semantic import analyze

# Phase names supported for emission subsetting (RFC-0009 §3.3)
ALL_PHASES: frozenset[str] = frozenset(
    [
        "tokens",
        "ast",
        "symbols",
        "tac",
        "cfg",
        "optimized_tac",
        "optimization",
        "python",
    ]
)


# =============================================================================
# 1. Compilation Options and Results (RFC-0002 §3.6, RFC-0009 §3.3)
# =============================================================================


@dataclass(frozen=True)
class CompileOptions:
    """Options controlling the compilation and execution pipeline."""

    run: bool = False
    optimize: bool = True
    emit: list[str] | None = None  # None means emit all phases
    timeout_seconds: float = 5.0
    max_output_bytes: int = 64 * 1024


@dataclass(frozen=True)
class CompileResult:
    """Comprehensive result of compilation and optional execution.

    Contains full diagnostics, phase artifacts (or None if not emitted/reached),
    timings in milliseconds, and the run result.
    """

    ok: bool
    tokens: list[dict[str, Any]] | None
    ast: dict[str, Any] | None
    symbols: list[dict[str, Any]] | None
    tac: list[str] | None
    cfg: list[dict[str, Any]] | None
    optimized_tac: list[str] | None
    optimization: dict[str, Any] | None
    python: str | None
    python_line_map: list[int] | None
    run: RunResult | None
    diagnostics: list[Diagnostic]
    timings_ms: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        """Convert CompileResult to JSON-serializable dictionary."""
        return {
            "ok": self.ok,
            "tokens": self.tokens,
            "ast": self.ast,
            "symbols": self.symbols,
            "tac": self.tac,
            "cfg": self.cfg,
            "optimized_tac": self.optimized_tac,
            "optimization": self.optimization,
            "python": self.python,
            "python_line_map": self.python_line_map,
            "run": self.run.to_dict() if self.run is not None else None,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "timings_ms": self.timings_ms,
        }


# =============================================================================
# 2. Main Compile Orchestrator (RFC-0002 §3.5, RFC-0009 §3.3)
# =============================================================================


def compile_source(
    source: str,
    options: CompileOptions | None = None,
) -> CompileResult:
    """Compile MiniLang source code through the complete compiler pipeline.

    Follows RFC-0002 §3.5 stop rules:
    - Lexer errors stop immediately.
    - Parser errors stop before semantic analysis.
    - Semantic errors stop before IR generation.
    - If ok is False, unreached phases evaluate to None.

    Args:
        source: MiniLang source code text.
        options: Compilation and execution configuration.

    Returns:
        CompileResult data structure.
    """
    if options is None:
        options = CompileOptions()
    emit_set = set(options.emit) if options.emit is not None else ALL_PHASES
    timings: dict[str, int] = {}
    diagnostics: list[Diagnostic] = []

    # -------------------------------------------------------------------------
    # Phase 1: Lexer (RFC-0001)
    # -------------------------------------------------------------------------
    t0 = time.perf_counter()
    try:
        tokens = tokenize(source)
    except LexerError as lex_err:
        tokens = []
        diagnostics.append(lex_err.diagnostic)
    timings["lex"] = max(0, int((time.perf_counter() - t0) * 1000))

    tokens_out: list[dict[str, Any]] | None = None
    if "tokens" in emit_set:
        tokens_out = [t.to_dict() for t in tokens]

    if any(d.severity == "error" for d in diagnostics):
        # Stop rule: Lexer error stops pipeline immediately
        return CompileResult(
            ok=False,
            tokens=tokens_out,
            ast=None,
            symbols=None,
            tac=None,
            cfg=None,
            optimized_tac=None,
            optimization=None,
            python=None,
            python_line_map=None,
            run=None,
            diagnostics=diagnostics,
            timings_ms=timings,
        )

    # -------------------------------------------------------------------------
    # Phase 2: Parser (RFC-0001, RFC-0003)
    # -------------------------------------------------------------------------
    t0 = time.perf_counter()
    parse_res = parse(tokens)
    timings["parse"] = max(0, int((time.perf_counter() - t0) * 1000))
    diagnostics.extend(parse_res.diagnostics)

    ast_out: dict[str, Any] | None = None
    if "ast" in emit_set and parse_res.program is not None:
        ast_out = node_to_dict(parse_res.program)

    if not parse_res.ok:
        # Stop rule: Parser errors stop before semantic analysis
        return CompileResult(
            ok=False,
            tokens=tokens_out,
            ast=ast_out,
            symbols=None,
            tac=None,
            cfg=None,
            optimized_tac=None,
            optimization=None,
            python=None,
            python_line_map=None,
            run=None,
            diagnostics=diagnostics,
            timings_ms=timings,
        )

    ast_root: Program = parse_res.program

    # -------------------------------------------------------------------------
    # Phase 3: Semantic Analysis (RFC-0005)
    # -------------------------------------------------------------------------
    t0 = time.perf_counter()
    sem_res = analyze(ast_root)
    timings["semantic"] = max(0, int((time.perf_counter() - t0) * 1000))
    diagnostics.extend(sem_res.diagnostics)

    symbols_out: list[dict[str, Any]] | None = None
    if "symbols" in emit_set:
        symbols_out = sem_res.symbols

    if not sem_res.ok:
        # Stop rule: Semantic errors stop before IR / Codegen
        return CompileResult(
            ok=False,
            tokens=tokens_out,
            ast=ast_out,
            symbols=symbols_out,
            tac=None,
            cfg=None,
            optimized_tac=None,
            optimization=None,
            python=None,
            python_line_map=None,
            run=None,
            diagnostics=diagnostics,
            timings_ms=timings,
        )

    # -------------------------------------------------------------------------
    # Phase 4: IR Generation (RFC-0006)
    # -------------------------------------------------------------------------
    t0 = time.perf_counter()
    ir_gen = IRGenerator()
    tac_instructions: list[TACInstr] = ir_gen.generate(ast_root)
    cfgs: list[CFG] = build_all_cfgs(tac_instructions)
    timings["ir"] = max(0, int((time.perf_counter() - t0) * 1000))

    tac_out: list[str] | None = None
    if "tac" in emit_set:
        tac_out = format_tac(tac_instructions)

    cfg_out: list[dict[str, Any]] | None = None
    if "cfg" in emit_set:
        cfg_out = [c.to_dict() for c in cfgs]

    # -------------------------------------------------------------------------
    # Phase 5: Optimization (RFC-0007)
    # -------------------------------------------------------------------------
    t0 = time.perf_counter()
    optimized_ast = ast_root
    optimized_tac_instrs = tac_instructions
    opt_report: OptimizationReport | None = None

    if options.optimize:
        optimized_ast, opt_report = optimize_program(ast_root)
        optimized_tac_instrs, _ = optimize_tac(tac_instructions)
    timings["optimize"] = max(0, int((time.perf_counter() - t0) * 1000))

    opt_tac_out: list[str] | None = None
    if "optimized_tac" in emit_set:
        opt_tac_out = format_tac(optimized_tac_instrs)

    opt_out: dict[str, Any] | None = None
    if "optimization" in emit_set:
        if opt_report is not None:
            opt_out = opt_report.to_dict()
        else:
            opt_out = {"notes": [], "iterations": 0}

    # -------------------------------------------------------------------------
    # Phase 6: Python Code Generation (RFC-0008)
    # -------------------------------------------------------------------------
    t0 = time.perf_counter()
    target_ast = optimized_ast if options.optimize else ast_root
    generated = generate_python(target_ast)
    timings["codegen"] = max(0, int((time.perf_counter() - t0) * 1000))

    python_out: str | None = None
    python_line_map: list[int] | None = None
    if "python" in emit_set:
        python_out = generated.code
        python_line_map = generated.line_map

    # -------------------------------------------------------------------------
    # Phase 7: Runner Sandbox (RFC-0009 §3.1)
    # -------------------------------------------------------------------------
    run_res: RunResult | None = None
    if options.run:
        t0 = time.perf_counter()
        run_res = run_python(
            generated,
            RunOptions(
                timeout_seconds=options.timeout_seconds,
                max_output_bytes=options.max_output_bytes,
            ),
        )
        timings["run"] = max(0, int((time.perf_counter() - t0) * 1000))
        # Note: runtime diagnostics belong in run_res.diagnostics per RFC-0009 §3.3

    return CompileResult(
        ok=True,
        tokens=tokens_out,
        ast=ast_out,
        symbols=symbols_out,
        tac=tac_out,
        cfg=cfg_out,
        optimized_tac=opt_tac_out,
        optimization=opt_out,
        python=python_out,
        python_line_map=python_line_map,
        run=run_res,
        diagnostics=diagnostics,
        timings_ms=timings,
    )
