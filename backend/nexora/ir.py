"""Intermediate Representation (Three-Address Code) for MiniLang v1.

Governed by RFC-0006, this module defines the TAC operand and instruction set,
the AST-to-TAC lowering visitor, basic block partitioning and CFG generation,
text and JSON serialization, and TAC validation.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from .ast_nodes import (
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
    Node,
    NodeVisitor,
    Program,
    ShowStmt,
    SkipStmt,
    StopStmt,
    StringLiteral,
    TaskDecl,
    UnaryExpr,
    WhenStmt,
)
from .errors import InternalCompilerError
from .symbols import FunctionType, Type, type_from_name

# =============================================================================
# 1. Operands (RFC-0006 §3.1)
# =============================================================================


@dataclass(frozen=True)
class Const:
    """Constant literal operand with static type."""

    value: int | float | str | bool | None
    type: Type

    def __repr__(self) -> str:
        """Return representation for debugging."""
        return f"Const({self.value!r}, {self.type.value})"


@dataclass(frozen=True)
class Var:
    """User variable or task parameter operand."""

    name: str
    type: Type

    def __repr__(self) -> str:
        """Return representation for debugging."""
        return f"Var({self.name}, {self.type.value})"


@dataclass(frozen=True)
class Temp:
    """Compiler-generated temporary operand (t1, t2, ...)."""

    name: str
    type: Type

    def __repr__(self) -> str:
        """Return representation for debugging."""
        return f"Temp({self.name}, {self.type.value})"


Operand = Const | Var | Temp


def format_operand(op: Operand) -> str:
    """Format an operand into its textual TAC representation."""
    if isinstance(op, (Var, Temp)):
        return op.name
    if isinstance(op, Const):
        if op.type == Type.BOOL:
            return "true" if op.value else "false"
        if op.type == Type.INT:
            return str(op.value)
        if op.type == Type.FLOAT:
            return repr(op.value)
        if op.type == Type.STRING:
            return json.dumps(op.value)
        if op.type == Type.EMPTY or op.value is None:
            return "empty"
        return str(op.value)
    raise InternalCompilerError(f"Unknown operand type: {type(op)}")


# =============================================================================
# 2. Instruction Set (RFC-0006 §3.2)
# =============================================================================


@dataclass(frozen=True)
class Copy:
    """Assignment instruction: dest = src."""

    dest: Var | Temp
    src: Operand
    source_line: int = 0


@dataclass(frozen=True)
class BinOp:
    """Binary operation: dest = left op right."""

    dest: Var | Temp
    op: str
    left: Operand
    right: Operand
    source_line: int = 0


@dataclass(frozen=True)
class UnOp:
    """Unary operation or widening conversion: dest = op operand."""

    dest: Var | Temp
    op: str
    operand: Operand
    source_line: int = 0


@dataclass(frozen=True)
class Label:
    """Branch jump target."""

    name: str
    source_line: int = 0


@dataclass(frozen=True)
class Goto:
    """Unconditional jump to target label."""

    target: str
    source_line: int = 0


@dataclass(frozen=True)
class IfFalse:
    """Conditional jump when condition evaluates to false (no)."""

    cond: Operand
    target: str
    source_line: int = 0


@dataclass(frozen=True)
class IfTrue:
    """Conditional jump when condition evaluates to true (yes)."""

    cond: Operand
    target: str
    source_line: int = 0


@dataclass(frozen=True)
class Param:
    """Push an argument onto call stack for upcoming Call instruction."""

    arg: Operand
    source_line: int = 0


@dataclass(frozen=True)
class Call:
    """Task call consuming preceding argc Param instructions."""

    dest: Var | Temp | None
    func: str
    argc: int
    source_line: int = 0


@dataclass(frozen=True)
class Return:
    """Return from current task with optional value."""

    value: Operand | None = None
    source_line: int = 0


@dataclass(frozen=True)
class Print:
    """Console output instruction implementing show statement."""

    value: Operand
    source_line: int = 0


@dataclass(frozen=True)
class Ask:
    """Console input instruction implementing ask statement."""

    dest: Var | Temp
    type: Type
    source_line: int = 0


@dataclass(frozen=True)
class FuncBegin:
    """Function / task header."""

    name: str
    params: list[tuple[str, Type]]
    ret: Type
    source_line: int = 0


@dataclass(frozen=True)
class FuncEnd:
    """Function / task trailer."""

    name: str
    source_line: int = 0


TACInstr = (
    Copy
    | BinOp
    | UnOp
    | Label
    | Goto
    | IfFalse
    | IfTrue
    | Param
    | Call
    | Return
    | Print
    | Ask
    | FuncBegin
    | FuncEnd
)


# =============================================================================
# 3. IR Generator (RFC-0006 §3.4)
# =============================================================================


class IRGenerator(NodeVisitor):
    """Lowers an annotated MiniLang AST into Three-Address Code (TAC)."""

    def __init__(self) -> None:
        """Initialize IRGenerator with fresh counters and instruction buffers."""
        self._temp_counter: int = 0
        self._label_counter: int = 0
        self._instructions: list[TACInstr] = []
        self._loop_stack: list[tuple[str, str]] = []  # (start_label, end_label)
        self._current_ret_type: Type = Type.VOID

    def new_temp(self, type_: Type) -> Temp:
        """Allocate a new unique compiler temporary."""
        self._temp_counter += 1
        return Temp(f"t{self._temp_counter}", type_)

    def new_label(self) -> str:
        """Allocate a new unique branch label."""
        self._label_counter += 1
        return f"L{self._label_counter}"

    def emit(self, instr: TACInstr) -> None:
        """Append an instruction to the current function's instruction stream."""
        self._instructions.append(instr)

    def widen(self, operand: Operand, line: int) -> Operand:
        """Widen an int operand to float if required."""
        if operand.type == Type.FLOAT:
            return operand
        if (
            isinstance(operand, Const)
            and operand.type == Type.INT
            and isinstance(operand.value, int)
        ):
            return Const(float(operand.value), Type.FLOAT)
        t = self.new_temp(Type.FLOAT)
        self.emit(UnOp(t, "float", operand, source_line=line))
        return t

    def _emit_assign(self, var: Var, value: Operand, line: int) -> None:
        """Emit assignment with mandatory peephole optimization when dest is a fresh temp."""
        if isinstance(value, Temp) and self._instructions:
            last_instr = self._instructions[-1]
            if getattr(last_instr, "dest", None) == value:
                # Peephole: Retarget last instruction's destination to the variable
                self._instructions[-1] = dataclasses.replace(last_instr, dest=var)
                return
        self.emit(Copy(var, value, source_line=line))

    def generate(self, program: Program) -> list[TACInstr]:
        """Generate flat TAC instructions for an entire MiniLang program."""
        self._temp_counter = 0
        self._label_counter = 0
        self._instructions.clear()
        self._loop_stack.clear()

        # Separate tasks from top-level statements
        tasks: list[TaskDecl] = []
        top_level_stmts: list[Node] = []
        for item in program.body:
            if isinstance(item, TaskDecl):
                tasks.append(item)
            else:
                top_level_stmts.append(item)

        # 1. Lower all user tasks in source order
        for task in tasks:
            self._lower_task(task)

        # 2. Lower synthetic __main function containing top-level statements
        self._lower_main(top_level_stmts)

        return list(self._instructions)

    def _lower_task(self, task: TaskDecl) -> None:
        """Lower a single TaskDecl into FuncBegin ... FuncEnd."""
        params: list[tuple[str, Type]] = []
        for p in task.params:
            p_type = (
                p.symbol.type
                if p.symbol
                else (type_from_name(p.type_ref.name) or Type.INT)
            )
            params.append((p.name, p_type))

        if task.symbol and isinstance(task.symbol.type, FunctionType):
            ret_type = task.symbol.type.ret
        elif task.return_type is not None:
            ret_type = type_from_name(task.return_type.name) or Type.INT
        else:
            ret_type = Type.VOID

        self._current_ret_type = ret_type
        self.emit(FuncBegin(task.name, params, ret_type, source_line=task.line))

        for stmt in task.body.statements:
            self.visit(stmt)

        # Guarantee every task ends with a Return before FuncEnd
        if not (self._instructions and isinstance(self._instructions[-1], Return)):
            self.emit(Return(None, source_line=task.line))

        self.emit(FuncEnd(task.name, source_line=task.line))

    def _lower_main(self, top_level_stmts: list[Node]) -> None:
        """Lower top-level statements into synthetic func __main(): ... endfunc."""
        self._current_ret_type = Type.VOID
        self.emit(FuncBegin("__main", [], Type.VOID, source_line=0))

        for stmt in top_level_stmts:
            self.visit(stmt)

        # Guarantee __main ends with Return before FuncEnd
        if not (self._instructions and isinstance(self._instructions[-1], Return)):
            self.emit(Return(None, source_line=0))

        self.emit(FuncEnd("__main", source_line=0))

    # -------------------------------------------------------------------------
    # Expressions
    # -------------------------------------------------------------------------

    def visit_IntLiteral(self, node: IntLiteral) -> Operand:
        return Const(node.value, Type.INT)

    def visit_FloatLiteral(self, node: FloatLiteral) -> Operand:
        return Const(node.value, Type.FLOAT)

    def visit_StringLiteral(self, node: StringLiteral) -> Operand:
        return Const(node.value, Type.STRING)

    def visit_BoolLiteral(self, node: BoolLiteral) -> Operand:
        return Const(node.value, Type.BOOL)

    def visit_EmptyLiteral(self, node: EmptyLiteral) -> Operand:
        return Const(None, Type.EMPTY)

    def visit_Identifier(self, node: Identifier) -> Operand:
        t = node.type or (node.symbol.type if node.symbol else Type.INT)
        return Var(node.name, t)

    def visit_UnaryExpr(self, node: UnaryExpr) -> Operand:
        opnd = self.visit(node.operand)
        res_type = node.type or (Type.BOOL if node.op == "not" else opnd.type)
        t = self.new_temp(res_type)
        self.emit(UnOp(t, node.op, opnd, source_line=node.line))
        return t

    def visit_BinaryExpr(self, node: BinaryExpr) -> Operand:
        # Short-circuit logic for 'both' and 'either'
        if node.op == "both":
            a = self.visit(node.left)
            t = self.new_temp(Type.BOOL)
            self.emit(Copy(t, a, source_line=node.line))
            lend = self.new_label()
            self.emit(IfFalse(t, lend, source_line=node.line))
            b = self.visit(node.right)
            self.emit(Copy(t, b, source_line=node.line))
            self.emit(Label(lend, source_line=node.line))
            return t

        if node.op == "either":
            a = self.visit(node.left)
            t = self.new_temp(Type.BOOL)
            self.emit(Copy(t, a, source_line=node.line))
            lend = self.new_label()
            self.emit(IfTrue(t, lend, source_line=node.line))
            b = self.visit(node.right)
            self.emit(Copy(t, b, source_line=node.line))
            self.emit(Label(lend, source_line=node.line))
            return t

        # Standard binary operations
        a = self.visit(node.left)
        b = self.visit(node.right)

        # Implicit mixed-arithmetic widening in expressions
        if a.type == Type.INT and b.type == Type.FLOAT:
            a = self.widen(a, node.line)
        elif b.type == Type.INT and a.type == Type.FLOAT:
            b = self.widen(b, node.line)

        res_type = node.type or Type.INT
        t = self.new_temp(res_type)
        self.emit(BinOp(t, node.op, a, b, source_line=node.line))
        return t

    def visit_CallExpr(self, node: CallExpr) -> Operand | None:
        # 1. Evaluate all arguments left to right
        evaluated_args: list[Operand] = []
        for i, arg in enumerate(node.args):
            opnd = self.visit(arg)
            if (
                node.arg_widenings
                and i < len(node.arg_widenings)
                and node.arg_widenings[i]
            ):
                opnd = self.widen(opnd, node.line)
            evaluated_args.append(opnd)

        # 2. Push params in order
        for opnd in evaluated_args:
            self.emit(Param(opnd, source_line=node.line))

        # 3. Emit Call
        ret_type = node.type or Type.VOID
        if ret_type == Type.VOID:
            self.emit(
                Call(None, node.callee, len(evaluated_args), source_line=node.line)
            )
            return None
        t = self.new_temp(ret_type)
        self.emit(Call(t, node.callee, len(evaluated_args), source_line=node.line))
        return t

    # -------------------------------------------------------------------------
    # Statements
    # -------------------------------------------------------------------------

    def visit_MakeStmt(self, node: MakeStmt) -> None:
        val = self.visit(node.initializer)
        if node.needs_widening:
            val = self.widen(val, node.line)
        var_type = node.symbol.type if node.symbol else val.type
        var = Var(node.name, var_type)
        self._emit_assign(var, val, node.line)

    def visit_AssignStmt(self, node: AssignStmt) -> None:
        val = self.visit(node.value)
        if node.needs_widening:
            val = self.widen(val, node.line)
        var_type = node.symbol.type if node.symbol else val.type
        var = Var(node.name, var_type)
        self._emit_assign(var, val, node.line)

    def visit_ShowStmt(self, node: ShowStmt) -> None:
        val = self.visit(node.value)
        self.emit(Print(val, source_line=node.line))

    def visit_AskStmt(self, node: Any) -> None:
        var_type = node.symbol.type if getattr(node, "symbol", None) else Type.STRING
        if hasattr(node, "type_ref") and node.type_ref:
            var_type = type_from_name(node.type_ref.name) or var_type
        var = Var(node.name, var_type)
        self.emit(Ask(var, var_type, source_line=node.line))

    def visit_ExprStmt(self, node: ExprStmt) -> None:
        self.visit(node.expression)

    def visit_GiveStmt(self, node: GiveStmt) -> None:
        if node.value is not None:
            val = self.visit(node.value)
            if node.needs_widening:
                val = self.widen(val, node.line)
            self.emit(Return(val, source_line=node.line))
        else:
            self.emit(Return(None, source_line=node.line))

    def visit_Block(self, node: Block) -> None:
        for stmt in node.statements:
            self.visit(stmt)

    def visit_WhenStmt(self, node: WhenStmt) -> None:
        cond = self.visit(node.condition)
        if node.else_branch is None:
            lend = self.new_label()
            self.emit(IfFalse(cond, lend, source_line=node.line))
            self.visit(node.then_block)
            self.emit(Label(lend, source_line=node.line))
        else:
            lelse = self.new_label()
            lend = self.new_label()
            self.emit(IfFalse(cond, lelse, source_line=node.line))
            self.visit(node.then_block)
            self.emit(Goto(lend, source_line=node.line))
            self.emit(Label(lelse, source_line=node.line))
            self.visit(node.else_branch)
            self.emit(Label(lend, source_line=node.line))

    def visit_DuringStmt(self, node: DuringStmt) -> None:
        lstart = self.new_label()
        lend = self.new_label()
        self._loop_stack.append((lstart, lend))

        self.emit(Label(lstart, source_line=node.line))
        cond = self.visit(node.condition)
        self.emit(IfFalse(cond, lend, source_line=node.line))
        self.visit(node.body)
        self.emit(Goto(lstart, source_line=node.line))
        self.emit(Label(lend, source_line=node.line))

        self._loop_stack.pop()

    def visit_StopStmt(self, node: StopStmt) -> None:
        if not self._loop_stack:
            raise InternalCompilerError(
                "stop statement outside loop context in IR generation",
                assertion="len(self._loop_stack) > 0",
            )
        _, lend = self._loop_stack[-1]
        self.emit(Goto(lend, source_line=node.line))

    def visit_SkipStmt(self, node: SkipStmt) -> None:
        if not self._loop_stack:
            raise InternalCompilerError(
                "skip statement outside loop context in IR generation",
                assertion="len(self._loop_stack) > 0",
            )
        lstart, _ = self._loop_stack[-1]
        self.emit(Goto(lstart, source_line=node.line))


