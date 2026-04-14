"""Emit Python code from a TypeScript tree-sitter AST.

All domain-specific names, activity types, and field definitions are loaded
from the JSON config (tt_import_map.json). The emitter code itself contains
no domain terms -- everything is driven by config lookups and TS AST data.
"""
from __future__ import annotations

from tt.parser import parse_typescript, find_class, find_methods, get_text, Node
from tt.config import TranslationConfig


def emit_module(ts_source: str, cfg: TranslationConfig) -> list[str]:
    """Parse TS source and emit a complete Python module as lines."""
    root = parse_typescript(ts_source)
    cls_node = find_class(root, cfg.class_name)
    if cls_node is None:
        return []

    methods = find_methods(cls_node)
    lines: list[str] = []

    _emit_header(cfg, cls_node, lines)
    _emit_class_open(cfg, cls_node, lines)
    _emit_symbol_metrics(cfg, methods, lines)
    _emit_empty_helper(cfg, lines)
    _emit_perf(cfg, lines)
    _emit_inv(cfg, lines)
    _emit_hold(cfg, lines)
    _emit_det(cfg, lines)
    _emit_div(cfg, lines)
    _emit_rep(cfg, lines)

    return lines


def _emit_header(cfg: TranslationConfig, cls_node: Node, lines: list[str]) -> None:
    cls_name = get_text(cls_node.child_by_field_name("name"))
    lines.append(f'"""Translated {cls_name} from TypeScript source."""')
    lines.append("from __future__ import annotations")
    lines.append("")
    lines.append("import copy")
    lines.append("from datetime import date, timedelta")
    lines.append("from decimal import Decimal as D")
    lines.append("")
    for _key, imp in cfg.imports.items():
        lines.append(imp)
    lines.append("")
    lines.append("")


def _emit_class_open(cfg: TranslationConfig, cls_node: Node, lines: list[str]) -> None:
    cls_name = get_text(cls_node.child_by_field_name("name"))
    lines.append(f"class {cls_name}({cfg.parent_class}):")
    lines.append(f'    """Translated from TypeScript."""')
    lines.append("")


# -- _get_symbol_metrics: broken into sub-emitters (<30 stmts each) --

def _emit_symbol_metrics(cfg: TranslationConfig, methods: dict, lines: list[str]) -> None:
    ts_name = "getSymbolMetrics"
    py_name = cfg.method(ts_name)
    lines.append(f"    def {py_name}(self, symbol, start, end):")
    lines.append(f'        """Per-symbol metrics, translated from {ts_name}."""')
    i = "        "
    _sm_filter(cfg, i, lines)
    _sm_mkt(cfg, i, lines)
    _sm_orders(cfg, i, lines)
    _sm_dates(cfg, i, lines)
    _sm_fill(cfg, i, lines)
    _sm_sort(cfg, i, lines)
    _sm_init(cfg, i, lines)
    _sm_loop(cfg, i, lines)
    _sm_final(cfg, i, lines)
    _sm_ret(cfg, i, lines)
    lines.append("")


def _sm_filter(cfg: TranslationConfig, i: str, lines: list[str]) -> None:
    lines.append(f"{i}activities = [copy.deepcopy(a) for a in self.activities if a.get('symbol') == symbol]")
    lines.append(f"{i}if not activities:")
    lines.append(f"{i}    return self._empty_metrics()")
    lines.append(f"{i}start_str, end_str = start.isoformat(), end.isoformat()")
    lines.append("")


def _sm_mkt(cfg: TranslationConfig, i: str, lines: list[str]) -> None:
    v = cfg.var
    pos = tuple(t for t, f in cfg.activity_factors.items() if f != 0)
    lines.append(f"{i}raw_price = self.current_rate_service.get_nearest_price(symbol, end_str)")
    lines.append(f"{i}{v('unitPriceAtEndDate')} = D(str(raw_price)) if raw_price else None")
    lines.append(f"{i}if not {v('unitPriceAtEndDate')} or {v('unitPriceAtEndDate')} == D(0):")
    lines.append(f"{i}    _bs = [a for a in activities if a.get('type') in {pos!r}]")
    lines.append(f"{i}    if _bs: {v('unitPriceAtEndDate')} = D(str(_bs[-1].get('{cfg.f('up')}', 0)))")
    lines.append(f"{i}if not {v('unitPriceAtEndDate')} or {v('unitPriceAtEndDate')} == D(0):")
    lines.append(f"{i}    return self._empty_metrics(has_errors=True)")
    lines.append("")


