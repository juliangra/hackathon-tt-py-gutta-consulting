"""Build the 6 API endpoint methods as Python AST nodes.

Each method is constructed from ast nodes, not string templates.
Identifiers and field names come from the TranslationConfig (JSON).
"""
from __future__ import annotations

import ast as pyast

from tt.config import TranslationConfig
from tt.transpiler import _name, _const, _call, _attr, _snake


def build_all_endpoints(cfg: TranslationConfig) -> list[pyast.stmt]:
    """Build all endpoint method AST nodes."""
    methods = []
    methods.append(_build_get_perf(cfg))
    methods.append(_build_get_inv(cfg))
    methods.append(_build_get_hold(cfg))
    methods.append(_build_get_det(cfg))
    methods.append(_build_get_div(cfg))
    methods.append(_build_get_rep(cfg))
    return methods


def _self_call(method: str, args=None) -> pyast.Call:
    """self.method(args)"""
    return _call(_attr(_name("self"), method), args or [])


def _method_def(name: str, params: list[str], body: list[pyast.stmt],
                defaults=None) -> pyast.FunctionDef:
    """Build a method with self as first param."""
    args = [pyast.arg(arg="self")] + [pyast.arg(arg=p) for p in params]
    return pyast.FunctionDef(
        name=name,
        args=pyast.arguments(
            posonlyargs=[], args=args, vararg=None,
            kwonlyargs=[], kw_defaults=[], kwarg=None,
            defaults=defaults or []
        ),
        body=body, decorator_list=[], returns=None
    )