# =============================================================================
# 4. Basic Blocks and Control Flow Graph (CFG) (RFC-0006 §3.6)
# =============================================================================


@dataclass
class BasicBlock:
    """A straight-line sequence of instructions with single entry and exit points."""

    id: int
    label: str | None
    instrs: list[TACInstr]
    succ: list[int] = field(default_factory=list)
    pred: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert basic block to JSON-serializable dictionary."""
        return {
            "id": self.id,
            "label": self.label,
            "instrs": [format_instruction(instr).strip() for instr in self.instrs],
            "succ": list(self.succ),
            "pred": list(self.pred),
        }


@dataclass
class CFG:
    """Control Flow Graph for a single function."""

    function: str
    blocks: list[BasicBlock]
    entry: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert CFG to JSON-serializable dictionary."""
        return {
            "function": self.function,
            "entry": self.entry,
            "blocks": [b.to_dict() for b in self.blocks],
        }


def build_cfg(function_instrs: Sequence[TACInstr]) -> CFG:
    """Build a Control Flow Graph from a function's instructions (FuncBegin ... FuncEnd)."""
    if not function_instrs or not isinstance(function_instrs[0], FuncBegin):
        raise InternalCompilerError(
            "build_cfg requires instruction list starting with FuncBegin",
            assertion="isinstance(function_instrs[0], FuncBegin)",
        )
    if not isinstance(function_instrs[-1], FuncEnd):
        raise InternalCompilerError(
            "build_cfg requires instruction list ending with FuncEnd",
            assertion="isinstance(function_instrs[-1], FuncEnd)",
        )

    func_name = function_instrs[0].name
    body = list(function_instrs[1:-1])

    if not body:
        block = BasicBlock(id=0, label=None, instrs=[])
        return CFG(function=func_name, blocks=[block], entry=0)

    # 1. Identify leaders
    is_leader = [False] * len(body)
    is_leader[0] = True

    for i, instr in enumerate(body):
        if isinstance(instr, Label):
            is_leader[i] = True
        elif isinstance(instr, (Goto, IfFalse, IfTrue, Return)) and i + 1 < len(body):
            is_leader[i + 1] = True

    # 2. Partition into basic blocks
    leader_indices = [i for i, leader in enumerate(is_leader) if leader]
    blocks: list[BasicBlock] = []
    label_to_block_id: dict[str, int] = {}

    for b_id, start_idx in enumerate(leader_indices):
        end_idx = (
            leader_indices[b_id + 1] if b_id + 1 < len(leader_indices) else len(body)
        )
        block_instrs = body[start_idx:end_idx]
        block_label: str | None = None
        if block_instrs and isinstance(block_instrs[0], Label):
            block_label = block_instrs[0].name
            label_to_block_id[block_label] = b_id

        blocks.append(BasicBlock(id=b_id, label=block_label, instrs=block_instrs))

    # 3. Determine control flow edges (successors)
    for b_id, b in enumerate(blocks):
        if not b.instrs:
            if b_id + 1 < len(blocks):
                b.succ.append(b_id + 1)
            continue

        last_instr = b.instrs[-1]
        if isinstance(last_instr, Goto):
            target_id = label_to_block_id.get(last_instr.target)
            if target_id is not None:
                b.succ.append(target_id)
        elif isinstance(last_instr, (IfFalse, IfTrue)):
            target_id = label_to_block_id.get(last_instr.target)
            if target_id is not None:
                b.succ.append(target_id)
            # Fall-through successor
            if b_id + 1 < len(blocks) and (b_id + 1) != target_id:
                b.succ.append(b_id + 1)
        elif isinstance(last_instr, Return):
            # No successors
            pass
        else:
            # Fall-through to next block
            if b_id + 1 < len(blocks):
                b.succ.append(b_id + 1)

    # 4. Compute predecessors from successors
    for b in blocks:
        for s_id in b.succ:
            if b.id not in blocks[s_id].pred:
                blocks[s_id].pred.append(b.id)

    return CFG(function=func_name, blocks=blocks, entry=0)


