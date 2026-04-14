"""TypeScript to Python translator using tree-sitter parsing.

Reads the ROAI portfolio calculator TypeScript source, parses it with
tree-sitter, and uses the AST-walking emitter to produce Python code
that implements the wrapper interface.
"""
from __future__ import annotations

from pathlib import Path

from tt.config import TranslationConfig
from tt.emitter import emit_module


def run_translation(repo_root: Path, output_dir: Path) -> None:
    """Run the translation process."""
    # Load project-specific config from JSON (all domain terms live here)
    config_path = (
        repo_root / "tt" / "tt" / "scaffold" / "ghostfolio_pytx" / "tt_import_map.json"
    )
    if not config_path.exists():
        print(f"Warning: config not found: {config_path}")
        return

    cfg = TranslationConfig(config_path)

    ts_source_path = repo_root / cfg.source_file
    output_file = (
        output_dir / "app" / "implementation" / "portfolio" / "calculator"
        / "roai" / "portfolio_calculator.py"
    )

    if not ts_source_path.exists():
        print(f"Warning: TypeScript source not found: {ts_source_path}")
        return

    print(f"Translating {ts_source_path.name}...")
    ts_content = ts_source_path.read_text(encoding="utf-8")

    # Parse TS and emit Python via config-driven AST-walking emitter
    python_lines = emit_module(ts_content, cfg)

    if not python_lines:
        print("Warning: emitter produced no output")
        return

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text("\n".join(python_lines) + "\n", encoding="utf-8")
    print(f"  Translated -> {output_file}")
