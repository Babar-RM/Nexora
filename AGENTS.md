# AGENTS.md — Nexora (MiniLang → Python compiler)

Instructions for AI coding agents (Claude Code, Cursor, Copilot, etc.) and for humans who work with them.
**Read this file completely before changing anything.** Then read `rules.md` and the RFCs in `docs/rfcs/`.
If this file and an RFC disagree, the RFC wins. If an RFC and the code disagree, the code has a bug (or the RFC needs an amendment — never silently diverge).

---

## 1. Project summary

**Nexora** is a source-to-source compiler (transpiler). It reads programs written in **MiniLang**, a small custom language, validates them, and generates equivalent **Python** source code. It can optionally run the generated code and report the output.

It is deliberately a *real* compiler, not a text replacer. Keyword-to-Python substitution (e.g. `show` → `print` string replacement) is forbidden. All translation goes through the full pipeline:

```
MiniLang source
  → Lexer            (text → tokens)
  → Parser           (tokens → AST)
  → Semantic analysis (AST → validated, typed AST + symbol table)
  → IR generator     (AST → Three-Address Code)
  → Optimizer        (constant folding etc.)
  → Python codegen   (optimized AST → Python source)
  → Runner           (execute generated Python in a sandboxed subprocess)
```

### Compiler Pipeline

```mermaid
flowchart TD
    SRC["MiniLang Source (.mini file)"]
    LEX["Lexer\ntokens.py · lexer.py\ntext → tokens"]
    PAR["Parser\nparser.py\ntokens → AST"]
    SEM["Semantic Analyzer\nsymbols.py · semantic.py\nAST → typed AST + symbol table"]
    IR["IR Generator\nir.py\nAST → Three-Address Code"]
    OPT["Optimizer\noptimizer.py\nconstant folding · dead-code elim"]
    COD["Python Codegen\ncodegen_python.py\noptimized AST → Python source"]
    RUN["Runner\nrunner.py\nsandboxed subprocess"]
    OUT["Output / Result"]

    SRC --> LEX --> PAR --> SEM --> IR --> OPT --> COD --> RUN --> OUT

    ERR["NexoraError\nerrors.py\nphase · code · line · col · message"]
    LEX -. "LexerError" .-> ERR
    PAR -. "ParserError" .-> ERR
    SEM -. "SemanticError" .-> ERR

    PIPE["pipeline.py\n(only public entry point)"]
    PIPE -.->|orchestrates| LEX
    PIPE -.->|orchestrates| PAR
    PIPE -.->|orchestrates| SEM
    PIPE -.->|orchestrates| IR
    PIPE -.->|orchestrates| OPT
    PIPE -.->|orchestrates| COD
    PIPE -.->|orchestrates| RUN
```

Backend is built first. The frontend (code editor + compiler visualizer) is built last.

---

## 2. Current status

Update this table in the same PR that changes a phase's status.

| Phase | Files | Status | Governing RFC |
|---|---|---|---|
| Errors / diagnostics | `errors.py` | Implemented | RFC-0004 |
| Tokens + Lexer | `tokens.py`, `lexer.py` | Implemented (COLON, ASCII-only amendments complete) | RFC-0001 |
| AST nodes | `ast_nodes.py` | Implemented | RFC-0003 |
| Parser | `parser.py` | Not started | RFC-0001, RFC-0003 |
| Symbol table + Semantic | `symbols.py`, `semantic.py` | Not started | RFC-0005 |
| IR (TAC) | `ir.py` | Not started | RFC-0006 (planned) |
| Optimizer | `optimizer.py` | Not started | RFC-0007 (planned) |
| Python codegen | `codegen_python.py` | Not started | RFC-0008 (planned) |
| Runner + API | `runner.py`, `api.py` | Not started | RFC-0009 (planned) |
| Frontend | `frontend/` | Not started | RFC-0010 (planned) |

Never describe a feature as "implemented" anywhere (README, portfolio, UI) until it is built **and** tested.

