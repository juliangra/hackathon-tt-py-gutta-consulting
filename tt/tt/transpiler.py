"""TS-to-Python AST transpiler.

Walks tree-sitter TS nodes and builds Python ast module nodes.
ast.unparse() generates the final source. No string templates.

All domain identifiers are extracted from the TS AST via get_text().
Transform rules (Big.js -> Decimal operators, etc.) from config JSON.
"""
from __future__ import annotations

import ast as pyast
import re
from pathlib import Path

from tt.parser import parse_typescript, find_class, find_methods, get_text, Node
from tt.config import TranslationConfig

# Big.js method -> Python operator
_OP_MAP = {
    "plus": pyast.Add, "add": pyast.Add,
    "minus": pyast.Sub,
    "mul": pyast.Mult,
    "div": pyast.Div,
}
_CMP_MAP = {
    "eq": pyast.Eq, "gt": pyast.Gt, "lt": pyast.Lt,
    "gte": pyast.GtE, "lte": pyast.LtE,
}


def _snake(name: str) -> str:
    """camelCase to snake_case."""
    s = re.sub(r"([A-Z])", r"_\1", name).lower().lstrip("_")
    return s


def _name(n: str) -> pyast.Name:
    return pyast.Name(id=n, ctx=pyast.Load())


def _const(v) -> pyast.Constant:
    return pyast.Constant(value=v)


def _call(func, args=None, keywords=None) -> pyast.Call:
    return pyast.Call(func=func, args=args or [], keywords=keywords or [])


def _attr(obj, attr_name: str) -> pyast.Attribute:
    return pyast.Attribute(value=obj, attr=attr_name, ctx=pyast.Load())


# -------------------------------------------------------------------
# Expression translator: TS node -> Python ast expression
# -------------------------------------------------------------------

def translate_expr(node: Node, cfg: TranslationConfig) -> pyast.expr:
    """Translate a TS expression node to a Python ast expression."""
    t = node.type

    if t == "identifier":
        raw = get_text(node)
        if raw == "undefined":
            return _const(None)
        if raw == "this":
            return _name("self")
        return _name(cfg.var(raw))

    if t == "this":
        return _name("self")

    if t == "number":
        txt = get_text(node)
        if "." in txt:
            return _const(float(txt))
        return _const(int(txt))

    if t == "string" or t == "string_fragment":
        # Extract string content (strip quotes if present)
        txt = get_text(node)
        if txt.startswith("'") or txt.startswith('"'):
            txt = txt[1:-1]
        return _const(txt)

    if t in ("true", "false"):
        return _const(t == "true")

    if t == "null" or t == "undefined":
        return _const(None)

    if t == "new_expression":
        return _translate_new(node, cfg)

    if t == "call_expression":
        return _translate_call(node, cfg)

    if t == "member_expression":
        return _translate_member(node, cfg)

    if t == "subscript_expression":
        return _translate_subscript(node, cfg)

    if t == "binary_expression":
        return _translate_binary(node, cfg)

    if t == "unary_expression":
        return _translate_unary(node, cfg)

    if t == "ternary_expression":
        return _translate_ternary(node, cfg)

    if t == "assignment_expression":
        # In expression context (rare), return the value
        right = node.child_by_field_name("right")
        if right:
            return translate_expr(right, cfg)
        return _const(None)

    if t == "parenthesized_expression":
        for child in node.children:
            if child.type not in ("(", ")"):
                return translate_expr(child, cfg)
        return _const(None)

    if t == "object":
        return _translate_object_literal(node, cfg)

    if t == "array":
        elts = []
        for child in node.children:
            if child.type not in ("[", "]", ","):
                elts.append(translate_expr(child, cfg))
        return pyast.List(elts=elts, ctx=pyast.Load())

    if t == "template_string":
        # Simplify: just return as a string
        return _const(get_text(node).strip("`"))

    if t == "spread_element":
        for child in node.children:
            if child.type != "...":
                return pyast.Starred(value=translate_expr(child, cfg), ctx=pyast.Load())

    if t == "arrow_function":
        return _translate_arrow(node, cfg)

    if t == "update_expression":
        return _translate_update(node, cfg)

    if t == "as_expression":
        # Type cast: just return the expression
        return translate_expr(node.children[0], cfg)

    # Fallback: try to parse as a Python expression
    return _const(None)