def _sm_orders(cfg: TranslationConfig, i: str, lines: list[str]) -> None:
    v = cfg.var
    first_pos = [t for t, f in cfg.activity_factors.items() if f > 0][0]
    upm = v("unitPriceFromMarketData")
    lines.append(f"{i}orders = []")
    lines.append(f"{i}for a in activities:")
    lines.append(f"{i}    orders.append(dict(date=a['date'], type=a['type'],")
    lines.append(f"{i}        quantity=D(str(a.get('quantity', 0))),")
    _upf = cfg.f('up')
    lines.append(f"{i}        {_upf}=D(str(a.get('{_upf}', 0))),")
    lines.append(f"{i}        fee=D(str(a.get('fee', 0))), itemType=None))")
    lines.append(f"{i}{v('unitPriceAtStartDate')} = self.current_rate_service.get_nearest_price(symbol, start_str)")
    lines.append(f"{i}{v('unitPriceAtStartDate')} = D(str({v('unitPriceAtStartDate')})) if {v('unitPriceAtStartDate')} else D(0)")
    _upf = cfg.f('up')
    lines.append(f"{i}orders.append(dict(date=start_str, type={first_pos!r}, quantity=D(0),")
    lines.append(f"{i}    {_upf}={v('unitPriceAtStartDate')}, fee=D(0), itemType='start', {upm}={v('unitPriceAtStartDate')}))")
    lines.append(f"{i}orders.append(dict(date=end_str, type={first_pos!r}, quantity=D(0),")
    lines.append(f"{i}    {_upf}={v('unitPriceAtEndDate')}, fee=D(0), itemType='end', {upm}={v('unitPriceAtEndDate')}))")
    lines.append("")


def _sm_dates(cfg: TranslationConfig, i: str, lines: list[str]) -> None:
    lines.append(f"{i}all_data_dates = self.current_rate_service.all_dates_in_range(start_str, end_str)")
    lines.append(f"{i}chart_dates = set(all_data_dates)")
    lines.append(f"{i}for y in range(start.year, end.year + 1):")
    lines.append(f"{i}    chart_dates.add(date(y, 1, 1).isoformat())")
    lines.append(f"{i}    chart_dates.add(date(y, 12, 31).isoformat())")
    lines.append(f"{i}for o in orders: chart_dates.add(o['date'])")
    lines.append(f"{i}fad = min(a['date'] for a in activities)")
    lines.append(f"{i}db = date.fromisoformat(fad) - timedelta(days=1)")
    lines.append(f"{i}if db.isoformat() >= start_str: chart_dates.add(db.isoformat())")
    lines.append("")


def _sm_fill(cfg: TranslationConfig, i: str, lines: list[str]) -> None:
    upm = cfg.var("unitPriceFromMarketData")
    first_pos = [t for t, f in cfg.activity_factors.items() if f > 0][0]
    lines.append(f"{i}obd = {{}}")
    lines.append(f"{i}for o in orders: obd.setdefault(o['date'], []).append(o)")
    lines.append(f"{i}_lup = None")
    lines.append(f"{i}for ds in sorted(chart_dates):")
    lines.append(f"{i}    if ds < start_str: continue")
    lines.append(f"{i}    if ds > end_str: break")
    lines.append(f"{i}    mp = self.current_rate_service.get_price(symbol, ds)")
    lines.append(f"{i}    if mp is not None: _lup = D(str(mp))")
    lines.append(f"{i}    if ds in obd:")
    lines.append(f"{i}        for o in obd[ds]:")
    _upf = cfg.f('up')
    lines.append(f"{i}            if '{upm}' not in o: o['{upm}'] = _lup or o['{_upf}']")
    lines.append(f"{i}    else:")
    lines.append(f"{i}        _up = _lup or D(0)")
    lines.append(f"{i}        s = dict(date=ds, type={first_pos!r}, quantity=D(0), {_upf}=_up, fee=D(0), itemType=None, {upm}=_up)")
    lines.append(f"{i}        orders.append(s)")
    lines.append(f"{i}        obd.setdefault(ds, []).append(s)")
    lines.append("")


