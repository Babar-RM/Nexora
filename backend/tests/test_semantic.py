"""Tests for MiniLang v1 Semantic Analysis and Type Checking.

Governed by RFC-0001 §3.3–§3.6, RFC-0004 §3.4, and RFC-0005.
"""

from nexora.ast_nodes import (
    CallExpr,
    Expr,
    GiveStmt,
    Identifier,
    MakeStmt,
    Node,
    NodeVisitor,
)
from nexora.lexer import tokenize
from nexora.parser import parse
from nexora.semantic import analyze
from nexora.symbols import Type


def _analyze_source(source: str):
    """Helper to tokenize, parse, and analyze source code."""
    tokens = tokenize(source)
    parse_res = parse(tokens)
    assert parse_res.ok, f"Parse failed: {[d.message for d in parse_res.diagnostics]}"
    return analyze(parse_res.program)


class TestSemanticTypingAndWidening:
    """Tests covering typing rules and widening per RFC-0005 §3.2 and §3.7."""

    def test_numeric_widening_in_make(self) -> None:
        """'make p: float = 1;' widens int to float and sets needs_widening."""
        source = "make p: float = 1;"
        res = _analyze_source(source)
        assert res.ok is True
        make_stmt = res.program.body[0]
        assert isinstance(make_stmt, MakeStmt)
        assert make_stmt.needs_widening is True
        assert make_stmt.symbol.type == Type.FLOAT

    def test_mixed_arithmetic_produces_float(self) -> None:
        """Arithmetic between int and float produces float."""
        source = "make x = 1 + 2.5;"
        res = _analyze_source(source)
        assert res.ok is True
        make_stmt = res.program.body[0]
        assert isinstance(make_stmt, MakeStmt)
        assert make_stmt.initializer.type == Type.FLOAT

    def test_division_always_produces_float(self) -> None:
        """True division always yields Type.FLOAT (RFC-0001 §3.6, RFC-0005 §3.2)."""
        source = "make x = 7 / 2;"
        res = _analyze_source(source)
        assert res.ok is True
        make_stmt = res.program.body[0]
        assert isinstance(make_stmt, MakeStmt)
        assert make_stmt.initializer.type == Type.FLOAT

    def test_string_concatenation(self) -> None:
        """String + String yields Type.STRING."""
        source = 'make s = "hello " + "world";'
        res = _analyze_source(source)
        assert res.ok is True
        make_stmt = res.program.body[0]
        assert isinstance(make_stmt, MakeStmt)
        assert make_stmt.initializer.type == Type.STRING

    def test_task_argument_widening(self) -> None:
        """Passing int argument to float parameter sets arg_widenings."""
        source = """
        task compute(factor: float): float {
            give factor * 2.0;
        }
        make res = compute(5);
        """
        res = _analyze_source(source)
        assert res.ok is True
        make_stmt = res.program.body[1]
        assert isinstance(make_stmt, MakeStmt)
        call = make_stmt.initializer
        assert isinstance(call, CallExpr)
        assert call.arg_widenings == [True]

    def test_give_widening(self) -> None:
        """Returning int from float task sets needs_widening on GiveStmt."""
        source = """
        task get_ratio(): float {
            give 10;
        }
        """
        res = _analyze_source(source)
        assert res.ok is True
        task = res.program.body[0]
        give_stmt = task.body.statements[0]
        assert isinstance(give_stmt, GiveStmt)
        assert give_stmt.needs_widening is True

    def test_hoisting_allows_forward_and_recursive_calls(self) -> None:
        """Tasks are hoisted so forward and recursive calls succeed."""
        source = """
        task caller(): int {
            give callee();
        }

        task callee(): int {
            give 42;
        }

        task factorial(n: int): int {
            when (n <= 1) {
                give 1;
            }
            give n * factorial(n - 1);
        }
        """
        res = _analyze_source(source)
        assert res.ok is True