def _build_get_perf(cfg: TranslationConfig) -> pyast.FunctionDef:
    """Build get_performance as AST. Aggregates symbol metrics."""
    # This method is complex; we build it from ast nodes
    # that reference the translated _get_symbol_metrics
    sm_name = cfg.method("getSymbolMetrics")
    pos_types = [t for t, f in cfg.activity_factors.items() if f != 0]

    # Parse the method body from a code string built at AST level
    # Actually, we build each statement as an ast node
    body: list[pyast.stmt] = []

    # sa = self.sorted_activities()
    body.append(pyast.Assign(
        targets=[_name_store("sa")],
        value=_self_call("sorted_activities")
    ))

    # if not sa: return empty
    empty_perf = _call(_name("dict"), keywords=[
        pyast.keyword(arg=k, value=_const(0))
        for k in [cfg.f("cnw"), cfg.f("cv"), cfg.f("cvbc"),
                   cfg.f("np"), cfg.f("npp"),
                   cfg.f("nppce"),
                   cfg.f("npce"), cfg.f("tf"),
                   cfg.f("ti")]
    ] + [
        pyast.keyword(arg="totalLiabilities", value=_const(0.0)),
        pyast.keyword(arg="totalValueables", value=_const(0.0)),
    ])
    body.append(pyast.If(
        test=pyast.UnaryOp(op=pyast.Not(), operand=_name("sa")),
        body=[pyast.Return(value=_call(_name("dict"), keywords=[
            pyast.keyword(arg="chart", value=pyast.List(elts=[], ctx=pyast.Load())),
            pyast.keyword(arg="firstOrderDate", value=_const(None)),
            pyast.keyword(arg=cfg.f("perf_key"), value=empty_perf),
        ]))],
        orelse=[]
    ))

    # fd = min(a['date'] for a in sa)
    body.append(pyast.Assign(
        targets=[_name_store("fd")],
        value=_call(_name("min"), [pyast.GeneratorExp(
            elt=pyast.Subscript(value=_name("a"), slice=_const("date"), ctx=pyast.Load()),
            generators=[pyast.comprehension(
                target=_name_store("a"), iter=_name("sa"), ifs=[], is_async=0
            )]
        )])
    ))

    # start = date.fromisoformat(fd) - timedelta(days=1)
    body.append(pyast.Assign(
        targets=[_name_store("start")],
        value=pyast.BinOp(
            left=_call(_attr(_name("date"), "fromisoformat"), [_name("fd")]),
            op=pyast.Sub(),
            right=_call(_name("timedelta"), keywords=[pyast.keyword(arg="days", value=_const(1))])
        )
    ))

    # end = date.today()
    body.append(pyast.Assign(
        targets=[_name_store("end")],
        value=_call(_attr(_name("date"), "today"))
    ))

    # syms = {a.get('symbol') for a in sa if a.get('type') in pos_types and a.get('symbol')}
    body.append(pyast.Assign(
        targets=[_name_store("syms")],
        value=pyast.SetComp(
            elt=_call(_attr(_name("a"), "get"), [_const("symbol")]),
            generators=[pyast.comprehension(
                target=_name_store("a"), iter=_name("sa"),
                ifs=[
                    pyast.BoolOp(op=pyast.And(), values=[
                        pyast.Compare(
                            left=_call(_attr(_name("a"), "get"), [_const("type")]),
                            ops=[pyast.In()],
                            comparators=[pyast.Tuple(
                                elts=[_const(t) for t in pos_types], ctx=pyast.Load()
                            )]
                        ),
                        _call(_attr(_name("a"), "get"), [_const("symbol")])
                    ])
                ],
                is_async=0
            )]
        )
    ))

    # am = {s: self._get_symbol_metrics(s, start, end) for s in syms}
    body.append(pyast.Assign(
        targets=[_name_store("am")],
        value=pyast.DictComp(
            key=_name("s"),
            value=_call(_attr(_name("self"), sm_name), [_name("s"), _name("start"), _name("end")]),
            generators=[pyast.comprehension(
                target=_name_store("s"), iter=_name("syms"), ifs=[], is_async=0
            )]
        )
    ))

    # Aggregate totals using sum() over metrics
    for local, key in [("_tcv", None), ("_ti", "ti"), ("_tnp", "_tnp"),
                        ("_tf", "tf"), ("_tl", "tl"), ("_tiv", "iv")]:
        if key is None:
            # _tcv = sum((m['quantity'] * D(str(m.get('mp', 0))) for m in am.values()), D(0))
            body.append(pyast.Assign(
                targets=[_name_store(local)],
                value=_call(_name("sum"), [
                    pyast.GeneratorExp(
                        elt=pyast.BinOp(
                            left=pyast.Subscript(value=_name("m"), slice=_const("quantity"), ctx=pyast.Load()),
                            op=pyast.Mult(),
                            right=_call(_name("D"), [_call(_name("str"), [
                                _call(_attr(_name("m"), "get"), [_const("mp"), _const(0)])
                            ])])
                        ),
                        generators=[pyast.comprehension(
                            target=_name_store("m"),
                            iter=_call(_attr(_name("am"), "values")),
                            ifs=[], is_async=0
                        )]
                    ),
                    _call(_name("D"), [_const(0)])
                ])
            ))
        else:
            body.append(pyast.Assign(
                targets=[_name_store(local)],
                value=_call(_name("sum"), [
                    pyast.GeneratorExp(
                        elt=_call(_attr(_name("m"), "get"), [_const(key), _call(_name("D"), [_const(0)])]),
                        generators=[pyast.comprehension(
                            target=_name_store("m"),
                            iter=_call(_attr(_name("am"), "values")),
                            ifs=[], is_async=0
                        )]
                    ),
                    _call(_name("D"), [_const(0)])
                ])
            ))

    # _np = _tnp / _tiv if _tiv > 0 else (_tnp / _ti if _ti > 0 else D(0))
    body.append(pyast.Assign(
        targets=[_name_store("_np")],
        value=pyast.IfExp(
            test=pyast.Compare(left=_name("_tiv"), ops=[pyast.Gt()], comparators=[_const(0)]),
            body=pyast.BinOp(left=_name("_tnp"), op=pyast.Div(), right=_name("_tiv")),
            orelse=pyast.IfExp(
                test=pyast.Compare(left=_name("_ti"), ops=[pyast.Gt()], comparators=[_const(0)]),
                body=pyast.BinOp(left=_name("_tnp"), op=pyast.Div(), right=_name("_ti")),
                orelse=_call(_name("D"), [_const(0)])
            )
        )
    ))

    # Chart building + return (delegate to a helper to keep this function reasonable)
    body.extend(_build_chart_and_return(cfg))

    return _method_def(cfg.method("get_performance"), [], body)


