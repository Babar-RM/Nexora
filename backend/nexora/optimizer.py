"""Optimizer implementation for MiniLang v1 (AST and TAC optimization).

Governed by RFC-0007. Implements:
1. Shared folding module for constant evaluation (RFC-0007 §3.3)
2. AST-level optimizer for constant folding, safe algebraic simplification,
   dead-branch and dead-code elimination (RFC-0007 §3.4)
3. TAC-level optimizer for local value propagation, folding, branch folding,
   unreachable-block removal, jump cleanup, and dead-code elimination (RFC-0007 §3.5)
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .ast_nodes import (
    BinaryExpr,
    Block,
    BoolLiteral,
    DuringStmt,
    EmptyLiteral,
    Expr,
    ExprStmt,
    FloatLiteral,
    GiveStmt,
    Identifier,
    IntLiteral,
    NodeTransformer,
    Program,
    Stmt,
    StringLiteral,
    UnaryExpr,
    WhenStmt,
    clone_tree,
    unparse,
)
from .errors import InternalCompilerError
from .ir import (
    Ask,
    BinOp,
    Call,
    Const,
    Copy,
    FuncBegin,
    FuncEnd,
    Goto,
    IfFalse,
    IfTrue,
    Label,
    Operand,
    Param,
    Print,
    Return,
    TACInstr,
    Temp,
    UnOp,
    Var,
    build_cfg,
    format_instruction,
)
from .symbols import Type, binary_result_type, is_numeric, unary_result_type

# =============================================================================
# 1. Public API & Reporting Data Structures (RFC-0007 §3.1, §3.8)
# =============================================================================

MAX_NOTES_PER_COMPILATION: int = 500


@dataclass(frozen=True)
class OptimizationNote:
    """Diagnostic note recording an optimization transformation."""

    level: str  # "ast" | "tac" | "summary"
    kind: (
        str  # "fold", "simplify", "dead-branch", "dead-code", "propagate", "jump", ...
    )
    line: int  # MiniLang line (0 if synthetic)
    column: int
    before: str  # short text of old form, e.g. "3 * 4"
    after: str  # short text of new form, e.g. "12"

    def to_dict(self) -> dict[str, Any]:
        """Convert note to dictionary for JSON serialization."""
        return {
            "level": self.level,
            "kind": self.kind,
            "line": self.line,
            "column": self.column,
            "before": self.before,
            "after": self.after,
        }


@dataclass
class OptimizationReport:
    """Report summarizing all optimizations performed across iterations."""

    notes: list[OptimizationNote]
    iterations: int

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary for JSON serialization."""
        return {
            "iterations": self.iterations,
            "notes": [n.to_dict() for n in self.notes],
        }


class NoteCollector:
    """Collects optimization notes up to MAX_NOTES_PER_COMPILATION cap."""

    def __init__(self, max_notes: int = MAX_NOTES_PER_COMPILATION) -> None:
        self.max_notes = max_notes
        self.notes: list[OptimizationNote] = []
        self._suppressed: int = 0

    def add(
        self,
        level: str,
        kind: str,
        line: int,
        column: int,
        before: str,
        after: str,
    ) -> None:
        """Record an optimization note, respecting the maximum limit."""
        if len(self.notes) < self.max_notes:
            self.notes.append(
                OptimizationNote(
                    level=level,
                    kind=kind,
                    line=line,
                    column=column,
                    before=before,
                    after=after,
                )
            )
        else:
            self._suppressed += 1

    def finalize(self) -> list[OptimizationNote]:
        """Return all collected notes, appending a summary note if truncated."""
        res = list(self.notes)
        if self._suppressed > 0:
            res.append(
                OptimizationNote(
                    level="summary",
                    kind="truncated",
                    line=0,
                    column=0,
                    before="",
                    after=f"and {self._suppressed} more",
                )
            )
        return res


# =============================================================================
# 2. Shared Folding Module (RFC-0007 §3.2, §3.3)
# =============================================================================


def fold_unary(op: str, value: object, vtype: Type) -> tuple[object, Type] | None:
    """Evaluate constant unary operation compile-time.

    Returns (folded_value, static_type) or None if the operation cannot be folded
    under RFC-0007 §3.2 safety rules.
    """
    res_type = unary_result_type(op, vtype)
    if res_type is None or res_type == Type.ERROR:
        return None

    try:
        if op == "-":
            if vtype == Type.INT:
                res = -int(value)  # type: ignore[arg-type]
            elif vtype == Type.FLOAT:
                res = -float(value)  # type: ignore[arg-type]
            else:
                return None
        elif op == "not":
            if vtype == Type.BOOL:
                res = not bool(value)
            else:
                return None
        elif op == "float":
            if is_numeric(vtype):
                res = float(value)  # type: ignore[arg-type]
            else:
                return None
        else:
            return None
    except (ArithmeticError, ValueError, OverflowError):
        return None

    # Never-fold checks (RFC-0007 §3.2)
    if isinstance(res, float):
        if math.isnan(res) or math.isinf(res):
            return None
    elif isinstance(res, int) and res.bit_length() > 10000:
        return None

    return res, res_type