class TestSemanticErrors:
    """Test suite asserting codes E3001–E3019 and warnings W4001, W4003."""

    def test_e3001_undeclared_variable(self) -> None:
        """Undeclared variable triggers E3001."""
        source = "show(total);"
        res = _analyze_source(source)
        assert res.ok is False
        assert any(d.code == "E3001" for d in res.diagnostics)

    def test_e3001_global_declared_after_task_hint(self) -> None:
        """Global variable declared after a task triggers E3001 with specific hint."""
        source = """
        task f(): int {
            give global_x;
        }
        make global_x = 10;
        """
        res = _analyze_source(source)
        assert res.ok is False
        e3001 = next(d for d in res.diagnostics if d.code == "E3001")
        assert "global variables must be declared before the task" in (e3001.hint or "")

    def test_e3002_redeclaration_and_no_shadowing(self) -> None:
        """Redeclaration in the same or nested scope triggers E3002."""
        source = """
        make x = 1;
        {
            make x = 2;
        }
        """
        res = _analyze_source(source)
        assert res.ok is False
        assert any(d.code == "E3002" for d in res.diagnostics)

    def test_e3003_type_mismatch_in_assignment(self) -> None:
        """Incompatible types in assignment or make trigger E3003."""
        source = """
        make age: int = "twenty";
        """
        res = _analyze_source(source)
        assert res.ok is False
        assert any(d.code == "E3003" for d in res.diagnostics)

    def test_e3004_invalid_operator_operands(self) -> None:
        """Applying operator to incompatible types triggers E3004."""
        source = 'make x = "hello" - 2;'
        res = _analyze_source(source)
        assert res.ok is False
        assert any(d.code == "E3004" for d in res.diagnostics)

    def test_e3005_condition_not_bool(self) -> None:
        """Non-bool condition triggers E3005."""
        source = "when (42) { show(1); }"
        res = _analyze_source(source)
        assert res.ok is False
        assert any(d.code == "E3005" for d in res.diagnostics)

    def test_e3006_wrong_number_of_arguments(self) -> None:
        """Wrong argument count triggers E3006."""
        source = """
        task add(x: int, y: int): int { give x + y; }
        show(add(1));
        """
        res = _analyze_source(source)
        assert res.ok is False
        assert any(d.code == "E3006" for d in res.diagnostics)

    def test_e3007_call_non_task(self) -> None:
        """Invoking a variable as a task triggers E3007."""
        source = """
        make a = 5;
        a(1, 2);
        """
        res = _analyze_source(source)
        assert res.ok is False
        assert any(d.code == "E3007" for d in res.diagnostics)

    def test_e3008_argument_type_mismatch(self) -> None:
        """Wrong argument type triggers E3008."""
        source = """
        task greet(name: string) { show(name); }
        greet(123);
        """
        res = _analyze_source(source)
        assert res.ok is False
        assert any(d.code == "E3008" for d in res.diagnostics)

    def test_e3009_assignment_to_global_in_task(self) -> None:
        """Writing to a global inside a task triggers E3009 (RFC-0001 §3.4 rule 8)."""
        source = """
        make counter = 0;
        task increment() {
            counter = counter + 1;
        }
        """
        res = _analyze_source(source)
        assert res.ok is False
        assert any(d.code == "E3009" for d in res.diagnostics)

    def test_e3010_give_outside_task(self) -> None:
        """'give' statement at top level triggers E3010."""
        source = "give 10;"
        res = _analyze_source(source)
        assert res.ok is False
        assert any(d.code == "E3010" for d in res.diagnostics)

    def test_e3011_return_type_mismatch(self) -> None:
        """Returning wrong type or returning a value from void task triggers E3011."""
        source = """
        task f(): int {
            give "wrong";
        }
        task v() {
            give 1;
        }
        """
        res = _analyze_source(source)
        assert res.ok is False
        assert any(d.code == "E3011" for d in res.diagnostics)

    def test_e3012_missing_give_on_some_path(self) -> None:
        """Non-void task missing give triggers E3012."""
        source = """
        task check(n: int): int {
            when (n > 0) {
                give 1;
            }
        }
        """
        res = _analyze_source(source)
        assert res.ok is False
        assert any(d.code == "E3012" for d in res.diagnostics)

    def test_e3013_void_used_as_value(self) -> None:
        """Using a void task call in expression triggers E3013."""
        source = """
        task do_work() {
            show("done");
        }
        make x = do_work();
        """
        res = _analyze_source(source)
        assert res.ok is False
        assert any(d.code == "E3013" for d in res.diagnostics)

    def test_e3014_unknown_type_name(self) -> None:
        """Unknown type name triggers E3014."""
        source = "make x: integer = 1;"
        res = _analyze_source(source)
        assert res.ok is False
        assert any(d.code == "E3014" for d in res.diagnostics)

    def test_e3015_reserved_name(self) -> None:
        """Declaring variable with reserved name or compiler prefix triggers E3015."""
        source = """
        make int = 1;
        make __nx_internal = 2;
        """
        res = _analyze_source(source)
        assert res.ok is False
        assert any(d.code == "E3015" for d in res.diagnostics)

    def test_e3016_duplicate_task_or_parameter_name(self) -> None:
        """Duplicate task name or parameter triggers E3016."""
        source = """
        task duplicate(a: int, a: int): int { give a; }
        task duplicate(): int { give 0; }
        """
        res = _analyze_source(source)
        assert res.ok is False
        assert any(d.code == "E3016" for d in res.diagnostics)

    def test_e3017_stop_outside_during_loop(self) -> None:
        """'stop' outside during loop triggers E3017."""
        source = "stop;"
        res = _analyze_source(source)
        assert res.ok is False
        assert any(d.code == "E3017" for d in res.diagnostics)

    def test_e3018_skip_outside_during_loop(self) -> None:
        """'skip' outside during loop triggers E3018."""
        source = "skip;"
        res = _analyze_source(source)
        assert res.ok is False
        assert any(d.code == "E3018" for d in res.diagnostics)

    def test_e3019_invalid_type_for_ask(self) -> None:
        """'ask' with bool type triggers E3019."""
        source = "ask flag: bool;"
        res = _analyze_source(source)
        assert res.ok is False
        assert any(d.code == "E3019" for d in res.diagnostics)

    def test_w4001_unreachable_code_after_give(self) -> None:
        """Code following an unconditional give triggers W4001."""
        source = """
        task f(): int {
            give 1;
            show(2);
        }
        """
        res = _analyze_source(source)
        assert any(d.code == "W4001" for d in res.diagnostics)

    def test_w4003_unused_variable_warning(self) -> None:
        """Unused variable triggers W4003."""
        source = "make unused_val = 100;"
        res = _analyze_source(source)
        assert any(d.code == "W4003" for d in res.diagnostics)