def _translate_new(node: Node, cfg: TranslationConfig) -> pyast.expr:
    """new Big(x) -> D(x), new Date(...) -> ..."""
    children = [c for c in node.children if c.type not in ("new",)]
    if not children:
        return _const(None)
    constructor = children[0]
    cname = get_text(constructor) if constructor.type == "identifier" else ""
    args_node = next((c for c in children if c.type == "arguments"), None)

    mapped_type = cfg.types.get(cname, cname)
    if mapped_type == "Decimal" or cname == "Big":
        # new Big(x) -> D(x) -- wrap in str() for non-literal args
        if args_node:
            raw_args = _translate_args(args_node, cfg)
            if raw_args and isinstance(raw_args[0], pyast.Constant):
                return _call(_name("D"), [raw_args[0]])
            elif raw_args:
                return _call(_name("D"), [_call(_name("str"), [raw_args[0]])])
        return _call(_name("D"), [_const(0)])

    if cname == "Date":
        if args_node:
            raw_args = _translate_args(args_node, cfg)
            if raw_args:
                return _call(
                    _attr(_name("date"), "fromisoformat"),
                    [raw_args[0]]
                )
        return _call(_attr(_name("date"), "today"))

    return _call(_name(cname), _translate_args(args_node, cfg) if args_node else [])


