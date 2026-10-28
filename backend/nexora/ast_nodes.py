"""Abstract Syntax Tree (AST) node definitions for MiniLang v1.

Governed by RFC-0003, this module defines all AST node dataclasses, position
tracking, child node iteration, visitor/transformer patterns, serialization,
and tree validation.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .symbols import Symbol, Type

# Valid operators per RFC-0001 §3.2 and RFC-0003 §3.2, §3.9
VALID_UNARY_OPS: frozenset[str] = frozenset({"-", "not"})
VALID_BINARY_OPS: frozenset[str] = frozenset(
    {"either", "both", "==", "!=", "<", "<=", ">", ">=", "+", "-", "*", "/", "%"}
)


# =============================================================================
# Base Classes (RFC-0003 §3.1)
# =============================================================================


@dataclass(kw_only=True)
class Node:
    """Base class for all AST nodes with 1-based source position tracking."""

    line: int
    column: int

    def to_dict(self) -> dict[str, Any]:
        """Serialize the AST node to a JSON-compatible dictionary."""
        return node_to_dict(self)


@dataclass(kw_only=True)
class Expr(Node):
    """Base class for all expression nodes.

    Semantic analysis annotates `type` on every expression.
    """

    type: Type | None = field(default=None, compare=False, repr=False)


@dataclass(kw_only=True)
class Stmt(Node):
    """Base class for all statement nodes."""


# =============================================================================
# Program and Declarations (RFC-0003 §3.2)
# =============================================================================


@dataclass
class TypeRef(Node):
    """Reference to a type name (e.g. 'int', 'float', 'string', 'bool')."""

    name: str


@dataclass
class Param(Node):
    """Task parameter definition with name and declared type."""

    name: str
    type_ref: TypeRef
    symbol: Symbol | None = field(default=None, compare=False, repr=False)


@dataclass
class TaskDecl(Node):
    """Top-level task declaration."""

    name: str
    params: list[Param]
    return_type: TypeRef | None
    body: Block
    symbol: Symbol | None = field(default=None, compare=False, repr=False)


@dataclass
class Program(Node):
    """Root AST node representing a complete MiniLang source program."""

    body: list[Stmt | TaskDecl]


# =============================================================================
# Statements (RFC-0003 §3.2)
# =============================================================================


@dataclass
class Block(Stmt):
    """A brace-delimited block of statements creating a new lexical scope."""

    statements: list[Stmt]


@dataclass
class MakeStmt(Stmt):
    """Variable declaration with mandatory initializer and optional type annotation."""

    name: str
    declared_type: TypeRef | None
    initializer: Expr
    symbol: Symbol | None = field(default=None, compare=False, repr=False)
    needs_widening: bool = field(default=False, compare=False, repr=False)


@dataclass
class AssignStmt(Stmt):
    """Assignment statement modifying an existing declared variable."""

    name: str
    value: Expr
    symbol: Symbol | None = field(default=None, compare=False, repr=False)
    needs_widening: bool = field(default=False, compare=False, repr=False)


@dataclass
class WhenStmt(Stmt):
    """Conditional branching statement with mandatory then-block and optional else."""

    condition: Expr
    then_block: Block
    else_branch: Block | WhenStmt | None = None


@dataclass
class DuringStmt(Stmt):
    """Loop statement repeating body while condition evaluates to yes."""

    condition: Expr
    body: Block


@dataclass
class GiveStmt(Stmt):
    """Return statement from a task with optional return value."""

    value: Expr | None = None
    needs_widening: bool = field(default=False, compare=False, repr=False)


@dataclass
class ShowStmt(Stmt):
    """Output statement printing expression value followed by newline."""

    value: Expr


@dataclass
class AskStmt(Stmt):
    """Input statement reading a value of specified type from standard input."""

    name: str
    type_ref: TypeRef
    symbol: Symbol | None = field(default=None, compare=False, repr=False)


@dataclass
class StopStmt(Stmt):
    """Break statement exiting the innermost enclosing during-loop."""


@dataclass
class SkipStmt(Stmt):
    """Continue statement advancing to the next iteration of innermost during-loop."""


@dataclass
class ExprStmt(Stmt):
    """Expression evaluated as a statement (e.g. task invocation)."""

    expression: Expr


# =============================================================================
# Expressions (RFC-0003 §3.2)
# =============================================================================


@dataclass
class IntLiteral(Expr):
    """Integer literal value (e.g. 42)."""

    value: int


@dataclass
class FloatLiteral(Expr):
    """Floating-point literal value (e.g. 3.14)."""

    value: float


@dataclass
class StringLiteral(Expr):
    """String literal value."""

    value: str


@dataclass
class BoolLiteral(Expr):
    """Boolean literal value (yes or no)."""

    value: bool


@dataclass
class EmptyLiteral(Expr):
    """Literal representing empty (None)."""


@dataclass
class Identifier(Expr):
    """Identifier reference to a variable or name."""

    name: str
    symbol: Symbol | None = field(default=None, compare=False, repr=False)


@dataclass
class UnaryExpr(Expr):
    """Unary operation applied to an operand ('-' or 'not')."""

    op: str
    operand: Expr


@dataclass
class BinaryExpr(Expr):
    """Binary operation between left and right expressions."""

    op: str
    left: Expr
    right: Expr


@dataclass
class CallExpr(Expr):
    """Invocation of a named task with argument expressions."""

    callee: str
    args: list[Expr]
    symbol: Symbol | None = field(default=None, compare=False, repr=False)
    arg_widenings: list[bool] = field(default_factory=list, compare=False, repr=False)


# =============================================================================
# Traversal and Iteration (RFC-0003 §3.5)
# =============================================================================


def iter_children(node: Node) -> Iterator[Node]:
    """Yield all immediate child AST nodes of `node` in source order."""
    match node:
        case Program(body=body):
            yield from body
        case TaskDecl(params=params, return_type=return_type, body=body):
            yield from params
            if return_type is not None:
                yield return_type
            yield body
        case Param(type_ref=type_ref):
            yield type_ref
        case TypeRef():
            return
        case Block(statements=statements):
            yield from statements
        case MakeStmt(declared_type=declared_type, initializer=initializer):
            if declared_type is not None:
                yield declared_type
            yield initializer
        case AssignStmt(value=value):
            yield value
        case WhenStmt(
            condition=condition, then_block=then_block, else_branch=else_branch
        ):
            yield condition
            yield then_block
            if else_branch is not None:
                yield else_branch
        case DuringStmt(condition=condition, body=body):
            yield condition
            yield body
        case GiveStmt(value=value):
            if value is not None:
                yield value
        case ShowStmt(value=value):
            yield value
        case AskStmt(type_ref=type_ref):
            yield type_ref
        case StopStmt() | SkipStmt():
            return
        case ExprStmt(expression=expression):
            yield expression
        case (
            IntLiteral()
            | FloatLiteral()
            | StringLiteral()
            | BoolLiteral()
            | EmptyLiteral()
            | Identifier()
        ):
            return
        case UnaryExpr(operand=operand):
            yield operand
        case BinaryExpr(left=left, right=right):
            yield left
            yield right
        case CallExpr(args=args):
            yield from args


class NodeVisitor:
    """Base class for traversing AST nodes via visit_<ClassName> methods."""

    def visit(self, node: Node) -> Any:
        """Dispatch visit to visit_<ClassName> or fall back to generic_visit."""
        method_name = f"visit_{type(node).__name__}"
        visitor = getattr(self, method_name, self.generic_visit)
        return visitor(node)

    def generic_visit(self, node: Node) -> Any:
        """Default visitor that traverses all child nodes in source order."""
        for child in iter_children(node):
            self.visit(child)
        return None


class NodeTransformer(NodeVisitor):
    """AST visitor that allows rewriting or replacing nodes."""

    def generic_visit(self, node: Node) -> Node:
        """Walk children and replace them with transformed results."""
        match node:
            case Program(body=body):
                node.body = [self.visit(item) for item in body]
            case TaskDecl(params=params, return_type=return_type, body=body):
                node.params = [self.visit(p) for p in params]
                if return_type is not None:
                    node.return_type = self.visit(return_type)
                node.body = self.visit(body)
            case Param(type_ref=type_ref):
                node.type_ref = self.visit(type_ref)
            case TypeRef():
                pass
            case Block(statements=statements):
                node.statements = [self.visit(s) for s in statements]
            case MakeStmt(declared_type=declared_type, initializer=initializer):
                if declared_type is not None:
                    node.declared_type = self.visit(declared_type)
                node.initializer = self.visit(initializer)
            case AssignStmt(value=value):
                node.value = self.visit(value)
            case WhenStmt(
                condition=condition, then_block=then_block, else_branch=else_branch
            ):
                node.condition = self.visit(condition)
                node.then_block = self.visit(then_block)
                if else_branch is not None:
                    node.else_branch = self.visit(else_branch)
            case DuringStmt(condition=condition, body=body):
                node.condition = self.visit(condition)
                node.body = self.visit(body)
            case GiveStmt(value=value):
                if value is not None:
                    node.value = self.visit(value)
            case ShowStmt(value=value):
                node.value = self.visit(value)
            case AskStmt(type_ref=type_ref):
                node.type_ref = self.visit(type_ref)
            case StopStmt() | SkipStmt():
                pass
            case ExprStmt(expression=expression):
                node.expression = self.visit(expression)
            case (
                IntLiteral()
                | FloatLiteral()
                | StringLiteral()
                | BoolLiteral()
                | EmptyLiteral()
                | Identifier()
            ):
                pass
            case UnaryExpr(operand=operand):
                node.operand = self.visit(operand)
            case BinaryExpr(left=left, right=right):
                node.left = self.visit(left)
                node.right = self.visit(right)
            case CallExpr(args=args):
                node.args = [self.visit(a) for a in args]
        return node


# =============================================================================
# Serialization (RFC-0003 §3.6)
# =============================================================================


def node_to_dict(node: Node) -> dict[str, Any]:
    """Serialize an AST node to a JSON-compatible dictionary.

    Follows RFC-0003 §3.6 rules:
    - 'type' is the class name of the node.
    - 'line' and 'column' are included.
    - Child nodes become nested dicts; lists become lists of dicts.
    - Semantic annotations are exported if present (e.g. 'resolved_type').
    """
    result: dict[str, Any] = {
        "type": type(node).__name__,
        "line": node.line,
        "column": node.column,
    }

    # Semantic type annotation
    if isinstance(node, Expr) and node.type is not None:
        result["resolved_type"] = str(node.type)

    match node:
        case Program(body=body):
            result["body"] = [node_to_dict(stmt) for stmt in body]
        case TaskDecl(name=name, params=params, return_type=return_type, body=body):
            result["name"] = name
            result["params"] = [node_to_dict(p) for p in params]
            result["return_type"] = node_to_dict(return_type) if return_type else None
            result["body"] = node_to_dict(body)
        case Param(name=name, type_ref=type_ref):
            result["name"] = name
            result["type_ref"] = node_to_dict(type_ref)
        case TypeRef(name=name):
            result["name"] = name
        case Block(statements=statements):
            result["statements"] = [node_to_dict(s) for s in statements]
        case MakeStmt(name=name, declared_type=declared_type, initializer=initializer):
            result["name"] = name
            result["declared_type"] = (
                node_to_dict(declared_type) if declared_type is not None else None
            )
            result["initializer"] = node_to_dict(initializer)
        case AssignStmt(name=name, value=value):
            result["name"] = name
            result["value"] = node_to_dict(value)
        case WhenStmt(
            condition=condition, then_block=then_block, else_branch=else_branch
        ):
            result["condition"] = node_to_dict(condition)
            result["then_block"] = node_to_dict(then_block)
            result["else_branch"] = (
                node_to_dict(else_branch) if else_branch is not None else None
            )
        case DuringStmt(condition=condition, body=body):
            result["condition"] = node_to_dict(condition)
            result["body"] = node_to_dict(body)
        case GiveStmt(value=value):
            result["value"] = node_to_dict(value) if value is not None else None
        case ShowStmt(value=value):
            result["value"] = node_to_dict(value)
        case AskStmt(name=name, type_ref=type_ref):
            result["name"] = name
            result["type_ref"] = node_to_dict(type_ref)
        case StopStmt() | SkipStmt():
            pass
        case ExprStmt(expression=expression):
            result["expression"] = node_to_dict(expression)
        case (
            IntLiteral(value=value)
            | FloatLiteral(value=value)
            | StringLiteral(value=value)
        ):
            result["value"] = value
        case BoolLiteral(value=value):
            result["value"] = value
        case EmptyLiteral():
            pass
        case Identifier(name=name):
            result["name"] = name
        case UnaryExpr(op=op, operand=operand):
            result["op"] = op
            result["operand"] = node_to_dict(operand)
        case BinaryExpr(op=op, left=left, right=right):
            result["op"] = op
            result["left"] = node_to_dict(left)
            result["right"] = node_to_dict(right)
        case CallExpr(callee=callee, args=args):
            result["callee"] = callee
            result["args"] = [node_to_dict(arg) for arg in args]

    return result


# =============================================================================
# Pretty Printer (RFC-0003 §3.7)
# =============================================================================


def dump(node: Node, indent: int = 0) -> str:
    """Return an indented ASCII tree representation of an AST node for debugging.

    Args:
        node: The root AST node to print.
        indent: Current indentation level (spaces = indent * 2).

    Returns:
        Formatted multi-line tree string.
    """
    prefix = "  " * indent
    name = type(node).__name__

    # Detail string for the node header
    detail = ""
    match node:
        case Program():
            detail = ""
        case TaskDecl(name=task_name):
            detail = f" {task_name}"
        case Param(name=param_name):
            detail = f" {param_name}"
        case TypeRef(name=type_name):
            detail = f" {type_name}"
        case MakeStmt(name=var_name):
            detail = f" {var_name}"
        case AssignStmt(name=var_name):
            detail = f" {var_name}"
        case AskStmt(name=var_name):
            detail = f" {var_name}"
        case IntLiteral(value=val) | FloatLiteral(value=val):
            detail = f" {val}"
        case StringLiteral(value=val):
            detail = f' "{val}"'
        case BoolLiteral(value=val):
            detail = f" {val}"
        case Identifier(name=var_name):
            detail = f" {var_name}"
        case UnaryExpr(op=op):
            detail = f" {op}"
        case BinaryExpr(op=op):
            detail = f" {op}"
        case CallExpr(callee=callee):
            detail = f" {callee}"

    lines = [f"{prefix}{name}{detail}"]
    for child in iter_children(node):
        lines.append(dump(child, indent + 1))
    return "\n".join(lines)


# =============================================================================
# Invariant Validation (RFC-0003 §3.9)
# =============================================================================


def validate_ast(program: Program) -> list[str]:
    """Check all RFC-0003 §3.9 invariants on an AST tree.

    Invariants checked:
    1. Every node has positive line and column numbers.
    2. TaskDecl occurs only directly in Program.body.
    3. WhenStmt.else_branch is None, a Block, or a WhenStmt.
    4. UnaryExpr.op in {"-", "not"}.
    5. BinaryExpr.op in {"either", "both", "==", "!=", "<", "<=", ">", ">=", "+", "-", "*", "/", "%"}.
    6. No node instance is shared between parents (tree, not DAG).

    Returns:
        List of invariant violation descriptions (empty if tree is valid).
    """
    violations: list[str] = []
    seen_node_ids: set[int] = set()

    def check_node(node: Node, in_program_root: bool) -> None:
        # Check node uniqueness (tree, not DAG)
        node_id = id(node)
        if node_id in seen_node_ids:
            violations.append(
                f"Shared node detected: {type(node).__name__} at line {node.line}, column {node.column}"
            )
            return
        seen_node_ids.add(node_id)

        # Invariant 1: Positive line and column
        if node.line <= 0 or node.column <= 0:
            violations.append(
                f"Invalid position ({node.line}:{node.column}) on {type(node).__name__}"
            )

        # Invariant 2: TaskDecl only directly in Program.body
        if isinstance(node, TaskDecl) and not in_program_root:
            violations.append(
                f"TaskDecl '{node.name}' at line {node.line} found in a nested position (only valid at top level)"
            )

        # Invariant 3: WhenStmt else_branch
        if (
            isinstance(node, WhenStmt)
            and node.else_branch is not None
            and not isinstance(node.else_branch, Block)
            and not isinstance(node.else_branch, WhenStmt)
        ):
            violations.append(
                f"WhenStmt at line {node.line} has invalid else_branch type {type(node.else_branch).__name__}"
            )

        # Invariant 4: UnaryExpr.op
        if isinstance(node, UnaryExpr) and node.op not in VALID_UNARY_OPS:
            violations.append(
                f"UnaryExpr at line {node.line} has invalid operator '{node.op}'"
            )

        # Invariant 5: BinaryExpr.op
        if isinstance(node, BinaryExpr) and node.op not in VALID_BINARY_OPS:
            violations.append(
                f"BinaryExpr at line {node.line} has invalid operator '{node.op}'"
            )

        # Recurse to children
        for child in iter_children(node):
            check_node(child, in_program_root=False)

    if not isinstance(program, Program):
        return [f"Root node must be Program, found {type(program).__name__}"]

    seen_node_ids.add(id(program))
    if program.line <= 0 or program.column <= 0:
        violations.append(
            f"Invalid position ({program.line}:{program.column}) on Program root"
        )

    for top_level_item in program.body:
        check_node(top_level_item, in_program_root=True)

    return violations