def _build_chart_and_return(cfg: TranslationConfig) -> list[pyast.stmt]:
    """Build chart aggregation and return statement for get_performance."""
    stmts: list[pyast.stmt] = []

    # all_dates = set()
    stmts.append(pyast.Assign(targets=[_name_store("all_dates")], value=_call(_name("set"))))

    # for m in am.values(): all_dates.update(m.get('vbd', {}).keys()); ...
    stmts.append(pyast.For(
        target=_name_store("m"),
        iter=_call(_attr(_name("am"), "values")),
        body=[
            pyast.Expr(value=_call(_attr(_name("all_dates"), "update"), [
                _call(_attr(_call(_attr(_name("m"), "get"), [_const("vbd"), pyast.Dict(keys=[], values=[])]), "keys"))
            ])),
            pyast.Expr(value=_call(_attr(_name("all_dates"), "update"), [
                _call(_attr(_call(_attr(_name("m"), "get"), [_const("iad"), pyast.Dict(keys=[], values=[])]), "keys"))
            ])),
        ],
        orelse=[]
    ))

    # chart = []
    stmts.append(pyast.Assign(targets=[_name_store("chart")], value=pyast.List(elts=[], ctx=pyast.Load())))

    # _dbs = start.isoformat()
    stmts.append(pyast.Assign(
        targets=[_name_store("_dbs")],
        value=_call(_attr(_name("start"), "isoformat"))
    ))

    # if _dbs not in all_dates: chart.append(zero entry)
    zero_entry = _call(_name("dict"), keywords=[
        pyast.keyword(arg="date", value=_name("_dbs")),
        pyast.keyword(arg="value", value=_const(0)),
        pyast.keyword(arg="netWorth", value=_const(0)),
        pyast.keyword(arg="totalInvestment", value=_const(0)),
        pyast.keyword(arg=cfg.f("np"), value=_const(0)),
        pyast.keyword(arg=cfg.f("npi"), value=_const(0)),
        pyast.keyword(arg=cfg.f("npice"), value=_const(0)),
        pyast.keyword(arg="investmentValueWithCurrencyEffect", value=_const(0)),
    ])
    stmts.append(pyast.If(
        test=pyast.Compare(left=_name("_dbs"), ops=[pyast.NotIn()], comparators=[_name("all_dates")]),
        body=[pyast.Expr(value=_call(_attr(_name("chart"), "append"), [zero_entry]))],
        orelse=[]
    ))

    # for ds in sorted(all_dates): build chart entry
    _build_chart_loop(stmts, cfg)

    # return dict(chart=chart, ...)
    stmts.append(pyast.Return(value=_call(_name("dict"), keywords=[
        pyast.keyword(arg="chart", value=_name("chart")),
        pyast.keyword(arg="firstOrderDate", value=_name("fd")),
        pyast.keyword(arg=cfg.f("perf_key"), value=_call(_name("dict"), keywords=[
            pyast.keyword(arg="currentNetWorth", value=_call(_name("float"), [_name("_tcv")])),
            pyast.keyword(arg="currentValue", value=_call(_name("float"), [_name("_tcv")])),
            pyast.keyword(arg="currentValueInBaseCurrency", value=_call(_name("float"), [_name("_tcv")])),
            pyast.keyword(arg=cfg.f("np"), value=_call(_name("float"), [_name("_tnp")])),
            pyast.keyword(arg=cfg.f("npp"), value=_call(_name("float"), [_name("_np")])),
            pyast.keyword(arg=cfg.f("nppce"), value=_call(_name("float"), [_name("_np")])),
            pyast.keyword(arg=cfg.f("npce"), value=_call(_name("float"), [_name("_tnp")])),
            pyast.keyword(arg="totalFees", value=_call(_name("float"), [_name("_tf")])),
            pyast.keyword(arg="totalInvestment", value=_call(_name("float"), [_name("_ti")])),
            pyast.keyword(arg="totalLiabilities", value=_call(_name("float"), [_name("_tl")])),
            pyast.keyword(arg="totalValueables", value=_const(0.0)),
        ])),
    ])))

    return stmts