def build_all_cfgs(tac: Sequence[TACInstr]) -> list[CFG]:
    """Build CFGs for every function present in the TAC stream."""
    cfgs: list[CFG] = []
    current_fn: list[TACInstr] = []

    for instr in tac:
        if isinstance(instr, FuncBegin):
            current_fn = [instr]
        elif isinstance(instr, FuncEnd):
            current_fn.append(instr)
            cfgs.append(build_cfg(current_fn))
            current_fn = []
        elif current_fn:
            current_fn.append(instr)

    return cfgs


def flatten_cfg(
    cfg: CFG, params: list[tuple[str, Type]] | None = None, ret: Type = Type.VOID
) -> list[TACInstr]:
    """Flatten a CFG back into a linear list of TAC instructions."""
    instrs: list[TACInstr] = [
        FuncBegin(name=cfg.function, params=params or [], ret=ret, source_line=0)
    ]
    for block in cfg.blocks:
        instrs.extend(block.instrs)
    instrs.append(FuncEnd(name=cfg.function, source_line=0))
    return instrs


# =============================================================================
# 5. Formats (RFC-0006 §3.7)
# =============================================================================


def format_instruction(instr: TACInstr) -> str:
    """Format a single instruction to its display string (indented or at column 0)."""
    if isinstance(instr, FuncBegin):
        param_str = ", ".join(p[0] for p in instr.params)
        return f"func {instr.name}({param_str}):"
    if isinstance(instr, FuncEnd):
        return "endfunc"
    if isinstance(instr, Label):
        return f"{instr.name}:"
    if isinstance(instr, Copy):
        return f"  {instr.dest.name} = {format_operand(instr.src)}"
    if isinstance(instr, BinOp):
        return f"  {instr.dest.name} = {format_operand(instr.left)} {instr.op} {format_operand(instr.right)}"
    if isinstance(instr, UnOp):
        return f"  {instr.dest.name} = {instr.op} {format_operand(instr.operand)}"
    if isinstance(instr, Goto):
        return f"  goto {instr.target}"
    if isinstance(instr, IfFalse):
        return f"  ifFalse {format_operand(instr.cond)} goto {instr.target}"
    if isinstance(instr, IfTrue):
        return f"  ifTrue {format_operand(instr.cond)} goto {instr.target}"
    if isinstance(instr, Param):
        return f"  param {format_operand(instr.arg)}"
    if isinstance(instr, Call):
        if instr.dest is not None:
            return f"  {instr.dest.name} = call {instr.func}, {instr.argc}"
        return f"  call {instr.func}, {instr.argc}"
    if isinstance(instr, Return):
        if instr.value is not None:
            return f"  return {format_operand(instr.value)}"
        return "  return"
    if isinstance(instr, Print):
        return f"  print {format_operand(instr.value)}"
    if isinstance(instr, Ask):
        return f"  {instr.dest.name} = ask {instr.type.value}"
    raise InternalCompilerError(f"Unknown instruction class: {type(instr)}")


