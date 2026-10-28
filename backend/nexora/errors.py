"""Diagnostics and error handling for the Nexora compiler pipeline.

This module defines the shared diagnostic data structures, exception classes,
diagnostic collection bags, and source code excerpt rendering utilities
governed by RFC-0004.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Diagnostic:
    """A compiler diagnostic representing an error or warning.

    Attributes:
        phase: The compiler phase producing the diagnostic (e.g., 'Lexical Error').
        code: Stable error/warning code (e.g., 'E1001').
        severity: 'error' or 'warning'.
        message: Human-readable diagnostic description.
        line: 1-based source line number, if applicable.
        column: 1-based source column number, if applicable.
        length: Length in characters of the offending source span.
        hint: Optional guidance or suggestion for remediation.
    """

    phase: str
    code: str
    severity: str
    message: str
    line: int | None = None
    column: int | None = None
    length: int = 1
    hint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert the diagnostic to a JSON-serializable dictionary."""
        data: dict[str, Any] = {
            "phase": self.phase,
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "line": self.line,
            "column": self.column,
            "length": self.length,
        }
        if self.hint is not None:
            data["hint"] = self.hint
        return data


class NexoraError(Exception):
    """Base exception for all Nexora compiler errors containing a Diagnostic."""

    def __init__(
        self,
        diagnostic_or_message: Diagnostic | str,
        line: int | None = None,
        column: int | None = None,
        phase: str = "Compile Error",
        code: str = "E0000",
        length: int = 1,
        hint: str | None = None,
    ) -> None:
        """Initialize NexoraError with either a Diagnostic instance or individual fields."""
        if isinstance(diagnostic_or_message, Diagnostic):
            self.diagnostic = diagnostic_or_message
        else:
            self.diagnostic = Diagnostic(
                phase=phase,
                code=code,
                severity="error",
                message=diagnostic_or_message,
                line=line,
                column=column,
                length=length,
                hint=hint,
            )
        super().__init__(self.diagnostic.message)

    @property
    def phase(self) -> str:
        """Return the compiler phase."""
        return self.diagnostic.phase

    @property
    def code(self) -> str:
        """Return the error code."""
        return self.diagnostic.code

    @property
    def line(self) -> int | None:
        """Return the line number."""
        return self.diagnostic.line

    @property
    def column(self) -> int | None:
        """Return the column number."""
        return self.diagnostic.column

    @property
    def message(self) -> str:
        """Return the error message."""
        return self.diagnostic.message

    @property
    def length(self) -> int:
        """Return the span length."""
        return self.diagnostic.length

    @property
    def hint(self) -> str | None:
        """Return the remediation hint if present."""
        return self.diagnostic.hint

    def to_dict(self) -> dict[str, Any]:
        """Convert the underlying diagnostic to a dictionary."""
        return self.diagnostic.to_dict()


class LexerError(NexoraError):
    """Raised when a lexical error is encountered during tokenization."""

    def __init__(
        self,
        message: str,
        line: int | None = None,
        column: int | None = None,
        code: str = "E1001",
        length: int = 1,
        hint: str | None = None,
    ) -> None:
        """Initialize a LexerError."""
        super().__init__(
            Diagnostic(
                phase="Lexical Error",
                code=code,
                severity="error",
                message=message,
                line=line,
                column=column,
                length=length,
                hint=hint,
            )
        )


class ParserError(NexoraError):
    """Raised when a syntax error is encountered during parsing."""

    def __init__(
        self,
        message: str,
        line: int | None = None,
        column: int | None = None,
        code: str = "E2001",
        length: int = 1,
        hint: str | None = None,
        recoverable: bool = True,
    ) -> None:
        """Initialize a ParserError."""
        self.recoverable = recoverable
        super().__init__(
            Diagnostic(
                phase="Syntax Error",
                code=code,
                severity="error",
                message=message,
                line=line,
                column=column,
                length=length,
                hint=hint,
            )
        )


class SemanticError(NexoraError):
    """Raised when a semantic or type error is encountered."""

    def __init__(
        self,
        message: str,
        line: int | None = None,
        column: int | None = None,
        code: str = "E3001",
        length: int = 1,
        hint: str | None = None,
        symbol: str | None = None,
    ) -> None:
        """Initialize a SemanticError."""
        self.symbol = symbol
        super().__init__(
            Diagnostic(
                phase="Semantic Error",
                code=code,
                severity="error",
                message=message,
                line=line,
                column=column,
                length=length,
                hint=hint,
            )
        )


class InternalCompilerError(Exception):
    """Raised when an internal compiler invariant is violated (a bug in Nexora)."""

    def __init__(self, message: str, assertion: str | None = None) -> None:
        """Initialize an InternalCompilerError."""
        self.assertion = assertion
        super().__init__(message)