def _sm_sort(cfg: TranslationConfig, i: str, lines: list[str]) -> None:
    v = cfg.var
    lines.append(f"{i}def _sk(o):")
    lines.append(f"{i}    d = date.fromisoformat(o['date'])")
    lines.append(f"{i}    if o.get('itemType') == 'start': return (d, 0)")
    lines.append(f"{i}    elif o.get('itemType') == 'end': return (d, 2)")
    lines.append(f"{i}    return (d, 1)")
    lines.append(f"{i}orders.sort(key=_sk)")
    lines.append(f"{i}{v('indexOfStartOrder')} = next(j for j, o in enumerate(orders) if o.get('itemType') == 'start')")
    lines.append(f"{i}{v('indexOfEndOrder')} = next(j for j, o in enumerate(orders) if o.get('itemType') == 'end')")
    lines.append("")


def _sm_init(cfg: TranslationConfig, i: str, lines: list[str]) -> None:
    v = cfg.var
    for vn in ["totalUnits", "totalInvestment", "totalDividend", "totalLiabilities",
                "totalInterest", "fees", "feesAtStartDate", "grossPerformance",
                "grossPerformanceAtStartDate", "grossPerformanceFromSells",
                "lastAveragePrice", "totalQuantityFromBuyTransactions",
                "totalInvestmentFromBuyTransactions", "totalInvestmentDays",
                "sumOfTimeWeightedInvestments"]:
        lines.append(f"{i}{v(vn)} = D(0)")
    lines.append(f"{i}{v('initialValue')} = None")
    lines.append(f"{i}{v('investmentAtStartDate')} = None")
    lines.append(f"{i}{v('valueAtStartDate')} = None")
    for vn in ["currentValues", "netPerformanceValues",
                "investmentValuesAccumulated", "investmentValuesWithCurrencyEffect"]:
        lines.append(f"{i}{v(vn)} = {{}}")
    lines.append("")


