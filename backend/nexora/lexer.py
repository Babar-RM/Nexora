"""Lexer implementation for MiniLang v1.

This module converts raw source code into a stream of tokens according to
the lexical specification in RFC-0001 §3.1 and error handling in RFC-0004.
"""

from __future__ import annotations

from typing import Any

from .errors import LexerError
from .tokens import KEYWORDS, Token, TokenType


def _is_digit(ch: str) -> bool:
    """Check if character is an ASCII digit [0-9]."""
    return "0" <= ch <= "9"


def _is_alpha(ch: str) -> bool:
    """Check if character is an ASCII letter [a-zA-Z] or underscore."""
    return ("a" <= ch <= "z") or ("A" <= ch <= "Z") or ch == "_"


def _is_alnum(ch: str) -> bool:
    """Check if character is ASCII alphanumeric or underscore."""
    return _is_alpha(ch) or _is_digit(ch)


class Lexer:
    """Scans MiniLang source code into a sequence of Tokens.

    Fails fast on the first lexical error with a LexerError.
    """

    def __init__(self, source: str) -> None:
        """Initialize the Lexer with source text.

        Args:
            source: MiniLang source code as a string.
        """
        self._source: str = source
        self._length: int = len(source)
        self._start: int = 0
        self._current: int = 0
        self._line: int = 1
        self._column: int = 1
        self._tokens: list[Token] = []

    def tokenize(self) -> list[Token]:
        """Tokenize the entire source into a list of Tokens ending with EOF.

        Returns:
            A list of Token instances ending with an EOF token.

        Raises:
            LexerError: If an unexpected character, unterminated string,
                or invalid escape sequence is encountered.
        """
        while not self._is_at_end():
            self._start = self._current
            self._scan_token()

        # Append final EOF token (RFC-0002 §3.4)
        self._tokens.append(
            Token(
                type=TokenType.EOF,
                lexeme="",
                value=None,
                line=self._line,
                column=self._column,
            )
        )
        return self._tokens

    def _is_at_end(self) -> bool:
        """Return True if cursor has reached the end of source."""
        return self._current >= self._length

    def _advance(self) -> str:
        """Consume and return the current character, updating line and column."""
        ch = self._source[self._current]
        self._current += 1

        if ch == "\n":
            self._line += 1
            self._column = 1
        elif ch == "\r":
            # If \r\n, wait for \n to increment line; if standalone \r, increment
            if self._peek() == "\n":
                # Will increment line on the upcoming \n
                pass
            else:
                self._line += 1
                self._column = 1
        else:
            self._column += 1

        return ch

    def _peek(self) -> str:
        """Return current character without consuming it, or empty string if at end."""
        if self._is_at_end():
            return ""
        return self._source[self._current]

    def _peek_next(self) -> str:
        """Return next character without consuming it, or empty string if past end."""
        if self._current + 1 >= self._length:
            return ""
        return self._source[self._current + 1]

    def _match(self, expected: str) -> bool:
        """Consume current character if it matches expected."""
        if self._is_at_end():
            return False
        if self._source[self._current] != expected:
            return False
        self._advance()
        return True

    def _add_token(self, token_type: TokenType, value: Any = None) -> None:
        """Add a token with the current lexeme spanning from self._start to self._current."""
        lexeme = self._source[self._start : self._current]
        # Token starts at the column recorded before consuming its characters
        token_column = self._token_start_column
        token_line = self._token_start_line
        self._tokens.append(
            Token(
                type=token_type,
                lexeme=lexeme,
                value=value,
                line=token_line,
                column=token_column,
            )
        )

    def _scan_token(self) -> None:
        """Scan a single token or skip comments/whitespace."""
        self._token_start_line = self._line
        self._token_start_column = self._column

        ch = self._advance()

        # Whitespace
        if ch in (" ", "\t", "\r", "\n"):
            return

        # Comments or division
        if ch == "/":
            if self._match("/"):
                # Single-line comment: skip until newline or EOF
                while not self._is_at_end() and self._peek() not in ("\n", "\r"):
                    self._advance()
                return
            self._add_token(TokenType.SLASH)
            return

        # Single or double character operators
        if ch == "+":
            self._add_token(TokenType.PLUS)
            return
        if ch == "-":
            self._add_token(TokenType.MINUS)
            return
        if ch == "*":
            self._add_token(TokenType.STAR)
            return
        if ch == "%":
            self._add_token(TokenType.PERCENT)
            return
        if ch == ":":
            self._add_token(TokenType.COLON)
            return
        if ch == "(":
            self._add_token(TokenType.LEFT_PAREN)
            return
        if ch == ")":
            self._add_token(TokenType.RIGHT_PAREN)
            return
        if ch == "{":
            self._add_token(TokenType.LEFT_BRACE)
            return
        if ch == "}":
            self._add_token(TokenType.RIGHT_BRACE)
            return
        if ch == ",":
            self._add_token(TokenType.COMMA)
            return
        if ch == ";":
            self._add_token(TokenType.SEMICOLON)
            return

        if ch == "=":
            if self._match("="):
                self._add_token(TokenType.EQUAL_EQUAL)
            else:
                self._add_token(TokenType.EQUAL)
            return

        if ch == "!":
            if self._match("="):
                self._add_token(TokenType.BANG_EQUAL)
                return
            raise LexerError(
                message="unexpected character '!'",
                line=self._token_start_line,
                column=self._token_start_column,
                code="E1001",
                length=1,
            )

        if ch == "<":
            if self._match("="):
                self._add_token(TokenType.LESS_EQUAL)
            else:
                self._add_token(TokenType.LESS)
            return

        if ch == ">":
            if self._match("="):
                self._add_token(TokenType.GREATER_EQUAL)
            else:
                self._add_token(TokenType.GREATER)
            return

        # String literals
        if ch == '"':
            self._scan_string()
            return

        # Number literals
        if _is_digit(ch):
            self._scan_number()
            return

        # Identifiers and keywords
        if _is_alpha(ch):
            self._scan_identifier()
            return

        # If we reach here, it's an unrecognized or non-ASCII character (E1001)
        raise LexerError(
            message=f"unexpected character '{ch}'",
            line=self._token_start_line,
            column=self._token_start_column,
            code="E1001",
            length=1,
        )

    def _scan_string(self) -> None:
        """Scan a string literal with escape sequence validation."""
        chars: list[str] = []
        string_start_line = self._token_start_line
        string_start_column = self._token_start_column

        while not self._is_at_end() and self._peek() != '"':
            ch = self._peek()

            # Raw newlines are forbidden inside string literals (RFC-0001 §3.1, RFC-0004 E1002)
            if ch in ("\n", "\r"):
                raise LexerError(
                    message="unterminated string literal",
                    line=string_start_line,
                    column=string_start_column,
                    code="E1002",
                    length=max(1, self._column - string_start_column),
                    hint="strings must close on the same line",
                )

            if ch == "\\":
                esc_line = self._line
                esc_col = self._column
                self._advance()  # consume backslash

                if self._is_at_end():
                    raise LexerError(
                        message="unterminated string literal",
                        line=string_start_line,
                        column=string_start_column,
                        code="E1002",
                        length=max(1, self._column - string_start_column),
                        hint="strings must close on the same line",
                    )

                esc_ch = self._advance()
                if esc_ch == "n":
                    chars.append("\n")
                elif esc_ch == "t":
                    chars.append("\t")
                elif esc_ch == '"':
                    chars.append('"')
                elif esc_ch == "\\":
                    chars.append("\\")
                else:
                    # Invalid escape sequence (RFC-0004 E1003)
                    raise LexerError(
                        message=f"invalid escape sequence '\\{esc_ch}'",
                        line=esc_line,
                        column=esc_col,
                        code="E1003",
                        length=2,
                        hint='valid escapes are \\n \\t \\" \\\\',
                    )
            else:
                chars.append(self._advance())

        if self._is_at_end():
            raise LexerError(
                message="unterminated string literal",
                line=string_start_line,
                column=string_start_column,
                code="E1002",
                length=max(1, self._column - string_start_column),
                hint="strings must close on the same line",
            )

        # Consume closing quote
        self._advance()
        lexeme = self._source[self._start : self._current]
        value = "".join(chars)
        self._tokens.append(
            Token(
                type=TokenType.STRING,
                lexeme=lexeme,
                value=value,
                line=string_start_line,
                column=string_start_column,
            )
        )

    def _scan_number(self) -> None:
        """Scan integer or float literals."""
        while _is_digit(self._peek()):
            self._advance()

        # Check for fractional float part: . followed by digit
        if self._peek() == "." and _is_digit(self._peek_next()):
            # Consume the '.'
            self._advance()
            while _is_digit(self._peek()):
                self._advance()

            lexeme = self._source[self._start : self._current]
            self._tokens.append(
                Token(
                    type=TokenType.FLOAT,
                    lexeme=lexeme,
                    value=float(lexeme),
                    line=self._token_start_line,
                    column=self._token_start_column,
                )
            )
            return

        lexeme = self._source[self._start : self._current]
        self._tokens.append(
            Token(
                type=TokenType.INT,
                lexeme=lexeme,
                value=int(lexeme),
                line=self._token_start_line,
                column=self._token_start_column,
            )
        )

    def _scan_identifier(self) -> None:
        """Scan an identifier or keyword."""
        while _is_alnum(self._peek()):
            self._advance()

        lexeme = self._source[self._start : self._current]
        token_type = KEYWORDS.get(lexeme, TokenType.IDENT)

        value: Any = None
        if token_type == TokenType.YES:
            value = True
        elif token_type == TokenType.NO:
            value = False

        self._tokens.append(
            Token(
                type=token_type,
                lexeme=lexeme,
                value=value,
                line=self._token_start_line,
                column=self._token_start_column,
            )
        )


def tokenize(source: str) -> list[Token]:
    """Convenience function to tokenize MiniLang source code using Lexer.

    Args:
        source: MiniLang source code string.

    Returns:
        List of Token instances ending with EOF.
    """
    return Lexer(source).tokenize()
