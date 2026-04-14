# Tree-sitter Compliance Audit

This document records our due-diligence audit of `tree-sitter` and `tree-sitter-typescript` against the competition rules. Reference this when questioned by judges or teammates.

Complementary reading: [RESEARCH.md](./RESEARCH.md) covers the research/tooling side — library mappings (Big.js, date-fns, lodash), prior-art projects, and architecture recommendations. It also records the organizer's (Pal de Vibe) direct confirmation that Python AST libs are allowed.

## TL;DR

**SAFE to use on all four competition rules.**

| Rule | Status | Reasoning |
|---|---|---|
| Rule 1 — No LLMs in TT | ✅ SAFE | Deterministic parser, zero ML/inference, no network calls |
| Rule 5 — AST libraries allowed | ✅ SAFE | Tree-sitter IS an AST parsing library — exactly the category the rule permits |
| Rule 6 — No node/js-tools at runtime | ✅ SAFE | Pure C extension, no subprocess/fork/exec, never invokes `tree-sitter generate` |
| Rule 9 — No project-specific logic | ✅ SAFE | General-purpose parser used by Neovim, GitHub, Atom, 24k+ stars |

## What we use

| Package | PyPI version | License | Upstream repo |
|---|---|---|---|
| `tree-sitter` | 0.25.2 | MIT | [tree-sitter/py-tree-sitter](https://github.com/tree-sitter/py-tree-sitter) |
| `tree-sitter-typescript` | 0.23.2 | MIT | [tree-sitter/tree-sitter-typescript](https://github.com/tree-sitter/tree-sitter-typescript) |

Core runtime: [tree-sitter/tree-sitter](https://github.com/tree-sitter/tree-sitter) (MIT, v0.26.8).

## Key evidence

### 1. No node/js at runtime

- The Python install path compiles a C extension via setuptools. No npm, no node, no `tree-sitter generate`.
- Runtime call path: `import tree_sitter_typescript` → `_binding.language_typescript()` → opaque `TSLanguage*` capsule → handed to `tree_sitter.Parser.parse(bytes)`.
- **No subprocess, no fork/exec, no shell-out** at any point.
- `otool -L` on the installed `.so` files shows they link only to `/usr/lib/libSystem.B.dylib` — no libnode, no V8, no JS engine.

### 2. The `grammar.js` files are build-time only

- `typescript/grammar.js` is a JavaScript DSL consumed by the Rust CLI `tree-sitter generate` at the **upstream maintainer's build time** to produce `parser.c`.
- The generated files `typescript/src/parser.c` (8.7 MB) and `tsx/src/parser.c` (8.7 MB) are **committed to the repo** and compiled into the Python wheel.
- Code search of `bindings/python` in tree-sitter-typescript for `grammar.js` returns **0 matches**.
- Our TT never reads or executes `grammar.js`. We never invoke `tree-sitter generate`.

### 3. The `package.json` / `binding.gyp` at repo root are inert

- These files exist to support the separate Node.js distribution channel (npm).
- setuptools/pip does not touch them. `setup.py` only compiles C sources.

### 4. Prebuilt wheels on PyPI

- `cibuildwheel` is configured for cp39+ — PyPI ships prebuilt binary wheels.
- Most installs download a compiled wheel; no C compilation needed on the user's machine.

### 5. Licensing

- Both repos: MIT.
- No copyleft, no distribution concerns.
- Attribution requirement: preserve MIT notices (handled by PyPI metadata + `THIRD_PARTY_LICENSES` if we choose to include one).

## Rule checker impact

Reviewed all 15 checks in `evaluate/checks/implementation_rules/`:

- `detect_llm_usage.py` — checks for `anthropic`, `openai`, `langchain`, `transformers`, `boto3`. Tree-sitter not in LLM_IMPORT_PACKAGES. **Pass.**
- `detect_direct_mappings.py` — matches `@scope/pkg` NPM paths. Our imports are `tree_sitter`/`tree_sitter_typescript` (Python module names). **Pass.**
- `detect_explicit_implementation.py` — checks function length and domain identifiers (`totalInvestment`, `BUY`/`SELL`). Tree-sitter API uses none. **Pass.**
- All other checks — no reference to tree-sitter, subprocess, or external tool invocation. **Pass.**

No rule check is scoped to detect AST-library usage (consistent with Rule 5 explicitly allowing AST libs).

## Fork / vendor?

**Not required.** Both packages are self-contained prebuilt wheels with permissive MIT licenses. Keep them in `pyproject.toml` as-is.

## Talking points for judges

1. Two PyPI packages: `tree-sitter` + `tree-sitter-typescript`, both MIT.
2. `grammar.js` files are build-time artifacts only — shipped in source tarball for the separate Node.js channel. Our TT never reads or executes them.
3. The C extension links against libpython only, not node/V8.
4. We never invoke `tree-sitter generate` or any JS tool.
5. Pure Python runtime path: `import` → capsule → `Parser.parse(bytes)`.