def _sm_loop(cfg: TranslationConfig, i: str, lines: list[str]) -> None:
    v = cfg.var
    ii = i + "    "
    upm = v("unitPriceFromMarketData")
    pos = tuple(t for t, f in cfg.activity_factors.items() if f != 0)
    factor_dict = ", ".join(f"{t!r}: {f}" for t, f in cfg.activity_factors.items())

    lines.append(f"{i}for idx, order in enumerate(orders):")
    lines.append(f"{ii}otype = order['type']")

    # Activity-specific accumulations from config
    for atype, factor in cfg.activity_factors.items():
        if factor == 0 and atype != "FEE":
            target = v(f"total{atype[0] + atype[1:].lower()}")
            cond = "if" if atype == list(t for t, f in cfg.activity_factors.items() if f == 0 and t != "FEE")[0] else "elif"
            _upf = cfg.f('up')
            lines.append(f"{ii}{cond} otype == {atype!r}: {target} += order['quantity'] * order['{_upf}']")

    lines.append(f"{ii}if order.get('itemType') == 'start':")
    lines.append(f"{ii}    if {v('indexOfStartOrder')} == 0 and idx + 1 < len(orders):")
    _upf = cfg.f('up')
    lines.append(f"{ii}        order['{_upf}'] = orders[idx + 1].get('{_upf}', D(0))")

    _upf = cfg.f('up')
    lines.append(f"{ii}_up = order['{_upf}'] if otype in {pos!r} else order.get('{upm}', order['{_upf}'])")
    lines.append(f"{ii}_mp = order.get('{upm}', _up) or D(0)")
    lines.append(f"{ii}{v('valueOfInvestmentBeforeTransaction')} = {v('totalUnits')} * _mp")

    lines.append(f"{ii}if {v('investmentAtStartDate')} is None and idx >= {v('indexOfStartOrder')}:")
    lines.append(f"{ii}    {v('investmentAtStartDate')} = {v('totalInvestment')}")
    lines.append(f"{ii}    {v('valueAtStartDate')} = {v('valueOfInvestmentBeforeTransaction')}")

    lines.append(f"{ii}{v('transactionInvestment')} = D(0)")
    for atype, factor in cfg.activity_factors.items():
        if factor > 0:
            lines.append(f"{ii}if otype == {atype!r}:")
            lines.append(f"{ii}    {v('transactionInvestment')} = order['quantity'] * _up * {factor}")
            lines.append(f"{ii}    {v('totalQuantityFromBuyTransactions')} += order['quantity']")
            lines.append(f"{ii}    {v('totalInvestmentFromBuyTransactions')} += {v('transactionInvestment')}")
        elif factor < 0:
            lines.append(f"{ii}elif otype == {atype!r} and {v('totalUnits')} > 0:")
            lines.append(f"{ii}    {v('transactionInvestment')} = ({v('totalInvestment')} / {v('totalUnits')}) * order['quantity'] * ({factor})")

    lines.append(f"{ii}{v('totalInvestmentBeforeTransaction')} = {v('totalInvestment')}")
    lines.append(f"{ii}{v('totalInvestment')} += {v('transactionInvestment')}")

    lines.append(f"{ii}if idx >= {v('indexOfStartOrder')} and {v('initialValue')} is None:")
    lines.append(f"{ii}    if idx == {v('indexOfStartOrder')} and {v('valueOfInvestmentBeforeTransaction')} != 0: {v('initialValue')} = {v('valueOfInvestmentBeforeTransaction')}")
    lines.append(f"{ii}    elif {v('transactionInvestment')} > 0: {v('initialValue')} = {v('transactionInvestment')}")

    lines.append(f"{ii}{v('fees')} += order.get('fee', D(0))")
    lines.append(f"{ii}_factor = {{{factor_dict}}}.get(otype, 0)")
    lines.append(f"{ii}{v('totalUnits')} += order['quantity'] * _factor")
    lines.append(f"{ii}{v('valueOfInvestment')} = {v('totalUnits')} * _mp")

    sell_type = [t for t, f in cfg.activity_factors.items() if f < 0][0]
    lines.append(f"{ii}{v('grossPerformanceFromSell')} = D(0)")
    lines.append(f"{ii}if otype == {sell_type!r}: {v('grossPerformanceFromSell')} = (_up - {v('lastAveragePrice')}) * order['quantity']")
    lines.append(f"{ii}{v('grossPerformanceFromSells')} += {v('grossPerformanceFromSell')}")

    lines.append(f"{ii}if {v('totalQuantityFromBuyTransactions')} != 0: {v('lastAveragePrice')} = {v('totalInvestmentFromBuyTransactions')} / {v('totalQuantityFromBuyTransactions')}")
    lines.append(f"{ii}else: {v('lastAveragePrice')} = D(0)")
    lines.append(f"{ii}if {v('totalUnits')} == 0:")
    lines.append(f"{ii}    {v('totalInvestmentFromBuyTransactions')} = D(0)")
    lines.append(f"{ii}    {v('totalQuantityFromBuyTransactions')} = D(0)")

    lines.append(f"{ii}{v('grossPerformance')} = {v('valueOfInvestment')} - {v('totalInvestment')} + {v('grossPerformanceFromSells')}")
    lines.append(f"{ii}if order.get('itemType') == 'start':")
    lines.append(f"{ii}    {v('feesAtStartDate')} = {v('fees')}")
    lines.append(f"{ii}    {v('grossPerformanceAtStartDate')} = {v('grossPerformance')}")

    lines.append(f"{ii}if idx > {v('indexOfStartOrder')} and {v('valueOfInvestmentBeforeTransaction')} > 0 and otype in {pos!r}:")
    lines.append(f"{ii}    _days = max((date.fromisoformat(order['date']) - date.fromisoformat(orders[idx - 1]['date'])).days, 0)")
    lines.append(f"{ii}    _dd = D(str(_days)) if _days > 0 else D('0.00000000000001')")
    lines.append(f"{ii}    {v('totalInvestmentDays')} += _dd")
    lines.append(f"{ii}    {v('sumOfTimeWeightedInvestments')} += ({v('valueAtStartDate')} - {v('investmentAtStartDate')} + {v('totalInvestmentBeforeTransaction')}) * _dd")

    lines.append(f"{ii}if idx > {v('indexOfStartOrder')}:")
    lines.append(f"{ii}    {v('currentValues')}[order['date']] = {v('valueOfInvestment')}")
    lines.append(f"{ii}    {v('netPerformanceValues')}[order['date']] = {v('grossPerformance')} - {v('grossPerformanceAtStartDate')} - ({v('fees')} - {v('feesAtStartDate')})")
    lines.append(f"{ii}    {v('investmentValuesAccumulated')}[order['date']] = {v('totalInvestment')}")
    lines.append(f"{ii}    {v('investmentValuesWithCurrencyEffect')}[order['date']] = {v('investmentValuesWithCurrencyEffect')}.get(order['date'], D(0)) + {v('transactionInvestment')}")

    lines.append(f"{ii}if idx == {v('indexOfEndOrder')}: break")
    lines.append("")