def format_tac(instrs: Sequence[TACInstr]) -> list[str]:
    """Format a sequence of TAC instructions into human-readable lines."""
    return [format_instruction(instr) for instr in instrs]


def instruction_to_dict(instr: TACInstr) -> dict[str, Any]:
    """Serialize a single TAC instruction into a dictionary for JSON conversion."""
    text = format_instruction(instr).strip()
    base: dict[str, Any] = {"line": instr.source_line, "text": text}

    if isinstance(instr, FuncBegin):
        base.update(
            {
                "op": "func",
                "name": instr.name,
                "params": [{"name": p[0], "type": p[1].value} for p in instr.params],
                "ret": instr.ret.value,
            }
        )
    elif isinstance(instr, FuncEnd):
        base.update({"op": "endfunc", "name": instr.name})
    elif isinstance(instr, Label):
        base.update({"op": "label", "name": instr.name})
    elif isinstance(instr, Copy):
        base.update(
            {
                "op": "copy",
                "dest": instr.dest.name,
                "src": format_operand(instr.src),
                "type": instr.dest.type.value,
            }
        )
    elif isinstance(instr, BinOp):
        base.update(
            {
                "op": "binop",
                "dest": instr.dest.name,
                "operator": instr.op,
                "left": format_operand(instr.left),
                "right": format_operand(instr.right),
                "type": instr.dest.type.value,
            }
        )
    elif isinstance(instr, UnOp):
        base.update(
            {
                "op": "unop",
                "dest": instr.dest.name,
                "operator": instr.op,
                "operand": format_operand(instr.operand),
                "type": instr.dest.type.value,
            }
        )
    elif isinstance(instr, Goto):
        base.update({"op": "goto", "target": instr.target})
    elif isinstance(instr, IfFalse):
        base.update(
            {
                "op": "iffalse",
                "cond": format_operand(instr.cond),
                "target": instr.target,
            }
        )
    elif isinstance(instr, IfTrue):
        base.update(
            {
                "op": "iftrue",
                "cond": format_operand(instr.cond),
                "target": instr.target,
            }
        )
    elif isinstance(instr, Param):
        base.update(
            {
                "op": "param",
                "arg": format_operand(instr.arg),
                "type": instr.arg.type.value,
            }
        )
    elif isinstance(instr, Call):
        base.update(
            {
                "op": "call",
                "dest": instr.dest.name if instr.dest else None,
                "func": instr.func,
                "argc": instr.argc,
                "type": instr.dest.type.value if instr.dest else "void",
            }
        )
    elif isinstance(instr, Return):
        base.update(
            {
                "op": "return",
                "value": format_operand(instr.value) if instr.value else None,
            }
        )
    elif isinstance(instr, Print):
        base.update({"op": "print", "value": format_operand(instr.value)})
    elif isinstance(instr, Ask):
        base.update(
            {
                "op": "ask",
                "dest": instr.dest.name,
                "type": instr.type.value,
            }
        )
    return base


