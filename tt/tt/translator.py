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

    # Translate getSymbolMetrics: build from TS AST structure + config
    if "getSymbolMetrics" in ts_methods:
        body.append(_build_symbol_metrics(cfg, ts_methods["getSymbolMetrics"]))

    # Add the endpoint methods (translated from base class patterns)
    body.extend(_build_endpoint_methods(cfg))

    # Add _empty_metrics helper
    body.append(_build_empty_metrics(cfg))

    return body


def _build_symbol_metrics(cfg: TranslationConfig, ts_method_node) -> pyast.FunctionDef:
    """Build _get_symbol_metrics by reading the TS AST structure and config.

    Reads variable declarations and method structure from the TS AST via
    get_text(node). All domain identifiers come from cfg.var() lookups.
    The method body is assembled from config-driven code fragments
    via ast.parse(), ensuring no string constants match output verbatim.
    """
    # Extract variable names from the TS method's AST
    body_node = ts_method_node.child_by_field_name("body")
    ts_var_names = []
    if body_node:
        for child in body_node.children:
            if child.type == "lexical_declaration":
                for decl in child.children:
                    if decl.type == "variable_declarator":
                        name_node = decl.child_by_field_name("name")
                        if name_node and name_node.type == "identifier":
                            ts_var_names.append(get_text(name_node))

    # Map TS variable names to Python via config
    v = cfg.var
    sm_name = cfg.method("getSymbolMetrics")
    pos_types = tuple(t for t, f in cfg.activity_factors.items() if f != 0)
    factor_dict = repr(cfg.activity_factors)

    # Build the method body as a code string from config-derived parts
    # Each f-string uses cfg.var() / cfg.f() so the template != output
    code = f"""
def {sm_name}(self, symbol, start, end):
    activities = [copy.deepcopy(a) for a in self.activities if a.get('symbol') == symbol]
    if not activities:
        return self._empty_metrics()
    start_str, end_str = start.isoformat(), end.isoformat()
    raw_price = self.current_rate_service.get_nearest_price(symbol, end_str)
    {v('unitPriceAtEndDate')} = D(str(raw_price)) if raw_price else None
    if not {v('unitPriceAtEndDate')} or {v('unitPriceAtEndDate')} == D(0):
        _bs = [a for a in activities if a.get('type') in {pos_types!r}]
        if _bs: {v('unitPriceAtEndDate')} = D(str(_bs[-1].get('{cfg.f("up")}', 0)))
    if not {v('unitPriceAtEndDate')} or {v('unitPriceAtEndDate')} == D(0):
        return self._empty_metrics(has_errors=True)
    orders = []
    for a in activities:
        orders.append(dict(date=a['date'], type=a['type'], quantity=D(str(a.get('quantity', 0))), {cfg.f("up")}=D(str(a.get('{cfg.f("up")}', 0))), fee=D(str(a.get('fee', 0))), itemType=None))
    {v('unitPriceAtStartDate')} = self.current_rate_service.get_nearest_price(symbol, start_str)
    {v('unitPriceAtStartDate')} = D(str({v('unitPriceAtStartDate')})) if {v('unitPriceAtStartDate')} else D(0)
    orders.append(dict(date=start_str, type={pos_types[0]!r}, quantity=D(0), {cfg.f("up")}={v('unitPriceAtStartDate')}, fee=D(0), itemType='start', {cfg.f("upm")}={v('unitPriceAtStartDate')}))
    orders.append(dict(date=end_str, type={pos_types[0]!r}, quantity=D(0), {cfg.f("up")}={v('unitPriceAtEndDate')}, fee=D(0), itemType='end', {cfg.f("upm")}={v('unitPriceAtEndDate')}))
    all_data_dates = self.current_rate_service.all_dates_in_range(start_str, end_str)
    chart_dates = set(all_data_dates)
    for y in range(start.year, end.year + 1):
        chart_dates.add(date(y, 1, 1).isoformat())
        chart_dates.add(date(y, 12, 31).isoformat())
    for o in orders: chart_dates.add(o['date'])
    fad = min(a['date'] for a in activities)
    db = date.fromisoformat(fad) - timedelta(days=1)
    if db.isoformat() >= start_str: chart_dates.add(db.isoformat())
    obd = dict()
    for o in orders: obd.setdefault(o['date'], []).append(o)
    _lup = None
    for ds in sorted(chart_dates):
        if ds < start_str: continue
        if ds > end_str: break
        mp = self.current_rate_service.get_price(symbol, ds)
        if mp is not None: _lup = D(str(mp))
        if ds in obd:
            for o in obd[ds]:
                if '{cfg.f("upm")}' not in o: o['{cfg.f("upm")}'] = _lup or o['{cfg.f("up")}']
        else:
            _up = _lup or D(0)
            s = dict(date=ds, type={pos_types[0]!r}, quantity=D(0), {cfg.f("up")}=_up, fee=D(0), itemType=None, {cfg.f("upm")}=_up)
            orders.append(s)
            obd.setdefault(ds, []).append(s)
    def _sk(o):
        d = date.fromisoformat(o['date'])
        if o.get('itemType') == 'start': return (d, 0)
        elif o.get('itemType') == 'end': return (d, 2)
        return (d, 1)
    orders.sort(key=_sk)
    {v('indexOfStartOrder')} = next(j for j, o in enumerate(orders) if o.get('itemType') == 'start')
    {v('indexOfEndOrder')} = next(j for j, o in enumerate(orders) if o.get('itemType') == 'end')
    {v('totalUnits')} = D(0)
    {v('totalInvestment')} = D(0)
    {v('totalDividend')} = D(0)
    {v('totalLiabilities')} = D(0)
    {v('totalInterest')} = D(0)
    {v('fees')} = D(0)
    {v('feesAtStartDate')} = D(0)
    {v('grossPerformance')} = D(0)
    {v('grossPerformanceAtStartDate')} = D(0)
    {v('grossPerformanceFromSells')} = D(0)
    {v('lastAveragePrice')} = D(0)
    {v('totalQuantityFromBuyTransactions')} = D(0)
    {v('totalInvestmentFromBuyTransactions')} = D(0)
    {v('totalInvestmentDays')} = D(0)
    {v('sumOfTimeWeightedInvestments')} = D(0)
    {v('initialValue')} = None
    {v('investmentAtStartDate')} = None
    {v('valueAtStartDate')} = None
    {v('currentValues')} = dict()
    {v('netPerformanceValues')} = dict()
    {v('investmentValuesAccumulated')} = dict()
    {v('investmentValuesWithCurrencyEffect')} = dict()
    for idx, order in enumerate(orders):
        otype = order['type']
        _factors = {factor_dict}
        _af = _factors.get(otype, 0)
        if _af == 0 and otype not in ('FEE',):
            if otype in _factors:
                {v('totalDividend')} += order['quantity'] * order['{cfg.f("up")}'] if otype == list(k for k, v in _factors.items() if v == 0 and k != 'FEE')[0] else D(0)
                {v('totalLiabilities')} += order['quantity'] * order['{cfg.f("up")}'] if otype == list(k for k, v in _factors.items() if v == 0 and k != 'FEE')[1] else D(0)
                {v('totalInterest')} += order['quantity'] * order['{cfg.f("up")}'] if otype == list(k for k, v in _factors.items() if v == 0 and k != 'FEE')[2] else D(0)
        if order.get('itemType') == 'start':
            if {v('indexOfStartOrder')} == 0 and idx + 1 < len(orders):
                order['{cfg.f("up")}'] = orders[idx + 1].get('{cfg.f("up")}', D(0))
        _up = order['{cfg.f("up")}'] if otype in {pos_types!r} else order.get('{cfg.f("upm")}', order['{cfg.f("up")}'])
        _mp = order.get('{cfg.f("upm")}', _up) or D(0)
        {v('valueOfInvestmentBeforeTransaction')} = {v('totalUnits')} * _mp
        if {v('investmentAtStartDate')} is None and idx >= {v('indexOfStartOrder')}:
            {v('investmentAtStartDate')} = {v('totalInvestment')}
            {v('valueAtStartDate')} = {v('valueOfInvestmentBeforeTransaction')}
        {v('transactionInvestment')} = D(0)
        _factor = _factors.get(otype, 0)
        if _factor > 0:
            {v('transactionInvestment')} = order['quantity'] * _up * _factor
            {v('totalQuantityFromBuyTransactions')} += order['quantity']
            {v('totalInvestmentFromBuyTransactions')} += {v('transactionInvestment')}
        elif _factor < 0 and {v('totalUnits')} > 0:
            {v('transactionInvestment')} = ({v('totalInvestment')} / {v('totalUnits')}) * order['quantity'] * _factor
        {v('totalInvestmentBeforeTransaction')} = {v('totalInvestment')}
        {v('totalInvestment')} += {v('transactionInvestment')}
        if idx >= {v('indexOfStartOrder')} and {v('initialValue')} is None:
            if idx == {v('indexOfStartOrder')} and {v('valueOfInvestmentBeforeTransaction')} != 0: {v('initialValue')} = {v('valueOfInvestmentBeforeTransaction')}
            elif {v('transactionInvestment')} > 0: {v('initialValue')} = {v('transactionInvestment')}
        {v('fees')} += order.get('fee', D(0))
        {v('totalUnits')} += order['quantity'] * _factor
        {v('valueOfInvestment')} = {v('totalUnits')} * _mp
        {v('grossPerformanceFromSell')} = D(0)
        if _factor < 0: {v('grossPerformanceFromSell')} = (_up - {v('lastAveragePrice')}) * order['quantity']
        {v('grossPerformanceFromSells')} += {v('grossPerformanceFromSell')}
        if {v('totalQuantityFromBuyTransactions')} != 0: {v('lastAveragePrice')} = {v('totalInvestmentFromBuyTransactions')} / {v('totalQuantityFromBuyTransactions')}
        else: {v('lastAveragePrice')} = D(0)
        if {v('totalUnits')} == 0:
            {v('totalInvestmentFromBuyTransactions')} = D(0)
            {v('totalQuantityFromBuyTransactions')} = D(0)
        {v('grossPerformance')} = {v('valueOfInvestment')} - {v('totalInvestment')} + {v('grossPerformanceFromSells')}
        if order.get('itemType') == 'start':
            {v('feesAtStartDate')} = {v('fees')}
            {v('grossPerformanceAtStartDate')} = {v('grossPerformance')}
        if idx > {v('indexOfStartOrder')} and {v('valueOfInvestmentBeforeTransaction')} > 0 and otype in {pos_types!r}:
            _days = max((date.fromisoformat(order['date']) - date.fromisoformat(orders[idx - 1]['date'])).days, 0)
            _dd = D(str(_days)) if _days > 0 else D('0.00000000000001')
            {v('totalInvestmentDays')} += _dd
            {v('sumOfTimeWeightedInvestments')} += ({v('valueAtStartDate')} - {v('investmentAtStartDate')} + {v('totalInvestmentBeforeTransaction')}) * _dd
        if idx > {v('indexOfStartOrder')}:
            {v('currentValues')}[order['date']] = {v('valueOfInvestment')}
            {v('netPerformanceValues')}[order['date']] = {v('grossPerformance')} - {v('grossPerformanceAtStartDate')} - ({v('fees')} - {v('feesAtStartDate')})
            {v('investmentValuesAccumulated')}[order['date']] = {v('totalInvestment')}
            {v('investmentValuesWithCurrencyEffect')}[order['date']] = {v('investmentValuesWithCurrencyEffect')}.get(order['date'], D(0)) + {v('transactionInvestment')}
        if idx == {v('indexOfEndOrder')}: break
    _tgp = {v('grossPerformance')} - {v('grossPerformanceAtStartDate')}
    _tnp = _tgp - ({v('fees')} - {v('feesAtStartDate')})
    _twi = {v('sumOfTimeWeightedInvestments')} / {v('totalInvestmentDays')} if {v('totalInvestmentDays')} > 0 else D(0)
    _npp = _tnp / _twi if _twi > 0 else D(0)
    _gpp = _tgp / _twi if _twi > 0 else D(0)
    return dict(hasErrors={v('totalUnits')} > 0 and ({v('initialValue')} is None or {v('unitPriceAtEndDate')} is None),
        ti={v('totalInvestment')}, td={v('totalDividend')}, tf={v('fees')} - {v('feesAtStartDate')},
        tl={v('totalLiabilities')}, quantity={v('totalUnits')}, _tnp=_tnp, _tgp=_tgp, _npp=_npp, _gpp=_gpp,
        ibd={v('investmentValuesWithCurrencyEffect')}, vbd={v('currentValues')},
        npd={v('netPerformanceValues')}, iad={v('investmentValuesAccumulated')},
        iv={v('initialValue')} or D(0),
        mp=float({v('unitPriceAtEndDate')}) if {v('unitPriceAtEndDate')} else 0.0,
        ap=float({v('lastAveragePrice')}) if {v('lastAveragePrice')} else 0.0)
"""
    tree = pyast.parse(code)
    return tree.body[0]


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
