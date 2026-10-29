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
                new_body: list[Any] = []
                for item in body:
                    res = self.visit(item)
                    if res is None:
                        continue
                    if isinstance(res, list):
                        new_body.extend(res)
                    elif isinstance(res, Block):
                        new_body.extend(res.statements)
                    else:
                        new_body.append(res)
                node.body = new_body
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
                new_stmts: list[Any] = []
                for s in statements:
                    res = self.visit(s)
                    if res is None:
                        continue
                    if isinstance(res, list):
                        new_stmts.extend(res)
                    elif isinstance(res, Block):
                        new_stmts.extend(res.statements)
                    else:
                        new_stmts.append(res)
                node.statements = new_stmts
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


# =============================================================================
# Tree Cloning and Unparsing (RFC-0003 Addendum / RFC-0007 §3.1)
# =============================================================================


def clone_tree(node: Any) -> Any:
    """Recursively clone an AST node, creating a deep structural copy while sharing annotations.

    Per RFC-0007 §3.1: copies nodes but shares annotation objects (`type`, `symbol`).
    """
    match node:
        case Program(body=body, line=line, column=column):
            return Program(
                body=[clone_tree(item) for item in body],
                line=line,
                column=column,
            )
        case TaskDecl(
            name=name,
            params=params,
            return_type=return_type,
            body=body,
            line=line,
            column=column,
            symbol=symbol,
        ):
            return TaskDecl(
                name=name,
                params=[clone_tree(p) for p in params],
                return_type=(
                    clone_tree(return_type) if return_type is not None else None
                ),
                body=clone_tree(body),
                line=line,
                column=column,
                symbol=symbol,
            )
        case Param(name=name, type_ref=type_ref, line=line, column=column):
            return Param(
                name=name,
                type_ref=clone_tree(type_ref),
                line=line,
                column=column,
            )
        case TypeRef(name=name, line=line, column=column):
            return TypeRef(name=name, line=line, column=column)
        case Block(statements=statements, line=line, column=column):
            return Block(
                statements=[clone_tree(s) for s in statements],
                line=line,
                column=column,
            )
        case MakeStmt(
            name=name,
            declared_type=declared_type,
            initializer=initializer,
            line=line,
            column=column,
            symbol=symbol,
            needs_widening=needs_widening,
        ):
            return MakeStmt(
                name=name,
                declared_type=(
                    clone_tree(declared_type) if declared_type is not None else None
                ),
                initializer=clone_tree(initializer),
                line=line,
                column=column,
                symbol=symbol,
                needs_widening=needs_widening,
            )
        case AssignStmt(
            name=name,
            value=value,
            line=line,
            column=column,
            symbol=symbol,
            needs_widening=needs_widening,
        ):
            return AssignStmt(
                name=name,
                value=clone_tree(value),
                line=line,
                column=column,
                symbol=symbol,
                needs_widening=needs_widening,
            )
        case WhenStmt(
            condition=condition,
            then_block=then_block,
            else_branch=else_branch,
            line=line,
            column=column,
        ):
            return WhenStmt(
                condition=clone_tree(condition),
                then_block=clone_tree(then_block),
                else_branch=(
                    clone_tree(else_branch) if else_branch is not None else None
                ),
                line=line,
                column=column,
            )
        case DuringStmt(condition=condition, body=body, line=line, column=column):
            return DuringStmt(
                condition=clone_tree(condition),
                body=clone_tree(body),
                line=line,
                column=column,
            )
        case GiveStmt(
            value=value,
            line=line,
            column=column,
            needs_widening=needs_widening,
        ):
            return GiveStmt(
                value=clone_tree(value) if value is not None else None,
                line=line,
                column=column,
                needs_widening=needs_widening,
            )
        case ShowStmt(value=value, line=line, column=column):
            return ShowStmt(
                value=clone_tree(value),
                line=line,
                column=column,
            )
        case AskStmt(
            name=name,
            type_ref=type_ref,
            line=line,
            column=column,
            symbol=symbol,
        ):
            return AskStmt(
                name=name,
                type_ref=clone_tree(type_ref),
                line=line,
                column=column,
                symbol=symbol,
            )
        case StopStmt(line=line, column=column):
            return StopStmt(line=line, column=column)
        case SkipStmt(line=line, column=column):
            return SkipStmt(line=line, column=column)
        case ExprStmt(expression=expression, line=line, column=column):
            return ExprStmt(
                expression=clone_tree(expression),
                line=line,
                column=column,
            )
        case IntLiteral(value=value, line=line, column=column, type=typ):
            return IntLiteral(value=value, line=line, column=column, type=typ)
        case FloatLiteral(value=value, line=line, column=column, type=typ):
            return FloatLiteral(value=value, line=line, column=column, type=typ)
        case StringLiteral(value=value, line=line, column=column, type=typ):
            return StringLiteral(value=value, line=line, column=column, type=typ)
        case BoolLiteral(value=value, line=line, column=column, type=typ):
            return BoolLiteral(value=value, line=line, column=column, type=typ)
        case EmptyLiteral(line=line, column=column, type=typ):
            return EmptyLiteral(line=line, column=column, type=typ)
        case Identifier(name=name, line=line, column=column, type=typ, symbol=symbol):
            return Identifier(
                name=name, line=line, column=column, type=typ, symbol=symbol
            )
        case UnaryExpr(op=op, operand=operand, line=line, column=column, type=typ):
            return UnaryExpr(
                op=op,
                operand=clone_tree(operand),
                line=line,
                column=column,
                type=typ,
            )
        case BinaryExpr(
            op=op,
            left=left,
            right=right,
            line=line,
            column=column,
            type=typ,
        ):
            return BinaryExpr(
                op=op,
                left=clone_tree(left),
                right=clone_tree(right),
                line=line,
                column=column,
                type=typ,
            )
        case CallExpr(
            callee=callee,
            args=args,
            line=line,
            column=column,
            type=typ,
            symbol=symbol,
            arg_widenings=arg_widenings,
        ):
            return CallExpr(
                callee=callee,
                args=[clone_tree(a) for a in args],
                line=line,
                column=column,
                type=typ,
                symbol=symbol,
                arg_widenings=(
                    list(arg_widenings) if arg_widenings is not None else None
                ),
            )
        case _:
            raise ValueError(f"Unknown node type for clone_tree: {type(node).__name__}")


