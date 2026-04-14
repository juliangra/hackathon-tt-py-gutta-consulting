"""Stdlib transforms: date-fns, lodash, array methods."""
from __future__ import annotations

import ast as pyast

from tt.transpiler import _name, _const, _call, _attr, translate_expr
from tt.parser import get_text, Node
from tt.config import TranslationConfig


def try_date_fns(func_name: str, args: list) -> pyast.expr | None:
    """Handle date-fns function calls."""
    if func_name == "format":
        return _call(_attr(args[0], "isoformat")) if args else _const("")
    if func_name == "isBefore" and len(args) >= 2:
        return pyast.Compare(left=args[0], ops=[pyast.Lt()], comparators=[args[1]])
    if func_name == "isAfter" and len(args) >= 2:
        return pyast.Compare(left=args[0], ops=[pyast.Gt()], comparators=[args[1]])
    if func_name == "differenceInDays" and len(args) >= 2:
        return _attr(pyast.BinOp(left=args[0], op=pyast.Sub(), right=args[1]), "days")
    if func_name == "addMilliseconds" and len(args) >= 2:
        return pyast.BinOp(left=args[0], op=pyast.Add(),
            right=_call(_name("timedelta"), keywords=[pyast.keyword(arg="milliseconds", value=args[1])]))
    if func_name == "eachYearOfInterval":
        return pyast.ListComp(
            elt=_call(_name("date"), [_name("_y"), _const(1), _const(1)]),
            generators=[pyast.comprehension(
                target=pyast.Name(id="_y", ctx=pyast.Store()),
                iter=_call(_name("range"), [_attr(_name("start"), "year"),
                    pyast.BinOp(left=_attr(_name("end"), "year"), op=pyast.Add(), right=_const(1))]),
                ifs=[], is_async=0)])
    if func_name == "isThisYear" and args:
        return pyast.Compare(left=_attr(args[0], "year"), ops=[pyast.Eq()],
            comparators=[_attr(_call(_attr(_name("date"), "today")), "year")])
    if func_name in ("startOfDay", "endOfDay") and args:
        return args[0]
    if func_name == "startOfYear" and args:
        return _call(_name("date"), [_attr(args[0], "year"), _const(1), _const(1)])
    if func_name == "endOfYear" and args:
        return _call(_name("date"), [_attr(args[0], "year"), _const(12), _const(31)])
    if func_name == "subDays" and len(args) >= 2:
        return pyast.BinOp(left=args[0], op=pyast.Sub(),
            right=_call(_name("timedelta"), keywords=[pyast.keyword(arg="days", value=args[1])]))
    if func_name == "isWithinInterval" and len(args) >= 2:
        return pyast.Compare(left=_attr(args[1], "start"),
            ops=[pyast.LtE(), pyast.LtE()], comparators=[args[0], _attr(args[1], "end")])
    if func_name == "isNumber" and args:
        return _call(_name("isinstance"), [args[0],
            pyast.Tuple(elts=[_name("int"), _name("float"), _name("D")], ctx=pyast.Load())])
    return None


def try_lodash(func_name: str, args: list, func_node, cfg: TranslationConfig) -> pyast.expr | None:
    """Handle lodash and other known function calls."""
    if func_name == "cloneDeep" and args:
        return _call(_attr(_name("copy"), "deepcopy"), [args[0]])
    if func_name == "sortBy":
        if len(args) >= 2:
            return _call(_name("sorted"), [args[0]], keywords=[pyast.keyword(arg="key", value=args[1])])
        if args:
            return _call(_name("sorted"), [args[0]])
    if func_name == "parseDate" and args:
        return _call(_attr(_name("date"), "fromisoformat"), [args[0]])
    if func_name in ("resetHours",) and args:
        return args[0]
    if func_name == "getSum" and args:
        return _call(_name("sum"), args)
    if func_name == "getFactor":
        return _call(_name("get_factor"), args)
    full_text = get_text(func_node) if func_node else ""
    if "Logger" in full_text or "console" in full_text:
        return _const(None)
    return None


def try_array_method(name: str, obj_node: Node, args: list, cfg) -> pyast.expr | None:
    """Handle array/collection method calls."""
    if name == "includes":
        return pyast.Compare(left=args[0] if args else _const(None),
            ops=[pyast.In()], comparators=[translate_expr(obj_node, cfg)])
    if name == "filter":
        return _call(_name("list"), [_call(_name("filter"),
            [args[0] if args else _const(None), translate_expr(obj_node, cfg)])])
    if name == "length":
        return _call(_name("len"), [translate_expr(obj_node, cfg)])
    if name == "push":
        return _call(_attr(translate_expr(obj_node, cfg), "append"), args)
    if name == "at":
        return pyast.Subscript(value=translate_expr(obj_node, cfg),
            slice=args[0] if args else _const(0), ctx=pyast.Load())
    if name == "findIndex":
        return _call(_name("next"), [pyast.GeneratorExp(elt=_name("_i"),
            generators=[pyast.comprehension(
                target=pyast.Tuple(elts=[_name("_i"), _name("_x")], ctx=pyast.Store()),
                iter=_call(_name("enumerate"), [translate_expr(obj_node, cfg)]),
                ifs=[_call(args[0] if args else _name("None"), [_name("_x")])],
                is_async=0)])])
    return None
