"""Symbol table and type system definitions for MiniLang v1.

Governed by RFC-0005, this module defines the static types, scopes, symbols,
and symbol table data structures used during semantic analysis.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class Type(Enum):
    """Enumeration of MiniLang types."""

    INT = "int"
    FLOAT = "float"
    STRING = "string"
    BOOL = "bool"
    EMPTY = "empty"
    VOID = "void"
    ERROR = "error"  # Poisoned type to suppress cascading diagnostics (RFC-0005 §3.1)

    def __str__(self) -> str:
        """Return the string representation of the type."""
        return self.value


@dataclass(frozen=True)
class FunctionType:
    """Represents a task signature with parameter types and a return type."""

    params: tuple[Type, ...]
    ret: Type  # Type.VOID for tasks without a declared return type

    def __str__(self) -> str:
        """Render function signature as (T1, T2) -> TRet."""
        params_str = ", ".join(p.value for p in self.params)
        return f"({params_str}) -> {self.ret.value}"


def is_numeric(t: Type) -> bool:
    """Return True if the type is int or float."""
    return t in (Type.INT, Type.FLOAT)


def is_assignable(target: Type, source: Type) -> bool:
    """Return True if source can be assigned/passed to target.

    Allows exact matches, int -> float widening, and suppresses errors if either is ERROR.
    """
    if target == Type.ERROR or source == Type.ERROR:
        return True
    if target == source:
        return True
    # Implicit int -> float widening (RFC-0001 §3.3, RFC-0005 §3.1)
    return target == Type.FLOAT and source == Type.INT


def type_from_name(name: str) -> Type | None:
    """Map type name string to Type enum, or None if unknown/unsupported."""
    # Note: 'void' is not accepted in user annotations in v1 (RFC-0005 §3.1)
    mapping = {
        "int": Type.INT,
        "float": Type.FLOAT,
        "string": Type.STRING,
        "bool": Type.BOOL,
    }
    return mapping.get(name)


def unary_result_type(op: str, operand: Type) -> Type | None:
    """Compute the static result type of a unary operation.

    Returns Type or None if the operation is invalid.
    """
    if operand == Type.ERROR:
        return Type.ERROR
    if op == "-":
        if is_numeric(operand):
            return operand
        return None
    if op == "not":
        if operand == Type.BOOL:
            return Type.BOOL
        return None
    if op == "float":
        if is_numeric(operand):
            return Type.FLOAT
        return None
    return None


def binary_result_type(op: str, left: Type, right: Type) -> Type | None:
    """Compute the static result type of a binary operation per RFC-0005 §3.2.

    Returns Type or None if the operation is invalid.
    """
    if left == Type.ERROR or right == Type.ERROR:
        return Type.ERROR

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

    # Relational: <, <=, >, >=
    if op in ("<", "<=", ">", ">="):
        if is_numeric(left) and is_numeric(right):
            return Type.BOOL
        if left == Type.STRING and right == Type.STRING:
            return Type.BOOL
        return None

    # Equality: ==, !=
    if op in ("==", "!="):
        if is_numeric(left) and is_numeric(right):
            return Type.BOOL
        if left == right and left in (Type.STRING, Type.BOOL, Type.EMPTY):
            return Type.BOOL
        return None

    # Logical: both, either
    if op in ("both", "either"):
        if left == Type.BOOL and right == Type.BOOL:
            return Type.BOOL
        return None

    return None


class ScopeKind(Enum):
    """Kinds of lexical scope in MiniLang."""

    GLOBAL = "global"
    TASK = "task"
    BLOCK = "block"


class SymbolKind(Enum):
    """Kinds of declared symbols."""

    VARIABLE = "variable"
    PARAMETER = "parameter"
    TASK = "task"


@dataclass
class Symbol:
    """A declared program entity in the symbol table."""

    name: str
    kind: SymbolKind
    type: Type | FunctionType
    line: int
    column: int
    scope_kind: ScopeKind
    order: int
    used: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert symbol to dictionary matching UI snapshot contract."""
        return {
            "name": self.name,
            "kind": self.kind.value,
            "type": str(self.type.value if isinstance(self.type, Type) else self.type),
            "scope": self.scope_kind.value,
            "line": self.line,
            "column": self.column,
        }


class Scope:
    """A single lexical scope holding symbol declarations and referencing a parent."""

    def __init__(self, kind: ScopeKind, parent: Scope | None = None) -> None:
        """Initialize a Scope."""
        self.kind: ScopeKind = kind
        self.parent: Scope | None = parent
        self.symbols: dict[str, Symbol] = {}


class SymbolTable:
    """Hierarchical scoped symbol table enforcing MiniLang scope rules."""

    def __init__(self) -> None:
        """Initialize an empty symbol table."""
        self._current: Scope = Scope(ScopeKind.GLOBAL, None)
        self._all_symbols: list[Symbol] = []
        self._next_order: int = 0

    @property
    def current(self) -> Scope:
        """Return the current active scope."""
        return self._current

    def push(self, kind: ScopeKind) -> Scope:
        """Push a new nested scope onto the scope stack."""
        self._current = Scope(kind=kind, parent=self._current)
        return self._current

    def pop(self) -> Scope:
        """Pop the current scope and return it."""
        if self._current.parent is None:
            raise RuntimeError("Cannot pop root global scope")
        popped = self._current
        self._current = self._current.parent
        return popped

    def declare(self, symbol: Symbol) -> bool:
        """Declare a symbol in the current scope.

        Returns False if the name is already visible in any enclosing scope (no shadowing).
        """
        # No shadowing rule (RFC-0005 §3.4 rule 2): declare fails if lookup finds symbol
        if self.lookup(symbol.name) is not None:
            return False

        symbol.order = self._next_order
        self._next_order += 1
        self._current.symbols[symbol.name] = symbol
        self._all_symbols.append(symbol)
        return True

    def lookup(self, name: str) -> Symbol | None:
        """Resolve a name by walking outward through the scope chain."""
        scope: Scope | None = self._current
        while scope is not None:
            if name in scope.symbols:
                return scope.symbols[name]
            scope = scope.parent
        return None

    def lookup_current(self, name: str) -> Symbol | None:
        """Check if name is declared directly in the innermost scope."""
        return self._current.symbols.get(name)

    @property
    def in_task(self) -> bool:
        """Return True if currently inside a task body."""
        scope: Scope | None = self._current
        while scope is not None:
            if scope.kind == ScopeKind.TASK:
                return True
            scope = scope.parent
        return False

    def snapshot(self) -> list[dict[str, Any]]:
        """Return all declared symbols in declaration order for UI inspection."""
        return [sym.to_dict() for sym in self._all_symbols]
