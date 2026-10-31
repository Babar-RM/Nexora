"""Integration tests for the unified compiler pipeline.

Governed by RFC-0002 §3.5-§3.7 and RFC-0009 §3.3:
- Full compilation flow for valid MiniLang program
- Stop-on-error rules (lexer error stops immediately; parser error stops before semantic, etc.)
- Partial emission (subsets of phases emitted)
- Execution integration with run: True
- Timing metrics presence
"""

from __future__ import annotations

from nexora.pipeline import CompileOptions, compile_source


def test_pipeline_valid_program_full_flow() -> None:
    """Test full compilation of valid program with all phases enabled."""
    src = """make x = 10;
make y = 20;
show(x + y);
"""
    result = compile_source(src, CompileOptions(run=False, optimize=True))

    assert result.ok is True
    assert result.tokens is not None
    assert result.ast is not None
    assert result.symbols is not None
    assert result.tac is not None
    assert result.cfg is not None
    assert result.optimized_tac is not None
    assert result.optimization is not None
    assert result.python is not None
    assert result.python_line_map is not None
    assert result.run is None
    assert len(result.diagnostics) == 0

    # Verify timing metrics recorded
    for phase in ("lex", "parse", "semantic", "ir", "optimize", "codegen"):
        assert phase in result.timings_ms


def test_pipeline_with_execution() -> None:
    """Test full compilation and sandbox execution with run=True."""
    src = """task double(n: int): int {
    give n * 2;
}
show(double(21));
"""
    result = compile_source(src, CompileOptions(run=True, optimize=True))

    assert result.ok is True
    assert result.run is not None
    assert result.run.exit_code == 0
    assert result.run.stdout == "42\n"
    assert "run" in result.timings_ms


def test_pipeline_lexer_error_stops_early() -> None:
    """Test that a lexical error aborts subsequent phases."""
    src = "make $invalid = 10;"
    result = compile_source(src)

    assert result.ok is False
    assert result.ast is None
    assert result.symbols is None
    assert result.tac is None
    assert result.python is None
    assert len(result.diagnostics) > 0
    assert result.diagnostics[0].phase == "Lexical Error"


def test_pipeline_parser_error_stops_before_semantic() -> None:
    """Test that a parser error aborts semantic analysis and codegen."""
    src = "make x = ;"
    result = compile_source(src)

    assert result.ok is False
    assert result.ast is not None  # partial AST exists
    assert result.symbols is None  # stopped before semantic
    assert result.tac is None
    assert result.python is None
    assert any(d.phase == "Syntax Error" for d in result.diagnostics)


def test_pipeline_semantic_error_stops_before_ir() -> None:
    """Test that a semantic type error aborts IR generation and codegen."""
    src = 'make x: int = "string";'
    result = compile_source(src)

    assert result.ok is False
    assert result.ast is not None
    assert result.symbols is not None
    assert result.tac is None  # stopped before IR
    assert result.python is None
    assert any(d.code == "E3003" for d in result.diagnostics)


def test_pipeline_emit_filtering() -> None:
    """Test that emit option filters phase outputs to None when not requested."""
    src = "make val = 5;\nshow(val);\n"
    # Request only tokens and python
    result = compile_source(src, CompileOptions(emit=["tokens", "python"]))

    assert result.ok is True
    assert result.tokens is not None
    assert result.python is not None
    assert result.ast is None
    assert result.symbols is None
    assert result.tac is None
    assert result.cfg is None
    assert result.optimized_tac is None
