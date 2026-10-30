"""Python code generator for MiniLang v1 (AST to Python 3.10+ transpilation).

Governed by RFC-0008. Implements:
1. GeneratedCode data structure with source code, line_map, and names dictionary (RFC-0008 §3.1)
2. PythonGenerator AST visitor (RFC-0008 §3.1-§3.7)
3. AST-based generated Python whitelist validator (RFC-0008 §3.9)
"""

from __future__ import annotations

import ast
import keyword
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
    Expr,
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
from .errors import InternalCompilerError

# =============================================================================
# 1. Reserved Words and Identifier Mangling (RFC-0008 §3.6)
# =============================================================================

RESERVED_PYTHON_NAMES: frozenset[str] = frozenset(
    set(keyword.kwlist)
    | {
        "print",
        "str",
        "float",
        "int",
        "bool",
        "isinstance",
        "repr",
        "input",
    }
)


def _collect_identifiers(node: Any, names: set[str]) -> None:
    """Collect all identifier names defined or referenced in the AST."""
    match node:
        case Program(body=body):
            for item in body:
                _collect_identifiers(item, names)
        case TaskDecl(name=name, params=params, body=body):
            names.add(name)
            for p in params:
                names.add(p.name)
            _collect_identifiers(body, names)
        case Block(statements=statements):
            for s in statements:
                _collect_identifiers(s, names)
        case MakeStmt(name=name, initializer=init):
            names.add(name)
            _collect_identifiers(init, names)
        case AssignStmt(name=name, value=val):
            names.add(name)
            _collect_identifiers(val, names)
        case AskStmt(name=name):
            names.add(name)
        case WhenStmt(condition=cond, then_block=then_b, else_branch=else_b):
            _collect_identifiers(cond, names)
            _collect_identifiers(then_b, names)
            if else_b is not None:
                _collect_identifiers(else_b, names)
        case DuringStmt(condition=cond, body=b):
            _collect_identifiers(cond, names)
            _collect_identifiers(b, names)
        case GiveStmt(value=val):
            if val is not None:
                _collect_identifiers(val, names)
        case ShowStmt(value=val):
            _collect_identifiers(val, names)
        case ExprStmt(expression=expr):
            _collect_identifiers(expr, names)
        case Identifier(name=name):
            names.add(name)
        case UnaryExpr(operand=operand):
            _collect_identifiers(operand, names)
        case BinaryExpr(left=left, right=right):
            _collect_identifiers(left, names)
            _collect_identifiers(right, names)
        case CallExpr(callee=callee, args=args):
            names.add(callee)
            for a in args:
                _collect_identifiers(a, names)
        case _:
            pass


def _build_rename_map(all_names: set[str]) -> dict[str, str]:
    """Build deterministic mapping for reserved Python identifiers (RFC-0008 §3.6).

    A name in RESERVED becomes name_. If name_ already exists in all_names
    or was already assigned, append another _ until unique.
    Returns:
        dict[str, str]: mapping from mangled Python name -> original MiniLang name.
    """
    sorted_reserved = sorted(n for n in all_names if n in RESERVED_PYTHON_NAMES)
    assigned_targets: set[str] = set()
    # Initial pool includes existing user names to avoid collisions
    occupied_names = set(all_names)

    mangled_to_original: dict[str, str] = {}

    for name in sorted_reserved:
        candidate = f"{name}_"
        while candidate in occupied_names or candidate in assigned_targets:
            candidate = f"{candidate}_"
        assigned_targets.add(candidate)
        occupied_names.add(candidate)
        mangled_to_original[candidate] = name

    return mangled_to_original


# =============================================================================
# 2. Output and Data Structures (RFC-0008 §3.1)
# =============================================================================