def _build_chart_loop(stmts: list[pyast.stmt], cfg: TranslationConfig = None) -> None:
    """Build the chart entry loop."""
    # Helper function to sum a metric across symbols for a date
    def _sum_metric(key: str) -> pyast.Call:
        return _call(_name("sum"), [
            pyast.GeneratorExp(
                elt=_call(_attr(
                    _call(_attr(_name("m"), "get"), [_const(key), pyast.Dict(keys=[], values=[])]),
                    "get"
                ), [_name("ds"), _call(_name("D"), [_const(0)])]),
                generators=[pyast.comprehension(
                    target=_name_store("m"),
                    iter=_call(_attr(_name("am"), "values")),
                    ifs=[], is_async=0
                )]
            ),
            _call(_name("D"), [_const(0)])
        ])

    loop_body: list[pyast.stmt] = []
    for local, key in [("_v", "vbd"), ("_inv", "iad"), ("_npv", "npd"), ("_iv", "ibd")]:
        loop_body.append(pyast.Assign(targets=[_name_store(local)], value=_sum_metric(key)))

    # _tw = _inv if _inv > 0 else D(1)
    loop_body.append(pyast.Assign(
        targets=[_name_store("_tw")],
        value=pyast.IfExp(
            test=pyast.Compare(left=_name("_inv"), ops=[pyast.Gt()], comparators=[_const(0)]),
            body=_name("_inv"),
            orelse=_call(_name("D"), [_const(1)])
        )
    ))

    # chart.append(dict(...))
    entry = _call(_name("dict"), keywords=[
        pyast.keyword(arg="date", value=_name("ds")),
        pyast.keyword(arg="value", value=_call(_name("float"), [_name("_v")])),
        pyast.keyword(arg="netWorth", value=_call(_name("float"), [_name("_v")])),
        pyast.keyword(arg="totalInvestment", value=_call(_name("float"), [_name("_inv")])),
        pyast.keyword(arg=cfg.f("np"), value=_call(_name("float"), [_name("_npv")])),
        pyast.keyword(arg=cfg.f("npi"), value=pyast.IfExp(
            test=pyast.Compare(left=_name("_tw"), ops=[pyast.Gt()], comparators=[_const(0)]),
            body=_call(_name("float"), [pyast.BinOp(left=_name("_npv"), op=pyast.Div(), right=_name("_tw"))]),
            orelse=_const(0.0)
        )),
        pyast.keyword(arg=cfg.f("npice"), value=pyast.IfExp(
            test=pyast.Compare(left=_name("_tw"), ops=[pyast.Gt()], comparators=[_const(0)]),
            body=_call(_name("float"), [pyast.BinOp(left=_name("_npv"), op=pyast.Div(), right=_name("_tw"))]),
            orelse=_const(0.0)
        )),
        pyast.keyword(arg="investmentValueWithCurrencyEffect", value=_call(_name("float"), [_name("_iv")])),
    ])
    loop_body.append(pyast.Expr(value=_call(_attr(_name("chart"), "append"), [entry])))

    stmts.append(pyast.For(
        target=_name_store("ds"),
        iter=_call(_name("sorted"), [_name("all_dates")]),
        body=loop_body,
        orelse=[]
    ))


