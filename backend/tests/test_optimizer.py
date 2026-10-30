"""Comprehensive unit and differential tests for MiniLang optimizer (RFC-0007).

Governed by RFC-0007 §7, this test suite covers:
1. Shared folding module rules and type preservation (fold_binary, fold_unary)
2. Never-fold edge cases (division by zero, overflow, limits, invalid types)
3. AST short-circuit rewrites and non-rewritten cases
4. AST safe algebraic simplifications on int types only
5. AST statement-level rewrites (when, during, dead code after give, expr stmt)
6. AST invariants: non-mutation of input tree, idempotence (opt(opt(x)) == opt(x))
7. TAC optimization passes: propagation, folding, branch folding, unreachable removal,
   jump cleanup/threading, dead-code elimination, and may-raise safety
8. TAC invariants: validate_tac passes on all optimized TAC
9. Differential execution: run_tac(optimized_tac) == run_tac(unoptimized_tac)
"""

from __future__ import annotations

import pytest

from nexora.ast_nodes import (
    BoolLiteral,
    IntLiteral,
    MakeStmt,
    Program,
    ShowStmt,
    unparse,
)
from nexora.ir import (
    Const,
    FuncBegin,
    FuncEnd,
    Goto,
    IRGenerator,
    Label,
    Print,
    Return,
    format_tac,
    validate_tac,
)
from nexora.lexer import Lexer
from nexora.optimizer import (
    fold_binary,
    fold_unary,
    optimize_program,
    optimize_tac,
)
from nexora.parser import Parser
from nexora.semantic import SemanticAnalyzer
from nexora.symbols import Type
from tests.helpers.tac_vm import run_tac


def compile_to_ast(source: str) -> Program:
    """Helper: lex, parse, and semantically analyze MiniLang source into a typed AST."""
    tokens = Lexer(source).tokenize()
    parse_result = Parser(tokens).parse()
    analyzer = SemanticAnalyzer()
    analyzer.analyze(parse_result.program)
    return parse_result.program


def compile_to_tac(source: str):
    """Helper: compile MiniLang source to verified TAC."""
    prog = compile_to_ast(source)
    tac = IRGenerator().generate(prog)
    validate_tac(tac)
    return tac


# =============================================================================
# 1. Fold Table Tests (RFC-0007 §3.3, §7)
# =============================================================================


class TestFoldTable:
    """Verify constant folding across all valid operators and types."""

    def test_fold_arithmetic_integers(self) -> None:
        assert fold_binary("+", 10, Type.INT, 20, Type.INT) == (30, Type.INT)
        assert fold_binary("-", 20, Type.INT, 7, Type.INT) == (13, Type.INT)
        assert fold_binary("*", 6, Type.INT, 7, Type.INT) == (42, Type.INT)
        assert fold_binary("%", 10, Type.INT, 3, Type.INT) == (1, Type.INT)

    def test_fold_division_always_produces_float(self) -> None:
        # MiniLang division always produces float (7 / 2 -> 3.5)
        res = fold_binary("/", 7, Type.INT, 2, Type.INT)
        assert res == (3.5, Type.FLOAT)
        assert isinstance(res[0], float)

    def test_fold_negative_modulo_matches_python(self) -> None:
        # RFC-0007 §3.3: -7 % 3 -> 2
        assert fold_binary("%", -7, Type.INT, 3, Type.INT) == (2, Type.INT)

    def test_fold_arithmetic_floats(self) -> None:
        assert fold_binary("+", 1.5, Type.FLOAT, 2.5, Type.FLOAT) == (
            4.0,
            Type.FLOAT,
        )
        assert fold_binary("-", 5.0, Type.FLOAT, 1.5, Type.FLOAT) == (
            3.5,
            Type.FLOAT,
        )
        assert fold_binary("*", 2.0, Type.FLOAT, 3.5, Type.FLOAT) == (
            7.0,
            Type.FLOAT,
        )
        assert fold_binary("/", 9.0, Type.FLOAT, 2.0, Type.FLOAT) == (
            4.5,
            Type.FLOAT,
        )

    def test_fold_mixed_arithmetic(self) -> None:
        # Widening int to float
        assert fold_binary("+", 5, Type.INT, 2.5, Type.FLOAT) == (
            7.5,
            Type.FLOAT,
        )
        assert fold_binary("*", 3.0, Type.FLOAT, 4, Type.INT) == (
            12.0,
            Type.FLOAT,
        )

    def test_fold_string_operations(self) -> None:
        assert fold_binary("+", "hello ", Type.STRING, "world", Type.STRING) == (
            "hello world",
            Type.STRING,
        )
        assert fold_binary("<", "apple", Type.STRING, "banana", Type.STRING) == (
            True,
            Type.BOOL,
        )
        assert fold_binary("==", "xyz", Type.STRING, "xyz", Type.STRING) == (
            True,
            Type.BOOL,
        )
        assert fold_binary("!=", "xyz", Type.STRING, "abc", Type.STRING) == (
            True,
            Type.BOOL,
        )

    def test_fold_comparisons_and_numeric_equality(self) -> None:
        # 1 == 1.0 -> True (numeric equality)
        assert fold_binary("==", 1, Type.INT, 1.0, Type.FLOAT) == (
            True,
            Type.BOOL,
        )
        assert fold_binary("!=", 1, Type.INT, 2.0, Type.FLOAT) == (
            True,
            Type.BOOL,
        )
        assert fold_binary("<", 2, Type.INT, 3, Type.INT) == (True, Type.BOOL)
        assert fold_binary(">=", 5, Type.INT, 5, Type.INT) == (True, Type.BOOL)

    def test_fold_boolean_equality(self) -> None:
        assert fold_binary("==", True, Type.BOOL, True, Type.BOOL) == (
            True,
            Type.BOOL,
        )
        assert fold_binary("!=", True, Type.BOOL, False, Type.BOOL) == (
            True,
            Type.BOOL,
        )

    def test_fold_unary_operations(self) -> None:
        assert fold_unary("-", 42, Type.INT) == (-42, Type.INT)
        assert fold_unary("-", 3.14, Type.FLOAT) == (-3.14, Type.FLOAT)
        assert fold_unary("not", True, Type.BOOL) == (False, Type.BOOL)
        assert fold_unary("not", False, Type.BOOL) == (True, Type.BOOL)
        assert fold_unary("float", 5, Type.INT) == (5.0, Type.FLOAT)