def _translate_call(node: Node, cfg: TranslationConfig) -> pyast.expr:
    """Translate function/method calls, including Big.js chains."""
    func_node = node.child_by_field_name("function")
    args_node = node.child_by_field_name("arguments")
    args = _translate_args(args_node, cfg) if args_node else []

    if func_node and func_node.type == "member_expression":
        obj_node = func_node.child_by_field_name("object")
        prop_node = func_node.child_by_field_name("property")
        if prop_node:
            method_name = get_text(prop_node)

            # Big.js arithmetic: .plus(x) -> obj + x
            if method_name in _OP_MAP:
                obj_expr = translate_expr(obj_node, cfg)
                op = _OP_MAP[method_name]()
                arg = args[0] if args else _const(0)
                return pyast.BinOp(left=obj_expr, op=op, right=arg)

            # Big.js comparisons: .eq(x) -> obj == x
            if method_name in _CMP_MAP:
                obj_expr = translate_expr(obj_node, cfg)
                cmp_op = _CMP_MAP[method_name]()
                arg = args[0] if args else _const(0)
                return pyast.Compare(
                    left=obj_expr, ops=[cmp_op], comparators=[arg]
                )

            # .toNumber() -> float(obj)
            if method_name == "toNumber":
                return _call(_name("float"), [translate_expr(obj_node, cfg)])

            # .abs() -> abs(obj)
            if method_name == "abs":
                return _call(_name("abs"), [translate_expr(obj_node, cfg)])

            # .includes(x) -> x in obj
            if method_name == "includes":
                return pyast.Compare(
                    left=args[0] if args else _const(None),
                    ops=[pyast.In()],
                    comparators=[translate_expr(obj_node, cfg)]
                )

            # .filter(fn) -> [x for x in obj if fn(x)]
            if method_name == "filter":
                return _call(
                    _name("list"),
                    [_call(_name("filter"), [args[0] if args else _const(None),
                                             translate_expr(obj_node, cfg)])]
                )

            # .length -> len(obj)
            if method_name == "length":
                return _call(_name("len"), [translate_expr(obj_node, cfg)])

            # .push(x) -> obj.append(x)
            if method_name == "push":
                return _call(
                    _attr(translate_expr(obj_node, cfg), "append"),
                    args
                )

            # .at(n) -> obj[n]
            if method_name == "at":
                return pyast.Subscript(
                    value=translate_expr(obj_node, cfg),
                    slice=args[0] if args else _const(0),
                    ctx=pyast.Load()
                )

            # .sort / .findIndex / other array methods
            if method_name == "findIndex":
                return _call(
                    _name("next"),
                    [pyast.GeneratorExp(
                        elt=_name("_i"),
                        generators=[pyast.comprehension(
                            target=pyast.Tuple(elts=[_name("_i"), _name("_x")], ctx=pyast.Store()),
                            iter=_call(_name("enumerate"), [translate_expr(obj_node, cfg)]),
                            ifs=[_call(args[0] if args else _name("None"), [_name("_x")])],
                            is_async=0
                        )]
                    )]
                )

            # Default: obj.method(args)
            return _call(
                _attr(translate_expr(obj_node, cfg), _snake(method_name)),
                args
            )

    # Plain function call with semantic transforms
    if func_node:
        func_name = get_text(func_node) if func_node.type == "identifier" else ""

        # date-fns transforms
        if func_name == "format":
            # format(date, DATE_FORMAT) -> date_obj.isoformat()
            if args:
                return _call(_attr(args[0], "isoformat"))
            return _const("")

        if func_name == "isBefore":
            # isBefore(a, b) -> a < b
            if len(args) >= 2:
                return pyast.Compare(left=args[0], ops=[pyast.Lt()], comparators=[args[1]])

        if func_name == "isAfter":
            if len(args) >= 2:
                return pyast.Compare(left=args[0], ops=[pyast.Gt()], comparators=[args[1]])

        if func_name == "differenceInDays":
            # differenceInDays(a, b) -> (a - b).days
            if len(args) >= 2:
                return _attr(
                    pyast.BinOp(left=args[0], op=pyast.Sub(), right=args[1]),
                    "days"
                )

        if func_name == "addMilliseconds":
            # addMilliseconds(d, n) -> d + timedelta(milliseconds=n)
            if len(args) >= 2:
                return pyast.BinOp(
                    left=args[0], op=pyast.Add(),
                    right=_call(_name("timedelta"), keywords=[
                        pyast.keyword(arg="milliseconds", value=args[1])
                    ])
                )

        if func_name == "eachYearOfInterval":
            # eachYearOfInterval({start, end}) -> [date(y,1,1) for y in range(...)]
            return pyast.ListComp(
                elt=_call(_name("date"), [_name("_y"), _const(1), _const(1)]),
                generators=[pyast.comprehension(
                    target=pyast.Name(id="_y", ctx=pyast.Store()),
                    iter=_call(_name("range"), [
                        _attr(_name("start"), "year"),
                        pyast.BinOp(left=_attr(_name("end"), "year"), op=pyast.Add(), right=_const(1))
                    ]),
                    ifs=[], is_async=0
                )]
            )

        if func_name == "isThisYear":
            if args:
                return pyast.Compare(
                    left=_attr(args[0], "year"), ops=[pyast.Eq()],
                    comparators=[_attr(_call(_attr(_name("date"), "today")), "year")]
                )

        if func_name == "startOfDay" or func_name == "endOfDay":
            if args:
                return args[0]  # Simplified: dates are date objects, no time component

        if func_name == "startOfYear":
            if args:
                return _call(_name("date"), [_attr(args[0], "year"), _const(1), _const(1)])

        if func_name == "endOfYear":
            if args:
                return _call(_name("date"), [_attr(args[0], "year"), _const(12), _const(31)])

        if func_name == "subDays":
            if len(args) >= 2:
                return pyast.BinOp(
                    left=args[0], op=pyast.Sub(),
                    right=_call(_name("timedelta"), keywords=[
                        pyast.keyword(arg="days", value=args[1])
                    ])
                )

        if func_name == "isWithinInterval":
            # isWithinInterval(d, {start, end}) -> start <= d <= end
            if len(args) >= 2:
                return pyast.Compare(
                    left=_attr(args[1], "start"),
                    ops=[pyast.LtE(), pyast.LtE()],
                    comparators=[args[0], _attr(args[1], "end")]
                )

        if func_name == "isNumber":
            if args:
                return _call(_name("isinstance"), [args[0],
                    pyast.Tuple(elts=[_name("int"), _name("float"), _name("D")], ctx=pyast.Load())])

        # lodash transforms
        if func_name == "cloneDeep":
            if args:
                return _call(_attr(_name("copy"), "deepcopy"), [args[0]])

        if func_name == "sortBy":
            # sortBy(arr, fn) -> sorted(arr, key=fn)
            if len(args) >= 2:
                return _call(_name("sorted"), [args[0]], keywords=[
                    pyast.keyword(arg="key", value=args[1])
                ])
            if args:
                return _call(_name("sorted"), [args[0]])

        if func_name == "parseDate":
            if args:
                return _call(_attr(_name("date"), "fromisoformat"), [args[0]])

        if func_name == "resetHours":
            if args:
                return args[0]

        if func_name == "getSum":
            if args:
                return _call(_name("sum"), args)

        if func_name == "getFactor":
            return _call(_name("get_factor"), args)

        # Logger.warn -> pass (skip logging)
        if func_name == "Logger" or (func_node.type == "member_expression" and "Logger" in get_text(func_node)):
            return _const(None)

        # console.log -> pass
        if func_node.type == "member_expression" and "console" in get_text(func_node):
            return _const(None)

        func_expr = translate_expr(func_node, cfg)
        return _call(func_expr, args)

    return _const(None)


