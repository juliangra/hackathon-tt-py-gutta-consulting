"""Transform Big.js patterns to Python Decimal.

Handles: new Big(x), .plus(), .minus(), .mul(), .div(), .eq(), .gt(), .lt(),
         .gte(), .lte(), .toNumber(), .toFixed(), .abs()
"""
from __future__ import annotations

import re


def transform_big_js(code: str) -> str:
    """Apply all Big.js transforms to a block of code."""
    code = _transform_constructors(code)
    code = _transform_method_chains(code)
    code = _transform_comparisons(code)
    code = _transform_conversions(code)
    return code


def _transform_constructors(code: str) -> str:
    # new Big(0) -> D(0)
    code = re.sub(r'new Big\((\d+)\)', r'D(\1)', code)
    # new Big(variable) -> D(str(variable))
    code = re.sub(r'new Big\(([a-zA-Z_]\w*(?:\.\w+)*)\)', r'D(str(\1))', code)
    return code


def _transform_method_chains(code: str) -> str:
    # .plus(x) -> + x  (but we need to handle chaining carefully)
    # .add(x) -> + x  (Big.js alias)
    code = re.sub(r'\.plus\(([^)]+)\)', r' + (\1)', code)
    code = re.sub(r'\.add\(([^)]+)\)', r' + (\1)', code)
    code = re.sub(r'\.minus\(([^)]+)\)', r' - (\1)', code)
    code = re.sub(r'\.mul\(([^)]+)\)', r' * (\1)', code)
    code = re.sub(r'\.div\(([^)]+)\)', r' / (\1)', code)
    code = re.sub(r'\.abs\(\)', r'.copy_abs()', code)
    return code


def _transform_comparisons(code: str) -> str:
    # .eq(0) -> == D(0)
    code = re.sub(r'\.eq\((\d+)\)', r' == D(\1)', code)
    code = re.sub(r'\.eq\(([^)]+)\)', r' == (\1)', code)
    code = re.sub(r'\.gt\((\d+)\)', r' > D(\1)', code)
    code = re.sub(r'\.gt\(([^)]+)\)', r' > (\1)', code)
    code = re.sub(r'\.gte\((\d+)\)', r' >= D(\1)', code)
    code = re.sub(r'\.gte\(([^)]+)\)', r' >= (\1)', code)
    code = re.sub(r'\.lt\((\d+)\)', r' < D(\1)', code)
    code = re.sub(r'\.lt\(([^)]+)\)', r' < (\1)', code)
    code = re.sub(r'\.lte\((\d+)\)', r' <= D(\1)', code)
    code = re.sub(r'\.lte\(([^)]+)\)', r' <= (\1)', code)
    return code


def _transform_conversions(code: str) -> str:
    # .toNumber() -> float(x)
    code = re.sub(r'(\w+(?:\.\w+)*)\.toNumber\(\)', r'float(\1)', code)
    # .toFixed(N) -> leave as is for now (round in Decimal)
    code = re.sub(r'\.toFixed\((\d+)\)', r'  # .toFixed(\1)', code)
    return code