def fold_binary(
    op: str,
    left: object,
    ltype: Type,
    right: object,
    rtype: Type,
) -> tuple[object, Type] | None:
    """Evaluate constant binary operation compile-time.

    Returns (folded_value, static_type) or None if the operation cannot be folded
    under RFC-0007 §3.2 safety rules.
    """
    res_type = binary_result_type(op, ltype, rtype)
    if res_type is None or res_type == Type.ERROR:
        return None

    # ZeroDivision checks (never fold division or modulo by zero)
    if op in ("/", "%") and (right == 0 or right == 0.0):
        return None

    try:
        if op == "+":
            if ltype == Type.INT and rtype == Type.INT:
                res = int(left) + int(right)  # type: ignore[arg-type]
            elif ltype == Type.STRING and rtype == Type.STRING:
                res = str(left) + str(right)
            elif is_numeric(ltype) and is_numeric(rtype):
                res = float(left) + float(right)  # type: ignore[arg-type]
            else:
                return None
        elif op == "-":
            if ltype == Type.INT and rtype == Type.INT:
                res = int(left) - int(right)  # type: ignore[arg-type]
            elif is_numeric(ltype) and is_numeric(rtype):
                res = float(left) - float(right)  # type: ignore[arg-type]
            else:
                return None
        elif op == "*":
            if ltype == Type.INT and rtype == Type.INT:
                res = int(left) * int(right)  # type: ignore[arg-type]
            elif is_numeric(ltype) and is_numeric(rtype):
                res = float(left) * float(right)  # type: ignore[arg-type]
            else:
                return None
        elif op == "/":
            # Always produces float in MiniLang
            res = float(left) / float(right)  # type: ignore[arg-type]
        elif op == "%":
            if ltype == Type.INT and rtype == Type.INT:
                res = int(left) % int(right)  # type: ignore[arg-type]
            elif is_numeric(ltype) and is_numeric(rtype):
                res = float(left) % float(right)  # type: ignore[arg-type]
            else:
                return None
        elif op == "<":
            res = left < right  # type: ignore[operator]
        elif op == "<=":
            res = left <= right  # type: ignore[operator]
        elif op == ">":
            res = left > right  # type: ignore[operator]
        elif op == ">=":
            res = left >= right  # type: ignore[operator]
        elif op == "==":
            res = left == right
        elif op == "!=":
            res = left != right
        else:
            return None
    except (ArithmeticError, ValueError, OverflowError):
        return None

    # Never-fold checks (RFC-0007 §3.2)
    if isinstance(res, float):
        if math.isnan(res) or math.isinf(res):
            return None
    elif isinstance(res, int):
        if res.bit_length() > 10000:
            return None
    elif isinstance(res, str) and len(res) > 65536:
        return None

    # Defensive check against mismatched result types
    if res_type == Type.INT and not isinstance(res, int):
        return None
    if res_type == Type.FLOAT and not isinstance(res, float):
        return None
    if res_type == Type.BOOL and not isinstance(res, bool):
        return None
    if res_type == Type.STRING and not isinstance(res, str):
        return None

    return res, res_type


# =============================================================================
# 3. AST-Level Optimizer (RFC-0007 §3.4)
# =============================================================================