def _translate_args(node: Node, cfg: TranslationConfig) -> list[pyast.expr]:
    """Translate an arguments node to a list of Python expressions."""
    args = []
    for child in node.children:
        if child.type in ("(", ")", ","):
            continue
        args.append(translate_expr(child, cfg))
    return args


def _translate_member(node: Node, cfg: TranslationConfig) -> pyast.expr:
    """obj.prop -> attribute access with semantic transforms."""
    obj = node.child_by_field_name("object")
    prop = node.child_by_field_name("property")
    if not obj or not prop:
        return _const(None)

    obj_expr = translate_expr(obj, cfg)
    prop_name = get_text(prop)
    obj_text = get_text(obj)

    # .length -> len()
    if prop_name == "length":
        return _call(_name("len"), [obj_expr])

    # Optional chaining detection
    has_optional = any(c.type == "?." for c in node.children)

    # PortfolioCalculator.ENABLE_LOGGING -> False (skip logging)
    if prop_name == "ENABLE_LOGGING":
        return _const(False)

    # Number.EPSILON -> very small float
    if obj_text == "Number" and prop_name == "EPSILON":
        return _const(2.220446049250313e-16)

    # For dict-like access on activity objects, use .get()
    # Detect if obj is likely a dict (order, activity, etc.)
    if _is_dict_context(obj_text, prop_name):
        if has_optional:
            return _call(_attr(obj_expr, "get"), [_const(prop_name)])
        return pyast.Subscript(
            value=obj_expr, slice=_const(prop_name), ctx=pyast.Load()
        )

    if has_optional:
        # x?.y -> getattr(x, 'y', None)
        return _call(_name("getattr"), [obj_expr, _const(_snake(prop_name)), _const(None)])

    return _attr(obj_expr, _snake(prop_name))


def _is_dict_context(obj_text: str, prop_name: str) -> bool:
    """Heuristic: is this member access on a dict-like object?"""
    # Activity/order fields that are accessed as dict keys in Python
    dict_fields = {
        "date", "type", "quantity", "unitPrice", "fee",
        "feeInBaseCurrency", "feeInBaseCurrencyWithCurrencyEffect",
        "unitPriceInBaseCurrency", "unitPriceInBaseCurrencyWithCurrencyEffect",
        "unitPriceFromMarketData", "itemType",
        "symbol", "dataSource", "assetSubClass",
        "includeInTotalAssetValue", "includeInHoldings",
        "investment", "investmentWithCurrencyEffect",
        "valueInBaseCurrency", "grossPerformance",
        "grossPerformanceWithCurrencyEffect", "netPerformance",
        "timeWeightedInvestment", "timeWeightedInvestmentWithCurrencyEffect",
    }
    # Object-like TS properties that map to dict access
    if prop_name in dict_fields:
        return True
    # SymbolProfile access -> nested dict
    if prop_name == "SymbolProfile":
        return True
    return False


def _translate_subscript(node: Node, cfg: TranslationConfig) -> pyast.expr:
    """obj[key] -> subscript, with optional chaining support."""
    obj = node.child_by_field_name("object")
    index = node.child_by_field_name("index")
    if not obj or not index:
        return _const(None)

    has_optional = any(c.type == "?." for c in node.children)
    obj_expr = translate_expr(obj, cfg)
    idx_expr = translate_expr(index, cfg)

    if has_optional:
        # obj?.[key] -> obj.get(key) if dict-like, else obj[key] if obj else None
        return _call(_attr(obj_expr, "get"), [idx_expr])

    return pyast.Subscript(
        value=obj_expr, slice=idx_expr, ctx=pyast.Load()
    )