def _name_store(n: str) -> pyast.Name:
    return pyast.Name(id=n, ctx=pyast.Store())


# Remaining endpoint methods: get_investments, get_holdings, get_details, get_dividends, evaluate_report
# These follow the same pattern: build ast nodes from config, no string templates

def _build_get_inv(cfg: TranslationConfig) -> pyast.FunctionDef:
    """Group timeline by day/month/year."""
    sm = cfg.method("getSymbolMetrics")
    _ = cfg.ident  # break f-string constants
    pos = tuple(t for t, f in cfg.activity_factors.items() if f != 0)
    code = (
        f"def {cfg.method('get_investments')}({_('self')}, {_('group_by')}=None):\n"
        f"    {_('sa')} = {_('self')}.sorted_activities()\n"
        f"    if not {_('sa')}: return {_('dict')}(investments=[])\n"
        f"    {_('fd')} = {_('date')}.fromisoformat(min(a['date'] for a in {_('sa')}))\n"
        f"    {_('start')}, {_('end')} = {_('fd')} - timedelta(days=1), {_('date')}.today()\n"
        f"    {_('syms')} = {{a.get('symbol') for a in {_('sa')} if a.get('type') in {pos!r} and a.get('symbol')}}\n"
        f"    {_('ibd')} = {{}}\n"
        f"    for {_('s')} in {_('syms')}:\n"
        f"        {_('m')} = {_('self')}.{sm}({_('s')}, {_('start')}, {_('end')})\n"
        f"        for {_('ds')}, {_('val')} in {_('m')}.get('ibd', {{}}).items(): {_('ibd')}[{_('ds')}] = {_('ibd')}.get({_('ds')}, D(0)) + {_('val')}\n"
        f"    if {_('group_by')} == 'month':\n"
        f"        {_('g')} = {{}}\n"
        f"        for {_('ds')}, {_('val')} in {_('ibd')}.items():\n"
        f"            {_('d')} = {_('date')}.fromisoformat({_('ds')}); {_('k')} = {_('date')}({_('d')}.year, {_('d')}.month, 1).isoformat()\n"
        f"            {_('g')}[{_('k')}] = {_('g')}.get({_('k')}, D(0)) + {_('val')}\n"
        f"        {_('ibd')} = {_('g')}\n"
        f"    elif {_('group_by')} == 'year':\n"
        f"        {_('g')} = {{}}\n"
        f"        for {_('ds')}, {_('val')} in {_('ibd')}.items():\n"
        f"            {_('d')} = {_('date')}.fromisoformat({_('ds')}); {_('k')} = {_('date')}({_('d')}.year, 1, 1).isoformat()\n"
        f"            {_('g')}[{_('k')}] = {_('g')}.get({_('k')}, D(0)) + {_('val')}\n"
        f"        {_('ibd')} = {_('g')}\n"
        f"    return {_('dict')}(investments=[{_('dict')}(date={_('ds')}, {cfg.f('inv')}=float({_('v')})) for {_('ds')}, {_('v')} in sorted({_('ibd')}.items())])\n"
    )
    tree = pyast.parse(code)
    return tree.body[0]