### Phase Completion Overview

```mermaid
gantt
    title Nexora Phase Build Plan
    dateFormat  YYYY-MM-DD
    axisFormat  %b %d

    section Foundation
    Errors / Diagnostics (errors.py)         :done,    err, 2026-01-01, 30d
    Tokens + Lexer (tokens.py / lexer.py)    :active,  lex, 2026-01-15, 45d

    section Frontend Parsing
    AST Nodes (ast_nodes.py)                 :         ast, after lex, 30d
    Parser (parser.py)                       :         par, after ast, 45d

    section Analysis
    Symbol Table and Semantic                :         sem, after par, 45d

    section Optimization and Codegen
    IR / TAC (ir.py)                         :         ir,  after sem, 30d
    Optimizer (optimizer.py)                 :         opt, after ir,  20d
    Python Codegen (codegen_python.py)       :         cod, after opt, 30d

    section Execution and Integration
    Runner + API (runner.py / api.py)        :         run, after cod, 30d
    Frontend (React + Vite)                  :         fe,  after run, 60d
```

---

## 3. Tech stack

| Area | Choice |
|---|---|
| Language | Python 3.10+ (dataclasses with `kw_only`, `match`, `X \| None` types) |
| Compiler core dependencies | **Standard library only**. No PLY, ANTLR, Lark, etc. Lexer and parser are hand-written (recursive descent). |
| Tests | `pytest` |
| Lint / format | `ruff` (`ruff check .` and `ruff format .`) |
| API | FastAPI + Uvicorn (added only in the API phase) |
| Execution | `subprocess` with timeout and resource limits. Never `exec()` / `eval()` user code in the server process. |
| Frontend (last) | React + Vite, Monaco Editor (or CodeMirror), Tailwind CSS |

Third-party packages are allowed only outside the compiler core (`api.py`, tests, tooling) and must be added to `requirements.txt` with a one-line justification in the PR.

---

## 4. Setup and commands

Run everything from `backend/`.

```bash
# one-time setup
python -m venv venv
# Windows PowerShell:  venv\Scripts\Activate.ps1
# Windows cmd:         venv\Scripts\activate.bat
# Linux / macOS:       source venv/bin/activate
pip install -r requirements.txt

# every day
pytest -v                      # run all tests
pytest tests/test_lexer.py -v  # run one test file
ruff check .                   # lint
ruff format .                  # format
python main.py examples/hello.mini   # run the CLI on a MiniLang file
uvicorn api:app --reload             # start the API (after the API phase exists)
```

`requirements.txt` (initial):

```
pytest
ruff
```

Before declaring any task finished, `pytest -v` and `ruff check .` must both pass.

---

## 5. Repository map

```
nexora/
├── AGENTS.md                  # this file
├── rules.md                   # engineering rules for the team
├── docs/
│   └── rfcs/                  # design decisions (RFC-0001 … RFC-0010)
├── backend/
│   ├── nexora/                # the compiler package
│   │   ├── __init__.py
│   │   ├── errors.py          # NexoraError + diagnostics
│   │   ├── tokens.py          # TokenType, Token, KEYWORDS
│   │   ├── lexer.py           # Lexer
│   │   ├── ast_nodes.py       # AST dataclasses + NodeVisitor
│   │   ├── parser.py          # recursive-descent Parser
│   │   ├── symbols.py         # Symbol, Scope, SymbolTable, Type
│   │   ├── semantic.py        # SemanticAnalyzer
│   │   ├── ir.py              # TAC instructions + generator
│   │   ├── optimizer.py       # constant folding, etc.
│   │   ├── codegen_python.py  # Python code generator
│   │   ├── runner.py          # sandboxed execution
│   │   └── pipeline.py        # chains all phases; the only public entry point
│   ├── api.py                 # FastAPI app (thin wrapper over pipeline)
│   ├── main.py                # CLI
│   ├── examples/              # sample .mini programs
│   ├── tests/
│   │   ├── fixtures/          # .mini inputs (valid/, invalid/)
│   │   ├── golden/            # expected generated Python
│   │   └── test_*.py
│   └── requirements.txt
└── frontend/                  # built last
```