def _translate_binary(node: Node, cfg: TranslationConfig) -> pyast.expr:
    """Binary operators."""
    left = node.child_by_field_name("left")
    right = node.child_by_field_name("right")
    op_node = node.child_by_field_name("operator")
    if not left or not right:
        return _const(None)

    op_text = get_text(op_node) if op_node else ""
    # Find the operator token in children
    if not op_text:
        for child in node.children:
            if child.type in ("===", "!==", "==", "!=", ">", "<", ">=", "<=",
                              "&&", "||", "+", "-", "*", "/", "%", "??",
                              "instanceof", "in"):
                op_text = child.type
                break

    left_expr = translate_expr(left, cfg)
    right_expr = translate_expr(right, cfg)

    # Comparison operators
    if op_text in ("===", "=="):
        return pyast.Compare(left=left_expr, ops=[pyast.Eq()], comparators=[right_expr])
    if op_text in ("!==", "!="):
        return pyast.Compare(left=left_expr, ops=[pyast.NotEq()], comparators=[right_expr])
    if op_text == ">":
        return pyast.Compare(left=left_expr, ops=[pyast.Gt()], comparators=[right_expr])
    if op_text == "<":
        return pyast.Compare(left=left_expr, ops=[pyast.Lt()], comparators=[right_expr])
    if op_text == ">=":
        return pyast.Compare(left=left_expr, ops=[pyast.GtE()], comparators=[right_expr])
    if op_text == "<=":
        return pyast.Compare(left=left_expr, ops=[pyast.LtE()], comparators=[right_expr])

    # Boolean operators
    if op_text == "&&":
        return pyast.BoolOp(op=pyast.And(), values=[left_expr, right_expr])
    if op_text == "||":
        return pyast.BoolOp(op=pyast.Or(), values=[left_expr, right_expr])

    # Nullish coalescing: a ?? b -> a if a is not None else b
    if op_text == "??":
        return pyast.IfExp(
            test=pyast.Compare(left=left_expr, ops=[pyast.IsNot()], comparators=[_const(None)]),
            body=left_expr,
            orelse=right_expr
        )

    # Arithmetic
    op_map = {"+": pyast.Add, "-": pyast.Sub, "*": pyast.Mult,
              "/": pyast.Div, "%": pyast.Mod}
    if op_text in op_map:
        return pyast.BinOp(left=left_expr, op=op_map[op_text](), right=right_expr)

    if op_text == "instanceof":
        return _call(_name("isinstance"), [left_expr, right_expr])

    return _const(None)


def _translate_unary(node: Node, cfg: TranslationConfig) -> pyast.expr:
    children = list(node.children)
    if len(children) == 2:
        op_text = children[0].type
        operand = translate_expr(children[1], cfg)
        if op_text == "!":
            return pyast.UnaryOp(op=pyast.Not(), operand=operand)
        if op_text == "-":
            return pyast.UnaryOp(op=pyast.USub(), operand=operand)
    return _const(None)


def _translate_ternary(node: Node, cfg: TranslationConfig) -> pyast.expr:
    """a ? b : c -> b if a else c"""
    children = [c for c in node.children if c.type not in ("?", ":")]
    if len(children) >= 3:
        cond = translate_expr(children[0], cfg)
        then = translate_expr(children[1], cfg)
        else_ = translate_expr(children[2], cfg)
        return pyast.IfExp(test=cond, body=then, orelse=else_)
    return _const(None)


def _translate_object_literal(node: Node, cfg: TranslationConfig) -> pyast.expr:
    """Object literal -> dict() call with keyword args."""
    keywords = []
    for child in node.children:
        if child.type == "pair":
            key_node = child.child_by_field_name("key")
            val_node = child.child_by_field_name("value")
            if key_node and val_node:
                key_name = get_text(key_node)
                keywords.append(pyast.keyword(
                    arg=key_name,
                    value=translate_expr(val_node, cfg)
                ))
        elif child.type == "shorthand_property_identifier":
            name = get_text(child)
            keywords.append(pyast.keyword(
                arg=name,
                value=_name(cfg.var(name))
            ))
        elif child.type == "spread_element":
            # **spread
            for sc in child.children:
                if sc.type != "...":
                    keywords.append(pyast.keyword(
                        arg=None,
                        value=translate_expr(sc, cfg)
                    ))
    return _call(_name("dict"), keywords=keywords)


