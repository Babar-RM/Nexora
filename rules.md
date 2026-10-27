# rules.md — Nexora Engineering Rules

This document captures the engineering conventions and team norms for the Nexora project. It supplements `AGENTS.md` (project structure and agent instructions). When the two conflict, `AGENTS.md` wins for agent behaviour; this file wins for team process.

RFC amendments must follow §9 of this file.

---

## 1. Code style

- **Python 3.10+** everywhere in `backend/`. Use `match`, `X | None`, and `kw_only=True` dataclasses freely.
- **Type-hint all public functions and methods.** No `Any` unless justified in a comment.
- **Docstrings** on every public class, method, and module. Use Google-style docstrings.
- Line length: **100 characters** (enforced by `ruff`).
- `ruff format .` is the canonical formatter. Running it must produce no diff before merging.
- `ruff check .` must produce zero warnings before merging. Use `# noqa: <code>` only with a comment explaining why.

---

## 2. Naming conventions

| Kind | Convention | Example |
|---|---|---|
| Module | `snake_case` | `ast_nodes.py`, `codegen_python.py` |
| Class | `PascalCase` | `TokenType`, `SemanticAnalyzer` |
| Function / method | `snake_case` | `parse_expression()`, `to_dict()` |
| Constant | `UPPER_SNAKE` | `KEYWORDS`, `MAX_NESTING_DEPTH` |
| Type alias | `PascalCase` | `NodeList`, `Scope` |
| Test function | `test_<unit>_<behaviour>` | `test_lexer_rejects_unterminated_string` |
| RFC files | `RFC-NNNN.md` (4-digit, zero-padded) | `RFC-0001.md`, `RFC-0010.md` |
| MiniLang source | `*.mini` | `hello.mini`, `factorial.mini` |

---

## 3. File-level rules

- **One class per file is preferred** for the large dataclass families (AST nodes). Exceptions are allowed when cohesion is high (e.g., `tokens.py` holds both `TokenType` and `Token`).
- Every module must have a module-level docstring explaining its role in the pipeline.
- `__init__.py` in `nexora/` should export only the symbols that `pipeline.py` needs; do not re-export everything.

---

## 4. Commit and branch rules

- Branch names: `feat/<short-description>`, `fix/<short-description>`, `docs/<short-description>`, `refactor/<short-description>`.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/):
  ```
  feat(parser): parse during-loop statements
  fix(lexer): reject non-ASCII characters (RFC-0001 §3.1.1)
  docs(rfcs): add RFC-0006 IR design
  test(semantic): cover undeclared variable error E3001
  ```
- Commits must be atomic: one logical change. Do not bundle unrelated fixes.
- Squash fixup commits before merging.

---

## 5. Pull request rules

- Every PR must reference at least one issue or RFC.
- PR description template (use this):
  ```
  ## What
  <one-sentence summary>

  ## Why
  <motivation; link to RFC or issue>

  ## How
  <key design decisions>

  ## Verification
  - `pytest -v` output: all N tests pass
  - `ruff check .`: zero warnings
  - Specific tests added: <list>
  ```
- PRs that delete tests to make a build pass are rejected without review.
- Reviewers: at minimum, the primary owner of the affected area (see AGENTS.md §16).

---

## 6. Testing rules

- **TDD preferred**: write the failing test first, then the implementation.
- Coverage target: **90 %** for `nexora/` package code. Measure with `pytest --cov=nexora`.
- Do not use `unittest.mock.patch` to bypass the actual compiler phases in integration tests. Use real fixtures.
- Fixture files in `tests/fixtures/valid/` must be runnable end-to-end without error.
- Fixture files in `tests/fixtures/invalid/` must trigger a specific, documented error code.
- Golden files (`tests/golden/`) are reviewed artifacts. Changing them requires a PR note explaining the intentional output change.

---

## 7. Error code management

Error codes are defined in RFC-0004. Rules:

- Codes are permanent. Once assigned, a code number is never reused, even if the error is removed.
- Codes are range-partitioned by phase (RFC-0004 §3.4):
  - `E1xxx` — Lexer errors (phase "Lexical Error")
  - `E2xxx` — Parser errors (phase "Syntax Error")
  - `E3xxx` — Semantic errors (phase "Semantic Error")
  - `W4xxx` — Warnings (severity "warning")
  - `R5xxx` — Runner errors (phase "Runtime Error")
- When adding a new error code, update RFC-0004's code table in the same PR.
- Every error code must have exactly one test that triggers it (minimum).

---

## 8. Documentation rules

- Keep `AGENTS.md §2` (status table) current. If a phase is "Not started" and you start it, update the row in the same PR.
- RFC files are the source of truth for design. If the code contradicts an RFC, that is a bug.
- Public API changes (function signatures, data structure fields) must be reflected in the governing RFC in the same PR.
- Do not copy-paste large blocks between the RFC and the code; reference the RFC by section.

---

## 9. RFC amendment process

1. An RFC is **Draft** when it is being written.
2. An RFC becomes **Accepted** when the team agrees it is complete and correct (at least two reviewers from different ownership areas).
3. **Accepted RFCs are immutable** except through the amendment process:
   a. Open a PR that adds an `## Amendment N — <title>` section at the bottom of the RFC.
   b. The amendment section must explain what changes and why.
   c. The amendment requires the same two-reviewer approval as a new RFC.
   d. Do not edit existing sections of an Accepted RFC; only append.
4. **Planned RFCs** (referenced in AGENTS.md status table as "planned") have not been written yet. Start one when the phase begins.

---

## 10. Security hygiene

- Never commit secrets, API keys, or passwords. Use `.env` files and add `.env` to `.gitignore`.
- Never commit the `venv/` directory.
- Generated Python is always executed in a separate subprocess (see `runner.py`). This is non-negotiable.
- Input limits (source ≤ 64 KB, nesting ≤ 200) are enforced at the start of the pipeline, before any parsing.

---

## 11. Definition of "Implemented"

A phase is **Implemented** only when ALL of the following are true:

1. The module file exists and has no `raise NotImplementedError` stubs.
2. All unit tests for that phase pass.
3. At least one end-to-end fixture exercises the phase.
4. `ruff check .` and `pytest -v` both pass with zero failures or warnings.
5. The status table in `AGENTS.md §2` has been updated.

Do not say "implemented" in READMEs, portfolios, presentations, or UI before all five conditions are met.

---

## 12. Dependency policy

| Location | Third-party allowed? | Requirement |
|---|---|---|
| `nexora/` (compiler core) | **No** | Standard library only |
| `api.py` | Yes | Must be in `requirements.txt` with justification |
| `tests/` | Yes (test tooling only) | Must be in `requirements.txt` with justification |
| `frontend/` | Yes | Managed by `package.json` |

When in doubt, add to `requirements.txt` and include a one-line comment: `# <package>: used for <reason> in <file>`.