### Module Dependency Graph

```mermaid
flowchart LR
    ERR["errors.py"]
    TOK["tokens.py"]
    LEX["lexer.py"]
    AST["ast_nodes.py"]
    PAR["parser.py"]
    SYM["symbols.py"]
    SEM["semantic.py"]
    IR["ir.py"]
    OPT["optimizer.py"]
    COD["codegen_python.py"]
    RUN["runner.py"]
    PIPE["pipeline.py"]
    API["api.py"]
    MAIN["main.py"]

    ERR --> TOK --> LEX --> AST --> PAR --> SYM --> SEM --> IR --> OPT --> COD --> RUN --> PIPE --> API
    PIPE --> MAIN
```

> **Import rule:** Arrows show the only permitted import direction. No backwards imports allowed — violating this is a bug.

MiniLang source files use the extension **`.mini`**.

---

## 6. Architecture rules (non-negotiable)

1. **Phases are isolated.** Each phase consumes the previous phase's output data structure and nothing else. The parser never looks at raw source text; the code generator never looks at tokens.
2. **Import direction is one-way.** A module may import only from modules earlier in this chain (plus the standard library):
   `errors → tokens → lexer → ast_nodes → parser → symbols → semantic → ir → optimizer → codegen_python → runner → pipeline → api`
   A backwards import is a bug, not a shortcut.
3. **No global mutable state.** No module-level counters, caches, or singletons. Every compile starts from scratch (`Lexer(source)`, `Parser(tokens)`, …). Two compiles in the same process must not affect each other.
4. **Data out, not print.** Compiler code never calls `print()` and never reads files. It receives strings and returns data structures. Only `main.py` and `api.py` do I/O.
5. **Every phase output must be serializable** (`to_dict()` / dataclass → JSON) so the frontend can display it.
6. **`pipeline.py` is the only public entry point** for `main.py`, `api.py`, and tests that need the full flow.
7. **Python is generated from the AST**, not from TAC. TAC is generated for analysis, optimization demos, visualization, and future targets (RFC-0002 §6).
8. **Errors carry location.** Every error has `phase`, `code`, `line`, `column`, `message` (RFC-0004).

### Error Class Hierarchy

```mermaid
classDiagram
    class NexoraError {
        +str phase
        +str code
        +int line
        +int column
        +str message
        +to_dict() dict
    }
    class LexerError {
        +phase = "lexer"
    }
    class ParserError {
        +phase = "parser"
        +bool recoverable
    }
    class SemanticError {
        +phase = "semantic"
        +str symbol
    }
    class InternalCompilerError {
        +str assertion
    }

    NexoraError <|-- LexerError
    NexoraError <|-- ParserError
    NexoraError <|-- SemanticError
    NexoraError <|-- InternalCompilerError
```

### Error Recovery Strategy

```mermaid
flowchart TD
    ERR_IN["Error encountered"]
    PHASE{Which phase?}
    LEXER_ERR["LexerError\nFail fast — stop lexing\nRFC-0004 §5.1"]
    PARSER_ERR["ParserError\nPanic-mode recovery\nSkip to safe sync point\nContinue parsing"]
    SEM_ERR["SemanticError\nCollect all errors\nAssign ERROR type\nAvoid cascading"]
    INTERNAL["InternalCompilerError\nNot shown to user\nIndicates invariant violation"]

    ERR_IN --> PHASE
    PHASE -->|Lexer| LEXER_ERR
    PHASE -->|Parser| PARSER_ERR
    PHASE -->|Semantic| SEM_ERR
    PHASE -->|Internal| INTERNAL
```

---

## 7. MiniLang quick reference

Authoritative definition: **RFC-0001**. This is a summary only.