_OP_PREC: dict[str, int] = {
    "either": 1,
    "both": 2,
    "==": 4,
    "!=": 4,
    "<": 5,
    "<=": 5,
    ">": 5,
    ">=": 5,
    "+": 6,
    "-": 6,
    "*": 7,
    "/": 7,
    "%": 7,
}


def _escape_str(val: str) -> str:
    escaped = (
        val.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
        .replace("\r", "\\r")
    )
    return f'"{escaped}"'


def _unparse_expr(node: Expr, parent_prec: int = 0) -> str:
    match node:
        case IntLiteral(value=v):
            return str(v)
        case FloatLiteral(value=v):
            s = str(v)
            if "." not in s and "e" not in s and "E" not in s:
                s += ".0"
            return s
        case StringLiteral(value=v):
            return _escape_str(v)
        case BoolLiteral(value=v):
            return "yes" if v else "no"
        case EmptyLiteral():
            return "empty"
        case Identifier(name=n):
            return n
        case UnaryExpr(op=op, operand=operand):
            prec = 8 if op == "-" else 3
            inner = _unparse_expr(operand, parent_prec=prec)
            res = f"{op}{inner}" if op == "-" else f"{op} {inner}"
            if prec < parent_prec:
                return f"({res})"
            return res
        case BinaryExpr(op=op, left=left, right=right):
            prec = _OP_PREC.get(op, 0)
            left_str = _unparse_expr(left, parent_prec=prec)
            right_str = _unparse_expr(right, parent_prec=prec + 1)
            res = f"{left_str} {op} {right_str}"
            if prec < parent_prec:
                return f"({res})"
            return res
        case CallExpr(callee=callee, args=args):
            args_str = ", ".join(_unparse_expr(a, 0) for a in args)
            return f"{callee}({args_str})"
        case _:
            return f"<{type(node).__name__}>"


def _unparse_block(block: Block, indent_level: int = 0) -> str:
    if not block.statements:
        return "{}"
    lines = ["{"]
    for s in block.statements:
        lines.append(_unparse_stmt(s, indent_level + 1))
    lines.append("    " * indent_level + "}")
    return "\n".join(lines)


def _unparse_stmt(node: Stmt | TaskDecl, indent_level: int = 0) -> str:
    ind = "    " * indent_level
    match node:
        case MakeStmt(name=name, declared_type=dtype, initializer=init):
            typ = f": {dtype.name}" if dtype is not None else ""
            return f"{ind}make {name}{typ} = {_unparse_expr(init)};"
        case AssignStmt(name=name, value=val):
            return f"{ind}{name} = {_unparse_expr(val)};"
        case AskStmt(name=name, type_ref=tref):
            return f"{ind}ask {name}: {tref.name};"
        case ShowStmt(value=val):
            return f"{ind}show({_unparse_expr(val)});"
        case GiveStmt(value=val):
            if val is not None:
                return f"{ind}give {_unparse_expr(val)};"
            return f"{ind}give;"
        case StopStmt():
            return f"{ind}stop;"
        case SkipStmt():
            return f"{ind}skip;"
        case ExprStmt(expression=expr):
            return f"{ind}{_unparse_expr(expr)};"
        case WhenStmt(condition=cond, then_block=then_b, else_branch=else_b):
            cond_str = _unparse_expr(cond)
            res = f"{ind}when ({cond_str}) {_unparse_block(then_b, indent_level)}"
            if else_b is not None:
                if isinstance(else_b, WhenStmt):
                    sub_when = _unparse_stmt(else_b, 0)
                    res += f" otherwise {sub_when.lstrip()}"
                elif isinstance(else_b, Block):
                    res += f" otherwise {_unparse_block(else_b, indent_level)}"
            return res
        case DuringStmt(condition=cond, body=body):
            cond_str = _unparse_expr(cond)
            return f"{ind}during ({cond_str}) {_unparse_block(body, indent_level)}"
        case TaskDecl(name=name, params=params, return_type=ret_type, body=body):
            params_str = ", ".join(f"{p.name}: {p.type_ref.name}" for p in params)
            ret_str = f": {ret_type.name}" if ret_type is not None else ""
            return f"{ind}task {name}({params_str}){ret_str} {_unparse_block(body, indent_level)}"
        case Block():
            return f"{ind}{_unparse_block(node, indent_level)}"
        case _:
            return f"{ind}/* {type(node).__name__} */"


def unparse(node: Node) -> str:
    """Format an AST node back into MiniLang source code representation."""
    if isinstance(node, Expr):
        return _unparse_expr(node, 0)
    if isinstance(node, Program):
        return "\n".join(_unparse_stmt(item, 0) for item in node.body)
    if isinstance(node, Block):
        return _unparse_block(node, 0)
    if isinstance(node, (Stmt, TaskDecl)):
        return _unparse_stmt(node, 0)
    if isinstance(node, TypeRef):
        return node.name
    if isinstance(node, Param):
        return f"{node.name}: {node.type_ref.name}"
    return f"/* {type(node).__name__} */"