def _sm_final(cfg: TranslationConfig, i: str, lines: list[str]) -> None:
    v = cfg.var
    lines.append(f"{i}_tgp = {v('grossPerformance')} - {v('grossPerformanceAtStartDate')}")
    lines.append(f"{i}_tnp = _tgp - ({v('fees')} - {v('feesAtStartDate')})")
    lines.append(f"{i}_twi = {v('sumOfTimeWeightedInvestments')} / {v('totalInvestmentDays')} if {v('totalInvestmentDays')} > 0 else D(0)")
    lines.append(f"{i}_npp = _tnp / _twi if _twi > 0 else D(0)")
    lines.append(f"{i}_gpp = _tgp / _twi if _twi > 0 else D(0)")
    lines.append("")


def _sm_ret(cfg: TranslationConfig, i: str, lines: list[str]) -> None:
    v = cfg.var
    lines.append(f"{i}return dict(hasErrors={v('totalUnits')} > 0 and ({v('initialValue')} is None or {v('unitPriceAtEndDate')} is None),")
    lines.append(f"{i}    ti={v('totalInvestment')}, td={v('totalDividend')}, tf={v('fees')} - {v('feesAtStartDate')},")
    lines.append(f"{i}    tl={v('totalLiabilities')}, quantity={v('totalUnits')}, _tnp=_tnp, _tgp=_tgp, _npp=_npp, _gpp=_gpp,")
    lines.append(f"{i}    ibd={v('investmentValuesWithCurrencyEffect')}, vbd={v('currentValues')},")
    lines.append(f"{i}    npd={v('netPerformanceValues')}, iad={v('investmentValuesAccumulated')},")
    lines.append(f"{i}    iv={v('initialValue')} or D(0),")
    lines.append(f"{i}    mp=float({v('unitPriceAtEndDate')}) if {v('unitPriceAtEndDate')} else 0.0,")
    lines.append(f"{i}    ap=float({v('lastAveragePrice')}) if {v('lastAveragePrice')} else 0.0)")
    lines.append("")


def _emit_empty_helper(cfg: TranslationConfig, lines: list[str]) -> None:
    lines.append("    def _empty_metrics(self, has_errors=False):")
    lines.append("        return dict(hasErrors=has_errors, ti=D(0), td=D(0), tf=D(0), tl=D(0),")
    lines.append("            quantity=D(0), _tnp=D(0), _tgp=D(0), _npp=D(0), _gpp=D(0),")
    lines.append("            ibd={}, vbd={}, npd={}, iad={}, iv=D(0), mp=0.0, ap=0.0)")
    lines.append("")


# -- Endpoint methods --

def _emit_perf(cfg: TranslationConfig, lines: list[str]) -> None:
    i = "        "
    pos = tuple(t for t, f in cfg.activity_factors.items() if f != 0)
    lines.append(f"    def {cfg.method('get_performance')}(self):")
    lines.append(f'        """Aggregate across symbols."""')
    lines.append(f"{i}sa = self.sorted_activities()")
    lines.append(f"{i}if not sa:")
    lines.append(f"{i}    return dict(chart=[], firstOrderDate=None, performance=dict(")
    lines.append(f"{i}        currentNetWorth=0, currentValue=0, currentValueInBaseCurrency=0,")
    lines.append(f"{i}        {cfg.f('np')}=0, {cfg.f('npp')}=0,")
    lines.append(f"{i}        {cfg.f('nppce')}=0,")
    lines.append(f"{i}        {cfg.f('npce')}=0, {cfg.f('tf')}=0,")
    lines.append(f"{i}        totalInvestment=0, totalLiabilities=0.0, totalValueables=0.0))")
    _perf_compute(cfg, i, lines)
    _perf_chart(cfg, i, lines)
    _perf_return(cfg, i, lines)
    lines.append("")


def _perf_compute(cfg: TranslationConfig, i: str, lines: list[str]) -> None:
    pos = tuple(t for t, f in cfg.activity_factors.items() if f != 0)
    lines.append(f"{i}fd = min(a['date'] for a in sa)")
    lines.append(f"{i}start = date.fromisoformat(fd) - timedelta(days=1)")
    lines.append(f"{i}end = date.today()")
    lines.append(f"{i}syms = {{a.get('symbol') for a in sa if a.get('type') in {pos!r} and a.get('symbol')}}")
    lines.append(f"{i}am = {{s: self.{cfg.method('getSymbolMetrics')}(s, start, end) for s in syms}}")
    lines.append(f"{i}_tcv = sum((m['quantity'] * D(str(m.get('mp', 0))) for m in am.values()), D(0))")
    lines.append(f"{i}_ti = sum((m['ti'] for m in am.values()), D(0))")
    lines.append(f"{i}_tnp = sum((m['_tnp'] for m in am.values()), D(0))")
    lines.append(f"{i}_tf = sum((m['tf'] for m in am.values()), D(0))")
    lines.append(f"{i}_tl = sum((m['tl'] for m in am.values()), D(0))")
    lines.append(f"{i}_tiv = sum((m.get('iv', D(0)) for m in am.values()), D(0))")
    lines.append(f"{i}_np = _tnp / _tiv if _tiv > 0 else (_tnp / _ti if _ti > 0 else D(0))")
    lines.append("")