```
// comment
make age = 20;                    // type inferred: int
make price: float = 5;            // optional annotation (int widens to float)
age = age + 1;                   // assignment, type must match

task add(x: int, y: int): int {
    give x + y;
}

task greet(name: string) {   // no return type = void
    show("Hello " + name);
}

when (age >= 18 both age < 60) {
    show("adult");
} otherwise when (age >= 60) {
    show("senior");
} otherwise {
    show("minor");
}

during (age < 25) {
    age = age + 1;
}

show(add(2, 3));
```

- Types: `int`, `float`, `string`, `bool`, `empty` (plus `void` for tasks with no return type).
- Keywords: `make show ask when otherwise during task give yes no both either not empty stop skip`.
- Operators by precedence (low → high): `either`, `both`, `not`, `== !=`, `< <= > >=`, `+ -`, `* / %`, unary `-`.
- Statements end with `;`. Blocks use `{ }`. `when`/`during` conditions use `( )` and must be `bool`.
- Statically typed, no implicit conversions except `int → float` widening.
- No shadowing. Tasks are declared at top level only.

### Operator Precedence (low → high)

```mermaid
flowchart TD
    P1["1  either  (lowest precedence)"]
    P2["2  both"]
    P3["3  not  (unary prefix)"]
    P4["4  == and !=  (equality)"]
    P5["5  lt, le, gt, ge  (relational)"]
    P6["6  + and -  (additive)"]
    P7["7  *, /, %  (multiplicative)"]
    P8["8  unary -  (highest precedence)"]

    P1 --> P2 --> P3 --> P4 --> P5 --> P6 --> P7 --> P8
```

### Type System

```mermaid
flowchart LR
    INT["int"]
    FLOAT["float"]
    STRING["string"]
    BOOL["bool"]
    VOID["void  (task return only)"]
    ERROR["ERROR  (propagated on type error)"]

    INT -->|"implicit widening"| FLOAT
```

---

## 8. Playbooks

### 8.1 Implementing a compiler phase

```mermaid
flowchart TD
    A["Read governing RFC"]
    B{RFC exists and clear?}
    C["Stop — propose RFC first\nDo not guess"]
    D["Create module file(s) from §5 repo map"]
    E["Write tests first or alongside phase code"]
    F["Wire phase into pipeline.py"]
    G["Add fixture to tests/fixtures/"]
    H["Update status table in AGENTS.md §2"]
    I["Run pytest -v and ruff check ."]
    J{All pass?}
    K["Fix failures"]
    L["Done"]

    A --> B
    B -->|No| C
    B -->|Yes| D
    D --> E --> F --> G --> H --> I --> J
    J -->|No| K --> I
    J -->|Yes| L
```

1. Read the governing RFC. If it does not exist or is unclear, **stop and propose an RFC**; do not guess.
2. Create the module file(s) listed in §5. Put only that phase's logic in them.
3. Write the tests first or alongside (see §9). Aim for the invariants listed in RFC-0002 §4 (phase contracts).
4. Wire the phase into `pipeline.py`.
5. Add at least one end-to-end fixture in `tests/fixtures/`.
6. Update the status table in §2.
7. Run `pytest -v` and `ruff check .`.

### 8.2 Adding or changing a language feature

A language change touches many files. Follow this checklist in order and do not skip steps:

```mermaid
flowchart TD
    LC1["1. RFC first — syntax, typing, semantics, Python mapping"]
    LC2["2. tokens.py / lexer.py — new tokens or keywords + lexer tests"]
    LC3["3. ast_nodes.py — new nodes + to_dict + visitor support"]
    LC4["4. parser.py — grammar rule + precedence + parser tests incl. error cases"]
    LC5["5. symbols.py / semantic.py — typing + scope rules + one test per error code"]
    LC6["6. ir.py / optimizer.py — lowering + optimization + tests"]
    LC7["7. codegen_python.py — emission + golden file"]
    LC8["8. Update RFC-0001 grammar, AGENTS.md quick ref, add example in examples/"]

    LC1 --> LC2 --> LC3 --> LC4 --> LC5 --> LC6 --> LC7 --> LC8
```