class ASTOptimizerPass(NodeTransformer):
    """Single post-order rewrite pass on the AST."""

    def __init__(self, collector: NoteCollector) -> None:
        self.collector = collector
        self.changes: int = 0

    def visit_UnaryExpr(self, node: UnaryExpr) -> Expr:
        """Post-order visit: simplify or fold unary expressions."""
        node = self.generic_visit(node)  # type: ignore[assignment]
        if not isinstance(node, UnaryExpr):
            return node

        # Double negation simplification: not (not e) -> e
        if (
            node.op == "not"
            and isinstance(node.operand, UnaryExpr)
            and node.operand.op == "not"
        ):
            self.changes += 1
            before = unparse(node)
            after = unparse(node.operand.operand)
            self.collector.add(
                level="ast",
                kind="simplify",
                line=node.line,
                column=node.column,
                before=before,
                after=after,
            )
            return node.operand.operand

        # Literal folding
        val_node = node.operand
        if isinstance(val_node, (IntLiteral, FloatLiteral, BoolLiteral)):
            folded = fold_unary(node.op, val_node.value, val_node.type or Type.ERROR)
            if folded is not None:
                res_val, res_type = folded
                self.changes += 1
                before = unparse(node)
                if res_type == Type.INT:
                    new_node = IntLiteral(
                        value=int(res_val),  # type: ignore[arg-type]
                        line=node.line,
                        column=node.column,
                        type=Type.INT,
                    )
                elif res_type == Type.FLOAT:
                    new_node = FloatLiteral(
                        value=float(res_val),  # type: ignore[arg-type]
                        line=node.line,
                        column=node.column,
                        type=Type.FLOAT,
                    )
                else:
                    new_node = BoolLiteral(
                        value=bool(res_val),
                        line=node.line,
                        column=node.column,
                        type=Type.BOOL,
                    )
                after = unparse(new_node)
                self.collector.add(
                    level="ast",
                    kind="fold",
                    line=node.line,
                    column=node.column,
                    before=before,
                    after=after,
                )
                return new_node

        return node

    def visit_BinaryExpr(self, node: BinaryExpr) -> Expr:
        """Post-order visit: fold literals, short-circuit, and simplify algebraically."""
        node = self.generic_visit(node)  # type: ignore[assignment]
        if not isinstance(node, BinaryExpr):
            return node

        # A. Constant folding on two literals (excluding both/either handled by short-circuit)
        if (
            node.op not in ("both", "either")
            and isinstance(
                node.left, (IntLiteral, FloatLiteral, StringLiteral, BoolLiteral)
            )
            and isinstance(
                node.right,
                (IntLiteral, FloatLiteral, StringLiteral, BoolLiteral),
            )
        ):
            folded = fold_binary(
                node.op,
                node.left.value,
                node.left.type or Type.ERROR,
                node.right.value,
                node.right.type or Type.ERROR,
            )
            if folded is not None:
                res_val, res_type = folded
                self.changes += 1
                before = unparse(node)
                if res_type == Type.INT:
                    new_node = IntLiteral(
                        value=int(res_val),  # type: ignore[arg-type]
                        line=node.line,
                        column=node.column,
                        type=Type.INT,
                    )
                elif res_type == Type.FLOAT:
                    new_node = FloatLiteral(
                        value=float(res_val),  # type: ignore[arg-type]
                        line=node.line,
                        column=node.column,
                        type=Type.FLOAT,
                    )
                elif res_type == Type.STRING:
                    new_node = StringLiteral(
                        value=str(res_val),
                        line=node.line,
                        column=node.column,
                        type=Type.STRING,
                    )
                else:
                    new_node = BoolLiteral(
                        value=bool(res_val),
                        line=node.line,
                        column=node.column,
                        type=Type.BOOL,
                    )
                after = unparse(new_node)
                self.collector.add(
                    level="ast",
                    kind="fold",
                    line=node.line,
                    column=node.column,
                    before=before,
                    after=after,
                )
                return new_node

        # B. Short-circuit rewrites (RFC-0007 §3.4 A)
        if node.op == "both":
            # yes both e -> e
            if isinstance(node.left, BoolLiteral) and node.left.value is True:
                self.changes += 1
                self.collector.add(
                    level="ast",
                    kind="simplify",
                    line=node.line,
                    column=node.column,
                    before=unparse(node),
                    after=unparse(node.right),
                )
                return node.right
            # no both e -> no
            if isinstance(node.left, BoolLiteral) and node.left.value is False:
                self.changes += 1
                res_node = BoolLiteral(
                    value=False,
                    line=node.line,
                    column=node.column,
                    type=Type.BOOL,
                )
                self.collector.add(
                    level="ast",
                    kind="simplify",
                    line=node.line,
                    column=node.column,
                    before=unparse(node),
                    after="no",
                )
                return res_node
            # e both yes -> e
            if isinstance(node.right, BoolLiteral) and node.right.value is True:
                self.changes += 1
                self.collector.add(
                    level="ast",
                    kind="simplify",
                    line=node.line,
                    column=node.column,
                    before=unparse(node),
                    after=unparse(node.left),
                )
                return node.left

        if node.op == "either":
            # yes either e -> yes
            if isinstance(node.left, BoolLiteral) and node.left.value is True:
                self.changes += 1
                res_node = BoolLiteral(
                    value=True,
                    line=node.line,
                    column=node.column,
                    type=Type.BOOL,
                )
                self.collector.add(
                    level="ast",
                    kind="simplify",
                    line=node.line,
                    column=node.column,
                    before=unparse(node),
                    after="yes",
                )
                return res_node
            # no either e -> e
            if isinstance(node.left, BoolLiteral) and node.left.value is False:
                self.changes += 1
                self.collector.add(
                    level="ast",
                    kind="simplify",
                    line=node.line,
                    column=node.column,
                    before=unparse(node),
                    after=unparse(node.right),
                )
                return node.right
            # e either no -> e
            if isinstance(node.right, BoolLiteral) and node.right.value is False:
                self.changes += 1
                self.collector.add(
                    level="ast",
                    kind="simplify",
                    line=node.line,
                    column=node.column,
                    before=unparse(node),
                    after=unparse(node.left),
                )
                return node.left

        # C. Safe algebraic simplifications on int-typed expressions (RFC-0007 §3.4 B)
        # Only for int operands: e + 0, 0 + e, e - 0, e * 1, 1 * e
        if node.type == Type.INT:
            if node.op == "+":
                if (
                    isinstance(node.right, IntLiteral)
                    and node.right.value == 0
                    and node.left.type == Type.INT
                ):
                    self.changes += 1
                    self.collector.add(
                        level="ast",
                        kind="simplify",
                        line=node.line,
                        column=node.column,
                        before=unparse(node),
                        after=unparse(node.left),
                    )
                    return node.left
                if (
                    isinstance(node.left, IntLiteral)
                    and node.left.value == 0
                    and node.right.type == Type.INT
                ):
                    self.changes += 1
                    self.collector.add(
                        level="ast",
                        kind="simplify",
                        line=node.line,
                        column=node.column,
                        before=unparse(node),
                        after=unparse(node.right),
                    )
                    return node.right
            elif node.op == "-":
                if (
                    isinstance(node.right, IntLiteral)
                    and node.right.value == 0
                    and node.left.type == Type.INT
                ):
                    self.changes += 1
                    self.collector.add(
                        level="ast",
                        kind="simplify",
                        line=node.line,
                        column=node.column,
                        before=unparse(node),
                        after=unparse(node.left),
                    )
                    return node.left
            elif node.op == "*":
                if (
                    isinstance(node.right, IntLiteral)
                    and node.right.value == 1
                    and node.left.type == Type.INT
                ):
                    self.changes += 1
                    self.collector.add(
                        level="ast",
                        kind="simplify",
                        line=node.line,
                        column=node.column,
                        before=unparse(node),
                        after=unparse(node.left),
                    )
                    return node.left
                if (
                    isinstance(node.left, IntLiteral)
                    and node.left.value == 1
                    and node.right.type == Type.INT
                ):
                    self.changes += 1
                    self.collector.add(
                        level="ast",
                        kind="simplify",
                        line=node.line,
                        column=node.column,
                        before=unparse(node),
                        after=unparse(node.right),
                    )
                    return node.right

        return node

    def visit_Block(self, node: Block) -> Block:
        """Visit block: recurse into statements and drop dead code after give."""
        # First process children
        node = self.generic_visit(node)  # type: ignore[assignment]
        if not isinstance(node, Block):
            return node

        # Remove dead statements after a give statement in the same block (RFC-0007 §3.4 C)
        new_stmts: list[Stmt] = []
        give_seen = False
        for s in node.statements:
            if give_seen:
                self.changes += 1
                self.collector.add(
                    level="ast",
                    kind="dead-code",
                    line=s.line,
                    column=s.column,
                    before=unparse(s),
                    after="(removed)",
                )
                continue
            new_stmts.append(s)
            if isinstance(s, GiveStmt):
                give_seen = True

        node.statements = new_stmts
        return node

    def visit_WhenStmt(self, node: WhenStmt) -> Any:
        """Visit when statement: branch elimination on constant boolean conditions."""
        node = self.generic_visit(node)  # type: ignore[assignment]
        if not isinstance(node, WhenStmt):
            return node

        if isinstance(node.condition, BoolLiteral):
            if node.condition.value is True:
                # when (yes) A otherwise B -> inlined statements of A
                self.changes += 1
                self.collector.add(
                    level="ast",
                    kind="dead-branch",
                    line=node.line,
                    column=node.column,
                    before=unparse(node),
                    after="then-block",
                )
                return node.then_block.statements
            if node.condition.value is False:
                # when (no) A otherwise B -> B
                self.changes += 1
                if node.else_branch is None:
                    self.collector.add(
                        level="ast",
                        kind="dead-branch",
                        line=node.line,
                        column=node.column,
                        before=unparse(node),
                        after="(removed)",
                    )
                    return None
                if isinstance(node.else_branch, Block):
                    self.collector.add(
                        level="ast",
                        kind="dead-branch",
                        line=node.line,
                        column=node.column,
                        before=unparse(node),
                        after="else-block",
                    )
                    return node.else_branch.statements
                if isinstance(node.else_branch, WhenStmt):
                    self.collector.add(
                        level="ast",
                        kind="dead-branch",
                        line=node.line,
                        column=node.column,
                        before=unparse(node),
                        after="otherwise-when",
                    )
                    return node.else_branch

        return node

    def visit_DuringStmt(self, node: DuringStmt) -> Any:
        """Visit during statement: drop loop if condition is constant false (no)."""
        node = self.generic_visit(node)  # type: ignore[assignment]
        if not isinstance(node, DuringStmt):
            return node

        if isinstance(node.condition, BoolLiteral) and node.condition.value is False:
            self.changes += 1
            self.collector.add(
                level="ast",
                kind="dead-branch",
                line=node.line,
                column=node.column,
                before=unparse(node),
                after="(removed)",
            )
            return None

        return node

    def visit_ExprStmt(self, node: ExprStmt) -> Any:
        """Visit expression statement: drop side-effect-free literal or identifier statements."""
        node = self.generic_visit(node)  # type: ignore[assignment]
        if not isinstance(node, ExprStmt):
            return node

        # ExprStmt of literal or identifier has no side effect (RFC-0007 §3.4 C)
        if isinstance(
            node.expression,
            (
                IntLiteral,
                FloatLiteral,
                StringLiteral,
                BoolLiteral,
                EmptyLiteral,
                Identifier,
            ),
        ):
            self.changes += 1
            self.collector.add(
                level="ast",
                kind="dead-code",
                line=node.line,
                column=node.column,
                before=unparse(node),
                after="(removed)",
            )
            return None

        return node