class DiagnosticBag:
    """Accumulates diagnostics for a compiler phase with an upper limit."""

    MAX_ERRORS: int = 50

    def __init__(self) -> None:
        """Initialize an empty DiagnosticBag."""
        self._diagnostics: list[Diagnostic] = []
        self._stopped: bool = False

    def error(
        self,
        code: str,
        message: str,
        line: int | None = None,
        column: int | None = None,
        length: int = 1,
        hint: str | None = None,
        phase: str = "Compile Error",
    ) -> None:
        """Add an error diagnostic to the bag."""
        if self._stopped:
            return

        error_count = sum(1 for d in self._diagnostics if d.severity == "error")
        if error_count >= self.MAX_ERRORS:
            self._diagnostics.append(
                Diagnostic(
                    phase=phase,
                    code="E0000",
                    severity="error",
                    message=f"too many errors ({self.MAX_ERRORS}); stopping",
                )
            )
            self._stopped = True
            return

        self._diagnostics.append(
            Diagnostic(
                phase=phase,
                code=code,
                severity="error",
                message=message,
                line=line,
                column=column,
                length=length,
                hint=hint,
            )
        )

    def warning(
        self,
        code: str,
        message: str,
        line: int | None = None,
        column: int | None = None,
        length: int = 1,
        hint: str | None = None,
    ) -> None:
        """Add a warning diagnostic to the bag."""
        self._diagnostics.append(
            Diagnostic(
                phase="Warning",
                code=code,
                severity="warning",
                message=message,
                line=line,
                column=column,
                length=length,
                hint=hint,
            )
        )

    @property
    def has_errors(self) -> bool:
        """Return True if any error-level diagnostic has been recorded."""
        return any(d.severity == "error" for d in self._diagnostics)

    def items(self) -> list[Diagnostic]:
        """Return all diagnostics sorted by line and column."""
        return sorted(
            self._diagnostics,
            key=lambda d: (
                d.line if d.line is not None else -1,
                d.column if d.column is not None else -1,
            ),
        )


def render(diagnostic: Diagnostic, source: str) -> str:
    """Render a diagnostic into formatted CLI output with a source excerpt.

    Args:
        diagnostic: The diagnostic to render.
        source: The complete original source code.

    Returns:
        Formatted multi-line diagnostic string.
    """
    prefix = f"{diagnostic.severity}[{diagnostic.code}]: {diagnostic.message}"
    if diagnostic.line is None:
        lines = [prefix]
        if diagnostic.hint:
            lines.append(f"   = hint: {diagnostic.hint}")
        return "\n".join(lines)

    col = diagnostic.column if diagnostic.column is not None else 1
    loc_str = f"  --> line {diagnostic.line}, column {col}"

    source_lines = source.splitlines()
    line_idx = diagnostic.line - 1
    if 0 <= line_idx < len(source_lines):
        raw_line = source_lines[line_idx]
        # Replace tabs with 4 spaces for consistent column alignment
        expanded_line = raw_line.replace("\t", "    ")
        # Estimate expanded column if line had tabs
        col_offset = 0
        for i in range(min(col - 1, len(raw_line))):
            col_offset += 4 if raw_line[i] == "\t" else 1

        line_num_str = f"{diagnostic.line}"
        margin_width = max(len(line_num_str), 2)
        blank_margin = " " * margin_width

        indent = " " * col_offset
        carets = "^" * max(1, diagnostic.length)

        out_lines = [
            prefix,
            loc_str,
            f"{blank_margin} |",
            f" {diagnostic.line} | {expanded_line}",
            f"{blank_margin} | {indent}{carets}",
        ]
        if diagnostic.hint:
            out_lines.append(f"{blank_margin} = hint: {diagnostic.hint}")
        return "\n".join(out_lines)

    lines = [prefix, loc_str]
    if diagnostic.hint:
        lines.append(f"   = hint: {diagnostic.hint}")
    return "\n".join(lines)


# Error codes registry table as defined in RFC-0004 §3.4
CODES: dict[str, str] = {
    # Lexical — E1xxx
    "E1001": "Unexpected character",
    "E1002": "Unterminated string",
    "E1003": "Invalid escape sequence",
    # Syntax — E2xxx
    "E2001": "Unexpected token",
    "E2002": "Missing ';'",
    "E2003": "Unclosed delimiter",
    "E2004": "Invalid assignment target / form",
    "E2005": "Task declared in a nested position",
    "E2006": "Nesting too deep",
    "E2007": "Missing parentheses around condition",
    "E2008": "Missing/invalid parameter or type annotation",
    # Semantic — E3xxx
    "E3001": "Undeclared name",
    "E3002": "Redeclaration / shadowing",
    "E3003": "Type mismatch in initialization/assignment",
    "E3004": "Invalid operand types for operator",
    "E3005": "Condition is not bool",
    "E3006": "Wrong number of arguments",
    "E3007": "Call of a non-task name",
    "E3008": "Argument type mismatch",
    "E3009": "Assignment to a global inside a task",
    "E3010": "'give' outside a task",
    "E3011": "Return/give type mismatch",
    "E3012": "Missing give on some path",
    "E3013": "Void value used as a value",
    "E3014": "Unknown type name",
    "E3015": "Reserved name used",
    "E3016": "Duplicate task name or parameter",
    "E3017": "'stop' outside a loop",
    "E3018": "'skip' outside a loop",
    "E3019": "Invalid type for 'ask'",
    # Warnings — W4xxx
    "W4001": "Unreachable code after 'give'",
    "W4002": "Division or modulo by constant zero",
    "W4003": "Variable declared but never used",
    # Runtime — R5xxx
    "R5001": "Division or modulo by zero",
    "R5002": "Time limit exceeded",
    "R5003": "Recursion limit exceeded",
    "R5004": "Output limit exceeded",
    "R5005": "Other runtime failure of the generated program",
    "R5006": "Invalid 'ask' input",
}
