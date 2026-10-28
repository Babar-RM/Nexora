"""Tests for MiniLang v1 Lexer and Token implementations.

Governed by RFC-0001 §3.1, §3.1.1, RFC-0002 §3.4, and RFC-0004 §3.4.
"""

import pytest

from nexora.errors import Diagnostic, DiagnosticBag, LexerError, render
from nexora.lexer import Lexer, tokenize
from nexora.tokens import KEYWORDS, Token, TokenType


class TestTokensAndLexer:
    """Test suite covering lexical analysis and tokenization."""

    def test_lexer_empty_source(self) -> None:
        """Empty source produces a single EOF token at line 1, column 1."""
        tokens = Lexer("").tokenize()
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.EOF
        assert tokens[0].line == 1
        assert tokens[0].column == 1
        assert tokens[0].lexeme == ""

    def test_lexer_colon_token(self) -> None:
        """Colon ':' produces TokenType.COLON (RFC-0001 §3.1.1 amendment)."""
        tokens = tokenize(":")
        assert len(tokens) == 2
        assert tokens[0].type == TokenType.COLON
        assert tokens[0].lexeme == ":"
        assert tokens[0].line == 1
        assert tokens[0].column == 1
        assert tokens[1].type == TokenType.EOF

    def test_lexer_make_annotated_sequence(self) -> None:
        """'make x: int = 1;' produces expected token sequence (RFC-0001 §3.1.1)."""
        source = "make x: int = 1;"
        tokens = tokenize(source)
        expected_types = [
            TokenType.MAKE,
            TokenType.IDENT,
            TokenType.COLON,
            TokenType.IDENT,
            TokenType.EQUAL,
            TokenType.INT,
            TokenType.SEMICOLON,
            TokenType.EOF,
        ]
        assert [t.type for t in tokens] == expected_types
        assert tokens[1].lexeme == "x"
        assert tokens[3].lexeme == "int"
        assert tokens[5].value == 1

    def test_lexer_all_16_keywords(self) -> None:
        """All 16 MiniLang v1 keywords are recognized with exact TokenTypes."""
        expected_keywords = {
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
        assert KEYWORDS == expected_keywords

        source = " ".join(expected_keywords.keys())
        tokens = tokenize(source)
        assert len(tokens) == len(expected_keywords) + 1
        for i, (word, expected_type) in enumerate(expected_keywords.items()):
            assert tokens[i].type == expected_type
            assert tokens[i].lexeme == word

        # Boolean literal keywords carry boolean values
        yes_tok = tokenize("yes")[0]
        assert yes_tok.type == TokenType.YES
        assert yes_tok.value is True

        no_tok = tokenize("no")[0]
        assert no_tok.type == TokenType.NO
        assert no_tok.value is False

    def test_lexer_identifiers(self) -> None:
        """Identifiers match [A-Za-z_][A-Za-z0-9_]*."""
        source = "alpha _beta var_123 CamelCase __nx_runtime"
        tokens = tokenize(source)
        assert len(tokens) == 6
        assert all(t.type == TokenType.IDENT for t in tokens[:5])
        assert [t.lexeme for t in tokens[:5]] == [
            "alpha",
            "_beta",
            "var_123",
            "CamelCase",
            "__nx_runtime",
        ]

    def test_lexer_rejects_non_ascii_in_identifier(self) -> None:
        """Non-ASCII characters in identifier positions raise E1001 (RFC-0001 §3.1.1)."""
        with pytest.raises(LexerError) as exc_info:
            tokenize("make é = 1;")
        err = exc_info.value
        assert err.code == "E1001"
        assert err.line == 1
        assert err.column == 6
        assert "unexpected character 'é'" in err.message

        with pytest.raises(LexerError) as exc_info_2:
            tokenize("make x² = 2;")
        err2 = exc_info_2.value
        assert err2.code == "E1001"
        assert err2.line == 1
        assert err2.column == 7
        assert "unexpected character '²'" in err2.message

    def test_lexer_integer_literals(self) -> None:
        """Integer literals parse correctly to int values."""
        tokens = tokenize("0 42 1000000")
        assert [t.type for t in tokens[:3]] == [
            TokenType.INT,
            TokenType.INT,
            TokenType.INT,
        ]
        assert [t.value for t in tokens[:3]] == [0, 42, 1000000]

    def test_lexer_float_literals(self) -> None:
        """Float literals parse correctly to float values."""
        tokens = tokenize("3.14 0.5 120.001")
        assert [t.type for t in tokens[:3]] == [
            TokenType.FLOAT,
            TokenType.FLOAT,
            TokenType.FLOAT,
        ]
        assert [t.value for t in tokens[:3]] == [3.14, 0.5, 120.001]

    def test_lexer_string_literals_and_escapes(self) -> None:
        """Strings and valid escape sequences (\\n, \\t, \\\", \\\\) are correctly unescaped."""
        tokens = tokenize(
            r'"hello world" "tab\there" "quote\"" "slash\\" "line\nbreak"'
        )
        assert len(tokens) == 6
        values = [t.value for t in tokens[:5]]
        assert values == [
            "hello world",
            "tab\there",
            'quote"',
            "slash\\",
            "line\nbreak",
        ]

    def test_lexer_unterminated_string_at_newline(self) -> None:
        """Strings with raw newlines raise E1002 (RFC-0004 §3.4)."""
        source = 'make s = "hello\nworld";'
        with pytest.raises(LexerError) as exc_info:
            tokenize(source)
        err = exc_info.value
        assert err.code == "E1002"
        assert err.line == 1
        assert err.column == 10
        assert "unterminated string literal" in err.message
        assert err.hint == "strings must close on the same line"

    def test_lexer_unterminated_string_at_eof(self) -> None:
        """Unclosed strings reaching EOF raise E1002."""
        source = 'show("hello'
        with pytest.raises(LexerError) as exc_info:
            tokenize(source)
        err = exc_info.value
        assert err.code == "E1002"
        assert err.line == 1
        assert err.column == 6
        assert "unterminated string literal" in err.message

    def test_lexer_invalid_escape_sequence(self) -> None:
        """Invalid escape sequence raises E1003 (RFC-0004 §3.4)."""
        source = r'"invalid \q escape"'
        with pytest.raises(LexerError) as exc_info:
            tokenize(source)
        err = exc_info.value
        assert err.code == "E1003"
        assert err.line == 1
        assert err.column == 10  # points to backslash
        assert r"invalid escape sequence '\q'" in err.message
        assert 'valid escapes are \\n \\t \\" \\\\' in (err.hint or "")

    def test_lexer_operators_and_punctuation(self) -> None:
        """All operators and punctuation are tokenized correctly."""
        source = "+ - * / % == != < <= > >= = : ( ) { } , ;"
        tokens = tokenize(source)
        expected = [
            TokenType.PLUS,
            TokenType.MINUS,
            TokenType.STAR,
            TokenType.SLASH,
            TokenType.PERCENT,
            TokenType.EQUAL_EQUAL,
            TokenType.BANG_EQUAL,
            TokenType.LESS,
            TokenType.LESS_EQUAL,
            TokenType.GREATER,
            TokenType.GREATER_EQUAL,
            TokenType.EQUAL,
            TokenType.COLON,
            TokenType.LEFT_PAREN,
            TokenType.RIGHT_PAREN,
            TokenType.LEFT_BRACE,
            TokenType.RIGHT_BRACE,
            TokenType.COMMA,
            TokenType.SEMICOLON,
            TokenType.EOF,
        ]
        assert [t.type for t in tokens] == expected

    def test_lexer_unexpected_standalone_exclamation(self) -> None:
        """Standalone '!' raises E1001."""
        source = "make x = !yes;"
        with pytest.raises(LexerError) as exc_info:
            tokenize(source)
        err = exc_info.value
        assert err.code == "E1001"
        assert err.line == 1
        assert err.column == 10
        assert "unexpected character '!'" in err.message

    def test_lexer_comments_and_whitespace(self) -> None:
        """Comments '// ...' and whitespace are skipped while line tracking is preserved."""
        source = """// First line comment
make a = 10; // Inline comment
// Middle comment

make b = 20;
"""
        tokens = tokenize(source)
        token_lexemes = [t.lexeme for t in tokens if t.type != TokenType.EOF]
        assert token_lexemes == [
            "make",
            "a",
            "=",
            "10",
            ";",
            "make",
            "b",
            "=",
            "20",
            ";",
        ]

        # Check line positions
        make_a = tokens[0]
        assert make_a.line == 2
        assert make_a.column == 1

        make_b = tokens[5]
        assert make_b.line == 5
        assert make_b.column == 1

    def test_lexer_token_serialization(self) -> None:
        """Token.to_dict() returns JSON-serializable structure with line and column."""
        tok = Token(type=TokenType.INT, lexeme="42", value=42, line=3, column=5)
        d = tok.to_dict()
        assert d == {
            "type": "INT",
            "lexeme": "42",
            "value": 42,
            "line": 3,
            "column": 5,
        }

    def test_lexer_full_program(self) -> None:
        """Tokenize a complete MiniLang program without error."""
        source = """// Factorial function
task factorial(n: int): int {
    when (n <= 1) {
        give 1;
    }
    give n * factorial(n - 1);
}

make result = factorial(5);
show(result);
"""
        tokens = tokenize(source)
        assert tokens[-1].type == TokenType.EOF
        assert any(t.type == TokenType.TASK for t in tokens)
        assert any(t.type == TokenType.WHEN for t in tokens)
        assert any(t.type == TokenType.GIVE for t in tokens)
        assert any(t.type == TokenType.SHOW for t in tokens)

    def test_lexer_invalid_number_forms(self) -> None:
        """.5 and 5. are invalid numbers; both trigger E1001 on '.'."""
        with pytest.raises(LexerError) as exc_info:
            tokenize(".5")
        assert exc_info.value.code == "E1001"
        assert exc_info.value.column == 1
        assert "unexpected character '.'" in exc_info.value.message

        with pytest.raises(LexerError) as exc_info_2:
            tokenize("5.")
        assert exc_info_2.value.code == "E1001"
        assert exc_info_2.value.column == 2
        assert "unexpected character '.'" in exc_info_2.value.message

    def test_lexer_fixtures(self) -> None:
        """Verify valid and invalid fixture files."""
        from pathlib import Path

        fixtures_dir = Path(__file__).parent / "fixtures"

        # Valid fixtures
        for valid_file in (fixtures_dir / "valid").glob("*.mini"):
            content = valid_file.read_text(encoding="utf-8")
            tokens = tokenize(content)
            assert tokens[-1].type == TokenType.EOF

        # Invalid fixtures
        unexpected_char_file = fixtures_dir / "invalid" / "unexpected_char.mini"
        with pytest.raises(LexerError) as exc_info:
            tokenize(unexpected_char_file.read_text(encoding="utf-8"))
        assert exc_info.value.code == "E1001"

        unterminated_file = fixtures_dir / "invalid" / "unterminated_string.mini"
        with pytest.raises(LexerError) as exc_info_2:
            tokenize(unterminated_file.read_text(encoding="utf-8"))
        assert exc_info_2.value.code == "E1002"

        escape_file = fixtures_dir / "invalid" / "invalid_escape.mini"
        with pytest.raises(LexerError) as exc_info_3:
            tokenize(escape_file.read_text(encoding="utf-8"))
        assert exc_info_3.value.code == "E1003"


class TestErrorsAndDiagnostics:
    """Test suite covering diagnostic structures and rendering from RFC-0004."""

    def test_diagnostic_to_dict(self) -> None:
        """Diagnostic.to_dict() contains required fields."""
        diag = Diagnostic(
            phase="Lexical Error",
            code="E1001",
            severity="error",
            message="unexpected character '@'",
            line=2,
            column=5,
            length=1,
            hint="remove this character",
        )
        d = diag.to_dict()
        assert d["phase"] == "Lexical Error"
        assert d["code"] == "E1001"
        assert d["severity"] == "error"
        assert d["message"] == "unexpected character '@'"
        assert d["line"] == 2
        assert d["column"] == 5
        assert d["length"] == 1
        assert d["hint"] == "remove this character"

    def test_diagnostic_bag_collection_and_sorting(self) -> None:
        """DiagnosticBag collects, limits, and sorts diagnostics."""
        bag = DiagnosticBag()
        bag.error("E2002", "missing ';'", line=5, column=10)
        bag.warning("W4003", "unused variable", line=2, column=1)
        bag.error("E1001", "unexpected char", line=1, column=4)

        items = bag.items()
        assert len(items) == 3
        # Should be sorted by line: line 1, then line 2, then line 5
        assert [item.line for item in items] == [1, 2, 5]
        assert bag.has_errors is True

    def test_diagnostic_render_output(self) -> None:
        """render() formats CLI excerpt with line, column, caret and hint."""
        source = "make age = 20;\nshow(total);\n"
        diag = Diagnostic(
            phase="Semantic Error",
            code="E3001",
            severity="error",
            message="use of undeclared variable 'total'",
            line=2,
            column=6,
            length=5,
            hint="declare it first with 'make total = ...;'",
        )
        rendered = render(diag, source)
        assert "error[E3001]: use of undeclared variable 'total'" in rendered
        assert "--> line 2, column 6" in rendered
        assert "show(total);" in rendered
        assert "^^^^^" in rendered
        assert "hint: declare it first" in rendered
