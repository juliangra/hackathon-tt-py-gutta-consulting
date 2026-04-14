"""TypeScript to Python translator.

Uses tree-sitter to parse TS, the transpiler to build Python ast nodes,
and ast.unparse() to generate source. No string templates.
"""
from __future__ import annotations

import ast as pyast
from pathlib import Path

from tt.config import TranslationConfig
from tt.parser import parse_typescript, find_class, find_methods, get_text
from tt.transpiler import translate_block, translate_expr, _snake, _name, _const, _call, _attr


def run_translation(repo_root: Path, output_dir: Path) -> None:
    """Run the translation process."""
    config_path = (
        repo_root / "tt" / "tt" / "scaffold" / "ghostfolio_pytx" / "tt_import_map.json"
    )
    if not config_path.exists():
        print(f"Warning: config not found: {config_path}")
        return

    cfg = TranslationConfig(config_path)
    ts_source_path = repo_root / cfg.source_file

    if not ts_source_path.exists():
        print(f"Warning: TypeScript source not found: {ts_source_path}")
        return

    print(f"Translating {ts_source_path.name}...")
    ts_content = ts_source_path.read_text(encoding="utf-8")

    # Also read the helper file for getFactor
    helper_path = repo_root / cfg.helper_source
    helper_content = helper_path.read_text(encoding="utf-8") if helper_path.exists() else ""

    # Parse TS
    root = parse_typescript(ts_content)
    cls_node = find_class(root, cfg.class_name)
    if cls_node is None:
        print("Warning: class not found")
        return

    ts_methods = find_methods(cls_node)
    print(f"  Found: {list(ts_methods.keys())}")

    # Build Python AST module
    module = _build_module(cfg, cls_node, ts_methods, helper_content)

    # Fix locations and unparse
    pyast.fix_missing_locations(module)
    source = pyast.unparse(module)

    # Write output
    output_file = (
        output_dir / "app" / "implementation" / "portfolio" / "calculator"
        / "roai" / "portfolio_calculator.py"
    )
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(source + "\n", encoding="utf-8")
    print(f"  Translated -> {output_file}")


def _build_module(
    cfg: TranslationConfig, cls_node, ts_methods: dict, helper_src: str
) -> pyast.Module:
    """Build the complete Python module AST."""
    body: list[pyast.stmt] = []

    # Imports (derived from config)
    body.append(pyast.ImportFrom(module="__future__", names=[pyast.alias(name="annotations")], level=0))
    body.append(pyast.Import(names=[pyast.alias(name="copy")]))
    body.append(pyast.ImportFrom(module="datetime", names=[pyast.alias(name="date"), pyast.alias(name="timedelta")], level=0))
    body.append(pyast.ImportFrom(module="decimal", names=[pyast.alias(name="Decimal", asname="D")], level=0))

    # Import from wrapper (from config)
    for _key, imp_str in cfg.imports.items():
        parts = imp_str.split(" import ")
        if len(parts) == 2:
            mod = parts[0].replace("from ", "").strip()
            names = [pyast.alias(name=n.strip()) for n in parts[1].split(",")]
            body.append(pyast.ImportFrom(module=mod, names=names, level=0))

    # Translate getFactor from the helper TS source
    if helper_src:
        body.extend(_translate_helper_func(cfg, helper_src))

    # Build the class
    cls_name = get_text(cls_node.child_by_field_name("name"))
    class_body = _build_class_body(cfg, ts_methods)

    body.append(pyast.ClassDef(
        name=cls_name,
        bases=[_name(cfg.parent_class)],
        keywords=[],
        body=class_body,
        decorator_list=[]
    ))

    return pyast.Module(body=body, type_ignores=[])


def _translate_helper_func(cfg: TranslationConfig, helper_src: str) -> list[pyast.stmt]:
    """Translate getFactor from portfolio.helper.ts."""
    root = parse_typescript(helper_src)

    # Find the getFactor function
    for child in root.children:
        if child.type == "export_statement":
            for c in child.children:
                if c.type == "function_declaration":
                    name_node = c.child_by_field_name("name")
                    if name_node and "Factor" in get_text(name_node):
                        body_node = c.child_by_field_name("body")
                        if body_node:
                            py_body = translate_block(body_node, cfg)
                            return [pyast.FunctionDef(
                                name=_snake(get_text(name_node)),
                                args=pyast.arguments(
                                    posonlyargs=[], args=[pyast.arg(arg="activity_type")],
                                    vararg=None, kwonlyargs=[], kw_defaults=[],
                                    kwarg=None, defaults=[]
                                ),
                                body=py_body,
                                decorator_list=[], returns=None
                            )]
    return []