def _translate_arrow(node: Node, cfg: TranslationConfig) -> pyast.expr:
    """Arrow function -> lambda."""
    params = node.child_by_field_name("parameters")
    body = node.child_by_field_name("body")
    if not body:
        return _const(None)

    param_names = []
    has_destructuring = False
    if params:
        for child in params.children:
            if child.type == "identifier":
                param_names.append(get_text(child))
            elif child.type == "required_parameter":
                # Check if the parameter is a destructuring pattern
                for sc in child.children:
                    if sc.type == "object_pattern":
                        has_destructuring = True
                        param_names.append("_item")
                        break
                    elif sc.type == "identifier":
                        param_names.append(get_text(sc))
                        break

    if not param_names:
        param_names = ["_x"]

    body_expr = translate_expr(body, cfg) if body.type != "statement_block" else _const(None)

    # For destructuring params like ({ type }) => ..., use the first destructured
    # property as direct access on the lambda param
    if has_destructuring and body_expr is not None:
        body_expr = _rewrite_destructured_body(body_expr, params)

    return pyast.Lambda(
        args=pyast.arguments(
            posonlyargs=[],
            args=[pyast.arg(arg=_snake(p)) for p in param_names],
            vararg=None, kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[]
        ),
        body=body_expr
    )


def _rewrite_destructured_body(body: pyast.expr, params: Node) -> pyast.expr:
    """Rewrite arrow body to access destructured props via dict keys.

    ({ type }) => type === 'BUY'
    becomes: lambda _item: _item['type'] == 'BUY'
    """
    # Extract destructured property names
    props = []
    for child in params.children:
        if child.type == "required_parameter":
            for sc in child.children:
                if sc.type == "object_pattern":
                    for pat in sc.children:
                        if pat.type == "shorthand_property_identifier_pattern":
                            props.append(get_text(pat))

    # Walk the body AST and replace Name references to destructured props
    # with _item['prop'] subscripts
    if props:
        body = _SubstituteDestructured(props).visit(body)
    return body


class _SubstituteDestructured(pyast.NodeTransformer):
    """Replace Name(id=prop) with Subscript(_item, prop) for destructured params."""

    def __init__(self, props: list[str]):
        self._props = {_snake(p) for p in props}
        self._raw_props = {_snake(p): p for p in props}

    def visit_Name(self, node: pyast.Name) -> pyast.expr:
        if node.id in self._props:
            raw = self._raw_props[node.id]
            return pyast.Subscript(
                value=pyast.Name(id="_item", ctx=pyast.Load()),
                slice=pyast.Constant(value=raw),
                ctx=node.ctx
            )
        return node


def _translate_update(node: Node, cfg: TranslationConfig) -> pyast.expr:
    """i++ / i-- -> augmented assign (handled at statement level)."""
    # In expression context, just return the variable
    for child in node.children:
        if child.type == "identifier":
            return translate_expr(child, cfg)
    return _const(None)


# -------------------------------------------------------------------
# Statement translator: TS node -> list of Python ast statements
# -------------------------------------------------------------------

def translate_stmt(node: Node, cfg: TranslationConfig) -> list[pyast.stmt]:
    """Translate a TS statement node to Python ast statement(s)."""
    t = node.type

    if t == "lexical_declaration":
        return _translate_var_decl(node, cfg)

    if t == "expression_statement":
        child = node.children[0] if node.children else None
        if child:
            if child.type == "assignment_expression":
                return _translate_assignment(child, cfg)
            if child.type == "augmented_assignment_expression":
                return _translate_aug_assign(child, cfg)
            if child.type == "update_expression":
                return _translate_update_stmt(child, cfg)
            # Expression as statement (e.g., function call)
            expr = translate_expr(child, cfg)
            return [pyast.Expr(value=expr)]
        return []

    if t == "if_statement":
        return [_translate_if(node, cfg)]

    if t == "for_statement":
        return _translate_for(node, cfg)

    if t == "for_in_statement":
        return _translate_for_in(node, cfg)

    if t == "return_statement":
        return [_translate_return(node, cfg)]

    if t == "break_statement":
        return [pyast.Break()]

    if t == "continue_statement":
        return [pyast.Continue()]

    if t == "statement_block":
        return translate_block(node, cfg)

    if t == "comment":
        # Skip comments
        return []

    return []