def tac_to_dict(instrs: Sequence[TACInstr]) -> list[dict[str, Any]]:
    """Convert a sequence of TAC instructions to a JSON-serializable list of dicts."""
    return [instruction_to_dict(i) for i in instrs]


# =============================================================================
# 6. Validator (RFC-0006 §3.8)
# =============================================================================


def validate_tac(instrs: Sequence[TACInstr]) -> None:
    """Validate TAC invariants, raising InternalCompilerError on any violation."""
    if not instrs:
        raise InternalCompilerError(
            "TAC instruction stream is empty", assertion="len(instrs) > 0"
        )

    in_func = False
    current_func: str | None = None
    labels_in_func: set[str] = set()
    jumps_in_func: list[tuple[str, int]] = []
    temps_defined: set[str] = set()
    temps_assigned_count: dict[str, int] = {}
    pending_params: int = 0
    last_instr: TACInstr | None = None

    for idx, instr in enumerate(instrs):
        # Invariant 1: FuncBegin / FuncEnd pairing and nesting
        if isinstance(instr, FuncBegin):
            if in_func:
                raise InternalCompilerError(
                    f"Nested function definition '{instr.name}' inside '{current_func}'",
                    assertion="not in_func",
                )
            in_func = True
            current_func = instr.name
            labels_in_func.clear()
            jumps_in_func.clear()
            temps_defined.clear()
            temps_assigned_count.clear()
            pending_params = 0
            last_instr = None
            continue

        if isinstance(instr, FuncEnd):
            if not in_func or current_func != instr.name:
                raise InternalCompilerError(
                    f"Mismatched FuncEnd '{instr.name}', expected '{current_func}'",
                    assertion="in_func and current_func == instr.name",
                )
            # Invariant 5: Function must end with Return before FuncEnd
            if not isinstance(last_instr, Return):
                raise InternalCompilerError(
                    f"Function '{current_func}' does not end with Return before FuncEnd",
                    assertion="isinstance(last_instr, Return)",
                )
            # Invariant 2: Jump targets must be defined in the same function
            for target, line in jumps_in_func:
                if target not in labels_in_func:
                    raise InternalCompilerError(
                        f"Jump to undefined label '{target}' in function '{current_func}' at line {line}",
                        assertion="target in labels_in_func",
                    )

            in_func = False
            current_func = None
            continue

        if not in_func:
            raise InternalCompilerError(
                f"Instruction '{format_instruction(instr).strip()}' outside function definition",
                assertion="in_func",
            )

        # Invariant 2: Labels unique per function
        if isinstance(instr, Label):
            if instr.name in labels_in_func:
                raise InternalCompilerError(
                    f"Duplicate label definition '{instr.name}' in function '{current_func}'",
                    assertion="instr.name not in labels_in_func",
                )
            labels_in_func.add(instr.name)

        # Track jumps for target validation
        if isinstance(instr, (Goto, IfFalse, IfTrue)):
            jumps_in_func.append((instr.target, instr.source_line))

        # Invariant 6: Condition operand in IfFalse / IfTrue must be BOOL
        if isinstance(instr, (IfFalse, IfTrue)) and instr.cond.type != Type.BOOL:
            raise InternalCompilerError(
                f"Condition in {type(instr).__name__} is not bool: {instr.cond.type.value}",
                assertion="instr.cond.type == Type.BOOL",
            )

        # Invariant 4: Call preceded by exactly argc Param instructions
        if isinstance(instr, Param):
            pending_params += 1
        elif isinstance(instr, Call):
            if pending_params != instr.argc:
                raise InternalCompilerError(
                    f"Call to '{instr.func}' expects {instr.argc} params but found {pending_params}",
                    assertion="pending_params == instr.argc",
                )
            pending_params = 0
        else:
            if pending_params > 0 and not isinstance(instr, Param):
                raise InternalCompilerError(
                    f"Instruction '{type(instr).__name__}' interposed between Param and Call",
                    assertion="pending_params == 0",
                )

        # Invariant 3: Temp defined before use on textual path
        def check_use(opnd: Operand, fn_name: str | None = current_func) -> None:
            if isinstance(opnd, Temp) and opnd.name not in temps_defined:
                raise InternalCompilerError(
                    f"Use of undefined temporary '{opnd.name}' in function '{fn_name}'",
                    assertion="opnd.name in temps_defined",
                )

        # Check operand uses
        if isinstance(instr, Copy):
            check_use(instr.src)
        elif isinstance(instr, BinOp):
            check_use(instr.left)
            check_use(instr.right)
        elif isinstance(instr, UnOp):
            check_use(instr.operand)
        elif isinstance(instr, (IfFalse, IfTrue)):
            check_use(instr.cond)
        elif isinstance(instr, Param):
            check_use(instr.arg)
        elif (
            isinstance(instr, Return)
            and instr.value is not None
            or isinstance(instr, Print)
        ):
            check_use(instr.value)

        # Register temp definitions
        dest = getattr(instr, "dest", None)
        if isinstance(dest, Temp):
            count = temps_assigned_count.get(dest.name, 0) + 1
            temps_assigned_count[dest.name] = count
            # In short-circuit patterns, a temp may be assigned twice before the merge label
            if count > 2:
                raise InternalCompilerError(
                    f"Temporary '{dest.name}' assigned more than twice in '{current_func}'",
                    assertion="count <= 2",
                )
            temps_defined.add(dest.name)

        last_instr = instr

    if in_func:
        raise InternalCompilerError(
            f"Unclosed function '{current_func}' at end of TAC stream",
            assertion="not in_func",
        )
