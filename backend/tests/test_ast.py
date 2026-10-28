"""Tests for MiniLang v1 Abstract Syntax Tree (AST) nodes.

Governed by RFC-0003.
"""

from nexora.ast_nodes import (
    AskStmt,
    AssignStmt,
    BinaryExpr,
    Block,
    BoolLiteral,
    CallExpr,
    DuringStmt,
    EmptyLiteral,
    ExprStmt,
    FloatLiteral,
    GiveStmt,
    Identifier,
    IntLiteral,
    MakeStmt,
    NodeTransformer,
    NodeVisitor,
    Param,
    Program,
    ShowStmt,
    SkipStmt,
    StopStmt,
    StringLiteral,
    TaskDecl,
    TypeRef,
    UnaryExpr,
    WhenStmt,
    dump,
    iter_children,
    node_to_dict,
    validate_ast,
)


class TestASTNodeCatalogue:
    """Tests covering instantiation and fields of every AST node class."""

    def test_literals(self) -> None:
        """Test literal node creation and position tracking."""
        i = IntLiteral(42, line=1, column=5)
        assert i.value == 42
        assert i.line == 1
        assert i.column == 5

        f = FloatLiteral(3.14, line=2, column=1)
        assert f.value == 3.14

        s = StringLiteral("hello", line=3, column=1)
        assert s.value == "hello"

        b = BoolLiteral(True, line=4, column=1)
        assert b.value is True

        e = EmptyLiteral(line=5, column=1)
        assert e.line == 5

    def test_expressions(self) -> None:
        """Test Identifier, UnaryExpr, BinaryExpr, and CallExpr nodes."""
        ident = Identifier("x", line=1, column=1)
        assert ident.name == "x"

        unary = UnaryExpr("-", ident, line=1, column=3)
        assert unary.op == "-"
        assert unary.operand == ident

        binary = BinaryExpr(
            "+", ident, IntLiteral(1, line=1, column=7), line=1, column=5
        )
        assert binary.op == "+"
        assert binary.left == ident
        assert isinstance(binary.right, IntLiteral)

        call = CallExpr(
            "add", [ident, IntLiteral(2, line=1, column=9)], line=1, column=1
        )
        assert call.callee == "add"
        assert len(call.args) == 2

    def test_statements_and_declarations(self) -> None:
        """Test statement and top-level declaration nodes."""
        tref = TypeRef("int", line=1, column=10)
        param = Param("x", tref, line=1, column=7)
        blk = Block(
            [GiveStmt(Identifier("x", line=2, column=10), line=2, column=5)],
            line=1,
            column=20,
        )

        task = TaskDecl("f", [param], tref, blk, line=1, column=1)
        assert task.name == "f"
        assert len(task.params) == 1
        assert task.return_type == tref
        assert task.body == blk

        make_stmt = MakeStmt(
            "a", tref, IntLiteral(10, line=3, column=15), line=3, column=1
        )
        assign_stmt = AssignStmt(
            "a", IntLiteral(20, line=4, column=5), line=4, column=1
        )
        when_stmt = WhenStmt(
            BoolLiteral(True, line=5, column=7), blk, None, line=5, column=1
        )
        during_stmt = DuringStmt(
            BoolLiteral(True, line=6, column=9), blk, line=6, column=1
        )
        show_stmt = ShowStmt(Identifier("a", line=7, column=6), line=7, column=1)
        ask_stmt = AskStmt("input_val", tref, line=8, column=1)
        stop_stmt = StopStmt(line=9, column=1)
        skip_stmt = SkipStmt(line=10, column=1)
        expr_stmt = ExprStmt(CallExpr("f", [], line=11, column=1), line=11, column=1)

        prog = Program(
            [
                task,
                make_stmt,
                assign_stmt,
                when_stmt,
                during_stmt,
                show_stmt,
                ask_stmt,
                stop_stmt,
                skip_stmt,
                expr_stmt,
            ],
            line=1,
            column=1,
        )
        assert len(prog.body) == 10


class TestASTSerialization:
    """Tests covering node_to_dict serialization conforming to RFC-0003 §3.6."""

    def test_binary_expr_serialization(self) -> None:
        """BinaryExpr serializes to matching RFC-0003 §3.6 format."""
        left = Identifier("a", line=1, column=13)
        right = Identifier("b", line=1, column=17)
        expr = BinaryExpr("+", left, right, line=1, column=15)

        d = expr.to_dict()
        assert d == {
            "type": "BinaryExpr",
            "op": "+",
            "line": 1,
            "column": 15,
            "left": {"type": "Identifier", "name": "a", "line": 1, "column": 13},
            "right": {"type": "Identifier", "name": "b", "line": 1, "column": 17},
        }

    def test_resolved_type_serialization(self) -> None:
        """When semantic type is populated, it serializes as resolved_type."""
        ident = Identifier("x", line=1, column=1)
        # Mock semantic type string
        ident.type = "int"  # type: ignore[assignment]
        d = ident.to_dict()
        assert d["resolved_type"] == "int"
        assert d["type"] == "Identifier"

    def test_task_decl_serialization(self) -> None:
        """TaskDecl serializes nested params, return_type, and body block."""
        tref = TypeRef("int", line=1, column=15)
        param = Param("n", tref, line=1, column=12)
        body = Block(
            [GiveStmt(Identifier("n", line=2, column=10), line=2, column=5)],
            line=1,
            column=20,
        )
        task = TaskDecl("f", [param], tref, body, line=1, column=1)

        d = node_to_dict(task)
        assert d["type"] == "TaskDecl"
        assert d["name"] == "f"
        assert len(d["params"]) == 1
        assert d["return_type"]["name"] == "int"
        assert len(d["body"]["statements"]) == 1