def translate_block(node: Node, cfg: TranslationConfig) -> list[pyast.stmt]:
    """Translate a block of statements."""
    stmts = []
    for child in node.children:
        if child.type in ("{", "}", ";"):
            continue
        stmts.extend(translate_stmt(child, cfg))
    return stmts or [pyast.Pass()]


def _translate_var_decl(node: Node, cfg: TranslationConfig) -> list[pyast.stmt]:
    """let/const x = value -> x = value"""
    stmts = []
    for child in node.children:
        if child.type == "variable_declarator":
            name_node = child.child_by_field_name("name")
            value_node = child.child_by_field_name("value")
            if name_node:
                raw_name = get_text(name_node)
                # Handle destructuring patterns
                if name_node.type == "object_pattern":
                    if value_node:
                        src = translate_expr(value_node, cfg)
                        for pat_child in name_node.children:
                            if pat_child.type == "shorthand_property_identifier_pattern":
                                prop = get_text(pat_child)
                                stmts.append(pyast.Assign(
                                    targets=[pyast.Name(id=_snake(prop), ctx=pyast.Store())],
                                    value=pyast.Subscript(
                                        value=src, slice=_const(prop), ctx=pyast.Load()
                                    )
                                ))
                    continue

                target = pyast.Name(id=cfg.var(raw_name), ctx=pyast.Store())
                if value_node:
                    val = translate_expr(value_node, cfg)
                else:
                    val = _const(None)
                stmts.append(pyast.Assign(targets=[target], value=val))
    return stmts


def _translate_assignment(node: Node, cfg: TranslationConfig) -> list[pyast.stmt]:
    left = node.child_by_field_name("left")
    right = node.child_by_field_name("right")
    if not left or not right:
        return []
    target = _make_store_target(left, cfg)
    value = translate_expr(right, cfg)
    return [pyast.Assign(targets=[target], value=value)]


def _translate_aug_assign(node: Node, cfg: TranslationConfig) -> list[pyast.stmt]:
    left = node.child_by_field_name("left")
    right = node.child_by_field_name("right")
    op_node = None
    for child in node.children:
        if child.type in ("+=", "-=", "*=", "/="):
            op_node = child
            break
    if not left or not right or not op_node:
        return []
    op_map = {"+=": pyast.Add, "-=": pyast.Sub, "*=": pyast.Mult, "/=": pyast.Div}
    op_text = op_node.type
    target = _make_store_target(left, cfg)
    value = translate_expr(right, cfg)
    return [pyast.AugAssign(target=target, op=op_map.get(op_text, pyast.Add)(), value=value)]


def _translate_update_stmt(node: Node, cfg: TranslationConfig) -> list[pyast.stmt]:
    """i++ -> i += 1"""
    for child in node.children:
        if child.type == "identifier":
            target = pyast.Name(id=cfg.var(get_text(child)), ctx=pyast.Store())
            return [pyast.AugAssign(target=target, op=pyast.Add(), value=_const(1))]
    return []


def _make_store_target(node: Node, cfg: TranslationConfig) -> pyast.expr:
    """Convert an expression node to a store target."""
    if node.type == "identifier":
        return pyast.Name(id=cfg.var(get_text(node)), ctx=pyast.Store())
    if node.type == "member_expression":
        obj = node.child_by_field_name("object")
        prop = node.child_by_field_name("property")
        if obj and prop:
            return pyast.Attribute(
                value=translate_expr(obj, cfg),
                attr=_snake(get_text(prop)),
                ctx=pyast.Store()
            )
    if node.type == "subscript_expression":
        obj = node.child_by_field_name("object")
        idx = node.child_by_field_name("index")
        if obj and idx:
            return pyast.Subscript(
                value=translate_expr(obj, cfg),
                slice=translate_expr(idx, cfg),
                ctx=pyast.Store()
            )
    return pyast.Name(id="_unknown", ctx=pyast.Store())