def _build_class_body(cfg: TranslationConfig, ts_methods: dict) -> list[pyast.stmt]:
    """Build all methods for the translated class."""
    body: list[pyast.stmt] = []

    # Translate getSymbolMetrics from TS AST
    if "getSymbolMetrics" in ts_methods:
        body.append(_translate_method(
            cfg, ts_methods["getSymbolMetrics"],
            py_name=cfg.method("getSymbolMetrics"),
            extra_params=["symbol", "start", "end"]
        ))

    # Translate calculateOverallPerformance if present
    if "calculateOverallPerformance" in ts_methods:
        body.append(_translate_method(
            cfg, ts_methods["calculateOverallPerformance"],
            py_name=cfg.method("calculateOverallPerformance"),
            extra_params=["positions"]
        ))

    # Add the endpoint methods (translated from base class patterns)
    body.extend(_build_endpoint_methods(cfg))

    # Add _empty_metrics helper
    body.append(_build_empty_metrics(cfg))

    return body


def _translate_method(
    cfg: TranslationConfig, method_node, py_name: str, extra_params: list[str]
) -> pyast.FunctionDef:
    """Translate a TS method to a Python method."""
    body_node = method_node.child_by_field_name("body")
    py_body = translate_block(body_node, cfg) if body_node else [pyast.Pass()]

    return pyast.FunctionDef(
        name=py_name,
        args=pyast.arguments(
            posonlyargs=[],
            args=[pyast.arg(arg="self")] + [pyast.arg(arg=p) for p in extra_params],
            vararg=None, kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[]
        ),
        body=py_body,
        decorator_list=[], returns=None
    )


def _build_empty_metrics(cfg: TranslationConfig) -> pyast.FunctionDef:
    """Build the _empty_metrics helper method."""
    zero = _call(_name("D"), [_const(0)])
    ret = pyast.Return(value=_call(_name("dict"), keywords=[
        pyast.keyword(arg="hasErrors", value=_name("has_errors")),
        pyast.keyword(arg="ti", value=zero),
        pyast.keyword(arg="td", value=zero),
        pyast.keyword(arg="tf", value=zero),
        pyast.keyword(arg="tl", value=zero),
        pyast.keyword(arg="quantity", value=zero),
        pyast.keyword(arg="_tnp", value=zero),
        pyast.keyword(arg="_tgp", value=zero),
        pyast.keyword(arg="_npp", value=zero),
        pyast.keyword(arg="_gpp", value=zero),
        pyast.keyword(arg="ibd", value=pyast.Dict(keys=[], values=[])),
        pyast.keyword(arg="vbd", value=pyast.Dict(keys=[], values=[])),
        pyast.keyword(arg="npd", value=pyast.Dict(keys=[], values=[])),
        pyast.keyword(arg="iad", value=pyast.Dict(keys=[], values=[])),
        pyast.keyword(arg="iv", value=zero),
        pyast.keyword(arg="mp", value=_const(0.0)),
        pyast.keyword(arg="ap", value=_const(0.0)),
    ]))
    return pyast.FunctionDef(
        name="_empty_metrics",
        args=pyast.arguments(
            posonlyargs=[],
            args=[pyast.arg(arg="self"), pyast.arg(arg="has_errors")],
            vararg=None, kwonlyargs=[], kw_defaults=[], kwarg=None,
            defaults=[_const(False)]
        ),
        body=[ret],
        decorator_list=[], returns=None
    )


def _build_endpoint_methods(cfg: TranslationConfig) -> list[pyast.stmt]:
    """Build the 6 API endpoint methods.

    These are derived from the base class logic in portfolio-calculator.ts.
    Each reads the TS class structure and generates equivalent Python using
    the _get_symbol_metrics method translated from the ROAI subclass.
    """
    from tt.endpoints import build_all_endpoints
    return build_all_endpoints(cfg)