### 8.3 Fixing a bug

1. Reproduce with a failing test (minimal `.mini` input or direct unit call).
2. Fix the root cause in the phase that owns the bug, not in a later phase that happens to hide it.
3. Keep the regression test.

### 8.4 Adding an error or warning

1. Pick the next free code in the right range (RFC-0004 §4).
2. Add it to the code table in RFC-0004 in the same PR.
3. Write a test asserting `code`, `line`, `column`, and the message text.

---

## 9. Testing requirements

- Every public class and function has unit tests. Every error code has at least one test that triggers it.
- Error tests assert **code, line, and column**, not just that "an error happened".
- Lexer, parser, and semantic phases each need both *valid* and *invalid* fixtures.
- **Golden tests** for codegen: `tests/golden/<name>.mini` + `tests/golden/<name>.py.expected`. Changing a golden file requires a note in the PR explaining why.
- **Round-trip / behaviour tests:** run the generated Python and assert on its output for programs in `examples/`.
- Tests must be deterministic and independent (no ordering assumptions, no network, no wall-clock sleeps).
- Test names: `test_<unit>_<behavior>` (e.g. `test_lexer_rejects_unterminated_string`).

### Test Taxonomy

```mermaid
flowchart LR
    T["tests/"]
    UNIT["Unit Tests\ntest_lexer.py\ntest_parser.py\ntest_semantic.py"]
    FIX["Fixture Tests\nfixtures/valid/\nfixtures/invalid/"]
    GOLD["Golden Tests\ngolden/*.mini\ngolden/*.py.expected"]
    E2E["Round-trip Tests\nRun generated Python\nAssert stdout"]

    T --> UNIT
    T --> FIX
    T --> GOLD
    T --> E2E
```

---

## 10. Error handling rules

- Use `NexoraError` subclasses (`LexerError`, `ParserError`, `SemanticError`) or the diagnostics collector defined in RFC-0004. Never raise bare `Exception`, `ValueError`, or `SystemExit` from compiler code for user mistakes.
- Lexer: fail fast (first error stops lexing, RFC-0004 §5.1).
- Parser: panic-mode recovery so several syntax errors can be reported in one run.
- Semantic analyzer: collect all errors; use the `ERROR` type to avoid cascading messages.
- Internal bugs (violated invariants) raise `AssertionError`/`InternalCompilerError`, which is *not* shown as a user error.
- Messages: say what is wrong, what was expected or found, and how to fix it when possible. Quote identifiers with single quotes.

---

## 11. Security rules

- **Never** run generated Python in the API process. Use `runner.py`: a separate `python` subprocess, `-I` isolated mode, hard timeout (default 5 s), output size cap (64 KB), no network, memory/CPU limits where the OS supports them, temporary working directory deleted afterwards.
- Never use `eval`, `exec`, `compile`, `os.system`, or `shell=True` anywhere in the compiler core.
- Limit input: source <= 64 KB, nesting depth <= 200, to avoid denial of service via pathological input.
- Do not log full user source in server logs.
- Do not commit secrets, `.env` files, or virtual environments.

### Sandboxed Execution Model

```mermaid
sequenceDiagram
    participant U as User / API
    participant P as pipeline.py
    participant C as codegen_python.py
    participant R as runner.py
    participant S as Subprocess python -I

    U->>P: compile(source)
    P->>C: generate Python source
    C-->>P: python_src: str
    P->>R: run(python_src, timeout=5s)
    R->>S: spawn python -I in temp dir
    Note over S: No network, 64 KB output cap, 5 s timeout
    S-->>R: stdout / stderr
    R-->>U: RunResult(stdout, stderr, exit_code)
    Note over R: temp dir deleted after run
```

---

## 12. Git and PR rules for agents

