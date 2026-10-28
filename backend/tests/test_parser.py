"""Tests for MiniLang v1 hand-written recursive-descent Parser.

Governed by RFC-0001 §3.2, RFC-0002 §3.4, RFC-0003, and RFC-0004 §3.4, §3.8.2.
"""

from nexora.ast_nodes import (
    AskStmt,
    AssignStmt,
    BinaryExpr,
    CallExpr,
    DuringStmt,
    ExprStmt,
    GiveStmt,
    Identifier,
    IntLiteral,
    MakeStmt,
    ShowStmt,
    SkipStmt,
    StopStmt,
    TaskDecl,
    UnaryExpr,
    WhenStmt,
    validate_ast,
)
from nexora.lexer import tokenize
from nexora.parser import Parser, parse


class TestParserValidPrograms:
    """Test suite covering valid grammatical constructs from RFC-0001 §3.2."""

    def test_parse_make_statements(self) -> None:
        """Parse make statements with and without type annotations."""
        source = """
        make age = 20;
        make price: float = 5.5;
        """
        tokens = tokenize(source)
        res = parse(tokens)
        assert res.ok is True
        assert len(res.program.body) == 2

        s1 = res.program.body[0]
        assert isinstance(s1, MakeStmt)
        assert s1.name == "age"
        assert s1.declared_type is None
        assert isinstance(s1.initializer, IntLiteral) and s1.initializer.value == 20

        s2 = res.program.body[1]
        assert isinstance(s2, MakeStmt)
        assert s2.name == "price"
        assert s2.declared_type is not None and s2.declared_type.name == "float"

        assert validate_ast(res.program) == []

    def test_parse_task_declarations(self) -> None:
        """Parse task declarations with parameters and return types."""
        source = """
        task add(x: int, y: int): int {
            give x + y;
        }

        task greet(name: string) {
            show("Hello " + name);
        }
        """
        tokens = tokenize(source)
        res = parse(tokens)
        assert res.ok is True
        assert len(res.program.body) == 2

        t1 = res.program.body[0]
        assert isinstance(t1, TaskDecl)
        assert t1.name == "add"
        assert len(t1.params) == 2
        assert t1.return_type is not None and t1.return_type.name == "int"
        assert len(t1.body.statements) == 1
        assert isinstance(t1.body.statements[0], GiveStmt)

        t2 = res.program.body[1]
        assert isinstance(t2, TaskDecl)
        assert t2.name == "greet"
        assert t2.return_type is None

        assert validate_ast(res.program) == []

    def test_parse_control_flow(self) -> None:
        """Parse when/otherwise when/otherwise and during loops."""
        source = """
        when (x > 10) {
            show("large");
        } otherwise when (x > 5) {
            show("medium");
        } otherwise {
            show("small");
        }

        during (x > 0) {
            when (x == 5) {
                stop;
            }
            when (x == 2) {
                skip;
            }
            x = x - 1;
        }
        """
        tokens = tokenize(source)
        res = parse(tokens)
        assert res.ok is True
        assert len(res.program.body) == 2

        when_stmt = res.program.body[0]
        assert isinstance(when_stmt, WhenStmt)
        assert isinstance(when_stmt.else_branch, WhenStmt)
        assert when_stmt.else_branch.else_branch is not None  # final Block

        during_stmt = res.program.body[1]
        assert isinstance(during_stmt, DuringStmt)
        assert len(during_stmt.body.statements) == 3
        assert isinstance(
            during_stmt.body.statements[0].then_block.statements[0], StopStmt
        )  # type: ignore[union-attr]
        assert isinstance(
            during_stmt.body.statements[1].then_block.statements[0], SkipStmt
        )  # type: ignore[union-attr]
        assert isinstance(during_stmt.body.statements[2], AssignStmt)

        assert validate_ast(res.program) == []

    def test_parse_ask_and_show(self) -> None:
        """Parse ask and show statements."""
        source = """
        ask name: string;
        show("Hello " + name);
        """
        tokens = tokenize(source)
        res = parse(tokens)
        assert res.ok is True
        assert len(res.program.body) == 2

        s1 = res.program.body[0]
        assert isinstance(s1, AskStmt)
        assert s1.name == "name"
        assert s1.type_ref.name == "string"

        s2 = res.program.body[1]
        assert isinstance(s2, ShowStmt)

        assert validate_ast(res.program) == []

    def test_parse_complete_factorial_example(self) -> None:
        """Parse complete example from RFC-0001 §3.8."""
        source = """
        task factorial(n: int): int {
            when (n <= 1) {
                give 1;
            }
            give n * factorial(n - 1);
        }

        make i = 1;
        during (i <= 5) {
            show(factorial(i));
            i = i + 1;
        }
        """
        tokens = tokenize(source)
        res = Parser(tokens).parse()
        assert res.ok is True
        assert len(res.program.body) == 3
        assert validate_ast(res.program) == []