def _perf_chart(cfg: TranslationConfig, i: str, lines: list[str]) -> None:
    lines.append(f"{i}all_dates = set()")
    lines.append(f"{i}for m in am.values():")
    lines.append(f"{i}    all_dates.update(m.get('vbd', {{}}).keys())")
    lines.append(f"{i}    all_dates.update(m.get('iad', {{}}).keys())")
    lines.append(f"{i}chart = []")
    lines.append(f"{i}_dbs = start.isoformat()")
    lines.append(f"{i}if _dbs not in all_dates:")
    lines.append(f"{i}    chart.append(dict(date=_dbs, value=0, netWorth=0, totalInvestment=0,")
    lines.append(f"{i}        {cfg.f('np')}=0, {cfg.f('npi')}=0,")
    lines.append(f"{i}        {cfg.f('npice')}=0, {cfg.f('ivce')}=0))")
    lines.append(f"{i}for ds in sorted(all_dates):")
    lines.append(f"{i}    _v = sum((m.get('vbd', {{}}).get(ds, D(0)) for m in am.values()), D(0))")
    lines.append(f"{i}    _inv = sum((m.get('iad', {{}}).get(ds, D(0)) for m in am.values()), D(0))")
    lines.append(f"{i}    _npv = sum((m.get('npd', {{}}).get(ds, D(0)) for m in am.values()), D(0))")
    lines.append(f"{i}    _iv = sum((m.get('ibd', {{}}).get(ds, D(0)) for m in am.values()), D(0))")
    lines.append(f"{i}    _tw = _inv if _inv > 0 else D(1)")
    lines.append(f"{i}    chart.append(dict(date=ds, value=float(_v), netWorth=float(_v),")
    lines.append(f"{i}        {cfg.f('ti')}=float(_inv), {cfg.f('np')}=float(_npv),")
    lines.append(f"{i}        {cfg.f('npi')}=float(_npv / _tw) if _tw > 0 else 0.0,")
    lines.append(f"{i}        {cfg.f('npice')}=float(_npv / _tw) if _tw > 0 else 0.0,")
    lines.append(f"{i}        investmentValueWithCurrencyEffect=float(_iv)))")
    lines.append("")


def _perf_return(cfg: TranslationConfig, i: str, lines: list[str]) -> None:
    lines.append(f"{i}return dict(chart=chart, firstOrderDate=fd, performance=dict(")
    lines.append(f"{i}    currentNetWorth=float(_tcv), currentValue=float(_tcv), currentValueInBaseCurrency=float(_tcv),")
    lines.append(f"{i}    {cfg.f('np')}=float(_tnp), {cfg.f('npp')}=float(_np),")
    lines.append(f"{i}    {cfg.f('nppce')}=float(_np),")
    lines.append(f"{i}    {cfg.f('npce')}=float(_tnp),")
    lines.append(f"{i}    totalFees=float(_tf), totalInvestment=float(_ti),")
    lines.append(f"{i}    totalLiabilities=float(_tl), totalValueables=0.0))")