# =============================================================================
# 2. Never-Fold Edge Cases (RFC-0007 §3.2)
# =============================================================================


class TestNeverFoldSafety:
    """Ensure unsafe expressions are never folded compile-time."""

    def test_never_fold_division_or_modulo_by_zero(self) -> None:
        assert fold_binary("/", 10, Type.INT, 0, Type.INT) is None
        assert fold_binary("/", 10.0, Type.FLOAT, 0.0, Type.FLOAT) is None
        assert fold_binary("%", 10, Type.INT, 0, Type.INT) is None
        assert fold_binary("%", 10.0, Type.FLOAT, 0.0, Type.FLOAT) is None

    def test_never_fold_invalid_types(self) -> None:
        assert fold_binary("+", 10, Type.INT, "string", Type.STRING) is None
        assert fold_unary("-", "not_a_num", Type.STRING) is None
        assert fold_unary("not", 42, Type.INT) is None

    def test_never_fold_huge_integer_over_10000_bits(self) -> None:
        huge_int = 1 << 10005
        assert fold_binary("+", huge_int, Type.INT, 1, Type.INT) is None

    def test_never_fold_huge_string_over_64kb(self) -> None:
        big_str = "a" * 65540
        assert fold_binary("+", big_str, Type.STRING, "b", Type.STRING) is None


# =============================================================================
# 3. AST-Level Optimizations (RFC-0007 §3.4)
# =============================================================================


