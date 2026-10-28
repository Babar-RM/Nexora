"""Recursive-descent parser implementation for MiniLang v1.

Governed by RFC-0001 §3.2, RFC-0002 §3.4, RFC-0003, and RFC-0004 §3.8.2.
Constructs the complete Abstract Syntax Tree (Program) from a stream of Tokens,
with panic-mode error recovery reporting stable E2xxx syntax diagnostics.
"""

from __future__ import annotations

from dataclasses import dataclass

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
    Param,
    Program,
    ShowStmt,
    SkipStmt,
    Stmt,
    StopStmt,
    StringLiteral,
    TaskDecl,
    TypeRef,
    UnaryExpr,
    WhenStmt,
)
from .errors import Diagnostic, DiagnosticBag
from .tokens import Token, TokenType

# Maximum AST nesting depth limit before reporting E2006 (RFC-0002 §3.9)
MAX_NESTING_DEPTH: int = 200

# Tokens that begin a statement for panic-mode synchronization (RFC-0004 §3.8.2)
STATEMENT_STARTERS: frozenset[TokenType] = frozenset(
    {
        TokenType.MAKE,
        TokenType.WHEN,
        TokenType.DURING,
        TokenType.TASK,
        TokenType.GIVE,
        TokenType.SHOW,
        TokenType.ASK,
        TokenType.STOP,
        TokenType.SKIP,
    }
)


@dataclass
class ParseResult:
    """The result of parsing a MiniLang token stream."""

    program: Program
    diagnostics: list[Diagnostic]

    @property
    def ok(self) -> bool:
        """Return True if parsing succeeded with no error-level diagnostics."""
        return not any(d.severity == "error" for d in self.diagnostics)