@dataclass(frozen=True)
class GeneratedCode:
    """Result of Python code generation.

    Attributes:
        code: Python source ending with a single newline.
        line_map: line_map[i] = MiniLang source line for generated line i+1 (0 = prelude/header/blank).
        names: Mapping from renamed Python identifier to original MiniLang name.
    """

    code: str
    line_map: list[int]
    names: dict[str, str]


# =============================================================================
# 3. Precedence & Parenthesization (RFC-0008 §3.4)
# =============================================================================

# Precedence levels (RFC-0008 §3.4 table, low to high)
# 1: or (either)
# 2: and (both)
# 3: not
# 4: == != < <= > >= (all comparisons share level 4)
# 5: + -
# 6: * / %
# 7: unary -
# 8: atoms (literals, names, calls)


def _expr_precedence(expr: Expr) -> int:
    """Return precedence level for expression."""
    match expr:
        case BinaryExpr(op=op):
            if op == "either":
                return 1
            if op == "both":
                return 2
            if op in ("==", "!=", "<", "<=", ">", ">="):
                return 4
            if op in ("+", "-"):
                return 5
            if op in ("*", "/", "%"):
                return 6
            return 0
        case UnaryExpr(op=op):
            if op == "not":
                return 3
            if op == "-":
                return 7
            return 0
        case IntLiteral(value=v):
            if v < 0:
                return 7  # Negative literal treated as unary minus level
            return 8
        case FloatLiteral(value=v):
            if v < 0:
                return 7
            return 8
        case _:
            return 8


def _needs_parens(child: Expr, parent: Expr, side: str | None = None) -> bool:
    """Determine whether child expression needs parentheses when enclosed in parent."""
    p_child = _expr_precedence(child)
    p_parent = _expr_precedence(parent)

    # 1. Child has lower precedence than parent
    if p_child < p_parent:
        return True

    # 3. Comparison chaining rule (RFC-0008 §3.4 rule 3):
    # Both parent and child are level 4 (comparison/equality), on either side
    if p_child == 4 and p_parent == 4:
        return True

    # 2. Level equal: parent is binary, child is on the right of a left-associative operator
    if (
        p_child == p_parent
        and side == "right"
        and isinstance(parent, BinaryExpr)
        and parent.op in ("-", "/", "%")
    ):
        return True

    # 4. Unary operator whose operand is itself unary (RFC-0008 §3.4 rule 4)
    # -(-x) or not (not x)
    if isinstance(parent, UnaryExpr) and isinstance(child, UnaryExpr):
        return True
    return bool(
        isinstance(parent, UnaryExpr)
        and parent.op == "-"
        and isinstance(child, (IntLiteral, FloatLiteral))
        and child.value < 0
    )


# =============================================================================
# 4. Code Generator Visitor (RFC-0008 §3.1-§3.7)
# =============================================================================