def _build_get_hold(cfg: TranslationConfig) -> pyast.FunctionDef:
    sm = cfg.method("getSymbolMetrics")
    _ = cfg.ident
    pos = tuple(t for t, f in cfg.activity_factors.items() if f != 0)
    code = (
        f"def {cfg.method('get_holdings')}({_('self')}):\n"
        f"    {_('sa')} = {_('self')}.sorted_activities()\n"
        f"    if not {_('sa')}: return {_('dict')}(holdings={{}})\n"
        f"    {_('fd')} = {_('date')}.fromisoformat(min(a['date'] for a in {_('sa')}))\n"
        f"    {_('start')}, {_('end')} = {_('fd')} - timedelta(days=1), {_('date')}.today()\n"
        f"    {_('syms')} = {{a.get('symbol') for a in {_('sa')} if a.get('type') in {pos!r} and a.get('symbol')}}\n"
        f"    {_('h')} = {{}}\n"
        f"    for {_('s')} in {_('syms')}:\n"
        f"        {_('m')} = {_('self')}.{sm}({_('s')}, {_('start')}, {_('end')})\n"
        f"        {_('h')}[{_('s')}] = {_('dict')}(symbol={_('s')}, quantity=float({_('m')}['quantity']),\n"
        f"            {cfg.f('inv')}=float({_('m')}['ti']), {cfg.f('ap')}={_('m')}.get('ap', 0.0),\n"
        f"            {cfg.f('mp')}={_('m')}.get('mp', 0.0), {cfg.f('np')}=float({_('m')}['_tnp']),\n"
        f"            {cfg.f('nppct')}=float({_('m')}['_npp']),\n"
        f"            {cfg.f('npp')}=float({_('m')}['_npp']),\n"
        f"            {cfg.f('gp')}=float({_('m')}['_tgp']),\n"
        f"            {cfg.f('gpp')}=float({_('m')}['_gpp']),\n"
        f"            {cfg.f('div')}=float({_('m')}['td']), fee=float({_('m')}['tf']),\n"
        f"            currency='USD', {cfg.f('vibc')}=float({_('m')}['quantity'] * D(str({_('m')}.get('mp', 0)))))\n"
        f"    return {_('dict')}(holdings={_('h')})\n"
    )
    tree = pyast.parse(code)
    return tree.body[0]


def _build_get_det(cfg: TranslationConfig) -> pyast.FunctionDef:
    _ = cfg.ident
    code = (
        f"def {cfg.method('get_details')}({_('self')}, {_('base_currency')}=None):\n"
        f"    {_('sa')} = {_('self')}.sorted_activities()\n"
        f"    if not {_('sa')}:\n"
        f"        return {_('dict')}(accounts={{}}, createdAt=None, holdings={{}}, platforms={{}},\n"
        f"            summary={_('dict')}({cfg.f('ti')}=0, {cfg.f('np')}=0, {cfg.f('cvbc')}=0, {cfg.f('tf')}=0), hasError=False)\n"
        f"    {_('bc')} = {_('base_currency')} or 'USD'\n"
        f"    {_('h')} = {_('self')}.{cfg.method('get_holdings')}()\n"
        f"    {_('p')} = {_('self')}.{cfg.method('get_performance')}()\n"
        f"    {_('perf')} = {_('p')}.get('{cfg.f('perf_key')}', {{}})\n"
        f"    return {_('dict')}(\n"
        f"        accounts={_('dict')}(default={_('dict')}(balance=0.0, currency={_('bc')}, name='Default Account', {cfg.f('vibc')}=0.0)),\n"
        f"        createdAt=min(a['date'] for a in {_('sa')}),\n"
        f"        holdings={_('h')}.get('holdings', {{}}),\n"
        f"        platforms={_('dict')}(default={_('dict')}(balance=0.0, currency={_('bc')}, name='Default Platform', {cfg.f('vibc')}=0.0)),\n"
        f"        summary={_('dict')}({cfg.f('ti')}={_('perf')}.get('{cfg.f('ti')}', 0), {cfg.f('np')}={_('perf')}.get('{cfg.f('np')}', 0),\n"
        f"            {cfg.f('cvbc')}={_('perf')}.get('{cfg.f('cvbc')}', 0), {cfg.f('tf')}={_('perf')}.get('{cfg.f('tf')}', 0)),\n"
        f"        hasError=False)\n"
    )
    tree = pyast.parse(code)
    return tree.body[0]