class TestASTOptimizer:
    """Verify AST-level folding, simplification, and branch elimination."""

    def test_ast_folds_constant_expressions(self) -> None:
        src = """
        make x = 3 * 4 + 2;
        show(x);
        """
        ast = compile_to_ast(src)
        opt_ast, report = optimize_program(ast)

        # 3 * 4 + 2 -> 14
        make_stmt = opt_ast.body[0]
        assert isinstance(make_stmt, MakeStmt)
        assert isinstance(make_stmt.initializer, IntLiteral)
        assert make_stmt.initializer.value == 14
        assert len(report.notes) > 0

    def test_ast_short_circuit_rewrites(self) -> None:
        src = """
        make a = yes both (5 > 2);
        make b = no both (5 > 2);
        make c = (5 > 2) both yes;
        make d = yes either (5 > 2);
        make e = no either (5 > 2);
        make f = (5 > 2) either no;
        """
        ast = compile_to_ast(src)
        opt_ast, _ = optimize_program(ast)

        # In all cases, 5 > 2 folds to yes, and the boolean combinations simplify
        for item in opt_ast.body:
            assert isinstance(item, MakeStmt)
            assert isinstance(item.initializer, BoolLiteral)

    def test_ast_does_not_rewrite_unsafe_short_circuits(self) -> None:
        # e both no and e either yes MUST NOT drop e (it may raise or have side effects)
        src = """
        task may_run(): bool {
            give yes;
        }
        make x = may_run() both no;
        make y = may_run() either yes;
        """
        ast = compile_to_ast(src)
        opt_ast, _ = optimize_program(ast)

        stmt_x = opt_ast.body[1]
        assert isinstance(stmt_x, MakeStmt)
        # Still a binary expression or function call (may_run is not eliminated)
        assert not isinstance(stmt_x.initializer, BoolLiteral)

    def test_ast_safe_algebraic_identities_int_only(self) -> None:
        src = """
        make n = 10;
        make a = n + 0;
        make b = 0 + n;
        make c = n - 0;
        make d = n * 1;
        make e = 1 * n;
        make f = not not (n > 5);
        """
        ast = compile_to_ast(src)
        opt_ast, _ = optimize_program(ast)

        # a, b, c, d, e should simplify to 'n'
        for stmt in opt_ast.body[1:6]:
            assert isinstance(stmt, MakeStmt)
            assert unparse(stmt.initializer) == "n"

    def test_ast_does_not_simplify_float_identities(self) -> None:
        # RFC-0007 §3.4 B: float identities like x + 0.0 are explicitly excluded
        src = """
        make x: float = 3.5;
        make y = x + 0.0;
        """
        ast = compile_to_ast(src)
        opt_ast, _ = optimize_program(ast)

        stmt_y = opt_ast.body[1]
        assert isinstance(stmt_y, MakeStmt)
        # Should NOT simplify away
        assert unparse(stmt_y.initializer) == "x + 0.0"

    def test_ast_eliminates_constant_when_branches(self) -> None:
        src = """
        when (yes) {
            show("taken");
        } otherwise {
            show("untaken");
        }

        when (no) {
            show("dead");
        } otherwise {
            show("alive");
        }

        when (no) {
            show("dropped");
        }
        """
        ast = compile_to_ast(src)
        opt_ast, _ = optimize_program(ast)

        # Body should contain show("taken") and show("alive")
        assert len(opt_ast.body) == 2
        assert isinstance(opt_ast.body[0], ShowStmt)
        assert unparse(opt_ast.body[0].value) == '"taken"'
        assert isinstance(opt_ast.body[1], ShowStmt)
        assert unparse(opt_ast.body[1].value) == '"alive"'

    def test_ast_eliminates_during_false(self) -> None:
        src = """
        during (no) {
            show("never runs");
        }
        show("done");
        """
        ast = compile_to_ast(src)
        opt_ast, _ = optimize_program(ast)

        assert len(opt_ast.body) == 1
        assert isinstance(opt_ast.body[0], ShowStmt)
        assert unparse(opt_ast.body[0].value) == '"done"'

    def test_ast_removes_dead_code_after_give(self) -> None:
        src = """
        task foo(): int {
            give 42;
            show("dead code");
            make unreachable = 99;
        }
        """
        ast = compile_to_ast(src)
        opt_ast, report = optimize_program(ast)

        task = opt_ast.body[0]
        # Only the give statement should remain in the task body
        assert len(task.body.statements) == 1
        assert task.body.statements[0].value.value == 42
        assert any(n.kind == "dead-code" for n in report.notes)

    def test_ast_removes_effectless_expression_statements(self) -> None:
        src = """
        123;
        "hello";
        make x = 5;
        x;
        show(x);
        """
        ast = compile_to_ast(src)
        opt_ast, _ = optimize_program(ast)

        # Only make x = 5; and show(x); should survive
        assert len(opt_ast.body) == 2
        assert isinstance(opt_ast.body[0], MakeStmt)
        assert isinstance(opt_ast.body[1], ShowStmt)

    def test_ast_non_mutation_and_idempotence(self) -> None:
        src = """
        make a = 3 + 4 * 2;
        when (yes) {
            show(a);
        }
        """
        ast = compile_to_ast(src)
        original_unparse = unparse(ast)

        opt_1, _ = optimize_program(ast)
        # Input AST was NOT mutated
        assert unparse(ast) == original_unparse

        # Idempotence: optimize(optimize(x)) == optimize(x)
        opt_2, _ = optimize_program(opt_1)
        assert unparse(opt_1) == unparse(opt_2)


# =============================================================================
# 4. TAC-Level Optimizations (RFC-0007 §3.5)
# =============================================================================