class PythonGenerator(NodeVisitor):
    """AST-to-Python transpiler for MiniLang programs."""

    target_name = "python"

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.line_map: list[int] = []
        self.orig_to_mangled: dict[str, str] = {}
        self.mangled_to_orig: dict[str, str] = {}

    def _emit(self, text: str, source_line: int = 0) -> None:
        """Emit a single line of Python source with source line mapping."""
        self.lines.append(text)
        self.line_map.append(source_line)

    def _mangle(self, name: str) -> str:
        """Return mangled Python identifier for given MiniLang name."""
        return self.orig_to_mangled.get(name, name)

    def generate(self, program: Program) -> GeneratedCode:
        """Generate Python 3.10+ source and source line map from program AST."""
        # 1. Collect all identifiers and build rename mapping (RFC-0008 §3.6)
        all_names: set[str] = set()
        _collect_identifiers(program, all_names)
        self.mangled_to_orig = _build_rename_map(all_names)
        self.orig_to_mangled = {
            orig: mangled for mangled, orig in self.mangled_to_orig.items()
        }

        # 2. Determine if prelude is needed (only if program contains show statement)
        has_show = self._contains_show(program)

        # 3. Emit header (always, line 1, source_line 0)
        self._emit(
            "# Generated by Nexora (MiniLang -> Python). Do not edit.",
            source_line=0,
        )
        self._emit("", source_line=0)

        # 4. Emit prelude if needed (RFC-0008 §3.2)
        if has_show:
            self._emit("def __nx_show(value):", source_line=0)
            self._emit("    if isinstance(value, bool):", source_line=0)
            self._emit('        print("true" if value else "false")', source_line=0)
            self._emit("    else:", source_line=0)
            self._emit("        print(value)", source_line=0)
            self._emit("", source_line=0)
            self._emit("", source_line=0)

        # 5. Hoist task definitions (RFC-0008 §3.2 rule 3)
        tasks: list[TaskDecl] = [
            item for item in program.body if isinstance(item, TaskDecl)
        ]
        top_stmts: list[Stmt] = [
            item for item in program.body if not isinstance(item, TaskDecl)
        ]

        for i, task in enumerate(tasks):
            self._gen_task(task)
            # Two blank lines after each task definition
            if i < len(tasks) - 1 or top_stmts:
                self._emit("", source_line=0)
                self._emit("", source_line=0)

        # 6. Emit top-level statements
        for stmt in top_stmts:
            self._gen_stmt(stmt, indent_level=0)

        # 7. Form code string with final newline
        code_str = "\n".join(self.lines) + "\n"

        # Invariant check (RFC-0008 §3.7): len(line_map) == code.count("\n")
        if len(self.line_map) != code_str.count("\n"):
            raise InternalCompilerError(
                f"Line map length ({len(self.line_map)}) != newline count ({code_str.count(chr(10))})",
                assertion="len(self.line_map) == code.count('\\n')",
            )

        return GeneratedCode(
            code=code_str,
            line_map=list(self.line_map),
            names=dict(self.mangled_to_orig),
        )

    def _contains_show(self, node: Any) -> bool:
        """Check if AST contains any ShowStmt."""
        match node:
            case Program(body=body):
                return any(self._contains_show(item) for item in body)
            case TaskDecl(body=body):
                return self._contains_show(body)
            case Block(statements=statements):
                return any(self._contains_show(s) for s in statements)
            case WhenStmt(then_block=then_b, else_branch=else_b):
                return self._contains_show(then_b) or (
                    else_b is not None and self._contains_show(else_b)
                )
            case DuringStmt(body=b):
                return self._contains_show(b)
            case ShowStmt():
                return True
            case _:
                return False

    # =========================================================================
    # Task & Statement Generation
    # =========================================================================

    def _gen_task(self, task: TaskDecl) -> None:
        """Generate Python def for task declaration."""
        func_name = self._mangle(task.name)
        param_names = [self._mangle(p.name) for p in task.params]
        params_str = ", ".join(param_names)
        self._emit(f"def {func_name}({params_str}):", source_line=task.line)
        self._gen_suite(task.body.statements, indent_level=1)

    def _gen_suite(self, stmts: list[Stmt], indent_level: int) -> None:
        """Generate statements inside a suite; emit pass if empty."""
        ind = "    " * indent_level
        if not stmts:
            self._emit(f"{ind}pass", source_line=0)
            return

        for stmt in stmts:
            self._gen_stmt(stmt, indent_level)

    def _gen_stmt(self, stmt: Stmt, indent_level: int) -> None:
        """Generate statement at specified indentation level."""
        ind = "    " * indent_level

        match stmt:
            case MakeStmt(
                name=name,
                initializer=init,
                needs_widening=needs_widening,
                line=line,
            ):
                var_name = self._mangle(name)
                init_str = self._gen_expr_widened(init, needs_widening)
                self._emit(f"{ind}{var_name} = {init_str}", source_line=line)

            case AssignStmt(
                name=name,
                value=val,
                needs_widening=needs_widening,
                line=line,
            ):
                var_name = self._mangle(name)
                val_str = self._gen_expr_widened(val, needs_widening)
                self._emit(f"{ind}{var_name} = {val_str}", source_line=line)

            case AskStmt(name=name, type_ref=tref, line=line):
                var_name = self._mangle(name)
                tname = tref.name
                if tname == "int":
                    self._emit(f"{ind}{var_name} = int(input())", source_line=line)
                elif tname == "float":
                    self._emit(f"{ind}{var_name} = float(input())", source_line=line)
                else:  # string
                    self._emit(f"{ind}{var_name} = input()", source_line=line)

            case ShowStmt(value=val, line=line):
                expr_str = self._gen_expr(val)
                self._emit(f"{ind}__nx_show({expr_str})", source_line=line)

            case GiveStmt(value=val, needs_widening=needs_widening, line=line):
                if val is not None:
                    val_str = self._gen_expr_widened(val, needs_widening)
                    self._emit(f"{ind}return {val_str}", source_line=line)
                else:
                    self._emit(f"{ind}return", source_line=line)

            case StopStmt(line=line):
                self._emit(f"{ind}break", source_line=line)

            case SkipStmt(line=line):
                self._emit(f"{ind}continue", source_line=line)

            case ExprStmt(expression=expr, line=line):
                expr_str = self._gen_expr(expr)
                self._emit(f"{ind}{expr_str}", source_line=line)

            case WhenStmt():
                self._gen_when(stmt, indent_level)

            case DuringStmt(condition=cond, body=body, line=line):
                cond_str = self._gen_expr(cond)
                self._emit(f"{ind}while {cond_str}:", source_line=line)
                self._gen_suite(body.statements, indent_level + 1)

            case Block(statements=stmts):
                # Nested blocks inline at same indentation (RFC-0008 §3.3)
                for s in stmts:
                    self._gen_stmt(s, indent_level)

            case _:
                raise InternalCompilerError(
                    f"Unknown statement type for codegen: {type(stmt).__name__}"
                )

    def _gen_when(self, stmt: WhenStmt, indent_level: int) -> None:
        """Generate if / elif / else chain flattened (RFC-0008 §3.3)."""
        ind = "    " * indent_level
        cond_str = self._gen_expr(stmt.condition)
        self._emit(f"{ind}if {cond_str}:", source_line=stmt.line)
        self._gen_suite(stmt.then_block.statements, indent_level + 1)

        curr_else = stmt.else_branch
        while curr_else is not None:
            if isinstance(curr_else, WhenStmt):
                elif_cond = self._gen_expr(curr_else.condition)
                self._emit(f"{ind}elif {elif_cond}:", source_line=curr_else.line)
                self._gen_suite(curr_else.then_block.statements, indent_level + 1)
                curr_else = curr_else.else_branch
            elif isinstance(curr_else, Block):
                self._emit(f"{ind}else:", source_line=curr_else.line)
                self._gen_suite(curr_else.statements, indent_level + 1)
                break
            else:
                break

    # =========================================================================
    # Expression Generation
    # =========================================================================

    def _gen_expr_widened(self, expr: Expr, needs_widening: bool) -> str:
        """Generate expression, applying widening to float if flagged (RFC-0008 §3.5)."""
        if not needs_widening:
            return self._gen_expr(expr)

        if isinstance(expr, IntLiteral):
            try:
                flt_val = float(expr.value)
                return repr(flt_val)
            except OverflowError:
                return f"float({expr.value})"

        raw_str = self._gen_expr(expr)
        return f"float({raw_str})"

    def _gen_expr(self, expr: Expr) -> str:
        """Format an expression node into a valid Python expression string."""
        match expr:
            case IntLiteral(value=v):
                return str(v)
            case FloatLiteral(value=v):
                return repr(v)
            case StringLiteral(value=v):
                return repr(v)
            case BoolLiteral(value=v):
                return "True" if v else "False"
            case EmptyLiteral():
                return "None"
            case Identifier(name=name):
                return self._mangle(name)
            case UnaryExpr(op=op, operand=operand):
                py_op = "not " if op == "not" else "-"
                op_needs_paren = _needs_parens(operand, expr)
                child_str = self._gen_expr(operand)
                if op_needs_paren:
                    child_str = f"({child_str})"
                return f"{py_op}{child_str}"

            case BinaryExpr(op=op, left=left, right=right):
                # Operator translation
                if op == "both":
                    py_op = "and"
                elif op == "either":
                    py_op = "or"
                else:
                    py_op = op

                left_paren = _needs_parens(left, expr, side="left")
                right_paren = _needs_parens(right, expr, side="right")

                left_str = self._gen_expr(left)
                if left_paren:
                    left_str = f"({left_str})"

                right_str = self._gen_expr(right)
                if right_paren:
                    right_str = f"({right_str})"

                return f"{left_str} {py_op} {right_str}"

            case CallExpr(callee=callee, args=args, arg_widenings=widenings):
                func_name = self._mangle(callee)
                arg_strs: list[str] = []
                for i, arg in enumerate(args):
                    widen = widenings[i] if widenings and i < len(widenings) else False
                    arg_strs.append(self._gen_expr_widened(arg, widen))
                return f"{func_name}({', '.join(arg_strs)})"

            case _:
                raise InternalCompilerError(
                    f"Unknown expression type for codegen: {type(expr).__name__}"
                )