class Parser:
    """Recursive-descent parser for MiniLang with panic-mode recovery."""

    def __init__(self, tokens: list[Token]) -> None:
        """Initialize the Parser with a list of tokens.

        Args:
            tokens: Sequence of Token instances ending with EOF.
        """
        self._tokens: list[Token] = tokens
        self._current: int = 0
        self._diagnostics: DiagnosticBag = DiagnosticBag()
        self._panic_mode: bool = False
        self._nesting_depth: int = 0

    def parse(self) -> ParseResult:
        """Parse all tokens into a Program AST node with collected diagnostics.

        Returns:
            ParseResult containing the Program AST and any syntax diagnostics.
        """
        body: list[Stmt | TaskDecl] = []

        while not self._is_at_end():
            if self._check(TokenType.TASK):
                decl = self._parse_task_decl()
                if decl is not None:
                    body.append(decl)
            else:
                stmt = self._parse_statement()
                if stmt is not None:
                    body.append(stmt)

        program = Program(body=body, line=1, column=1)
        return ParseResult(program=program, diagnostics=self._diagnostics.items())

    # =========================================================================
    # Token Navigation and Inspection Helpers
    # =========================================================================

    def _peek(self) -> Token:
        """Return current token without advancing."""
        return self._tokens[self._current]

    def _previous(self) -> Token:
        """Return the most recently consumed token."""
        return self._tokens[self._current - 1]

    def _is_at_end(self) -> bool:
        """Return True if current token is EOF."""
        return self._peek().type == TokenType.EOF

    def _advance(self) -> Token:
        """Consume and return current token."""
        if not self._is_at_end():
            self._current += 1
        return self._previous()

    def _check(self, token_type: TokenType) -> bool:
        """Return True if current token matches token_type."""
        if self._is_at_end():
            return False
        return self._peek().type == token_type

    def _check_next(self, token_type: TokenType) -> bool:
        """Return True if the token after current matches token_type."""
        if self._current + 1 >= len(self._tokens):
            return False
        return self._tokens[self._current + 1].type == token_type

    def _match(self, *token_types: TokenType) -> bool:
        """Advance and return True if current token matches any given type."""
        for tt in token_types:
            if self._check(tt):
                self._advance()
                return True
        return False

    def _error(
        self,
        code: str,
        message: str,
        line: int | None = None,
        column: int | None = None,
        length: int = 1,
        hint: str | None = None,
    ) -> None:
        """Record a syntax error diagnostic unless currently suppressing in panic mode."""
        if self._panic_mode:
            return
        self._panic_mode = True
        self._diagnostics.error(
            phase="Syntax Error",
            code=code,
            message=message,
            line=line,
            column=column,
            length=length,
            hint=hint,
        )

    def _synchronize(self) -> None:
        """Panic-mode recovery: discard tokens until a synchronization point (RFC-0004 §3.8.2)."""
        self._panic_mode = False

        if not self._is_at_end():
            self._advance()

        while not self._is_at_end():
            # Stop if we just passed a semicolon
            if self._previous().type == TokenType.SEMICOLON:
                return

            # Stop if the next token starts a new statement or closes a block
            if (
                self._peek().type in STATEMENT_STARTERS
                or self._peek().type == TokenType.RIGHT_BRACE
            ):
                return

            self._advance()

    def _consume_semicolon(self) -> bool:
        """Consume expected ';' or report E2002 at end of previous token (RFC-0004 §3.2)."""
        if self._match(TokenType.SEMICOLON):
            return True

        prev = self._previous()
        end_col = prev.column + len(prev.lexeme)

        self._error(
            code="E2002",
            message="expected ';' after statement",
            line=prev.line,
            column=end_col,
            length=1,
        )

        # If next token is on a later line or starts a new statement, recover without discarding
        if self._peek().line > prev.line or self._peek().type in STATEMENT_STARTERS:
            self._panic_mode = False
            return False

        self._synchronize()
        return False

    # =========================================================================
    # Declarations and Statements (RFC-0001 §3.2)
    # =========================================================================

    def _parse_task_decl(self) -> TaskDecl | None:
        """Parse 'task' IDENT '(' [ params ] ')' [ ':' typeName ] block."""
        task_token = self._advance()  # Consume 'task'
        line = task_token.line
        column = task_token.column

        if not self._check(TokenType.IDENT):
            self._error(
                code="E2001",
                message=f"expected task name, found '{self._peek().lexeme}'",
                line=self._peek().line,
                column=self._peek().column,
            )
            self._synchronize()
            return None

        name_token = self._advance()
        name = name_token.lexeme

        if not self._match(TokenType.LEFT_PAREN):
            self._error(
                code="E2001",
                message=f"expected '(' after task name, found '{self._peek().lexeme}'",
                line=self._peek().line,
                column=self._peek().column,
            )
            self._synchronize()
            return None

        params: list[Param] = []
        if not self._check(TokenType.RIGHT_PAREN):
            while True:
                if not self._check(TokenType.IDENT):
                    self._error(
                        code="E2008",
                        message=f"expected parameter name, found '{self._peek().lexeme}'",
                        line=self._peek().line,
                        column=self._peek().column,
                    )
                    self._synchronize()
                    return None

                param_name_tok = self._advance()

                if not self._match(TokenType.COLON):
                    self._error(
                        code="E2008",
                        message=f"expected ':' and a type after parameter '{param_name_tok.lexeme}'",
                        line=param_name_tok.line,
                        column=param_name_tok.column + len(param_name_tok.lexeme),
                    )
                    self._synchronize()
                    return None

                if not self._check(TokenType.IDENT):
                    self._error(
                        code="E2008",
                        message=f"expected type after ':', found '{self._peek().lexeme}'",
                        line=self._peek().line,
                        column=self._peek().column,
                    )
                    self._synchronize()
                    return None

                type_tok = self._advance()
                tref = TypeRef(
                    type_tok.lexeme, line=type_tok.line, column=type_tok.column
                )
                params.append(
                    Param(
                        param_name_tok.lexeme,
                        tref,
                        line=param_name_tok.line,
                        column=param_name_tok.column,
                    )
                )

                if not self._match(TokenType.COMMA):
                    break

        if not self._match(TokenType.RIGHT_PAREN):
            self._error(
                code="E2001",
                message=f"expected ')' after task parameters, found '{self._peek().lexeme}'",
                line=self._peek().line,
                column=self._peek().column,
            )
            self._synchronize()
            return None

        return_type: TypeRef | None = None
        if self._match(TokenType.COLON):
            if not self._check(TokenType.IDENT):
                self._error(
                    code="E2008",
                    message=f"expected return type after ':', found '{self._peek().lexeme}'",
                    line=self._peek().line,
                    column=self._peek().column,
                )
                self._synchronize()
                return None
            ret_type_tok = self._advance()
            return_type = TypeRef(
                ret_type_tok.lexeme, line=ret_type_tok.line, column=ret_type_tok.column
            )

        if not self._check(TokenType.LEFT_BRACE):
            self._error(
                code="E2001",
                message=f"expected '{{' before task body, found '{self._peek().lexeme}'",
                line=self._peek().line,
                column=self._peek().column,
            )
            self._synchronize()
            return None

        body = self._parse_block()
        return TaskDecl(
            name=name,
            params=params,
            return_type=return_type,
            body=body,
            line=line,
            column=column,
        )

    def _parse_statement(self) -> Stmt | None:
        """Parse a single statement according to RFC-0001 §3.2."""
        if self._match(TokenType.MAKE):
            return self._parse_make_stmt()
        if self._match(TokenType.WHEN):
            return self._parse_when_stmt()
        if self._match(TokenType.DURING):
            return self._parse_during_stmt()
        if self._match(TokenType.GIVE):
            return self._parse_give_stmt()
        if self._match(TokenType.SHOW):
            return self._parse_show_stmt()
        if self._match(TokenType.ASK):
            return self._parse_ask_stmt()
        if self._match(TokenType.STOP):
            return self._parse_stop_stmt()
        if self._match(TokenType.SKIP):
            return self._parse_skip_stmt()
        if self._check(TokenType.LEFT_BRACE):
            return self._parse_block()
        if self._check(TokenType.TASK):
            # Task declared in a nested position (RFC-0001 §3.2, RFC-0004 E2005)
            tok = self._peek()
            self._error(
                code="E2005",
                message="tasks can only be declared at the top level",
                line=tok.line,
                column=tok.column,
            )
            self._synchronize()
            return None

        # Lookahead 1 for assignStmt vs exprStmt (RFC-0001 §3.2)
        if self._check(TokenType.IDENT) and self._check_next(TokenType.EQUAL):
            return self._parse_assign_stmt()

        return self._parse_expr_stmt()

    def _parse_make_stmt(self) -> MakeStmt | None:
        """Parse 'make' IDENT [ ':' typeName ] '=' expression ';'."""
        keyword_token = self._previous()
        line = keyword_token.line
        column = keyword_token.column

        if not self._check(TokenType.IDENT):
            self._error(
                code="E2001",
                message=f"expected variable name after 'make', found '{self._peek().lexeme}'",
                line=self._peek().line,
                column=self._peek().column,
            )
            self._synchronize()
            return None

        name_tok = self._advance()
        name = name_tok.lexeme

        declared_type: TypeRef | None = None
        if self._match(TokenType.COLON):
            if not self._check(TokenType.IDENT):
                self._error(
                    code="E2008",
                    message=f"expected type name after ':', found '{self._peek().lexeme}'",
                    line=self._peek().line,
                    column=self._peek().column,
                )
                self._synchronize()
                return None
            t_tok = self._advance()
            declared_type = TypeRef(t_tok.lexeme, line=t_tok.line, column=t_tok.column)

        if not self._match(TokenType.EQUAL):
            self._error(
                code="E2001",
                message=f"expected '=' in 'make' statement, found '{self._peek().lexeme}'",
                line=self._peek().line,
                column=self._peek().column,
            )
            self._synchronize()
            return None

        initializer = self._parse_expression()
        self._consume_semicolon()
        return MakeStmt(
            name=name,
            declared_type=declared_type,
            initializer=initializer,
            line=line,
            column=column,
        )

    def _parse_assign_stmt(self) -> AssignStmt:
        """Parse IDENT '=' expression ';'."""
        name_tok = self._advance()  # IDENT
        self._advance()  # '='

        value = self._parse_expression()
        self._consume_semicolon()
        return AssignStmt(
            name=name_tok.lexeme,
            value=value,
            line=name_tok.line,
            column=name_tok.column,
        )

    def _parse_when_stmt(self) -> WhenStmt:
        """Parse 'when' '(' expression ')' block [ 'otherwise' ( whenStmt | block ) ]."""
        when_tok = self._previous()
        line = when_tok.line
        column = when_tok.column

        if not self._match(TokenType.LEFT_PAREN):
            self._error(
                code="E2007",
                message="expected '(' after 'when'",
                line=self._peek().line,
                column=self._peek().column,
            )

        condition = self._parse_expression()

        if not self._match(TokenType.RIGHT_PAREN):
            self._error(
                code="E2001",
                message=f"expected ')' after condition, found '{self._peek().lexeme}'",
                line=self._peek().line,
                column=self._peek().column,
            )

        then_block = self._parse_block()

        else_branch: Block | WhenStmt | None = None
        if self._match(TokenType.OTHERWISE):
            if self._match(TokenType.WHEN):
                else_branch = self._parse_when_stmt()
            elif self._check(TokenType.LEFT_BRACE):
                else_branch = self._parse_block()
            else:
                self._error(
                    code="E2001",
                    message=f"expected '{{' or 'when' after 'otherwise', found '{self._peek().lexeme}'",
                    line=self._peek().line,
                    column=self._peek().column,
                )
                self._synchronize()

        return WhenStmt(
            condition=condition,
            then_block=then_block,
            else_branch=else_branch,
            line=line,
            column=column,
        )

    def _parse_during_stmt(self) -> DuringStmt:
        """Parse 'during' '(' expression ')' block."""
        during_tok = self._previous()
        line = during_tok.line
        column = during_tok.column

        if not self._match(TokenType.LEFT_PAREN):
            self._error(
                code="E2007",
                message="expected '(' after 'during'",
                line=self._peek().line,
                column=self._peek().column,
            )

        condition = self._parse_expression()

        if not self._match(TokenType.RIGHT_PAREN):
            self._error(
                code="E2001",
                message=f"expected ')' after condition, found '{self._peek().lexeme}'",
                line=self._peek().line,
                column=self._peek().column,
            )

        body = self._parse_block()
        return DuringStmt(condition=condition, body=body, line=line, column=column)

    def _parse_give_stmt(self) -> GiveStmt:
        """Parse 'give' [ expression ] ';'."""
        give_tok = self._previous()
        line = give_tok.line
        column = give_tok.column

        value: Expr | None = None
        if not self._check(TokenType.SEMICOLON):
            value = self._parse_expression()

        self._consume_semicolon()
        return GiveStmt(value=value, line=line, column=column)

    def _parse_show_stmt(self) -> ShowStmt:
        """Parse 'show' '(' expression ')' ';'."""
        show_tok = self._previous()
        line = show_tok.line
        column = show_tok.column

        if not self._match(TokenType.LEFT_PAREN):
            self._error(
                code="E2001",
                message=f"expected '(' after 'show', found '{self._peek().lexeme}'",
                line=self._peek().line,
                column=self._peek().column,
            )

        value = self._parse_expression()

        if not self._match(TokenType.RIGHT_PAREN):
            self._error(
                code="E2001",
                message=f"expected ')' after expression, found '{self._peek().lexeme}'",
                line=self._peek().line,
                column=self._peek().column,
            )

        self._consume_semicolon()
        return ShowStmt(value=value, line=line, column=column)

    def _parse_ask_stmt(self) -> AskStmt | None:
        """Parse 'ask' IDENT ':' typeName ';'."""
        ask_tok = self._previous()
        line = ask_tok.line
        column = ask_tok.column

        if not self._check(TokenType.IDENT):
            self._error(
                code="E2001",
                message=f"expected variable name after 'ask', found '{self._peek().lexeme}'",
                line=self._peek().line,
                column=self._peek().column,
            )
            self._synchronize()
            return None

        name_tok = self._advance()

        if not self._match(TokenType.COLON):
            self._error(
                code="E2008",
                message=f"expected ':' and a type after variable '{name_tok.lexeme}'",
                line=name_tok.line,
                column=name_tok.column + len(name_tok.lexeme),
            )
            self._synchronize()
            return None

        if not self._check(TokenType.IDENT):
            self._error(
                code="E2008",
                message=f"expected type name after ':', found '{self._peek().lexeme}'",
                line=self._peek().line,
                column=self._peek().column,
            )
            self._synchronize()
            return None

        type_tok = self._advance()
        tref = TypeRef(type_tok.lexeme, line=type_tok.line, column=type_tok.column)
        self._consume_semicolon()
        return AskStmt(name=name_tok.lexeme, type_ref=tref, line=line, column=column)

    def _parse_stop_stmt(self) -> StopStmt:
        """Parse 'stop' ';'."""
        stop_tok = self._previous()
        self._consume_semicolon()
        return StopStmt(line=stop_tok.line, column=stop_tok.column)

    def _parse_skip_stmt(self) -> SkipStmt:
        """Parse 'skip' ';'."""
        skip_tok = self._previous()
        self._consume_semicolon()
        return SkipStmt(line=skip_tok.line, column=skip_tok.column)

    def _parse_expr_stmt(self) -> ExprStmt:
        """Parse expression ';'."""
        expr = self._parse_expression()

        # Reject assignment expression: assignment is a statement (RFC-0001 §3.2, RFC-0004 E2004)
        if self._check(TokenType.EQUAL):
            eq_tok = self._advance()
            self._error(
                code="E2004",
                message="assignment is a statement, not an expression",
                line=eq_tok.line,
                column=eq_tok.column,
            )

        self._consume_semicolon()
        return ExprStmt(expression=expr, line=expr.line, column=expr.column)

    def _parse_block(self) -> Block:
        """Parse '{' { statement } '}' with nesting depth checking."""
        if not self._match(TokenType.LEFT_BRACE):
            tok = self._peek()
            self._error(
                code="E2001",
                message=f"expected '{{' to open block, found '{tok.lexeme}'",
                line=tok.line,
                column=tok.column,
            )
            return Block(statements=[], line=tok.line, column=tok.column)

        open_brace = self._previous()
        line = open_brace.line
        column = open_brace.column

        self._nesting_depth += 1
        if self._nesting_depth > MAX_NESTING_DEPTH:
            self._error(
                code="E2006",
                message=f"program is nested too deeply (limit {MAX_NESTING_DEPTH})",
                line=line,
                column=column,
            )

        statements: list[Stmt] = []
        while not self._check(TokenType.RIGHT_BRACE) and not self._is_at_end():
            stmt = self._parse_statement()
            if stmt is not None:
                statements.append(stmt)

        self._nesting_depth -= 1

        if not self._match(TokenType.RIGHT_BRACE):
            # Unclosed delimiter (RFC-0004 E2003)
            self._error(
                code="E2003",
                message=f"expected '}}' to close block opened at line {line}",
                line=line,
                column=column,
            )

        return Block(statements=statements, line=line, column=column)

    # =========================================================================
    # Expressions (Precedence climbing per RFC-0001 §3.2)
    # =========================================================================

    def _parse_expression(self) -> Expr:
        """Parse expression: lowest precedence 'either'."""
        expr = self._parse_either()
        if self._check(TokenType.EQUAL):
            eq_tok = self._advance()
            self._error(
                code="E2004",
                message="assignment is a statement, not an expression",
                line=eq_tok.line,
                column=eq_tok.column,
            )
            # Parse right-hand side so parsing continues
            self._parse_expression()
        return expr

    def _parse_either(self) -> Expr:
        """Parse eitherExpr: bothExpr { 'either' bothExpr }."""
        expr = self._parse_both()

        while self._match(TokenType.EITHER):
            op_tok = self._previous()
            right = self._parse_both()
            expr = BinaryExpr(
                op="either",
                left=expr,
                right=right,
                line=op_tok.line,
                column=op_tok.column,
            )

        return expr

    def _parse_both(self) -> Expr:
        """Parse bothExpr: notExpr { 'both' notExpr }."""
        expr = self._parse_not()

        while self._match(TokenType.BOTH):
            op_tok = self._previous()
            right = self._parse_not()
            expr = BinaryExpr(
                op="both",
                left=expr,
                right=right,
                line=op_tok.line,
                column=op_tok.column,
            )

        return expr

    def _parse_not(self) -> Expr:
        """Parse notExpr: 'not' notExpr | equality."""
        if self._match(TokenType.NOT):
            op_tok = self._previous()
            operand = self._parse_not()
            return UnaryExpr(
                op="not", operand=operand, line=op_tok.line, column=op_tok.column
            )

        return self._parse_equality()

    def _parse_equality(self) -> Expr:
        """Parse equality: comparison { ('==' | '!=') comparison }."""
        expr = self._parse_comparison()

        while self._match(TokenType.EQUAL_EQUAL, TokenType.BANG_EQUAL):
            op_tok = self._previous()
            op = "==" if op_tok.type == TokenType.EQUAL_EQUAL else "!="
            right = self._parse_comparison()
            expr = BinaryExpr(
                op=op, left=expr, right=right, line=op_tok.line, column=op_tok.column
            )

        return expr

    def _parse_comparison(self) -> Expr:
        """Parse comparison: term { ('<' | '<=' | '>' | '>=') term }."""
        expr = self._parse_term()

        while self._match(
            TokenType.LESS,
            TokenType.LESS_EQUAL,
            TokenType.GREATER,
            TokenType.GREATER_EQUAL,
        ):
            op_tok = self._previous()
            right = self._parse_term()
            expr = BinaryExpr(
                op=op_tok.lexeme,
                left=expr,
                right=right,
                line=op_tok.line,
                column=op_tok.column,
            )

        return expr

    def _parse_term(self) -> Expr:
        """Parse term: factor { ('+' | '-') factor }."""
        expr = self._parse_factor()

        while self._match(TokenType.PLUS, TokenType.MINUS):
            op_tok = self._previous()
            right = self._parse_factor()
            expr = BinaryExpr(
                op=op_tok.lexeme,
                left=expr,
                right=right,
                line=op_tok.line,
                column=op_tok.column,
            )

        return expr

    def _parse_factor(self) -> Expr:
        """Parse factor: unary { ('*' | '/' | '%') unary }."""
        expr = self._parse_unary()

        while self._match(TokenType.STAR, TokenType.SLASH, TokenType.PERCENT):
            op_tok = self._previous()
            right = self._parse_unary()
            expr = BinaryExpr(
                op=op_tok.lexeme,
                left=expr,
                right=right,
                line=op_tok.line,
                column=op_tok.column,
            )

        return expr

    def _parse_unary(self) -> Expr:
        """Parse unary: '-' unary | call."""
        if self._match(TokenType.MINUS):
            op_tok = self._previous()
            operand = self._parse_unary()
            return UnaryExpr(
                op="-", operand=operand, line=op_tok.line, column=op_tok.column
            )

        return self._parse_call()

    def _parse_call(self) -> Expr:
        """Parse call: IDENT '(' [ arguments ] ')' | primary."""
        if self._check(TokenType.IDENT) and self._check_next(TokenType.LEFT_PAREN):
            ident_tok = self._advance()
            self._advance()  # consume '('

            args: list[Expr] = []
            if not self._check(TokenType.RIGHT_PAREN):
                while True:
                    args.append(self._parse_expression())
                    if not self._match(TokenType.COMMA):
                        break

            if not self._match(TokenType.RIGHT_PAREN):
                self._error(
                    code="E2001",
                    message=f"expected ')' after arguments, found '{self._peek().lexeme}'",
                    line=self._peek().line,
                    column=self._peek().column,
                )

            return CallExpr(
                callee=ident_tok.lexeme,
                args=args,
                line=ident_tok.line,
                column=ident_tok.column,
            )

        return self._parse_primary()

    def _parse_primary(self) -> Expr:
        """Parse primary literals, identifiers, or parenthesized expressions."""
        if self._match(TokenType.INT):
            tok = self._previous()
            return IntLiteral(value=int(tok.value), line=tok.line, column=tok.column)

        if self._match(TokenType.FLOAT):
            tok = self._previous()
            return FloatLiteral(
                value=float(tok.value), line=tok.line, column=tok.column
            )

        if self._match(TokenType.STRING):
            tok = self._previous()
            return StringLiteral(value=str(tok.value), line=tok.line, column=tok.column)

        if self._match(TokenType.YES):
            tok = self._previous()
            return BoolLiteral(value=True, line=tok.line, column=tok.column)

        if self._match(TokenType.NO):
            tok = self._previous()
            return BoolLiteral(value=False, line=tok.line, column=tok.column)

        if self._match(TokenType.EMPTY):
            tok = self._previous()
            return EmptyLiteral(line=tok.line, column=tok.column)

        if self._match(TokenType.IDENT):
            tok = self._previous()
            return Identifier(name=tok.lexeme, line=tok.line, column=tok.column)

        if self._match(TokenType.LEFT_PAREN):
            expr = self._parse_expression()
            if not self._match(TokenType.RIGHT_PAREN):
                self._error(
                    code="E2001",
                    message=f"expected ')' after expression, found '{self._peek().lexeme}'",
                    line=self._peek().line,
                    column=self._peek().column,
                )
            # Parenthesized expressions produce no wrapper node (RFC-0003 §3.2)
            return expr

        # Unexpected token (E2001)
        tok = self._peek()
        self._error(
            code="E2001",
            message=f"expected an expression, found '{tok.lexeme or tok.type.name}'",
            line=tok.line,
            column=tok.column,
        )
        # Advance to avoid infinite loop
        self._advance()
        return IntLiteral(0, line=tok.line, column=tok.column)


def parse(tokens: list[Token]) -> ParseResult:
    """Convenience function to parse a token sequence into a Program AST and diagnostics.

    Args:
        tokens: Sequence of Token instances ending with EOF.

    Returns:
        ParseResult containing Program AST and diagnostics.
    """
    return Parser(tokens).parse()
