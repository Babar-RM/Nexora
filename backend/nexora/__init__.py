"""Nexora compiler package."""

from .ast_nodes import (
    Block,
    Expr,
    Node,
    NodeTransformer,
    NodeVisitor,
    Program,
    Stmt,
    TaskDecl,
    dump,
    iter_children,
    node_to_dict,
    validate_ast,
)
from .errors import Diagnostic, DiagnosticBag, LexerError, NexoraError
from .lexer import Lexer, tokenize
from .parser import Parser, ParseResult, parse
from .semantic import SemanticAnalyzer, SemanticResult, analyze
from .symbols import (
    FunctionType,
    Scope,
    ScopeKind,
    Symbol,
    SymbolKind,
    SymbolTable,
    Type,
)
from .tokens import Token, TokenType

__all__ = [
    "Block",
    "Diagnostic",
    "DiagnosticBag",
    "Expr",
    "FunctionType",
    "Lexer",
    "LexerError",
    "NexoraError",
    "Node",
    "NodeTransformer",
    "NodeVisitor",
    "ParseResult",
    "Parser",
    "Program",
    "Scope",
    "ScopeKind",
    "SemanticAnalyzer",
    "SemanticResult",
    "Stmt",
    "Symbol",
    "SymbolKind",
    "SymbolTable",
    "TaskDecl",
    "Token",
    "TokenType",
    "Type",
    "analyze",
    "dump",
    "iter_children",
    "node_to_dict",
    "parse",
    "tokenize",
    "validate_ast",
]