- One logical change per commit; one feature or fix per PR.
- Commit messages follow Conventional Commits: `feat(parser): parse during statements`.
- Never force-push, rewrite shared history, or modify `main` directly.
- Never edit an RFC whose status is **Accepted** except through an amendment section approved per `rules.md` §9.
- Do not reformat unrelated files. Do not rename or move files without an RFC or explicit instruction.
- Do not delete tests to make a build pass.

---

## 13. How agents should respond to the team

The project owner prefers **step-by-step, file-by-file instructions that can be copy-pasted**.

- Give the **complete content** of a file (not fragments with "…rest unchanged") unless the change is a small, clearly located patch; for patches, state the file, the exact lines to find, and the exact replacement.
- State the file path before each code block.
- Provide exact terminal commands and the expected output.
- **Do not deliver zipped code packages** or tell the team to download an archive.
- After each step, say how to verify it (which test or command, what success looks like) and what comes next.
- If a request conflicts with an RFC or with this file, say so before writing code.

---

## 14. Do / Don't

**Do**
- Keep functions small and single-purpose; type-hint all public signatures.
- Prefer dataclasses and enums over dicts and magic strings.
- Track `line` and `column` on every token and AST node.
- Write the Python that Nexora generates so it is readable (real `if`/`while`/`def`, 4-space indentation).
- Ask for an RFC when the spec is ambiguous.

**Don't**
- Don't use regex-replace or string templates as a substitute for AST-based translation.
- Don't add features "while you're there" that no RFC covers.
- Don't catch broad exceptions to silence failures.
- Don't add dependencies to the compiler core.
- Don't mark TODOs without an issue reference (`# TODO(#12): ...`).

---

## 15. Definition of Done

A task is done only when:

- [ ] Behaviour matches the governing RFC.
- [ ] New/changed code has tests, including error cases; all tests pass.
- [ ] `ruff check .` and `ruff format --check .` pass.
- [ ] Public functions have type hints and docstrings.
- [ ] Docs updated (this file's status table, RFC if the design changed, examples).
- [ ] No regressions in golden or end-to-end tests.
- [ ] PR description explains *what* and *why* and lists how it was verified.

---

## 16. Ownership (initial split)

| Area | Primary owner |
|---|---|
| Lexer, parser, AST | Member 1 |
| Semantic analysis, symbol table, IR, optimizer, Python codegen | Member 2 |
| Language design, API, frontend, integration | Member 3 |
| Tests, documentation, research, demo/presentation | Member 4 |

Ownership means *first reviewer*, not *only editor*. The AST (RFC-0003) is the shared contract between members: changes to it need all owners' approval.

### Team Ownership Map

```mermaid
flowchart LR
    M1["Member 1\nLexer, Parser, AST"]
    M2["Member 2\nSemantic, Symbol Table, IR, Optimizer, Codegen"]
    M3["Member 3\nLanguage Design, API, Frontend, Integration"]
    M4["Member 4\nTests, Docs, Research, Demo"]

    subgraph SharedContract["Shared Contract — all owners"]
        AST_CONTRACT["ast_nodes.py\nChanges require all-owners approval"]
    end

    M1 --- AST_CONTRACT
    M2 --- AST_CONTRACT
    M3 --- AST_CONTRACT
    M4 --- AST_CONTRACT
```

---

## 17. Glossary

| Term | Definition |
|---|---|
| **Token** | Smallest meaningful unit of source (keyword, identifier, number, operator). |
| **AST** | Abstract Syntax Tree; the program's structure as a tree. |
| **Symbol table** | Map of declared names to their kind, type, and scope. |
| **TAC** | Three-Address Code; IR where each instruction has at most one operator. |
| **Constant folding** | Evaluating constant expressions at compile time (`3 * 4` → `12`). |
| **Transpiler** | Compiler whose target is another high-level language. |
| **Panic-mode recovery** | After a syntax error, skip tokens to a safe point and continue parsing. |
| **Golden test** | Compares generated output to a stored, reviewed expected file. |