class TestASTTraversalAndVisitor:
    """Tests covering iter_children, NodeVisitor, and NodeTransformer."""

    def test_iter_children_source_order(self) -> None:
        """iter_children yields all subnodes in source code order."""
        tref = TypeRef("int", line=1, column=1)
        left = Identifier("x", line=1, column=1)
        right = IntLiteral(5, line=1, column=5)
        binary = BinaryExpr("+", left, right, line=1, column=3)
        make = MakeStmt("y", tref, binary, line=1, column=1)

        children = list(iter_children(make))
        assert children == [tref, binary]

        binary_children = list(iter_children(binary))
        assert binary_children == [left, right]

    def test_node_visitor(self) -> None:
        """NodeVisitor traverses and dispatches to specific visit methods."""

        class IdentifierCollector(NodeVisitor):
            def __init__(self) -> None:
                self.names: list[str] = []

            def visit_Identifier(self, node: Identifier) -> None:
                self.names.append(node.name)

        expr = BinaryExpr(
            "+",
            Identifier("first", line=1, column=1),
            BinaryExpr(
                "*",
                Identifier("second", line=1, column=5),
                Identifier("third", line=1, column=10),
                line=1,
                column=8,
            ),
            line=1,
            column=3,
        )

        collector = IdentifierCollector()
        collector.visit(expr)
        assert collector.names == ["first", "second", "third"]

    def test_node_transformer(self) -> None:
        """NodeTransformer rewrites matching child nodes."""

        class MultiplyByTwoTransformer(NodeTransformer):
            def visit_IntLiteral(self, node: IntLiteral) -> IntLiteral:
                return IntLiteral(node.value * 2, line=node.line, column=node.column)

        expr = BinaryExpr(
            "+",
            IntLiteral(3, line=1, column=1),
            IntLiteral(4, line=1, column=5),
            line=1,
            column=3,
        )

        transformer = MultiplyByTwoTransformer()
        transformed = transformer.visit(expr)
        assert isinstance(transformed, BinaryExpr)
        assert isinstance(transformed.left, IntLiteral) and transformed.left.value == 6
        assert (
            isinstance(transformed.right, IntLiteral) and transformed.right.value == 8
        )


class TestASTPrettyPrinter:
    """Tests covering dump(node) matching RFC-0003 §3.7 and §3.8."""

    def test_dump_worked_example(self) -> None:
        """dump() prints tree format matching RFC-0003 §3.7."""
        left_sub = IntLiteral(2, line=1, column=14)
        mul = BinaryExpr(
            "*",
            IntLiteral(3, line=1, column=18),
            IntLiteral(4, line=1, column=22),
            line=1,
            column=20,
        )
        init_expr = BinaryExpr("+", left_sub, mul, line=1, column=16)
        make = MakeStmt("result", None, init_expr, line=1, column=1)
        show = ShowStmt(Identifier("result", line=1, column=32), line=1, column=27)
        prog = Program([make, show], line=1, column=1)

        output = dump(prog)
        expected = """Program
  MakeStmt result
    BinaryExpr +
      IntLiteral 2
      BinaryExpr *
        IntLiteral 3
        IntLiteral 4
  ShowStmt
    Identifier result"""
        assert output == expected


class TestASTValidation:
    """Tests covering validate_ast invariant checking (RFC-0003 §3.9)."""

    def test_validate_ast_valid_program(self) -> None:
        """A valid AST produces zero invariant violations."""
        prog = Program(
            [
                MakeStmt("x", None, IntLiteral(1, line=1, column=10), line=1, column=1),
                ShowStmt(Identifier("x", line=2, column=6), line=2, column=1),
            ],
            line=1,
            column=1,
        )
        violations = validate_ast(prog)
        assert violations == []

    def test_validate_ast_detects_nested_task_decl(self) -> None:
        """TaskDecl inside a Block is caught as a violation."""
        nested_task = TaskDecl(
            "bad", [], None, Block([], line=2, column=10), line=2, column=5
        )
        prog = Program(
            [Block([nested_task], line=1, column=1)],  # type: ignore[list-item]
            line=1,
            column=1,
        )
        violations = validate_ast(prog)
        assert any("found in a nested position" in v for v in violations)

    def test_validate_ast_detects_invalid_operator(self) -> None:
        """Invalid operators in UnaryExpr and BinaryExpr are flagged."""
        unary = UnaryExpr("~", IntLiteral(1, line=1, column=3), line=1, column=1)
        binary = BinaryExpr(
            "&",
            IntLiteral(1, line=1, column=1),
            IntLiteral(2, line=1, column=5),
            line=1,
            column=3,
        )
        prog = Program(
            [ExprStmt(unary, line=1, column=1), ExprStmt(binary, line=1, column=1)],
            line=1,
            column=1,
        )

        violations = validate_ast(prog)
        assert any(
            "UnaryExpr at line 1 has invalid operator '~'" in v for v in violations
        )
        assert any(
            "BinaryExpr at line 1 has invalid operator '&'" in v for v in violations
        )

    def test_validate_ast_detects_shared_node(self) -> None:
        """Reusing the same node instance in multiple positions is flagged (tree, not DAG)."""
        shared_literal = IntLiteral(10, line=1, column=1)
        binary = BinaryExpr("+", shared_literal, shared_literal, line=1, column=5)
        prog = Program([ExprStmt(binary, line=1, column=1)], line=1, column=1)

        violations = validate_ast(prog)
        assert any("Shared node detected" in v for v in violations)