# =============================================================================
# 5. Generated-Code Whitelist Validator (RFC-0008 §3.9)
# =============================================================================

WHITELISTED_AST_NODES: frozenset[type] = frozenset(
    {
        ast.Module,
        ast.FunctionDef,
        ast.arguments,
        ast.arg,
        ast.Return,
        ast.Assign,
        ast.Expr,
        ast.If,
        ast.While,
        ast.Pass,
        ast.Break,
        ast.Continue,
        ast.Call,
        ast.Name,
        ast.Constant,
        ast.BinOp,
        ast.UnaryOp,
        ast.BoolOp,
        ast.Compare,
        ast.IfExp,  # permitted in prelude only
        ast.Load,
        ast.Store,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.Mod,
        ast.USub,
        ast.Not,
        ast.And,
        ast.Or,
        ast.Eq,
        ast.NotEq,
        ast.Lt,
        ast.LtE,
        ast.Gt,
        ast.GtE,
    }
)

ALLOWED_BUILTIN_CALLS: frozenset[str] = frozenset(
    {"__nx_show", "print", "isinstance", "float", "int", "input"}
)


def validate_generated_python(code: str) -> None:
    """Validate that generated Python AST adheres strictly to the safe node whitelist.

    Raises InternalCompilerError if code violates whitelist or contains disallowed nodes.
    """
    try:
        parsed = ast.parse(code)
    except Exception as exc:
        raise InternalCompilerError(
            f"Generated Python failed to parse: {exc}", assertion="ast.parse(code)"
        ) from exc

    for node in ast.walk(parsed):
        # 1. Node type must be whitelisted
        if type(node) not in WHITELISTED_AST_NODES:
            raise InternalCompilerError(
                f"Disallowed AST node '{type(node).__name__}' in generated Python",
                assertion="type(node) in WHITELISTED_AST_NODES",
            )

        # 2. Every Call target must be a simple Name (no method/attribute calls)
        if isinstance(node, ast.Call) and not isinstance(node.func, ast.Name):
            raise InternalCompilerError(
                f"Call target must be a simple Name, got '{type(node.func).__name__}'",
                assertion="isinstance(node.func, ast.Name)",
            )


def generate_python(program: Program) -> GeneratedCode:
    """Public helper to generate and validate Python source code from a Program AST."""
    gen = PythonGenerator()
    result = gen.generate(program)
    validate_generated_python(result.code)
    return result