def optimize_program(program: Program) -> tuple[Program, OptimizationReport]:
    """Optimize MiniLang AST to a fixed point (up to 10 rounds).

    Does NOT mutate input AST. Returns cloned, optimized AST and report.
    """
    curr = clone_tree(program)
    collector = NoteCollector()
    total_rounds = 0

    for r in range(10):
        total_rounds = r + 1
        pass_opt = ASTOptimizerPass(collector)
        curr = pass_opt.visit(curr)  # type: ignore[assignment]
        if pass_opt.changes == 0:
            break

    return curr, OptimizationReport(
        notes=collector.finalize(),
        iterations=total_rounds,
    )


# =============================================================================
# 4. TAC-Level Optimizer (RFC-0007 §3.5)
# =============================================================================


def _is_leader(instr: TACInstr) -> bool:
    """Return whether instruction starts a new basic block."""
    return isinstance(instr, Label)


def _is_block_terminator(instr: TACInstr) -> bool:
    """Return whether instruction ends a basic block."""
    return isinstance(instr, (Goto, IfTrue, IfFalse, Return))


def _split_into_blocks(instrs: list[TACInstr]) -> list[list[TACInstr]]:
    """Partition a list of function body instructions into basic blocks."""
    if not instrs:
        return []

    blocks: list[list[TACInstr]] = []
    current_block: list[TACInstr] = []

    for instr in instrs:
        if _is_leader(instr) and current_block:
            blocks.append(current_block)
            current_block = [instr]
        else:
            current_block.append(instr)
            if _is_block_terminator(instr):
                blocks.append(current_block)
                current_block = []

    if current_block:
        blocks.append(current_block)

    return blocks


def _resolve_operand(op: Operand, env: dict[str, Operand]) -> Operand:
    """Recursively resolve operand through local copy environment."""
    curr = op
    visited: set[str] = set()
    while isinstance(curr, (Var, Temp)) and curr.name in env:
        if curr.name in visited:
            break
        visited.add(curr.name)
        curr = env[curr.name]
    return curr