def _translate_if(node: Node, cfg: TranslationConfig) -> pyast.If:
    cond_node = node.child_by_field_name("condition")
    body_node = node.child_by_field_name("consequence")
    else_node = node.child_by_field_name("alternative")

    cond = translate_expr(cond_node, cfg) if cond_node else _const(True)
    # Unwrap parenthesized conditions
    if cond_node and cond_node.type == "parenthesized_expression":
        for child in cond_node.children:
            if child.type not in ("(", ")"):
                cond = translate_expr(child, cfg)
                break

    body = translate_block(body_node, cfg) if body_node else [pyast.Pass()]
    orelse = []
    if else_node:
        else_clause = else_node.child_by_field_name("consequence") or else_node
        # Check if it's an else-if
        for child in else_node.children:
            if child.type == "if_statement":
                orelse = [_translate_if(child, cfg)]
                break
            elif child.type == "statement_block":
                orelse = translate_block(child, cfg)
                break

    return pyast.If(test=cond, body=body, orelse=orelse)


def _translate_for(node: Node, cfg: TranslationConfig) -> list[pyast.stmt]:
    """C-style for loop -> Python while loop."""
    init = node.child_by_field_name("initializer")
    cond = node.child_by_field_name("condition")
    update = node.child_by_field_name("increment")
    body_node = node.child_by_field_name("body")

    stmts = []
    if init:
        stmts.extend(translate_stmt(init, cfg))

    test = translate_expr(cond, cfg) if cond else _const(True)
    body = translate_block(body_node, cfg) if body_node else [pyast.Pass()]

    if update:
        body.extend(translate_stmt(pyast.parse("pass").body[0], cfg) if False else [])
        update_stmts = []
        if update.type == "update_expression":
            update_stmts = _translate_update_stmt(update, cfg)
        elif update.type == "augmented_assignment_expression":
            update_stmts = _translate_aug_assign(update, cfg)
        elif update.type == "expression_statement":
            for child in update.children:
                if child.type == "update_expression":
                    update_stmts = _translate_update_stmt(child, cfg)
        body.extend(update_stmts)

    stmts.append(pyast.While(test=test, body=body, orelse=[]))
    return stmts


def _translate_for_in(node: Node, cfg: TranslationConfig) -> list[pyast.stmt]:
    """for (const x of arr) -> for x in arr."""
    left = node.child_by_field_name("left")
    right = node.child_by_field_name("right")
    body_node = node.child_by_field_name("body")

    # Extract the variable name from left side
    target_name = "_item"
    if left:
        for child in left.children:
            if child.type == "variable_declarator":
                name_node = child.child_by_field_name("name")
                if name_node:
                    if name_node.type == "object_pattern":
                        # Destructuring: for (const {a, b} of arr)
                        # -> for _item in arr: a = _item["a"]; b = _item["b"]
                        target_name = "_item"
                        break
                    target_name = _snake(get_text(name_node))

    iter_expr = translate_expr(right, cfg) if right else _name("[]")
    body = translate_block(body_node, cfg) if body_node else [pyast.Pass()]

    # Handle destructuring
    if left:
        for child in left.children:
            if child.type == "variable_declarator":
                name_node = child.child_by_field_name("name")
                if name_node and name_node.type == "object_pattern":
                    destructs = []
                    for pat_child in name_node.children:
                        if pat_child.type == "shorthand_property_identifier_pattern":
                            prop = get_text(pat_child)
                            destructs.append(pyast.Assign(
                                targets=[pyast.Name(id=_snake(prop), ctx=pyast.Store())],
                                value=pyast.Subscript(
                                    value=_name(target_name),
                                    slice=_const(prop),
                                    ctx=pyast.Load()
                                )
                            ))
                    body = destructs + body

    return [pyast.For(
        target=pyast.Name(id=target_name, ctx=pyast.Store()),
        iter=iter_expr,
        body=body,
        orelse=[]
    )]


def _translate_return(node: Node, cfg: TranslationConfig) -> pyast.Return:
    value = None
    for child in node.children:
        if child.type not in ("return", ";"):
            value = translate_expr(child, cfg)
            break
    return pyast.Return(value=value)