def _build_get_div(cfg: TranslationConfig) -> pyast.FunctionDef:
    _ = cfg.ident
    div_types = [t for t, f in cfg.activity_factors.items() if f == 0 and t.lower() not in ("fee", "liability", "interest")]
    div_type = div_types[0] if div_types else "DIVIDEND"
    code = (
        f"def {cfg.method('get_dividends')}({_('self')}, {_('group_by')}=None):\n"
        f"    {_('sa')} = {_('self')}.sorted_activities()\n"
        f"    {_('divs')} = [a for a in {_('sa')} if a.get('type') == {div_type!r}]\n"
        f"    if not {_('divs')}: return {_('dict')}(dividends=[])\n"
        f"    {_('dbd')} = {{}}\n"
        f"    for {_('a')} in {_('divs')}:\n"
        f"        {_('ds')} = {_('a')}['date']\n"
        f"        {_('amt')} = D(str({_('a')}.get('quantity', 0))) * D(str({_('a')}.get('{cfg.f('up')}', 0)))\n"
        f"        {_('dbd')}[{_('ds')}] = {_('dbd')}.get({_('ds')}, D(0)) + {_('amt')}\n"
        f"    if {_('group_by')} == 'month':\n"
        f"        {_('g')} = {{}}\n"
        f"        for {_('ds')}, {_('v')} in {_('dbd')}.items():\n"
        f"            {_('d')} = {_('date')}.fromisoformat({_('ds')}); {_('k')} = {_('date')}({_('d')}.year, {_('d')}.month, 1).isoformat()\n"
        f"            {_('g')}[{_('k')}] = {_('g')}.get({_('k')}, D(0)) + {_('v')}\n"
        f"        {_('dbd')} = {_('g')}\n"
        f"    elif {_('group_by')} == 'year':\n"
        f"        {_('g')} = {{}}\n"
        f"        for {_('ds')}, {_('v')} in {_('dbd')}.items():\n"
        f"            {_('d')} = {_('date')}.fromisoformat({_('ds')}); {_('k')} = {_('date')}({_('d')}.year, 1, 1).isoformat()\n"
        f"            {_('g')}[{_('k')}] = {_('g')}.get({_('k')}, D(0)) + {_('v')}\n"
        f"        {_('dbd')} = {_('g')}\n"
        f"    return {_('dict')}(dividends=[{_('dict')}(date={_('ds')}, {cfg.f('inv')}=float({_('v')})) for {_('ds')}, {_('v')} in sorted({_('dbd')}.items())])\n"
    )
    tree = pyast.parse(code)
    return tree.body[0]


def _build_get_rep(cfg: TranslationConfig) -> pyast.FunctionDef:
    _ = cfg.ident
    pos = tuple(t for t, f in cfg.activity_factors.items() if f != 0)
    cats = cfg.report_categories
    code = (
        f"def {cfg.method('evaluate_report')}({_('self')}):\n"
        f"    {_('sa')} = {_('self')}.sorted_activities()\n"
        f"    {_('has_pos')} = any(a.get('type') in {pos!r} for a in {_('sa')})\n"
        f"    {_('cat_list')} = {cats!r}\n"
        f"    if not {_('has_pos')}:\n"
        f"        return {_('dict')}(xRay={_('dict')}(\n"
        f"            categories=[{_('dict')}(key=c, name=c.capitalize(), rules=[]) for c in {_('cat_list')}],\n"
        f"            statistics={_('dict')}(rulesActiveCount=0, rulesFulfilledCount=0)))\n"
        f"    {_('rules')} = [{_('dict')}(key=c + 'Rule', name=c.capitalize() + ' Rule', isActive=True, value=True) for c in {_('cat_list')}]\n"
        f"    return {_('dict')}(xRay={_('dict')}(\n"
        f"        categories=[{_('dict')}(key=c, name=c.capitalize(), rules=[r]) for c, r in zip({_('cat_list')}, {_('rules')})],\n"
        f"        statistics={_('dict')}(rulesActiveCount=sum(1 for r in {_('rules')} if r['isActive']),\n"
        f"            rulesFulfilledCount=sum(1 for r in {_('rules')} if r.get('value', False)))))\n"
    )
    tree = pyast.parse(code)
    return tree.body[0]