class TestParserPrecedenceAndAssociativity:
    """Test suite covering operator precedence and associativity per RFC-0001 §3.2."""

    def test_arithmetic_precedence(self) -> None:
        """1 + 2 * 3 parses as 1 + (2 * 3)."""
        tokens = tokenize("make x = 1 + 2 * 3;")
        res = parse(tokens)
        assert res.ok is True

        stmt = res.program.body[0]
        assert isinstance(stmt, MakeStmt)
        expr = stmt.initializer
        assert isinstance(expr, BinaryExpr)
        assert expr.op == "+"
        assert isinstance(expr.left, IntLiteral) and expr.left.value == 1
        assert isinstance(expr.right, BinaryExpr)
        assert expr.right.op == "*"
        assert expr.right.left.value == 2  # type: ignore[union-attr]
        assert expr.right.right.value == 3  # type: ignore[union-attr]

    def test_logical_operator_precedence(self) -> None:
        """either / both / not precedence: either < both < not."""
        tokens = tokenize("make b = a either not b both c;")
        res = parse(tokens)
        assert res.ok is True

        stmt = res.program.body[0]
        assert isinstance(stmt, MakeStmt)
        expr = stmt.initializer
        # Outermost should be either
        assert isinstance(expr, BinaryExpr) and expr.op == "either"
        assert isinstance(expr.left, Identifier) and expr.left.name == "a"
        # Right child should be both
        both_expr = expr.right
        assert isinstance(both_expr, BinaryExpr) and both_expr.op == "both"
        # Left of both should be unary not
        assert isinstance(both_expr.left, UnaryExpr) and both_expr.left.op == "not"

    def test_unary_minus_precedence(self) -> None:
        """-a * b parses as (-a) * b."""
        tokens = tokenize("make x = -a * b;")
        res = parse(tokens)
        assert res.ok is True

        stmt = res.program.body[0]
        assert isinstance(stmt, MakeStmt)
        expr = stmt.initializer
        assert isinstance(expr, BinaryExpr) and expr.op == "*"
        assert isinstance(expr.left, UnaryExpr) and expr.left.op == "-"

    def test_call_expression(self) -> None:
        """CallExpr correctly parses callee identifier and comma-separated arguments."""
        tokens = tokenize("add(1, 2 + 3);")
        res = parse(tokens)
        assert res.ok is True

        stmt = res.program.body[0]
        assert isinstance(stmt, ExprStmt)
        assert isinstance(stmt.expression, CallExpr)
        assert stmt.expression.callee == "add"
        assert len(stmt.expression.args) == 2


class TestParserErrorDiagnosticsAndRecovery:
    """Test suite covering RFC-0004 §3.4 syntax errors (E2xxx) and panic-mode recovery."""

    def test_missing_semicolon_e2002(self) -> None:
        """Missing semicolon triggers E2002 at end of statement token."""
        source = """
        make x = 5
        make y = 6;
        """
        tokens = tokenize(source)
        res = parse(tokens)
        assert res.ok is False
        assert any(d.code == "E2002" for d in res.diagnostics)
        # Recovers and parses second statement
        assert len(res.program.body) >= 1

    def test_unclosed_block_e2003(self) -> None:
        """Unclosed block triggers E2003 referencing the opening line."""
        source = "{\nmake x = 1;"
        tokens = tokenize(source)
        res = parse(tokens)
        assert res.ok is False
        e2003 = next((d for d in res.diagnostics if d.code == "E2003"), None)
        assert e2003 is not None
        assert "expected '}' to close block" in e2003.message

    def test_assignment_in_expression_e2004(self) -> None:
        """Assignment used in expression context triggers E2004."""
        source = "make x = (a = 3);"
        tokens = tokenize(source)
        res = parse(tokens)
        assert res.ok is False
        assert any(d.code == "E2004" for d in res.diagnostics)

    def test_task_declared_in_nested_position_e2005(self) -> None:
        """Task declared inside a block triggers E2005."""
        source = """
        {
            task helper() { }
        }
        """
        tokens = tokenize(source)
        res = parse(tokens)
        assert res.ok is False
        e2005 = next((d for d in res.diagnostics if d.code == "E2005"), None)
        assert e2005 is not None
        assert "tasks can only be declared at the top level" in e2005.message

    def test_missing_parentheses_around_condition_e2007(self) -> None:
        """when without opening '(' triggers E2007."""
        source = "when x > 5 { show(1); }"
        tokens = tokenize(source)
        res = parse(tokens)
        assert res.ok is False
        assert any(d.code == "E2007" for d in res.diagnostics)

    def test_missing_parameter_type_e2008(self) -> None:
        """Parameter missing ':' and type triggers E2008."""
        source = "task f(x) { }"
        tokens = tokenize(source)
        res = parse(tokens)
        assert res.ok is False
        assert any(d.code == "E2008" for d in res.diagnostics)

    def test_panic_mode_recovers_across_multiple_errors(self) -> None:
        """Panic-mode recovery reports multiple independent errors without crashing."""
        source = """
        make a = ;
        make b = 2;
        when { }
        make c = 3;
        """
        tokens = tokenize(source)
        res = parse(tokens)
        assert res.ok is False
        # Multiple diagnostics recorded
        assert len(res.diagnostics) >= 2
        # Statements between or after errors are still parsed
        make_names = [s.name for s in res.program.body if isinstance(s, MakeStmt)]
        assert "b" in make_names or "c" in make_names