class TestSemanticSuppressionAndInvariants:
    """Test suite covering cascade error suppression and post-analysis invariants."""

    def test_cascade_error_suppression(self) -> None:
        """Undeclared variables yield E3001, but operators on them do not produce E3004."""
        source = "make a = b + c;"
        res = _analyze_source(source)
        assert res.ok is False
        e3001_errors = [d for d in res.diagnostics if d.code == "E3001"]
        e3004_errors = [d for d in res.diagnostics if d.code == "E3004"]
        assert len(e3001_errors) == 2  # b and c
        assert len(e3004_errors) == 0  # no cascading '+' error

    def test_symbol_snapshot_contract(self) -> None:
        """SymbolTable.snapshot() contains entries for declared variables and tasks."""
        source = """
        make x = 10;
        task add(y: int): int {
            give x + y;
        }
        """
        res = _analyze_source(source)
        assert res.ok is True
        symbols = res.symbols
        names = [s["name"] for s in symbols]
        assert "x" in names
        assert "add" in names
        assert "y" in names

    def test_invariants_on_valid_program(self) -> None:
        """Every expression in a valid program has non-None type and symbols attached."""
        source = """
        task double_it(n: int): int {
            give n * 2;
        }
        make num = 5;
        make res = double_it(num);
        show(res);
        """
        res = _analyze_source(source)
        assert res.ok is True

        class InvariantChecker(NodeVisitor):
            def generic_visit(self, node: Node) -> None:
                if isinstance(node, Expr):
                    assert node.type is not None, (
                        f"Node {type(node).__name__} has None type"
                    )
                    assert node.type != Type.ERROR
                if isinstance(node, Identifier):
                    assert node.symbol is not None, (
                        f"Identifier {node.name} has None symbol"
                    )
                super().generic_visit(node)

        checker = InvariantChecker()
        checker.visit(res.program)