def _op_key(op: Var | Temp) -> str:
    """Return dictionary key for variable or temporary destination."""
    return op.name


def _optimize_function_round(
    func_name: str,
    func_begin: FuncBegin,
    body: list[TACInstr],
    func_end: FuncEnd,
    global_uses: dict[str, int],
    collector: NoteCollector,
) -> tuple[list[TACInstr], int]:
    """Run one optimization round on a single function's TAC body.

    Order per RFC-0007 §3.5:
    1. Local value propagation
    2. Folding
    3. Algebraic simplification
    4. Branch folding
    5. Unreachable-block removal
    6. Jump cleanup
    7. Dead-code elimination
    """
    changes = 0

    # -------------------------------------------------------------------------
    # 1. Local value propagation (per basic block)
    # -------------------------------------------------------------------------
    blocks = _split_into_blocks(body)
    new_body_1: list[TACInstr] = []

    for block in blocks:
        env: dict[str, Operand] = {}
        for instr in block:
            new_instr = instr
            # Replace read operands
            if isinstance(instr, BinOp):
                left_res = _resolve_operand(instr.left, env)
                right_res = _resolve_operand(instr.right, env)
                if left_res != instr.left or right_res != instr.right:
                    new_instr = BinOp(
                        dest=instr.dest,
                        op=instr.op,
                        left=left_res,
                        right=right_res,
                        source_line=instr.source_line,
                    )
                    changes += 1
                    collector.add(
                        level="tac",
                        kind="propagate",
                        line=instr.source_line,
                        column=0,
                        before=format_instruction(instr).strip(),
                        after=format_instruction(new_instr).strip(),
                    )
            elif isinstance(instr, UnOp):
                op_res = _resolve_operand(instr.operand, env)
                if op_res != instr.operand:
                    new_instr = UnOp(
                        dest=instr.dest,
                        op=instr.op,
                        operand=op_res,
                        source_line=instr.source_line,
                    )
                    changes += 1
                    collector.add(
                        level="tac",
                        kind="propagate",
                        line=instr.source_line,
                        column=0,
                        before=format_instruction(instr).strip(),
                        after=format_instruction(new_instr).strip(),
                    )
            elif isinstance(instr, Copy):
                src_res = _resolve_operand(instr.src, env)
                if src_res != instr.src:
                    new_instr = Copy(
                        dest=instr.dest,
                        src=src_res,
                        source_line=instr.source_line,
                    )
                    changes += 1
                    collector.add(
                        level="tac",
                        kind="propagate",
                        line=instr.source_line,
                        column=0,
                        before=format_instruction(instr).strip(),
                        after=format_instruction(new_instr).strip(),
                    )
            elif isinstance(instr, IfTrue):
                cond_res = _resolve_operand(instr.cond, env)
                if cond_res != instr.cond:
                    new_instr = IfTrue(
                        cond=cond_res,
                        target=instr.target,
                        source_line=instr.source_line,
                    )
                    changes += 1
                    collector.add(
                        level="tac",
                        kind="propagate",
                        line=instr.source_line,
                        column=0,
                        before=format_instruction(instr).strip(),
                        after=format_instruction(new_instr).strip(),
                    )
            elif isinstance(instr, IfFalse):
                cond_res = _resolve_operand(instr.cond, env)
                if cond_res != instr.cond:
                    new_instr = IfFalse(
                        cond=cond_res,
                        target=instr.target,
                        source_line=instr.source_line,
                    )
                    changes += 1
                    collector.add(
                        level="tac",
                        kind="propagate",
                        line=instr.source_line,
                        column=0,
                        before=format_instruction(instr).strip(),
                        after=format_instruction(new_instr).strip(),
                    )
            elif isinstance(instr, Param):
                arg_res = _resolve_operand(instr.arg, env)
                if arg_res != instr.arg:
                    new_instr = Param(
                        arg=arg_res,
                        source_line=instr.source_line,
                    )
                    changes += 1
                    collector.add(
                        level="tac",
                        kind="propagate",
                        line=instr.source_line,
                        column=0,
                        before=format_instruction(instr).strip(),
                        after=format_instruction(new_instr).strip(),
                    )
            elif isinstance(instr, Return) and instr.value is not None:
                val_res = _resolve_operand(instr.value, env)
                if val_res != instr.value:
                    new_instr = Return(
                        value=val_res,
                        source_line=instr.source_line,
                    )
                    changes += 1
                    collector.add(
                        level="tac",
                        kind="propagate",
                        line=instr.source_line,
                        column=0,
                        before=format_instruction(instr).strip(),
                        after=format_instruction(new_instr).strip(),
                    )
            elif isinstance(instr, Print):
                val_res = _resolve_operand(instr.value, env)
                if val_res != instr.value:
                    new_instr = Print(
                        value=val_res,
                        source_line=instr.source_line,
                    )
                    changes += 1
                    collector.add(
                        level="tac",
                        kind="propagate",
                        line=instr.source_line,
                        column=0,
                        before=format_instruction(instr).strip(),
                        after=format_instruction(new_instr).strip(),
                    )

            # Update environment: kill destination and record copy
            if isinstance(new_instr, (BinOp, UnOp, Copy, Ask)):
                d_key = _op_key(new_instr.dest)
                env.pop(d_key, None)
                # Drop facts referencing d_key
                keys_to_kill = [
                    k
                    for k, v in env.items()
                    if isinstance(v, (Var, Temp)) and v.name == d_key
                ]
                for k in keys_to_kill:
                    del env[k]

                if isinstance(new_instr, Copy) and (
                    isinstance(new_instr.src, Const)
                    or (
                        isinstance(new_instr.src, (Var, Temp))
                        and new_instr.src.name != d_key
                    )
                ):
                    env[d_key] = new_instr.src

            elif isinstance(new_instr, Call) and new_instr.dest is not None:
                d_key = _op_key(new_instr.dest)
                env.pop(d_key, None)
                keys_to_kill = [
                    k
                    for k, v in env.items()
                    if isinstance(v, (Var, Temp)) and v.name == d_key
                ]
                for k in keys_to_kill:
                    del env[k]

            new_body_1.append(new_instr)

    # -------------------------------------------------------------------------
    # 2. Folding & 3. Algebraic simplification
    # -------------------------------------------------------------------------
    new_body_2: list[TACInstr] = []
    for instr in new_body_1:
        if (
            isinstance(instr, BinOp)
            and isinstance(instr.left, Const)
            and isinstance(instr.right, Const)
        ):
            folded = fold_binary(
                instr.op,
                instr.left.value,
                instr.left.type,
                instr.right.value,
                instr.right.type,
            )
            if folded is not None:
                val, typ = folded
                replacement = Copy(
                    dest=instr.dest,
                    src=Const(val, typ),
                    source_line=instr.source_line,
                )
                changes += 1
                collector.add(
                    level="tac",
                    kind="fold",
                    line=instr.source_line,
                    column=0,
                    before=format_instruction(instr).strip(),
                    after=format_instruction(replacement).strip(),
                )
                new_body_2.append(replacement)
                continue

        if isinstance(instr, UnOp) and isinstance(instr.operand, Const):
            folded = fold_unary(
                instr.op,
                instr.operand.value,
                instr.operand.type,
            )
            if folded is not None:
                val, typ = folded
                replacement = Copy(
                    dest=instr.dest,
                    src=Const(val, typ),
                    source_line=instr.source_line,
                )
                changes += 1
                collector.add(
                    level="tac",
                    kind="fold",
                    line=instr.source_line,
                    column=0,
                    before=format_instruction(instr).strip(),
                    after=format_instruction(replacement).strip(),
                )
                new_body_2.append(replacement)
                continue

        # 3. Algebraic simplification
        if isinstance(instr, BinOp) and instr.dest.type == Type.INT:
            if (
                instr.op == "+"
                and isinstance(instr.right, Const)
                and instr.right.value == 0
                and instr.left.type == Type.INT
            ):
                replacement = Copy(
                    dest=instr.dest,
                    src=instr.left,
                    source_line=instr.source_line,
                )
                changes += 1
                collector.add(
                    level="tac",
                    kind="simplify",
                    line=instr.source_line,
                    column=0,
                    before=format_instruction(instr).strip(),
                    after=format_instruction(replacement).strip(),
                )
                new_body_2.append(replacement)
                continue
            if (
                instr.op == "+"
                and isinstance(instr.left, Const)
                and instr.left.value == 0
                and instr.right.type == Type.INT
            ):
                replacement = Copy(
                    dest=instr.dest,
                    src=instr.right,
                    source_line=instr.source_line,
                )
                changes += 1
                collector.add(
                    level="tac",
                    kind="simplify",
                    line=instr.source_line,
                    column=0,
                    before=format_instruction(instr).strip(),
                    after=format_instruction(replacement).strip(),
                )
                new_body_2.append(replacement)
                continue
            if (
                instr.op == "-"
                and isinstance(instr.right, Const)
                and instr.right.value == 0
                and instr.left.type == Type.INT
            ):
                replacement = Copy(
                    dest=instr.dest,
                    src=instr.left,
                    source_line=instr.source_line,
                )
                changes += 1
                collector.add(
                    level="tac",
                    kind="simplify",
                    line=instr.source_line,
                    column=0,
                    before=format_instruction(instr).strip(),
                    after=format_instruction(replacement).strip(),
                )
                new_body_2.append(replacement)
                continue
            if (
                instr.op == "*"
                and isinstance(instr.right, Const)
                and instr.right.value == 1
                and instr.left.type == Type.INT
            ):
                replacement = Copy(
                    dest=instr.dest,
                    src=instr.left,
                    source_line=instr.source_line,
                )
                changes += 1
                collector.add(
                    level="tac",
                    kind="simplify",
                    line=instr.source_line,
                    column=0,
                    before=format_instruction(instr).strip(),
                    after=format_instruction(replacement).strip(),
                )
                new_body_2.append(replacement)
                continue
            if (
                instr.op == "*"
                and isinstance(instr.left, Const)
                and instr.left.value == 1
                and instr.right.type == Type.INT
            ):
                replacement = Copy(
                    dest=instr.dest,
                    src=instr.right,
                    source_line=instr.source_line,
                )
                changes += 1
                collector.add(
                    level="tac",
                    kind="simplify",
                    line=instr.source_line,
                    column=0,
                    before=format_instruction(instr).strip(),
                    after=format_instruction(replacement).strip(),
                )
                new_body_2.append(replacement)
                continue

        new_body_2.append(instr)

    # -------------------------------------------------------------------------
    # 4. Branch folding
    # -------------------------------------------------------------------------
    new_body_3: list[TACInstr] = []
    for instr in new_body_2:
        if isinstance(instr, IfFalse) and isinstance(instr.cond, Const):
            if instr.cond.value is False:
                replacement = Goto(
                    target=instr.target,
                    source_line=instr.source_line,
                )
                changes += 1
                collector.add(
                    level="tac",
                    kind="fold-branch",
                    line=instr.source_line,
                    column=0,
                    before=format_instruction(instr).strip(),
                    after=format_instruction(replacement).strip(),
                )
                new_body_3.append(replacement)
                continue
            if instr.cond.value is True:
                changes += 1
                collector.add(
                    level="tac",
                    kind="fold-branch",
                    line=instr.source_line,
                    column=0,
                    before=format_instruction(instr).strip(),
                    after="(removed)",
                )
                continue

        if isinstance(instr, IfTrue) and isinstance(instr.cond, Const):
            if instr.cond.value is True:
                replacement = Goto(
                    target=instr.target,
                    source_line=instr.source_line,
                )
                changes += 1
                collector.add(
                    level="tac",
                    kind="fold-branch",
                    line=instr.source_line,
                    column=0,
                    before=format_instruction(instr).strip(),
                    after=format_instruction(replacement).strip(),
                )
                new_body_3.append(replacement)
                continue
            if instr.cond.value is False:
                changes += 1
                collector.add(
                    level="tac",
                    kind="fold-branch",
                    line=instr.source_line,
                    column=0,
                    before=format_instruction(instr).strip(),
                    after="(removed)",
                )
                continue

        new_body_3.append(instr)

    # -------------------------------------------------------------------------
    # 5. Unreachable-block removal
    # -------------------------------------------------------------------------
    if not new_body_3:
        new_body_4: list[TACInstr] = [Return(value=None, source_line=0)]
    else:
        # Build CFG using build_cfg
        try:
            cfg = build_cfg([func_begin] + new_body_3 + [func_end])
            reachable_block_ids: set[int] = set()
            worklist = [0]
            while worklist:
                b_id = worklist.pop()
                if b_id in reachable_block_ids:
                    continue
                reachable_block_ids.add(b_id)
                for succ_id in cfg.blocks[b_id].succ:
                    if succ_id not in reachable_block_ids:
                        worklist.append(succ_id)

            new_body_4 = []
            for b in cfg.blocks:
                if b.id in reachable_block_ids:
                    new_body_4.extend(b.instrs)
                else:
                    if b.instrs:
                        changes += len(b.instrs)
                        for unreachable_instr in b.instrs:
                            collector.add(
                                level="tac",
                                kind="dead-code",
                                line=unreachable_instr.source_line,
                                column=0,
                                before=format_instruction(unreachable_instr).strip(),
                                after="(unreachable block removed)",
                            )
            # Ensure function ends with a Return
            if not new_body_4 or not isinstance(new_body_4[-1], Return):
                new_body_4.append(Return(value=None, source_line=0))
        except (InternalCompilerError, KeyError, IndexError, ValueError):
            new_body_4 = new_body_3

    # -------------------------------------------------------------------------
    # 6. Jump cleanup
    # -------------------------------------------------------------------------
    # A. Thread jumps: if Label L is immediately followed by Goto L_target
    label_to_goto: dict[str, str] = {}
    for i, instr in enumerate(new_body_4):
        if isinstance(instr, Label):
            j = i + 1
            while j < len(new_body_4) and isinstance(new_body_4[j], Label):
                j += 1
            if j < len(new_body_4) and isinstance(new_body_4[j], Goto):
                label_to_goto[instr.name] = new_body_4[j].target

    def thread_target(target: str) -> str:
        curr = target
        visited = {curr}
        while curr in label_to_goto:
            nxt = label_to_goto[curr]
            if nxt in visited:
                break
            visited.add(nxt)
            curr = nxt
        return curr

    new_body_5: list[TACInstr] = []
    for instr in new_body_4:
        if isinstance(instr, Goto):
            th = thread_target(instr.target)
            if th != instr.target:
                changes += 1
                new_body_5.append(Goto(target=th, source_line=instr.source_line))
                continue
        elif isinstance(instr, IfTrue):
            th = thread_target(instr.target)
            if th != instr.target:
                changes += 1
                new_body_5.append(
                    IfTrue(
                        cond=instr.cond,
                        target=th,
                        source_line=instr.source_line,
                    )
                )
                continue
        elif isinstance(instr, IfFalse):
            th = thread_target(instr.target)
            if th != instr.target:
                changes += 1
                new_body_5.append(
                    IfFalse(
                        cond=instr.cond,
                        target=th,
                        source_line=instr.source_line,
                    )
                )
                continue
        new_body_5.append(instr)

    # B. Delete Goto L immediately followed by Label L
    new_body_6: list[TACInstr] = []
    idx = 0
    while idx < len(new_body_5):
        instr = new_body_5[idx]
        if isinstance(instr, Goto) and idx + 1 < len(new_body_5):
            next_instr = new_body_5[idx + 1]
            if isinstance(next_instr, Label) and next_instr.name == instr.target:
                changes += 1
                collector.add(
                    level="tac",
                    kind="jump",
                    line=instr.source_line,
                    column=0,
                    before=format_instruction(instr).strip(),
                    after="(deleted fall-through jump)",
                )
                idx += 1
                continue
        new_body_6.append(instr)
        idx += 1

    # C. Delete unreferenced labels
    referenced_labels: set[str] = set()
    for instr in new_body_6:
        if isinstance(instr, (Goto, IfTrue, IfFalse)):
            referenced_labels.add(instr.target)

    new_body_7: list[TACInstr] = []
    for instr in new_body_6:
        if isinstance(instr, Label) and instr.name not in referenced_labels:
            changes += 1
            collector.add(
                level="tac",
                kind="jump",
                line=instr.source_line,
                column=0,
                before=format_instruction(instr).strip(),
                after="(unreferenced label deleted)",
            )
            continue
        new_body_7.append(instr)

    # -------------------------------------------------------------------------
    # 7. Dead-code elimination
    # -------------------------------------------------------------------------
    # Count local uses
    local_uses: dict[str, int] = defaultdict(int)
    for instr in new_body_7:
        if isinstance(instr, Copy):
            if isinstance(instr.src, (Var, Temp)):
                local_uses[instr.src.name] += 1
        elif isinstance(instr, BinOp):
            if isinstance(instr.left, (Var, Temp)):
                local_uses[instr.left.name] += 1
            if isinstance(instr.right, (Var, Temp)):
                local_uses[instr.right.name] += 1
        elif isinstance(instr, UnOp):
            if isinstance(instr.operand, (Var, Temp)):
                local_uses[instr.operand.name] += 1
        elif isinstance(instr, (IfTrue, IfFalse)):
            if isinstance(instr.cond, (Var, Temp)):
                local_uses[instr.cond.name] += 1
        elif isinstance(instr, Param):
            if isinstance(instr.arg, (Var, Temp)):
                local_uses[instr.arg.name] += 1
        elif (
            (isinstance(instr, Return) and instr.value is not None)
            or isinstance(instr, Print)
        ) and isinstance(instr.value, (Var, Temp)):
            local_uses[instr.value.name] += 1

    def may_raise(instr: TACInstr) -> bool:
        """Check if instruction could raise a runtime error (RFC-0007 §3.5)."""
        if isinstance(instr, BinOp):
            return bool(
                instr.op in ("/", "%")
                and not (
                    isinstance(instr.right, Const)
                    and instr.right.value != 0
                    and instr.right.value != 0.0
                )
            )
        if isinstance(instr, UnOp):
            return bool(instr.op == "float" and not isinstance(instr.operand, Const))
        return bool(isinstance(instr, Call))

    new_body_8: list[TACInstr] = []
    for instr in new_body_7:
        if isinstance(instr, (Copy, BinOp, UnOp)):
            d = instr.dest
            d_name = d.name
            # For variables assigned in __main, count uses across whole program
            if func_name == "__main" and isinstance(d, Var):
                use_count = global_uses.get(d_name, 0)
            else:
                use_count = local_uses.get(d_name, 0)

            if use_count == 0 and not may_raise(instr):
                changes += 1
                collector.add(
                    level="tac",
                    kind="dead-code",
                    line=instr.source_line,
                    column=0,
                    before=format_instruction(instr).strip(),
                    after="(deleted dead instruction)",
                )
                continue

        new_body_8.append(instr)

    # Invariant safety: Ensure function ends with a Return
    if not new_body_8 or not isinstance(new_body_8[-1], Return):
        new_body_8.append(Return(value=None, source_line=0))

    return new_body_8, changes