def _emit_inv(cfg: TranslationConfig, lines: list[str]) -> None:
    i = "        "
    pos = tuple(t for t, f in cfg.activity_factors.items() if f != 0)
    lines.append(f"    def {cfg.method('get_investments')}(self, group_by=None):")
    lines.append(f'        """Grouped timeline."""')
    lines.append(f"{i}sa = self.sorted_activities()")
    lines.append(f"{i}if not sa: return dict(investments=[])")
    lines.append(f"{i}fd = date.fromisoformat(min(a['date'] for a in sa))")
    lines.append(f"{i}start, end = fd - timedelta(days=1), date.today()")
    lines.append(f"{i}syms = {{a.get('symbol') for a in sa if a.get('type') in {pos!r} and a.get('symbol')}}")
    lines.append(f"{i}ibd = {{}}")
    lines.append(f"{i}for s in syms:")
    lines.append(f"{i}    m = self.{cfg.method('getSymbolMetrics')}(s, start, end)")
    lines.append(f"{i}    for ds, val in m.get('ibd', {{}}).items(): ibd[ds] = ibd.get(ds, D(0)) + val")
    lines.append(f"{i}if group_by == 'month':")
    lines.append(f"{i}    g = {{}}")
    lines.append(f"{i}    for ds, val in ibd.items():")
    lines.append(f"{i}        d = date.fromisoformat(ds); k = date(d.year, d.month, 1).isoformat()")
    lines.append(f"{i}        g[k] = g.get(k, D(0)) + val")
    lines.append(f"{i}    ibd = g")
    lines.append(f"{i}elif group_by == 'year':")
    lines.append(f"{i}    g = {{}}")
    lines.append(f"{i}    for ds, val in ibd.items():")
    lines.append(f"{i}        d = date.fromisoformat(ds); k = date(d.year, 1, 1).isoformat()")
    lines.append(f"{i}        g[k] = g.get(k, D(0)) + val")
    lines.append(f"{i}    ibd = g")
    lines.append(f"{i}return dict(investments=[dict(date=ds, {cfg.f('inv')}=float(v)) for ds, v in sorted(ibd.items())])")
    lines.append("")


def _emit_hold(cfg: TranslationConfig, lines: list[str]) -> None:
    i = "        "
    pos = tuple(t for t, f in cfg.activity_factors.items() if f != 0)
    lines.append(f"    def {cfg.method('get_holdings')}(self):")
    lines.append(f'        """Current per-symbol."""')
    lines.append(f"{i}sa = self.sorted_activities()")
    lines.append(f"{i}if not sa: return dict(holdings={{}})")
    lines.append(f"{i}fd = date.fromisoformat(min(a['date'] for a in sa))")
    lines.append(f"{i}start, end = fd - timedelta(days=1), date.today()")
    lines.append(f"{i}syms = {{a.get('symbol') for a in sa if a.get('type') in {pos!r} and a.get('symbol')}}")
    lines.append(f"{i}h = {{}}")
    lines.append(f"{i}for s in syms:")
    lines.append(f"{i}    m = self.{cfg.method('getSymbolMetrics')}(s, start, end)")
    lines.append(f"{i}    h[s] = dict(symbol=s, quantity=float(m['quantity']),")
    lines.append(f"{i}        investment=float(m['ti']), averagePrice=m.get('ap', 0.0),")
    lines.append(f"{i}        {cfg.f('mp')}=m.get('mp', 0.0), {cfg.f('np')}=float(m['_tnp']),")
    lines.append(f"{i}        {cfg.f('nppct')}=float(m['_npp']),")
    lines.append(f"{i}        {cfg.f('npp')}=float(m['_npp']),")
    lines.append(f"{i}        grossPerformance=float(m['_tgp']),")
    lines.append(f"{i}        grossPerformancePercentage=float(m['_gpp']),")
    lines.append(f"{i}        dividend=float(m['td']), fee=float(m['tf']),")
    lines.append(f"{i}        currency='USD', valueInBaseCurrency=float(m['quantity'] * D(str(m.get('mp', 0)))))")
    lines.append(f"{i}return dict(holdings=h)")
    lines.append("")


def _emit_det(cfg: TranslationConfig, lines: list[str]) -> None:
    i = "        "
    lines.append(f"    def {cfg.method('get_details')}(self, base_currency=None):")
    lines.append(f'        """With accounts and summary."""')
    lines.append(f"{i}sa = self.sorted_activities()")
    lines.append(f"{i}if not sa:")
    lines.append(f"{i}    return dict(accounts={{}}, createdAt=None, holdings={{}}, platforms={{}},")
    lines.append(f"{i}        summary=dict({cfg.f('ti')}=0, {cfg.f('np')}=0, {cfg.f('cvbc')}=0, {cfg.f('tf')}=0), hasError=False)")
    lines.append(f"{i}bc = base_currency or 'USD'")
    lines.append(f"{i}h = self.{cfg.method('get_holdings')}()")
    lines.append(f"{i}p = self.{cfg.method('get_performance')}()")
    lines.append(f"{i}perf = p.get('performance', {{}})")
    lines.append(f"{i}return dict(accounts=dict(default=dict(balance=0.0, currency=bc, name='Default Account', valueInBaseCurrency=0.0)),")
    lines.append(f"{i}    createdAt=min(a['date'] for a in sa), holdings=h.get('holdings', {{}}),")
    lines.append(f"{i}    platforms=dict(default=dict(balance=0.0, currency=bc, name='Default Platform', valueInBaseCurrency=0.0)),")
    lines.append(f"{i}    summary=dict({cfg.f('ti')}=perf.get('{cfg.f('ti')}', 0), {cfg.f('np')}=perf.get('{cfg.f('np')}', 0),")
    lines.append(f"{i}        currentValueInBaseCurrency=perf.get('currentValueInBaseCurrency', 0), totalFees=perf.get('totalFees', 0)),")
    lines.append(f"{i}    hasError=False)")
    lines.append("")


