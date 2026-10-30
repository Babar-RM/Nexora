# Nexora: MiniLang → Python Source-to-Source Compiler

[![CI](https://img.shields.io/badge/build-passing-brightgreen)](#)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![Compiler-Core](https://img.shields.io/badge/dependencies-std--lib--only-success)](#)
[![Code-Style](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Tests](https://img.shields.io/badge/tests-174%20passed-brightgreen)](#)

**Nexora** is a high-assurance source-to-source compiler (transpiler) that translates programs written in **MiniLang**, a custom statically-typed programming language, into clean, idiomatic **Python 3.10+** code.

It is deliberately engineered as a *real* compiler rather than a regex or macro replacer. Keyword-to-Python textual substitution is strictly forbidden. Translation traverses an isolated, formal multi-stage compilation pipeline built entirely on standard library fundamentals.

---

## 1. Compiler Pipeline Architecture

Nexora enforces strict phase isolation, a one-way unidirectional dependency chain, zero global mutable state, and position-preserving diagnostics:

```
MiniLang source (.mini)
  │
  ▼
[1] Lexer (tokens.py, lexer.py)
      • Converts source text into strongly-typed Token stream
      • Enforces ASCII-only identifiers and tracks 1-based (line, column) positions
  │
  ▼
[2] Recursive-Descent Parser (parser.py, ast_nodes.py)
      • Builds Abstract Syntax Tree (AST) using explicit precedence climbing
      • Recovers via panic-mode synchronization to report multiple syntax errors
  │
  ▼
[3] Semantic Analysis & Type Checker (symbols.py, semantic.py)
      • Two-pass symbol resolution, task hoisting, and non-shadowing scope checks
      • Static type checking with implicit int -> float widening and error poisoning
  │
  ▼
[4] Intermediate Representation (IR / TAC) (ir.py)
      • Lowers AST into Linear Three-Address Code (TAC) and Basic-Block CFGs
      • Verified by strict TAC validator and reference TAC Virtual Machine
  │
  ▼
[5] Dual-Level Optimizer (optimizer.py)
      • AST Level: Constant folding, safe integer algebraic identities, dead-branch elimination
      • TAC Level: Local value propagation, branch folding, unreachable block removal, DCE
  │
  ▼
[6] Python 3.10+ Code Generator (codegen_python.py)
      • Generates idiomatic Python with exact operator precedence and parenthesization
      • Defends against Python's comparison-chaining trap: `(a == b) == c`
      • Builds source-line map for runtime error tracking and passes AST whitelist validator
  │
  ▼
[7] Sandboxed Runner (runner.py) & Public Pipeline (pipeline.py)
      • Subprocess execution with strict timeouts, memory isolation, and no network access
```

---

## 2. Current Status & RFC Roadmap

Nexora is designed under formal RFC specifications located in `docs/rfcs/`.

| Phase | Files | Status | Governing RFC |
|---|---|---|---|
| **Errors & Diagnostics** | `nexora/errors.py` | ✅ Implemented | RFC-0004 |
| **Tokens & Lexer** | `nexora/tokens.py`, `nexora/lexer.py` | ✅ Implemented | RFC-0001 |
| **AST Definitions** | `nexora/ast_nodes.py` | ✅ Implemented | RFC-0003 |
| **Recursive-Descent Parser** | `nexora/parser.py` | ✅ Implemented | RFC-0001, RFC-0003 |
| **Symbol Table & Semantic Analysis** | `nexora/symbols.py`, `nexora/semantic.py` | ✅ Implemented | RFC-0005 |
| **Three-Address Code (TAC) & CFG** | `nexora/ir.py` | ✅ Implemented | RFC-0006 |
| **Dual-Level Optimizer** | `nexora/optimizer.py` | ✅ Implemented | RFC-0007 |
| **Python 3.10+ Code Generator** | `nexora/codegen_python.py` | ✅ Implemented | RFC-0008 |
| **Sandboxed Runner & Pipeline API** | `nexora/runner.py`, `api.py` | ⏳ Planned | RFC-0009 |
| **Web Frontend & Compiler Visualizer** | `frontend/` (React + Vite) | ⏳ Planned | RFC-0010 |

---

## 3. MiniLang Quick Reference

MiniLang is a concise, statically-typed procedural language.

### Syntax Overview

```rust
// 1. Variable Declarations
make age = 20;                     // Type inferred as int
make price: float = 5;             // Explicit type annotation (int widens to float)
age = age + 1;                    // Mutable assignment (types must match)

// 2. Task (Function) Declarations
task add(x: int, y: int): int {
    give x + y;                    // 'give' returns value from task
}

task greet(name: string) {         // No return annotation = void
    show("Hello, " + name);        // Console output via 'show'
}

// 3. Conditional Branching
when (age >= 18 both age < 60) {
    show("adult");
} otherwise when (age >= 60) {
    show("senior");
} otherwise {
    show("minor");
}

// 4. Loops
during (age < 25) {
    age = age + 1;
    when (age == 23) {
        skip;                      // continue loop
    }
}

// 5. Task Invocation & Output
show(add(2, 3));
```

### Key Language Invariants
- **Types**: `int`, `float`, `string`, `bool`, `empty`, and `void` (task return only).
- **Keywords (16)**: `make`, `show`, `ask`, `when`, `otherwise`, `during`, `task`, `give`, `yes`, `no`, `both`, `either`, `not`, `empty`, `stop`, `skip`.
- **Precedence (Low to High)**:
  1. `either` (logical OR)
  2. `both` (logical AND)
  3. `not` (logical NOT)
  4. `==`, `!=` (equality)
  5. `<`, `<=`, `>`, `>=` (relational)
  6. `+`, `-` (additive & string concatenation)
  7. `*`, `/`, `%` (multiplicative; `/` always yields `float`, `%` is floor modulo)
  8. unary `-` (negation)
- **Scoping**: Lexical block scoping. Variable shadowing is strictly disallowed. Tasks are top-level only and hoisted.

---

## 4. Repository Structure

```
Nexora/
├── AGENTS.md                  # Instructions & contracts for AI coding agents
├── rules.md                   # Team engineering standards and PR norms
├── README.md                  # Project overview, architecture, and guides
├── docs/
│   └── rfcs/                  # Architectural design documents (RFC-0001 - RFC-0010)
└── backend/
    ├── nexora/                # Compiler package (Zero external dependencies)
    │   ├── __init__.py        # Public module exports
    │   ├── errors.py          # DiagnosticBag, NexoraError, code definitions
    │   ├── tokens.py          # TokenType enum and Token dataclass
    │   ├── lexer.py           # Hand-written Lexer
    │   ├── ast_nodes.py       # AST node hierarchy, clone_tree, unparse
    │   ├── parser.py          # Hand-written Recursive-Descent Parser
    │   ├── symbols.py         # Symbol, Scope, SymbolTable, Type system
    │   ├── semantic.py        # 2-Pass Semantic Analyzer & Type Checker
    │   ├── ir.py              # TAC instruction set, CFG builder, TAC VM
    │   ├── optimizer.py       # AST & TAC optimization passes
    │   ├── codegen_python.py  # Python 3.10+ Code Generator & AST Whitelist
    │   ├── runner.py          # Sandboxed Python execution & runtime error mapping
    │   └── pipeline.py        # Public orchestrator: compile_source entry point
    ├── api.py                 # FastAPI HTTP API (/health, /compile, /examples, /language)
    ├── main.py                # Command-Line Interface (CLI with --emit, --run, --json)
    ├── examples/              # Sample MiniLang programs (hello, factorial, fibonacci)
    ├── tests/
    │   ├── fixtures/          # Valid and invalid MiniLang test programs
    │   ├── golden/            # Expected Python code generation files
    │   ├── helpers/           # Reference TAC VM interpreter for differential tests
    │   ├── test_lexer.py      # Lexer test suite
    │   ├── test_ast.py        # AST invariants and visitor test suite
    │   ├── test_parser.py     # Parser precedence, associativity, recovery tests
    │   ├── test_semantic.py   # Type checking and diagnostic tests
    │   ├── test_ir.py         # TAC lowering, CFG, and TAC VM tests
    │   ├── test_optimizer.py  # Constant folding, DCE, and TAC optimization tests
    │   ├── test_codegen.py    # Python transpilation, line map, whitelist tests
    │   ├── test_runner.py     # Subprocess runner sandbox & runtime error tests
    │   ├── test_pipeline.py   # Full compilation pipeline orchestrator tests
    │   ├── test_cli.py        # CLI argument parsing, I/O, exit code tests
    │   └── test_api.py        # FastAPI endpoint integration & rate limiting tests
    └── requirements.txt       # Tooling, test, and API dependencies (pytest, ruff, fastapi, uvicorn, httpx)
```

---

## 5. Development & Testing Setup

Nexora is written for **Python 3.10+**. The compiler core contains **zero external dependencies** (standard library only).

### One-Time Environment Setup

From the `backend/` directory:

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment:
# On Windows PowerShell:
.\venv\Scripts\Activate.ps1
# On Linux / macOS:
source venv/bin/activate

# Install development & test dependencies
pip install -r requirements.txt
```

### Running Test Suites

```bash
# Run all tests (174 tests passing)
pytest -v

# Run a specific phase test suite
pytest tests/test_lexer.py -v
pytest tests/test_parser.py -v
pytest tests/test_semantic.py -v
pytest tests/test_ir.py -v
pytest tests/test_optimizer.py -v
pytest tests/test_codegen.py -v
```

### Code Style & Formatting

Nexora enforces strict code quality using [Ruff](https://github.com/astral-sh/ruff):

```bash
# Check for lint errors
ruff check .

# Check formatting compliance
ruff format --check .

# Auto-format codebase
ruff format .
```

---

## 6. Security & Safety Principles

1. **Subprocess Isolation**: Generated Python code is never executed in-process with `eval()` or `exec()`. Execution runs in a sandboxed `python -I` isolated subprocess.
2. **AST Whitelist Validation**: Generated Python code is parsed via Python's `ast` module and verified against a strict whitelist. Nodes such as `Import`, `ImportFrom`, `Attribute`, `Exec`, `Try`, `Lambda`, or direct OS system access are strictly rejected before execution.
3. **Never-Fold Guarantee**: The optimizer never evaluates or folds operations that could raise runtime errors (e.g. division by zero `1 / 0`, non-finite floats `inf`/`nan`, or integer bit lengths > 10,000 bits), ensuring runtime error semantics are preserved exactly.
4. **Deterministic Line Mapping**: Line maps maintain direct 1-to-1 correspondence between generated Python instructions and source MiniLang lines, allowing runtime exceptions to be mapped back accurately to the user's source code without exposing Python tracebacks.
