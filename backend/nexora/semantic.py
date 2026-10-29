"""Semantic analyzer and type checker implementation for MiniLang v1.

Governed by RFC-0001 §3.3–§3.6, RFC-0004 §3.4, and RFC-0005. Performs two-pass
scope resolution, static type checking, task hoisting, missing-give analysis,
and attaches type and symbol annotations to AST nodes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .ast_nodes import (
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
    NodeVisitor,
    Program,
    ShowStmt,
    SkipStmt,
    Stmt,
    StopStmt,
    StringLiteral,
    TaskDecl,
    UnaryExpr,
    WhenStmt,
)
from .errors import Diagnostic, DiagnosticBag
from .symbols import (
    FunctionType,
    ScopeKind,
    Symbol,
    SymbolKind,
    SymbolTable,
    Type,
    is_assignable,
    is_numeric,
    type_from_name,
)

RESERVED_TYPE_NAMES: frozenset[str] = frozenset(
    {"int", "float", "string", "bool", "void"}
)


@dataclass
class SemanticResult:
    """The result of semantic analysis."""

    program: Program
    symbols: list[dict[str, Any]]
    diagnostics: list[Diagnostic]

    @property
    def ok(self) -> bool:
        """Return True if analysis produced no error-level diagnostics."""
        return not any(d.severity == "error" for d in self.diagnostics)


def always_gives(node: Stmt | TaskDecl | None) -> bool:
    """Check if statement or block conservatively gives a value on every execution path."""
    match node:
        case GiveStmt():
            return True
        case Block(statements=statements):
            return any(always_gives(s) for s in statements)
        case WhenStmt(then_block=then_block, else_branch=else_branch):
            if else_branch is None:
                return False
            return always_gives(then_block) and always_gives(else_branch)
        case _:
            return False


class SemanticAnalyzer(NodeVisitor):
    """Walks the AST, resolves names, checks types, and writes annotations."""

    def __init__(self) -> None:
        """Initialize the SemanticAnalyzer."""
        self._table: SymbolTable = SymbolTable()
        self._diagnostics: DiagnosticBag = DiagnosticBag()
        self._current_task: TaskDecl | None = None
        self._current_task_ret_type: Type = Type.VOID
        self._loop_depth: int = 0

    def analyze(self, program: Program) -> SemanticResult:
        """Analyze a program AST and return SemanticResult with annotations and diagnostics."""
        # =====================================================================
        # Pass 1: Hoist all top-level task declarations (RFC-0005 §3.5)
        # =====================================================================
        for item in program.body:
            if isinstance(item, TaskDecl):
                self._hoist_task(item)

        # =====================================================================
        # Pass 2: Analyze all items in sequential order
        # =====================================================================
        for item in program.body:
            if isinstance(item, TaskDecl):
                self._analyze_task_body(item)
            else:
                self.visit(item)

        # =====================================================================
        # Post-analysis: Unused variable warnings W4003 (RFC-0005 §3.5)
        # =====================================================================
        for sym in self._table._all_symbols:
            if (
                sym.kind == SymbolKind.VARIABLE
                and not sym.used
                and not sym.name.startswith("_")
            ):
                self._diagnostics.warning(
                    code="W4003",
                    message=f"variable '{sym.name}' is declared but never used",
                    line=sym.line,
                    column=sym.column,
                )

        return SemanticResult(
            program=program,
            symbols=self._table.snapshot(),
            diagnostics=self._diagnostics.items(),
        )

    # =========================================================================
    # Pass 1: Task Hoisting
    # =========================================================================

    def _hoist_task(self, task: TaskDecl) -> None:
        """Validate signature and declare task symbol in global scope."""
        # Check reserved task name (E3015)
        if self._is_reserved_name(task.name):
            self._diagnostics.error(
                code="E3015",
                message=self._reserved_name_message(task.name),
                line=task.line,
                column=task.column,
            )

        # Check duplicate task name in global scope (E3016)
        existing = self._table.lookup(task.name)
        if existing is not None:
            self._diagnostics.error(
                code="E3016",
                message=f"task '{task.name}' is already defined at line {existing.line}",
                line=task.line,
                column=task.column,
            )
            return

        # Check parameters
        param_types: list[Type] = []
        seen_params: set[str] = set()

        for param in task.params:
            if self._is_reserved_name(param.name):
                self._diagnostics.error(
                    code="E3015",
                    message=self._reserved_name_message(param.name),
                    line=param.line,
                    column=param.column,
                )

            if param.name in seen_params:
                self._diagnostics.error(
                    code="E3016",
                    message=f"duplicate parameter '{param.name}'",
                    line=param.line,
                    column=param.column,
                )
            else:
                seen_params.add(param.name)

            p_type = type_from_name(param.type_ref.name)
            if p_type is None:
                self._diagnostics.error(
                    code="E3014",
                    message=f"unknown type '{param.type_ref.name}'",
                    line=param.type_ref.line,
                    column=param.type_ref.column,
                    hint="valid types are int, float, string, bool",
                )
                param_types.append(Type.ERROR)
            else:
                param_types.append(p_type)

        # Check return type
        ret_type = Type.VOID
        if task.return_type is not None:
            resolved_ret = type_from_name(task.return_type.name)
            if resolved_ret is None:
                self._diagnostics.error(
                    code="E3014",
                    message=f"unknown type '{task.return_type.name}'",
                    line=task.return_type.line,
                    column=task.return_type.column,
                    hint="valid types are int, float, string, bool",
                )
                ret_type = Type.ERROR
            else:
                ret_type = resolved_ret

        func_type = FunctionType(params=tuple(param_types), ret=ret_type)
        sym = Symbol(
            name=task.name,
            kind=SymbolKind.TASK,
            type=func_type,
            line=task.line,
            column=task.column,
            scope_kind=ScopeKind.GLOBAL,
            order=0,
        )
        self._table.declare(sym)
        task.symbol = sym

    # =========================================================================
    # Pass 2: Task Body Analysis
    # =========================================================================

    def _analyze_task_body(self, task: TaskDecl) -> None:
        """Analyze a hoisted task's parameters, body statements, and return paths."""
        if task.symbol is None:
            return

        self._table.push(ScopeKind.TASK)
        old_task = self._current_task
        old_ret = self._current_task_ret_type
        self._current_task = task
        self._current_task_ret_type = (
            task.symbol.type.ret
            if isinstance(task.symbol.type, FunctionType)
            else Type.VOID
        )

        # Declare parameters in the task scope (RFC-0005 §3.5)
        if isinstance(task.symbol.type, FunctionType):
            for param, p_type in zip(task.params, task.symbol.type.params):
                param_sym = Symbol(
                    name=param.name,
                    kind=SymbolKind.PARAMETER,
                    type=p_type,
                    line=param.line,
                    column=param.column,
                    scope_kind=ScopeKind.TASK,
                    order=0,
                )
                if not self._table.declare(param_sym):
                    existing = self._table.lookup(param.name)
                    prev_line = f" at line {existing.line}" if existing else ""
                    self._diagnostics.error(
                        code="E3002",
                        message=f"'{param.name}' is already declared{prev_line}",
                        line=param.line,
                        column=param.column,
                        hint="MiniLang does not allow shadowing",
                    )
                param.symbol = param_sym

        # Analyze task body statements directly without pushing a second block scope
        self._analyze_statements(task.body.statements)

        # Check missing give analysis (RFC-0005 §3.6)
        if self._current_task_ret_type not in (
            Type.VOID,
            Type.ERROR,
        ) and not always_gives(task.body):
            self._diagnostics.error(
                code="E3012",
                message=f"task '{task.name}' does not return a value on every path",
                line=task.line,
                column=task.column,
            )

        self._table.pop()
        self._current_task = old_task
        self._current_task_ret_type = old_ret

    def _analyze_statements(self, statements: list[Stmt]) -> None:
        """Analyze a list of statements in sequence and check for unreachable code (W4001)."""
        has_returned = False

        for stmt in statements:
            if has_returned:
                self._diagnostics.warning(
                    code="W4001",
                    message="unreachable code after 'give'",
                    line=stmt.line,
                    column=stmt.column,
                )
                # Still analyze the statement to catch other semantic errors
                self.visit(stmt)
            else:
                self.visit(stmt)
                if always_gives(stmt):
                    has_returned = True

    # =========================================================================
    # Statement Visitors
    # =========================================================================

    def visit_Block(self, node: Block) -> None:
        """Visit Block: push BLOCK scope, analyze statements, pop."""
        self._table.push(ScopeKind.BLOCK)
        self._analyze_statements(node.statements)
        self._table.pop()

    def visit_MakeStmt(self, node: MakeStmt) -> None:
        """Visit make statement: analyze initializer, check types, declare symbol."""
        # 1. Analyze initializer first so 'make x = x + 1' reports E3001 on the right (RFC-0005 §3.5)
        init_type = self.visit(node.initializer)

        # 2. Check reserved name (E3015)
        if self._is_reserved_name(node.name):
            self._diagnostics.error(
                code="E3015",
                message=self._reserved_name_message(node.name),
                line=node.line,
                column=node.column,
            )

        # 3. Check for void initializer value (E3013)
        if init_type == Type.VOID:
            self._diagnostics.error(
                code="E3013",
                message="cannot use void return value as a value",
                line=node.initializer.line,
                column=node.initializer.column,
            )
            init_type = Type.ERROR

        # 4. Resolve declared type if present
        var_type = init_type
        if node.declared_type is not None:
            resolved_type = type_from_name(node.declared_type.name)
            if resolved_type is None:
                self._diagnostics.error(
                    code="E3014",
                    message=f"unknown type '{node.declared_type.name}'",
                    line=node.declared_type.line,
                    column=node.declared_type.column,
                    hint="valid types are int, float, string, bool",
                )
                var_type = Type.ERROR
            else:
                var_type = resolved_type
                if not is_assignable(var_type, init_type):
                    self._diagnostics.error(
                        code="E3003",
                        message=f"cannot assign {init_type.value} to variable '{node.name}' of type {var_type.value}",
                        line=node.line,
                        column=node.column,
                    )
                elif var_type == Type.FLOAT and init_type == Type.INT:
                    node.needs_widening = True

        # 5. Declare symbol in current scope
        sym = Symbol(
            name=node.name,
            kind=SymbolKind.VARIABLE,
            type=var_type,
            line=node.line,
            column=node.column,
            scope_kind=self._table.current.kind,
            order=0,
        )
        if not self._table.declare(sym):
            existing = self._table.lookup(node.name)
            prev_line = f" at line {existing.line}" if existing else ""
            self._diagnostics.error(
                code="E3002",
                message=f"'{node.name}' is already declared{prev_line}",
                line=node.line,
                column=node.column,
                hint="MiniLang does not allow shadowing",
            )
        node.symbol = sym

    def visit_AssignStmt(self, node: AssignStmt) -> None:
        """Visit assignment: check variable exists, not global in task, assignable."""
        sym = self._table.lookup(node.name)
        if sym is None:
            hint = None
            if self._table.in_task:
                hint = (
                    "global variables must be declared before the task that uses them"
                )
            self._diagnostics.error(
                code="E3001",
                message=f"use of undeclared variable '{node.name}'",
                line=node.line,
                column=node.column,
                hint=hint,
            )
            target_type = Type.ERROR
        elif sym.kind == SymbolKind.TASK:
            self._diagnostics.error(
                code="E3007",
                message=f"'{node.name}' is a task, not a variable",
                line=node.line,
                column=node.column,
            )
            target_type = Type.ERROR
        else:
            # Check assignment to global inside a task (RFC-0005 §3.4 rule 5)
            if sym.scope_kind == ScopeKind.GLOBAL and self._table.in_task:
                self._diagnostics.error(
                    code="E3009",
                    message=f"cannot assign to global variable '{node.name}' inside a task",
                    line=node.line,
                    column=node.column,
                )
            target_type = sym.type if isinstance(sym.type, Type) else Type.ERROR
            sym.used = True
            node.symbol = sym

        value_type = self.visit(node.value)

        if value_type == Type.VOID:
            self._diagnostics.error(
                code="E3013",
                message="cannot use void return value as a value",
                line=node.value.line,
                column=node.value.column,
            )
        elif not is_assignable(target_type, value_type):
            self._diagnostics.error(
                code="E3003",
                message=f"cannot assign {value_type.value} to variable '{node.name}' of type {target_type.value}",
                line=node.line,
                column=node.column,
            )
        elif target_type == Type.FLOAT and value_type == Type.INT:
            node.needs_widening = True

    def visit_WhenStmt(self, node: WhenStmt) -> None:
        """Visit when statement: check condition is bool, analyze branches."""
        cond_type = self.visit(node.condition)
        if cond_type != Type.BOOL and cond_type != Type.ERROR:
            self._diagnostics.error(
                code="E3005",
                message=f"condition must be bool, found {cond_type.value}",
                line=node.condition.line,
                column=node.condition.column,
            )

        self.visit(node.then_block)
        if node.else_branch is not None:
            self.visit(node.else_branch)

    def visit_DuringStmt(self, node: DuringStmt) -> None:
        """Visit during loop: check condition is bool, track loop depth."""
        cond_type = self.visit(node.condition)
        if cond_type != Type.BOOL and cond_type != Type.ERROR:
            self._diagnostics.error(
                code="E3005",
                message=f"condition must be bool, found {cond_type.value}",
                line=node.condition.line,
                column=node.condition.column,
            )

        self._loop_depth += 1
        self.visit(node.body)
        self._loop_depth -= 1

    def visit_StopStmt(self, node: StopStmt) -> None:
        """Visit stop statement: verify inside during loop (E3017)."""
        if self._loop_depth <= 0:
            self._diagnostics.error(
                code="E3017",
                message="'stop' is only allowed inside a 'during' loop",
                line=node.line,
                column=node.column,
            )

    def visit_SkipStmt(self, node: SkipStmt) -> None:
        """Visit skip statement: verify inside during loop (E3018)."""
        if self._loop_depth <= 0:
            self._diagnostics.error(
                code="E3018",
                message="'skip' is only allowed inside a 'during' loop",
                line=node.line,
                column=node.column,
            )

    def visit_GiveStmt(self, node: GiveStmt) -> None:
        """Visit give statement: verify inside task and check return types (E3010, E3011)."""
        if not self._table.in_task or self._current_task is None:
            self._diagnostics.error(
                code="E3010",
                message="'give' is only allowed inside a task",
                line=node.line,
                column=node.column,
            )
            if node.value is not None:
                self.visit(node.value)
            return

        expected_ret = self._current_task_ret_type
        if expected_ret == Type.VOID:
            if node.value is not None:
                self._diagnostics.error(
                    code="E3011",
                    message="a void task cannot return a value",
                    line=node.line,
                    column=node.column,
                )
                self.visit(node.value)
        else:
            if node.value is None:
                self._diagnostics.error(
                    code="E3011",
                    message=f"task '{self._current_task.name}' is declared to return {expected_ret.value} but this path returns void",
                    line=node.line,
                    column=node.column,
                )
            else:
                val_type = self.visit(node.value)
                if not is_assignable(expected_ret, val_type):
                    self._diagnostics.error(
                        code="E3011",
                        message=f"task '{self._current_task.name}' is declared to return {expected_ret.value} but this path returns {val_type.value}",
                        line=node.line,
                        column=node.column,
                    )
                elif expected_ret == Type.FLOAT and val_type == Type.INT:
                    node.needs_widening = True

    def visit_ShowStmt(self, node: ShowStmt) -> None:
        """Visit show statement: check value is not void (E3013)."""
        val_type = self.visit(node.value)
        if val_type == Type.VOID:
            self._diagnostics.error(
                code="E3013",
                message="cannot pass void value to 'show'",
                line=node.value.line,
                column=node.value.column,
            )

    def visit_AskStmt(self, node: AskStmt) -> None:
        """Visit ask statement: check supported input types (E3019) and declare variable."""
        if self._is_reserved_name(node.name):
            self._diagnostics.error(
                code="E3015",
                message=self._reserved_name_message(node.name),
                line=node.line,
                column=node.column,
            )

        resolved_type = type_from_name(node.type_ref.name)
        if resolved_type is None:
            self._diagnostics.error(
                code="E3014",
                message=f"unknown type '{node.type_ref.name}'",
                line=node.type_ref.line,
                column=node.type_ref.column,
                hint="valid types are int, float, string, bool",
            )
            var_type = Type.ERROR
        elif resolved_type not in (Type.INT, Type.FLOAT, Type.STRING):
            self._diagnostics.error(
                code="E3019",
                message=f"'ask' does not support type '{resolved_type.value}'; valid types: int, float, string",
                line=node.type_ref.line,
                column=node.type_ref.column,
            )
            var_type = Type.ERROR
        else:
            var_type = resolved_type

        sym = Symbol(
            name=node.name,
            kind=SymbolKind.VARIABLE,
            type=var_type,
            line=node.line,
            column=node.column,
            scope_kind=self._table.current.kind,
            order=0,
        )
        if not self._table.declare(sym):
            existing = self._table.lookup(node.name)
            prev_line = f" at line {existing.line}" if existing else ""
            self._diagnostics.error(
                code="E3002",
                message=f"'{node.name}' is already declared{prev_line}",
                line=node.line,
                column=node.column,
                hint="MiniLang does not allow shadowing",
            )
        node.symbol = sym

    def visit_ExprStmt(self, node: ExprStmt) -> None:
        """Visit expression statement: void calls are permitted here."""
        self.visit(node.expression)

    # =========================================================================
    # Expression Visitors
    # =========================================================================

    def visit_IntLiteral(self, node: IntLiteral) -> Type:
        """Return and annotate Type.INT."""
        node.type = Type.INT
        return Type.INT

    def visit_FloatLiteral(self, node: FloatLiteral) -> Type:
        """Return and annotate Type.FLOAT."""
        node.type = Type.FLOAT
        return Type.FLOAT

    def visit_StringLiteral(self, node: StringLiteral) -> Type:
        """Return and annotate Type.STRING."""
        node.type = Type.STRING
        return Type.STRING

    def visit_BoolLiteral(self, node: BoolLiteral) -> Type:
        """Return and annotate Type.BOOL."""
        node.type = Type.BOOL
        return Type.BOOL

    def visit_EmptyLiteral(self, node: EmptyLiteral) -> Type:
        """Return and annotate Type.EMPTY."""
        node.type = Type.EMPTY
        return Type.EMPTY

    def visit_Identifier(self, node: Identifier) -> Type:
        """Resolve identifier and return its type (E3001, E3007)."""
        sym = self._table.lookup(node.name)
        if sym is None:
            hint = None
            if self._table.in_task:
                hint = (
                    "global variables must be declared before the task that uses them"
                )
            self._diagnostics.error(
                code="E3001",
                message=f"use of undeclared variable '{node.name}'",
                line=node.line,
                column=node.column,
                hint=hint,
            )
            node.type = Type.ERROR
            return Type.ERROR

        if sym.kind == SymbolKind.TASK:
            self._diagnostics.error(
                code="E3007",
                message=f"'{node.name}' is a task, not a variable",
                line=node.line,
                column=node.column,
            )
            node.type = Type.ERROR
            return Type.ERROR

        sym.used = True
        node.symbol = sym
        resolved_type = sym.type if isinstance(sym.type, Type) else Type.ERROR
        node.type = resolved_type
        return resolved_type

    def visit_UnaryExpr(self, node: UnaryExpr) -> Type:
        """Type-check unary operations '-' and 'not' (E3004)."""
        op_type = self.visit(node.operand)
        if op_type == Type.ERROR:
            node.type = Type.ERROR
            return Type.ERROR

        if node.op == "-":
            if is_numeric(op_type):
                node.type = op_type
                return op_type
            self._diagnostics.error(
                code="E3004",
                message=f"cannot apply '-' to {op_type.value}",
                line=node.line,
                column=node.column,
            )
            node.type = Type.ERROR
            return Type.ERROR

        if node.op == "not":
            if op_type == Type.BOOL:
                node.type = Type.BOOL
                return Type.BOOL
            self._diagnostics.error(
                code="E3004",
                message=f"cannot apply 'not' to {op_type.value}",
                line=node.line,
                column=node.column,
            )
            node.type = Type.ERROR
            return Type.ERROR

        node.type = Type.ERROR
        return Type.ERROR

    def visit_BinaryExpr(self, node: BinaryExpr) -> Type:
        """Type-check binary operations according to the typing table in RFC-0005 §3.2."""
        left_type = self.visit(node.left)
        right_type = self.visit(node.right)

        if left_type == Type.ERROR or right_type == Type.ERROR:
            node.type = Type.ERROR
            return Type.ERROR

        res_type = self._check_binary_op(node.op, left_type, right_type)
        if res_type is None:
            self._diagnostics.error(
                code="E3004",
                message=f"cannot apply '{node.op}' to {left_type.value} and {right_type.value}",
                line=node.line,
                column=node.column,
            )
            node.type = Type.ERROR
            return Type.ERROR

        node.type = res_type
        return res_type

    def _check_binary_op(self, op: str, left: Type, right: Type) -> Type | None:
        """Match operand types against operator rules."""
        # Arithmetic +
        if op == "+":
            if left == Type.INT and right == Type.INT:
                return Type.INT
            if is_numeric(left) and is_numeric(right):
                return Type.FLOAT
            if left == Type.STRING and right == Type.STRING:
                return Type.STRING
            return None

        # Arithmetic - and *
        if op in ("-", "*"):
            if left == Type.INT and right == Type.INT:
                return Type.INT
            if is_numeric(left) and is_numeric(right):
                return Type.FLOAT
            return None

        # Division / always yields float (RFC-0001 §3.6, RFC-0005 §3.2)
        if op == "/":
            if is_numeric(left) and is_numeric(right):
                return Type.FLOAT
            return None

        # Modulo %
        if op == "%":
            if left == Type.INT and right == Type.INT:
                return Type.INT
            if is_numeric(left) and is_numeric(right):
                return Type.FLOAT
            return None

        # Relational < <= > >=
        if op in ("<", "<=", ">", ">="):
            if is_numeric(left) and is_numeric(right):
                return Type.BOOL
            if left == Type.STRING and right == Type.STRING:
                return Type.BOOL
            return None

        # Equality == !=
        if op in ("==", "!="):
            if is_numeric(left) and is_numeric(right):
                return Type.BOOL
            if left == right and left in (Type.STRING, Type.BOOL, Type.EMPTY):
                return Type.BOOL
            return None

        # Logical both, either
        if op in ("both", "either"):
            if left == Type.BOOL and right == Type.BOOL:
                return Type.BOOL
            return None

        return None

    def visit_CallExpr(self, node: CallExpr) -> Type:
        """Type-check task call, argument counts, and argument types (E3001, E3006, E3007, E3008)."""
        sym = self._table.lookup(node.callee)
        if sym is None:
            self._diagnostics.error(
                code="E3001",
                message=f"use of undeclared task '{node.callee}'",
                line=node.line,
                column=node.column,
            )
            for arg in node.args:
                self.visit(arg)
            node.type = Type.ERROR
            return Type.ERROR

        if sym.kind != SymbolKind.TASK or not isinstance(sym.type, FunctionType):
            self._diagnostics.error(
                code="E3007",
                message=f"'{node.callee}' is a variable, not a task",
                line=node.line,
                column=node.column,
            )
            for arg in node.args:
                self.visit(arg)
            node.type = Type.ERROR
            return Type.ERROR

        sym.used = True
        node.symbol = sym
        func_type = sym.type

        # Check argument count (E3006)
        expected_count = len(func_type.params)
        actual_count = len(node.args)
        if actual_count != expected_count:
            arg_str = "arguments" if expected_count != 1 else "argument"
            self._diagnostics.error(
                code="E3006",
                message=f"task '{node.callee}' expects {expected_count} {arg_str}, got {actual_count}",
                line=node.line,
                column=node.column,
            )

        # Check argument types (E3008)
        node.arg_widenings = []
        for i, arg in enumerate(node.args):
            arg_type = self.visit(arg)
            if i < expected_count:
                param_type = func_type.params[i]
                if not is_assignable(param_type, arg_type):
                    self._diagnostics.error(
                        code="E3008",
                        message=f"argument {i + 1} of '{node.callee}' expects {param_type.value}, found {arg_type.value}",
                        line=arg.line,
                        column=arg.column,
                    )
                    node.arg_widenings.append(False)
                elif param_type == Type.FLOAT and arg_type == Type.INT:
                    node.arg_widenings.append(True)
                else:
                    node.arg_widenings.append(False)

        node.type = func_type.ret
        return func_type.ret

    # =========================================================================
    # Helpers
    # =========================================================================

    def _is_reserved_name(self, name: str) -> bool:
        """Return True if name is a predefined type or compiler prefix (RFC-0005 §3.3)."""
        return name in RESERVED_TYPE_NAMES or name.startswith("__nx_")

    def _reserved_name_message(self, name: str) -> str:
        """Generate appropriate E3015 error message."""
        if name in RESERVED_TYPE_NAMES:
            return f"'{name}' is a reserved name"
        return "names starting with '__nx_' are reserved"


def analyze(program: Program) -> SemanticResult:
    """Convenience function to run semantic analysis on an AST Program."""
    return SemanticAnalyzer().analyze(program)
