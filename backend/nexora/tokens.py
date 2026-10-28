"""Token definitions and keyword tables for the Nexora compiler.

This module defines the TokenType enumeration, Token dataclass, and KEYWORDS
lookup dictionary governed by RFC-0001 §3.1 and §3.1.1.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any


class TokenType(Enum):
    """Enumeration of all lexical token types in MiniLang v1."""

    # Keywords (RFC-0001 §3.1)
    MAKE = auto()
    SHOW = auto()
    ASK = auto()
    WHEN = auto()
    OTHERWISE = auto()
    DURING = auto()
    TASK = auto()
    GIVE = auto()
    YES = auto()
    NO = auto()
    BOTH = auto()
    EITHER = auto()
    NOT = auto()
    EMPTY = auto()
    STOP = auto()
    SKIP = auto()

    # Literals
    INT = auto()
    FLOAT = auto()
    STRING = auto()

    # Identifiers
    IDENT = auto()

    # Arithmetic operators
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    PERCENT = auto()

    # Comparison operators
    EQUAL_EQUAL = auto()
    BANG_EQUAL = auto()
    LESS = auto()
    LESS_EQUAL = auto()
    GREATER = auto()
    GREATER_EQUAL = auto()

    # Assignment
    EQUAL = auto()

    # Punctuation (including COLON per RFC-0001 §3.1.1)
    COLON = auto()
    LEFT_PAREN = auto()
    RIGHT_PAREN = auto()
    LEFT_BRACE = auto()
    RIGHT_BRACE = auto()
    COMMA = auto()
    SEMICOLON = auto()

    # End of file
    EOF = auto()


KEYWORDS: dict[str, TokenType] = {
    "make": TokenType.MAKE,
    "show": TokenType.SHOW,
    "ask": TokenType.ASK,
    "when": TokenType.WHEN,
    "otherwise": TokenType.OTHERWISE,
    "during": TokenType.DURING,
    "task": TokenType.TASK,
    "give": TokenType.GIVE,
    "yes": TokenType.YES,
    "no": TokenType.NO,
    "both": TokenType.BOTH,
    "either": TokenType.EITHER,
    "not": TokenType.NOT,
    "empty": TokenType.EMPTY,
    "stop": TokenType.STOP,
    "skip": TokenType.SKIP,
}


@dataclass(frozen=True)
class Token:
    """Represents a single lexical token in MiniLang source code.

    Attributes:
        type: The category of token (TokenType).
        lexeme: The exact raw source string matching this token.
        value: Parsed literal value (e.g. int, float, str, bool), or None.
        line: 1-based source line where the token starts.
        column: 1-based source column where the token starts.
    """

    type: TokenType
    lexeme: str
    value: Any = None
    line: int = 1
    column: int = 1

    def to_dict(self) -> dict[str, Any]:
        """Convert the token to a JSON-serializable dictionary."""
        data: dict[str, Any] = {
            "type": self.type.name,
            "lexeme": self.lexeme,
            "line": self.line,
            "column": self.column,
        }
        if self.value is not None:
            data["value"] = self.value
        return data