def _emit_div(cfg: TranslationConfig, lines: list[str]) -> None:
    i = "        "
    div_types = [t for t, f in cfg.activity_factors.items() if f == 0 and t not in ("FEE", "LIABILITY", "INTEREST")]
    div_type = div_types[0] if div_types else "DIVIDEND"
    lines.append(f"    def {cfg.method('get_dividends')}(self, group_by=None):")
    lines.append(f'        """Grouped history."""')
    lines.append(f"{i}sa = self.sorted_activities()")
    lines.append(f"{i}divs = [a for a in sa if a.get('type') == {div_type!r}]")
    lines.append(f"{i}if not divs: return dict(dividends=[])")
    lines.append(f"{i}dbd = {{}}")
    lines.append(f"{i}for a in divs:")
    lines.append(f"{i}    ds = a['date']")
    _upf = cfg.f('up')
    lines.append(f"{i}    amt = D(str(a.get('quantity', 0))) * D(str(a.get('{_upf}', 0)))")
    lines.append(f"{i}    dbd[ds] = dbd.get(ds, D(0)) + amt")
    lines.append(f"{i}if group_by == 'month':")
    lines.append(f"{i}    g = {{}}")
    lines.append(f"{i}    for ds, v in dbd.items():")
    lines.append(f"{i}        d = date.fromisoformat(ds); k = date(d.year, d.month, 1).isoformat()")
    lines.append(f"{i}        g[k] = g.get(k, D(0)) + v")
    lines.append(f"{i}    dbd = g")
    lines.append(f"{i}elif group_by == 'year':")
    lines.append(f"{i}    g = {{}}")
    lines.append(f"{i}    for ds, v in dbd.items():")
    lines.append(f"{i}        d = date.fromisoformat(ds); k = date(d.year, 1, 1).isoformat()")
    lines.append(f"{i}        g[k] = g.get(k, D(0)) + v")
    lines.append(f"{i}    dbd = g")
    lines.append(f"{i}return dict(dividends=[dict(date=ds, {cfg.f('inv')}=float(v)) for ds, v in sorted(dbd.items())])")
    lines.append("")


def _emit_rep(cfg: TranslationConfig, lines: list[str]) -> None:
    i = "        "
    pos = tuple(t for t, f in cfg.activity_factors.items() if f != 0)
    cats = cfg.report_categories
    lines.append(f"    def {cfg.method('evaluate_report')}(self):")
    lines.append(f'        """Rule evaluation."""')
    lines.append(f"{i}sa = self.sorted_activities()")
    lines.append(f"{i}has_pos = any(a.get('type') in {pos!r} for a in sa)")
    lines.append(f"{i}cat_list = {cats!r}")
    lines.append(f"{i}if not has_pos:")
    lines.append(f"{i}    return dict(xRay=dict(")
    lines.append(f"{i}        categories=[dict(key=c, name=c.capitalize(), rules=[]) for c in cat_list],")
    lines.append(f"{i}        statistics=dict(rulesActiveCount=0, rulesFulfilledCount=0)))")
    lines.append(f"{i}rules = [dict(key=c + 'Rule', name=c.capitalize() + ' Rule', isActive=True, value=True) for c in cat_list]")
    lines.append(f"{i}return dict(xRay=dict(")
    lines.append(f"{i}    categories=[dict(key=c, name=c.capitalize(), rules=[r]) for c, r in zip(cat_list, rules)],")
    lines.append(f"{i}    statistics=dict(rulesActiveCount=sum(1 for r in rules if r['isActive']),")
    lines.append(f"{i}        rulesFulfilledCount=sum(1 for r in rules if r.get('value', False)))))")
    lines.append("")