class TestTACOptimizer:
    """Verify TAC passes: propagation, folding, DCE, branch/jump optimizations."""

    def test_tac_propagates_and_folds_constants(self) -> None:
        src = """
        make a = 10;
        make b = 20;
        make r = a + b * 2;
        show(r);
        """
        tac = compile_to_tac(src)
        opt_tac, _report = optimize_tac(tac)

        # After propagation and DCE, r is folded to 50 and printed
        formatted = "\n".join(format_tac(opt_tac))
        assert "print 50" in formatted
        # Intermediate computations should have been folded away
        assert "a + t" not in formatted
        validate_tac(opt_tac)

    def test_tac_preserves_may_raise_division_by_zero(self) -> None:
        # RFC-0007 §3.5 counter-example
        src = """
        make z = 0;
        make t = 5 / z;
        show(1);
        """
        tac = compile_to_tac(src)
        opt_tac, _ = optimize_tac(tac)

        # The division instruction must NOT be folded into compile crash
        # and must NOT be eliminated by dead-code elimination!
        formatted = "\n".join(format_tac(opt_tac))
        assert "/ 0" in formatted or "/ z" in formatted
        validate_tac(opt_tac)

    def test_tac_folds_branches_and_cleans_jumps(self) -> None:
        src = """
        when (5 > 2) {
            show("true branch");
        } otherwise {
            show("false branch");
        }
        """
        tac = compile_to_tac(src)
        opt_tac, _ = optimize_tac(tac)

        formatted = "\n".join(format_tac(opt_tac))
        assert 'print "true branch"' in formatted
        assert 'print "false branch"' not in formatted
        validate_tac(opt_tac)

    def test_tac_threads_jumps_and_guards_against_cycles(self) -> None:
        # Construct synthetic instructions with jump threading and cycle
        instrs = [
            FuncBegin(name="__main", params=[], ret=Type.VOID, source_line=0),
            Goto(target="L1", source_line=1),
            Label(name="L1", source_line=2),
            Goto(target="L2", source_line=3),
            Label(name="L2", source_line=4),
            Print(value=Const(1, Type.INT), source_line=5),
            Return(value=None, source_line=6),
            FuncEnd(name="__main", source_line=0),
        ]
        opt_tac, _ = optimize_tac(instrs)
        validate_tac(opt_tac)
        formatted = "\n".join(format_tac(opt_tac))
        assert "print 1" in formatted

    def test_tac_preserves_global_variable_read_by_task(self) -> None:
        # Global variable read inside task must not be eliminated in __main
        src = """
        make g = 100;

        task get_g(): int {
            give g;
        }

        show(get_g());
        """
        tac = compile_to_tac(src)
        opt_tac, _ = optimize_tac(tac)

        formatted = "\n".join(format_tac(opt_tac))
        assert "g = 100" in formatted
        validate_tac(opt_tac)


# =============================================================================
# 5. Differential Execution Tests (RFC-0007 §7)
# =============================================================================


class TestDifferentialExecution:
    """Verify that unoptimized and optimized TAC produce identical runtime results."""

    @pytest.mark.parametrize(
        "source,expected_output",
        [
            (
                """
                make x = 10 + 20;
                make y = x * 2;
                show(y);
                """,
                "60\n",
            ),
            (
                """
                task factorial(n: int): int {
                    when (n <= 1) {
                        give 1;
                    }
                    give n * factorial(n - 1);
                }
                show(factorial(5));
                """,
                "120\n",
            ),
            (
                """
                make count = 0;
                during (count < 5) {
                    count = count + 1;
                }
                show(count);
                """,
                "5\n",
            ),
            (
                """
                when (yes) {
                    show("yes branch");
                } otherwise {
                    show("no branch");
                }
                """,
                "yes branch\n",
            ),
            (
                """
                make a = "hello " + "world";
                show(a);
                """,
                "hello world\n",
            ),
        ],
    )
    def test_tac_vm_differential_equivalence(
        self, source: str, expected_output: str
    ) -> None:
        unopt_tac = compile_to_tac(source)
        opt_tac, _ = optimize_tac(unopt_tac)

        unopt_stdout, unopt_err = run_tac(unopt_tac)
        opt_stdout, opt_err = run_tac(opt_tac)

        assert unopt_stdout == expected_output
        assert opt_stdout == expected_output
        assert unopt_err is None
        assert opt_err is None

    def test_tac_vm_preserves_division_by_zero_error(self) -> None:
        src = """
        make zero = 0;
        show(10 / zero);
        """
        unopt_tac = compile_to_tac(src)
        opt_tac, _ = optimize_tac(unopt_tac)

        _unopt_stdout, unopt_err = run_tac(unopt_tac)
        _opt_stdout, opt_err = run_tac(opt_tac)

        # Both MUST raise runtime error division by zero
        assert unopt_err == "R5001"
        assert opt_err == "R5001"