def _compute_global_var_uses(tac: Sequence[TACInstr]) -> dict[str, int]:
    """Count how many times each variable is read across all functions in the program."""
    uses: dict[str, int] = defaultdict(int)
    for instr in tac:
        if isinstance(instr, Copy):
            if isinstance(instr.src, Var):
                uses[instr.src.name] += 1
        elif isinstance(instr, BinOp):
            if isinstance(instr.left, Var):
                uses[instr.left.name] += 1
            if isinstance(instr.right, Var):
                uses[instr.right.name] += 1
        elif isinstance(instr, UnOp):
            if isinstance(instr.operand, Var):
                uses[instr.operand.name] += 1
        elif isinstance(instr, (IfTrue, IfFalse)):
            if isinstance(instr.cond, Var):
                uses[instr.cond.name] += 1
        elif isinstance(instr, Param):
            if isinstance(instr.arg, Var):
                uses[instr.arg.name] += 1
        elif (
            (isinstance(instr, Return) and instr.value is not None)
            or isinstance(instr, Print)
        ) and isinstance(instr.value, Var):
            uses[instr.value.name] += 1
    return uses


def optimize_tac(
    tac: list[TACInstr],
) -> tuple[list[TACInstr], OptimizationReport]:
    """Optimize TAC instruction stream to a fixed point (up to 10 rounds).

    Does NOT mutate input list. Operates per function on the CFG.
    """
    if not tac:
        return [], OptimizationReport(notes=[], iterations=0)

    collector = NoteCollector()
    current_tac = list(tac)
    total_rounds = 0

    for r in range(10):
        total_rounds = r + 1
        round_changes = 0

        # Split TAC into functions
        functions: list[tuple[str, FuncBegin, list[TACInstr], FuncEnd]] = []
        i = 0
        while i < len(current_tac):
            instr = current_tac[i]
            if isinstance(instr, FuncBegin):
                fb = instr
                fn_name = instr.name
                body: list[TACInstr] = []
                i += 1
                while i < len(current_tac) and not isinstance(current_tac[i], FuncEnd):
                    body.append(current_tac[i])
                    i += 1
                if i < len(current_tac) and isinstance(current_tac[i], FuncEnd):
                    fe = current_tac[i]
                    functions.append((fn_name, fb, body, fe))
            i += 1

        if not functions:
            break

        global_uses = _compute_global_var_uses(current_tac)

        new_tac: list[TACInstr] = []
        for fn_name, fb, body, fe in functions:
            opt_body, fn_changes = _optimize_function_round(
                fn_name, fb, body, fe, global_uses, collector
            )
            round_changes += fn_changes
            new_tac.append(fb)
            new_tac.extend(opt_body)
            new_tac.append(fe)

        current_tac = new_tac
        if round_changes == 0:
            break

    return current_tac, OptimizationReport(
        notes=collector.finalize(),
        iterations=total_rounds,
    )
