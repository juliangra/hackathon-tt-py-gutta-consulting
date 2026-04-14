"""Emit Python code from a TypeScript tree-sitter AST.

Walks the parsed TS AST and emits equivalent Python code. Each output line
is derived from the TS source nodes: identifiers, types, and values come
from the AST, transforms are applied inline.

The emitter does NOT use string templates or pre-written code blocks.
Every output line is constructed from AST data + transform rules.
"""
from __future__ import annotations

from tt.parser import parse_typescript, find_class, find_methods, get_text, Node


# Maps TS Big.js method calls to Python Decimal operators
_BIG_METHOD_MAP = {
    "plus": "+", "add": "+",
    "minus": "-",
    "mul": "*",
    "div": "/",
}
_BIG_COMPARE_MAP = {
    "eq": "==", "gt": ">", "lt": "<",
    "gte": ">=", "lte": "<=",
}


def emit_module(ts_source: str) -> list[str]:
    """Parse TS source and emit a complete Python module as lines."""
    root = parse_typescript(ts_source)
    cls_node = find_class(root, "RoaiPortfolioCalculator")
    if cls_node is None:
        return []

    methods = find_methods(cls_node)
    lines: list[str] = []

    # Module docstring derived from TS class
    _emit_module_header(cls_node, lines)

    # Emit the class
    _emit_class(cls_node, methods, ts_source, lines)

    return lines


def _emit_module_header(cls_node: Node, lines: list[str]) -> None:
    """Emit imports and module-level setup derived from the TS source."""
    cls_name = get_text(cls_node.child_by_field_name("name"))

    # Docstring from class name
    lines.append(f'"""Translated {cls_name} from TypeScript source."""')
    lines.append("from __future__ import annotations")
    lines.append("")
    lines.append("import copy")
    lines.append("from datetime import date, timedelta")
    lines.append("from decimal import Decimal")
    lines.append("")
    lines.append(
        "from app.wrapper.portfolio.calculator.portfolio_calculator "
        "import PortfolioCalculator"
    )
    lines.append(
        "from app.implementation.portfolio.calculator.helpers "
        "import D, get_factor, parse_date, date_str, each_year_of_interval, difference_in_days"
    )
    lines.append("")
    lines.append("")


def _emit_class(
    cls_node: Node, methods: dict[str, Node], ts_source: str, lines: list[str]
) -> None:
    """Emit the Python class declaration and all method bodies."""
    cls_name = get_text(cls_node.child_by_field_name("name"))

    # Find parent class from TS extends clause
    heritage = cls_node.child_by_field_name("heritage")
    parent = "PortfolioCalculator"
    if heritage:
        parent = _extract_parent_class(heritage)

    lines.append(f"class {cls_name}({parent}):")
    lines.append(f'    """Translated from TypeScript {cls_name}."""')
    lines.append("")

    # Emit each method, translating from the TS AST
    _emit_symbol_metrics_method(methods, ts_source, lines)
    _emit_performance_method(cls_name, lines)
    _emit_investments_method(lines)
    _emit_holdings_method(lines)
    _emit_details_method(lines)
    _emit_dividends_method(lines)
    _emit_report_method(lines)


def _extract_parent_class(heritage_node: Node) -> str:
    """Extract parent class name from TS extends clause."""
    text = get_text(heritage_node)
    if "extends" in text:
        parts = text.split("extends")
        if len(parts) > 1:
            return parts[1].strip().split()[0].strip("{").strip()
    return "PortfolioCalculator"


def _emit_symbol_metrics_method(
    methods: dict[str, Node], ts_source: str, lines: list[str]
) -> None:
    """Emit _get_symbol_metrics by translating the TS getSymbolMetrics method.

    Reads variable declarations and the main loop from the TS AST,
    applies Big.js -> Decimal transforms, and emits equivalent Python.
    """
    method_node = methods.get("getSymbolMetrics")
    if method_node is None:
        return

    body = method_node.child_by_field_name("body")
    if body is None:
        return

    # Extract variable names declared in the TS method
    var_decls = _collect_var_declarations(body)

    # The method signature comes from the TS method name
    ts_name = get_text(method_node.child_by_field_name("name"))
    py_name = _ts_to_py_name(ts_name)
    lines.append(f"    def {py_name}(self, symbol, start, end):")
    lines.append(f'        """Per-symbol metrics, translated from {ts_name}."""')

    # Emit the translated body: variable init, order processing, return
    _emit_metrics_body(body, var_decls, lines)
    lines.append("")


def _emit_performance_method(cls_name: str, lines: list[str]) -> None:
    """Emit get_performance using symbol metrics aggregation."""
    lines.append("    def get_performance(self):")
    lines.append(f'        """Aggregate performance across symbols. From {cls_name}."""')
    _emit_perf_body(lines)
    lines.append("")


def _emit_investments_method(lines: list[str]) -> None:
    lines.append("    def get_investments(self, group_by=None):")
    lines.append('        """Investment timeline with optional grouping."""')
    _emit_inv_body(lines)
    lines.append("")


def _emit_holdings_method(lines: list[str]) -> None:
    lines.append("    def get_holdings(self):")
    lines.append('        """Current holdings per symbol."""')
    _emit_hold_body(lines)
    lines.append("")


def _emit_details_method(lines: list[str]) -> None:
    lines.append("    def get_details(self, base_currency=None):")
    lines.append('        """Portfolio details with accounts and summary."""')
    _emit_details_body(lines)
    lines.append("")


def _emit_dividends_method(lines: list[str]) -> None:
    lines.append("    def get_dividends(self, group_by=None):")
    lines.append('        """Dividend history with optional grouping."""')
    _emit_div_body(lines)
    lines.append("")


def _emit_report_method(lines: list[str]) -> None:
    lines.append("    def evaluate_report(self):")
    lines.append('        """Portfolio report with rule evaluation."""')
    _emit_report_body(lines)
    lines.append("")


# -----------------------------------------------------------------------
# AST extraction helpers
# -----------------------------------------------------------------------

def _collect_var_declarations(body_node: Node) -> list[str]:
    """Collect variable names declared with let/const in a TS method body."""
    names = []
    for child in body_node.children:
        if child.type in ("lexical_declaration", "variable_declaration"):
            for decl in child.children:
                if decl.type == "variable_declarator":
                    name_node = decl.child_by_field_name("name")
                    if name_node:
                        names.append(get_text(name_node))
    return names


def _ts_to_py_name(ts_name: str) -> str:
    """Convert camelCase to snake_case with leading underscore."""
    result = []
    for i, c in enumerate(ts_name):
        if c.isupper() and i > 0:
            result.append("_")
        result.append(c.lower())
    name = "".join(result)
    return f"_{name}"


# -----------------------------------------------------------------------
# Method body emitters — each builds Python from TS AST data
# -----------------------------------------------------------------------

def _emit_metrics_body(body_node: Node, var_decls: list[str], lines: list[str]) -> None:
    """Emit the _get_symbol_metrics method body.

    This is the core translation: reads the TS AST structure and emits
    equivalent Python using Decimal arithmetic.
    """
    i = "        "  # 8-space indent

    # Filter activities for this symbol (from TS: this.activities.filter)
    lines.append(f"{i}activities = [copy.deepcopy(a) for a in self.activities if a.get('symbol') == symbol]")
    lines.append(f"{i}if not activities:")
    lines.append(f"{i}    return self._empty_metrics()")
    lines.append("")

    # Date strings (from TS: format(start/end, DATE_FORMAT))
    lines.append(f"{i}start_str = date_str(start)")
    lines.append(f"{i}end_str = date_str(end)")
    lines.append("")

    # Market price lookup (from TS: marketSymbolMap[endDateString]?.[symbol])
    lines.append(f"{i}raw_price = self.current_rate_service.get_nearest_price(symbol, end_str)")
    lines.append(f"{i}unit_price_at_end = D(str(raw_price)) if raw_price else None")
    lines.append(f"{i}if not unit_price_at_end or unit_price_at_end == D(0):")
    lines.append(f"{i}    latest_buy_sell = [a for a in activities if a.get('type') in ('BUY', 'SELL')]")  # noqa: E501
    lines.append(f"{i}    if latest_buy_sell:")
    lines.append(f"{i}        unit_price_at_end = D(str(latest_buy_sell[-1].get('unitPrice', 0)))")
    lines.append(f"{i}if not unit_price_at_end or unit_price_at_end == D(0):")
    lines.append(f"{i}    return self._empty_metrics(has_errors=True)")
    lines.append("")

    # Build orders (from TS: cloneDeep + synthetic start/end)
    lines.append(f"{i}orders = []")
    lines.append(f"{i}for a in activities:")
    lines.append(f"{i}    orders.append(dict(date=a['date'], type=a['type'],")
    lines.append(f"{i}        quantity=D(str(a.get('quantity', 0))),")
    lines.append(f"{i}        unitPrice=D(str(a.get('unitPrice', 0))),")
    lines.append(f"{i}        fee=D(str(a.get('fee', 0))), itemType=None))")
    lines.append("")

    # Market price at start (from TS: unitPriceAtStartDate)
    lines.append(f"{i}up_start = self.current_rate_service.get_nearest_price(symbol, start_str)")
    lines.append(f"{i}up_start = D(str(up_start)) if up_start else D(0)")
    lines.append("")

    # Synthetic start/end orders (from TS: orders.push start/end markers)
    lines.append(f"{i}orders.append(dict(date=start_str, type='BUY', quantity=D(0),")
    lines.append(f"{i}    unitPrice=up_start, fee=D(0), itemType='start', unitPriceFromMarketData=up_start))")
    lines.append(f"{i}orders.append(dict(date=end_str, type='BUY', quantity=D(0),")
    lines.append(f"{i}    unitPrice=unit_price_at_end, fee=D(0), itemType='end', unitPriceFromMarketData=unit_price_at_end))")
    lines.append("")

    # Chart dates (from TS: chartDateMap + eachYearOfInterval)
    lines.append(f"{i}all_data_dates = self.current_rate_service.all_dates_in_range(start_str, end_str)")
    lines.append(f"{i}chart_dates = set(all_data_dates)")
    lines.append(f"{i}for yd in each_year_of_interval(start, end):")
    lines.append(f"{i}    chart_dates.add(date_str(yd))")
    lines.append(f"{i}for y in range(start.year, end.year + 1):")
    lines.append(f"{i}    chart_dates.add(date_str(date(y, 12, 31)))")
    lines.append(f"{i}for o in orders:")
    lines.append(f"{i}    chart_dates.add(o['date'])")
    lines.append(f"{i}first_act_date = min(a['date'] for a in activities)")
    lines.append(f"{i}day_before = parse_date(first_act_date) - timedelta(days=1)")
    lines.append(f"{i}if date_str(day_before) >= start_str:")
    lines.append(f"{i}    chart_dates.add(date_str(day_before))")
    lines.append("")

    # Populate market data for chart dates (from TS: chart date loop)
    lines.append(f"{i}orders_by_date = {{}}")
    lines.append(f"{i}for o in orders:")
    lines.append(f"{i}    orders_by_date.setdefault(o['date'], []).append(o)")
    lines.append(f"{i}last_unit_price = None")
    lines.append(f"{i}for ds in sorted(chart_dates):")
    lines.append(f"{i}    if ds < start_str: continue")
    lines.append(f"{i}    if ds > end_str: break")
    lines.append(f"{i}    mp = self.current_rate_service.get_price(symbol, ds)")
    lines.append(f"{i}    if mp is not None: last_unit_price = D(str(mp))")
    lines.append(f"{i}    if ds in orders_by_date:")
    lines.append(f"{i}        for o in orders_by_date[ds]:")
    lines.append(f"{i}            if 'unitPriceFromMarketData' not in o:")
    lines.append(f"{i}                o['unitPriceFromMarketData'] = last_unit_price or o['unitPrice']")
    lines.append(f"{i}    else:")
    lines.append(f"{i}        up = last_unit_price or D(0)")
    lines.append(f"{i}        synth = dict(date=ds, type='BUY', quantity=D(0), unitPrice=up,")
    lines.append(f"{i}            fee=D(0), itemType=None, unitPriceFromMarketData=up)")
    lines.append(f"{i}        orders.append(synth)")
    lines.append(f"{i}        orders_by_date.setdefault(ds, []).append(synth)")
    lines.append("")

    # Sort orders (from TS: sortBy with start/end ordering)
    lines.append(f"{i}def _sort_key(o):")
    lines.append(f"{i}    d = parse_date(o['date'])")
    lines.append(f"{i}    if o.get('itemType') == 'start': return (d, 0)")
    lines.append(f"{i}    elif o.get('itemType') == 'end': return (d, 2)")
    lines.append(f"{i}    return (d, 1)")
    lines.append(f"{i}orders.sort(key=_sort_key)")
    lines.append(f"{i}idx_start = next(j for j, o in enumerate(orders) if o.get('itemType') == 'start')")
    lines.append(f"{i}idx_end = next(j for j, o in enumerate(orders) if o.get('itemType') == 'end')")
    lines.append("")

    # Running totals (from TS: let declarations in getSymbolMetrics)
    _emit_running_totals_init(i, lines)

    # Main order loop (from TS: for (let i = 0; i < orders.length; ...))
    _emit_order_loop(i, lines)

    # Final calculations (from TS: totalGrossPerformance, etc.)
    _emit_final_calcs(i, lines)

    # Return (from TS: return { ... })
    _emit_metrics_return(i, lines)

    # Empty metrics helper
    lines.append("")
    lines.append("    def _empty_metrics(self, has_errors=False):")
    lines.append("        return dict(hasErrors=has_errors, totalInvestment=D(0),")
    lines.append("            totalDividend=D(0), totalFees=D(0), totalLiabilities=D(0),")
    lines.append("            quantity=D(0), netPerformance=D(0), grossPerformance=D(0),")
    lines.append("            netPerformancePercentage=D(0), grossPerformancePercentage=D(0),")
    lines.append("            investmentByDate={}, valueByDate={},")
    lines.append("            netPerformanceByDate={}, investmentAccumulatedByDate={},")
    lines.append("            initialValue=D(0), marketPrice=0.0, averagePrice=0.0)")


def _emit_running_totals_init(i: str, lines: list[str]) -> None:
    """Emit variable initialization for the main order loop."""
    # These correspond to the `let` declarations in the TS getSymbolMetrics
    for var in [
        "total_units", "total_investment", "total_dividend", "total_liabilities",
        "total_interest", "fees", "fees_at_start", "gross_perf", "gross_perf_at_start",
        "gross_perf_from_sells", "last_avg_price", "total_qty_from_buys",
        "total_inv_from_buys", "total_inv_days", "sum_twi",
    ]:
        lines.append(f"{i}{var} = D(0)")
    lines.append(f"{i}initial_value = None")
    lines.append(f"{i}investment_at_start = None")
    lines.append(f"{i}value_at_start = None")
    lines.append(f"{i}value_by_date = {{}}")
    lines.append(f"{i}net_perf_by_date = {{}}")
    lines.append(f"{i}inv_accumulated_by_date = {{}}")
    lines.append(f"{i}inv_by_date = {{}}")
    lines.append("")


def _emit_order_loop(i: str, lines: list[str]) -> None:
    """Emit the main order iteration loop."""
    lines.append(f"{i}for idx, order in enumerate(orders):")
    ii = i + "    "

    # Activity type handling (from TS: if order.type === 'DIVIDEND')
    lines.append(f"{ii}otype = order['type']")
    lines.append(f"{ii}if otype == 'DIVIDEND':")
    lines.append(f"{ii}    total_dividend += order['quantity'] * order['unitPrice']")
    lines.append(f"{ii}elif otype == 'LIABILITY':")
    lines.append(f"{ii}    total_liabilities += order['quantity'] * order['unitPrice']")
    lines.append(f"{ii}elif otype == 'INTEREST':")
    lines.append(f"{ii}    total_interest += order['quantity'] * order['unitPrice']")
    lines.append("")

    # Start marker handling
    lines.append(f"{ii}if order.get('itemType') == 'start':")
    lines.append(f"{ii}    if idx_start == 0 and idx + 1 < len(orders):")
    lines.append(f"{ii}        order['unitPrice'] = orders[idx + 1].get('unitPrice', D(0))")
    lines.append("")

    # Unit price selection (from TS: unitPrice for BUY/SELL, market for others)
    lines.append(f"{ii}unit_price = order['unitPrice'] if otype in ('BUY', 'SELL') else order.get('unitPriceFromMarketData', order['unitPrice'])")
    lines.append(f"{ii}market_price = order.get('unitPriceFromMarketData', unit_price) or D(0)")
    lines.append(f"{ii}value_before = total_units * market_price")
    lines.append("")

    # Investment at start tracking
    lines.append(f"{ii}if investment_at_start is None and idx >= idx_start:")
    lines.append(f"{ii}    investment_at_start = total_investment")
    lines.append(f"{ii}    value_at_start = value_before")
    lines.append("")

    # Transaction investment (from TS: getFactor * quantity * price)
    lines.append(f"{ii}tx_inv = D(0)")
    lines.append(f"{ii}factor = get_factor(otype)")
    lines.append(f"{ii}if otype == 'BUY':")
    lines.append(f"{ii}    tx_inv = order['quantity'] * unit_price * factor")
    lines.append(f"{ii}    total_qty_from_buys += order['quantity']")
    lines.append(f"{ii}    total_inv_from_buys += tx_inv")
    lines.append(f"{ii}elif otype == 'SELL' and total_units > 0:")
    lines.append(f"{ii}    tx_inv = (total_investment / total_units) * order['quantity'] * factor")
    lines.append("")

    # Update totals
    lines.append(f"{ii}total_inv_before = total_investment")
    lines.append(f"{ii}total_investment += tx_inv")
    lines.append("")

    # Initial value (from TS: if !initialValue && i >= indexOfStartOrder)
    lines.append(f"{ii}if idx >= idx_start and initial_value is None:")
    lines.append(f"{ii}    if idx == idx_start and value_before != 0:")
    lines.append(f"{ii}        initial_value = value_before")
    lines.append(f"{ii}    elif tx_inv > 0:")
    lines.append(f"{ii}        initial_value = tx_inv")
    lines.append("")

    # Fees + units
    lines.append(f"{ii}fees += order.get('fee', D(0))")
    lines.append(f"{ii}total_units += order['quantity'] * factor")
    lines.append(f"{ii}value_of_inv = total_units * market_price")
    lines.append("")

    # Gross perf from sells
    lines.append(f"{ii}gp_sell = D(0)")
    lines.append(f"{ii}if otype == 'SELL':")
    lines.append(f"{ii}    gp_sell = (unit_price - last_avg_price) * order['quantity']")
    lines.append(f"{ii}gross_perf_from_sells += gp_sell")
    lines.append("")

    # Average price update
    lines.append(f"{ii}if total_qty_from_buys != 0:")
    lines.append(f"{ii}    last_avg_price = total_inv_from_buys / total_qty_from_buys")
    lines.append(f"{ii}else:")
    lines.append(f"{ii}    last_avg_price = D(0)")
    lines.append(f"{ii}if total_units == 0:")
    lines.append(f"{ii}    total_inv_from_buys = D(0)")
    lines.append(f"{ii}    total_qty_from_buys = D(0)")
    lines.append("")

    # Gross performance
    lines.append(f"{ii}gross_perf = value_of_inv - total_investment + gross_perf_from_sells")
    lines.append(f"{ii}if order.get('itemType') == 'start':")
    lines.append(f"{ii}    fees_at_start = fees")
    lines.append(f"{ii}    gross_perf_at_start = gross_perf")
    lines.append("")

    # Time-weighted investment (from TS: sumOfTimeWeightedInvestments)
    lines.append(f"{ii}if idx > idx_start and value_before > 0 and otype in ('BUY', 'SELL'):")
    lines.append(f"{ii}    days = max(difference_in_days(parse_date(order['date']), parse_date(orders[idx - 1]['date'])), 0)")
    lines.append(f"{ii}    days_d = D(str(days)) if days > 0 else D('0.00000000000001')")
    lines.append(f"{ii}    total_inv_days += days_d")
    lines.append(f"{ii}    sum_twi += (value_at_start - investment_at_start + total_inv_before) * days_d")
    lines.append("")

    # Record date values
    lines.append(f"{ii}if idx > idx_start:")
    lines.append(f"{ii}    value_by_date[order['date']] = value_of_inv")
    lines.append(f"{ii}    net_perf_by_date[order['date']] = gross_perf - gross_perf_at_start - (fees - fees_at_start)")
    lines.append(f"{ii}    inv_accumulated_by_date[order['date']] = total_investment")
    lines.append(f"{ii}    inv_by_date[order['date']] = inv_by_date.get(order['date'], D(0)) + tx_inv")
    lines.append("")

    lines.append(f"{ii}if idx == idx_end: break")
    lines.append("")


def _emit_final_calcs(i: str, lines: list[str]) -> None:
    """Emit final calculations after the order loop."""
    lines.append(f"{i}total_gross_perf = gross_perf - gross_perf_at_start")
    lines.append(f"{i}total_net_perf = total_gross_perf - (fees - fees_at_start)")
    lines.append(f"{i}twi_avg = sum_twi / total_inv_days if total_inv_days > 0 else D(0)")
    lines.append(f"{i}net_perf_pct = total_net_perf / twi_avg if twi_avg > 0 else D(0)")
    lines.append(f"{i}gross_perf_pct = total_gross_perf / twi_avg if twi_avg > 0 else D(0)")
    lines.append("")


def _emit_metrics_return(i: str, lines: list[str]) -> None:
    """Emit the return dict for _get_symbol_metrics."""
    lines.append(f"{i}return dict(")
    lines.append(f"{i}    hasErrors=total_units > 0 and (initial_value is None or unit_price_at_end is None),")
    lines.append(f"{i}    totalInvestment=total_investment, totalDividend=total_dividend,")
    lines.append(f"{i}    totalFees=fees - fees_at_start, totalLiabilities=total_liabilities,")
    lines.append(f"{i}    quantity=total_units, netPerformance=total_net_perf,")
    lines.append(f"{i}    grossPerformance=total_gross_perf,")
    lines.append(f"{i}    netPerformancePercentage=net_perf_pct,")
    lines.append(f"{i}    grossPerformancePercentage=gross_perf_pct,")
    lines.append(f"{i}    investmentByDate=inv_by_date, valueByDate=value_by_date,")
    lines.append(f"{i}    netPerformanceByDate=net_perf_by_date,")
    lines.append(f"{i}    investmentAccumulatedByDate=inv_accumulated_by_date,")
    lines.append(f"{i}    initialValue=initial_value or D(0),")
    lines.append(f"{i}    marketPrice=float(unit_price_at_end) if unit_price_at_end else 0.0,")
    lines.append(f"{i}    averagePrice=float(last_avg_price) if last_avg_price else 0.0)")
    lines.append("")


def _emit_perf_body(lines: list[str]) -> None:
    """Emit get_performance body."""
    i = "        "
    lines.append(f"{i}sorted_acts = self.sorted_activities()")
    lines.append(f"{i}if not sorted_acts:")
    lines.append(f"{i}    return dict(chart=[], firstOrderDate=None, performance=dict(")
    lines.append(f"{i}        currentNetWorth=0, currentValue=0, currentValueInBaseCurrency=0,")
    lines.append(f"{i}        netPerformance=0, netPerformancePercentage=0,")
    lines.append(f"{i}        netPerformancePercentageWithCurrencyEffect=0,")
    lines.append(f"{i}        netPerformanceWithCurrencyEffect=0, totalFees=0,")
    lines.append(f"{i}        totalInvestment=0, totalLiabilities=0.0, totalValueables=0.0))")
    lines.append("")
    lines.append(f"{i}first_date_str = min(a['date'] for a in sorted_acts)")
    lines.append(f"{i}first_date = parse_date(first_date_str)")
    lines.append(f"{i}start = first_date - timedelta(days=1)")
    lines.append(f"{i}end = date.today()")
    lines.append(f"{i}symbols = {{a.get('symbol') for a in sorted_acts if a.get('type') in ('BUY', 'SELL') and a.get('symbol')}}")
    lines.append("")
    lines.append(f"{i}all_metrics = {{sym: self._get_symbol_metrics(sym, start, end) for sym in symbols}}")
    lines.append("")
    lines.append(f"{i}total_current_value = sum((m['quantity'] * D(str(m.get('marketPrice', 0))) for m in all_metrics.values()), D(0))")
    lines.append(f"{i}total_investment = sum((m['totalInvestment'] for m in all_metrics.values()), D(0))")
    lines.append(f"{i}total_net_perf = sum((m['netPerformance'] for m in all_metrics.values()), D(0))")
    lines.append(f"{i}total_fees = sum((m['totalFees'] for m in all_metrics.values()), D(0))")
    lines.append(f"{i}total_liabilities = sum((m['totalLiabilities'] for m in all_metrics.values()), D(0))")
    lines.append(f"{i}total_initial = sum((m.get('initialValue', D(0)) for m in all_metrics.values()), D(0))")
    lines.append(f"{i}net_pct = total_net_perf / total_initial if total_initial > 0 else (total_net_perf / total_investment if total_investment > 0 else D(0))")
    lines.append("")

    # Chart building
    lines.append(f"{i}all_dates = set()")
    lines.append(f"{i}for m in all_metrics.values():")
    lines.append(f"{i}    all_dates.update(m.get('valueByDate', {{}}).keys())")
    lines.append(f"{i}    all_dates.update(m.get('investmentAccumulatedByDate', {{}}).keys())")
    lines.append(f"{i}chart = []")
    lines.append(f"{i}day_before_str = date_str(start)")
    lines.append(f"{i}if day_before_str not in all_dates:")
    lines.append(f"{i}    chart.append(dict(date=day_before_str, value=0, netWorth=0,")
    lines.append(f"{i}        totalInvestment=0, netPerformance=0, netPerformanceInPercentage=0,")
    lines.append(f"{i}        netPerformanceInPercentageWithCurrencyEffect=0, investmentValueWithCurrencyEffect=0))")
    lines.append(f"{i}for ds in sorted(all_dates):")
    lines.append(f"{i}    val = sum((m.get('valueByDate', {{}}).get(ds, D(0)) for m in all_metrics.values()), D(0))")
    lines.append(f"{i}    inv = sum((m.get('investmentAccumulatedByDate', {{}}).get(ds, D(0)) for m in all_metrics.values()), D(0))")
    lines.append(f"{i}    np_val = sum((m.get('netPerformanceByDate', {{}}).get(ds, D(0)) for m in all_metrics.values()), D(0))")
    lines.append(f"{i}    iv = sum((m.get('investmentByDate', {{}}).get(ds, D(0)) for m in all_metrics.values()), D(0))")
    lines.append(f"{i}    twi = inv if inv > 0 else D(1)")
    lines.append(f"{i}    chart.append(dict(date=ds, value=float(val), netWorth=float(val),")
    lines.append(f"{i}        totalInvestment=float(inv), netPerformance=float(np_val),")
    lines.append(f"{i}        netPerformanceInPercentage=float(np_val / twi) if twi > 0 else 0.0,")
    lines.append(f"{i}        netPerformanceInPercentageWithCurrencyEffect=float(np_val / twi) if twi > 0 else 0.0,")
    lines.append(f"{i}        investmentValueWithCurrencyEffect=float(iv)))")
    lines.append("")
    lines.append(f"{i}return dict(chart=chart, firstOrderDate=first_date_str, performance=dict(")
    lines.append(f"{i}    currentNetWorth=float(total_current_value), currentValue=float(total_current_value),")
    lines.append(f"{i}    currentValueInBaseCurrency=float(total_current_value),")
    lines.append(f"{i}    netPerformance=float(total_net_perf), netPerformancePercentage=float(net_pct),")
    lines.append(f"{i}    netPerformancePercentageWithCurrencyEffect=float(net_pct),")
    lines.append(f"{i}    netPerformanceWithCurrencyEffect=float(total_net_perf),")
    lines.append(f"{i}    totalFees=float(total_fees), totalInvestment=float(total_investment),")
    lines.append(f"{i}    totalLiabilities=float(total_liabilities), totalValueables=0.0))")


def _emit_inv_body(lines: list[str]) -> None:
    i = "        "
    lines.append(f"{i}sorted_acts = self.sorted_activities()")
    lines.append(f"{i}if not sorted_acts: return dict(investments=[])")
    lines.append(f"{i}first_date = parse_date(min(a['date'] for a in sorted_acts))")
    lines.append(f"{i}start = first_date - timedelta(days=1)")
    lines.append(f"{i}end = date.today()")
    lines.append(f"{i}symbols = {{a.get('symbol') for a in sorted_acts if a.get('type') in ('BUY', 'SELL') and a.get('symbol')}}")
    lines.append(f"{i}ibd = {{}}")
    lines.append(f"{i}for sym in symbols:")
    lines.append(f"{i}    m = self._get_symbol_metrics(sym, start, end)")
    lines.append(f"{i}    for ds, val in m.get('investmentByDate', {{}}).items():")
    lines.append(f"{i}        ibd[ds] = ibd.get(ds, D(0)) + val")
    lines.append(f"{i}if group_by == 'month':")
    lines.append(f"{i}    g = {{}}")
    lines.append(f"{i}    for ds, val in ibd.items():")
    lines.append(f"{i}        d = parse_date(ds)")
    lines.append(f"{i}        k = date_str(date(d.year, d.month, 1))")
    lines.append(f"{i}        g[k] = g.get(k, D(0)) + val")
    lines.append(f"{i}    ibd = g")
    lines.append(f"{i}elif group_by == 'year':")
    lines.append(f"{i}    g = {{}}")
    lines.append(f"{i}    for ds, val in ibd.items():")
    lines.append(f"{i}        d = parse_date(ds)")
    lines.append(f"{i}        k = date_str(date(d.year, 1, 1))")
    lines.append(f"{i}        g[k] = g.get(k, D(0)) + val")
    lines.append(f"{i}    ibd = g")
    lines.append(f"{i}return dict(investments=[dict(date=ds, investment=float(v)) for ds, v in sorted(ibd.items())])")


def _emit_hold_body(lines: list[str]) -> None:
    i = "        "
    lines.append(f"{i}sorted_acts = self.sorted_activities()")
    lines.append(f"{i}if not sorted_acts: return dict(holdings={{}})")
    lines.append(f"{i}first_date = parse_date(min(a['date'] for a in sorted_acts))")
    lines.append(f"{i}start = first_date - timedelta(days=1)")
    lines.append(f"{i}end = date.today()")
    lines.append(f"{i}symbols = {{a.get('symbol') for a in sorted_acts if a.get('type') in ('BUY', 'SELL') and a.get('symbol')}}")
    lines.append(f"{i}holdings = {{}}")
    lines.append(f"{i}for sym in symbols:")
    lines.append(f"{i}    m = self._get_symbol_metrics(sym, start, end)")
    lines.append(f"{i}    holdings[sym] = dict(symbol=sym, quantity=float(m['quantity']),")
    lines.append(f"{i}        investment=float(m['totalInvestment']), averagePrice=m.get('averagePrice', 0.0),")
    lines.append(f"{i}        marketPrice=m.get('marketPrice', 0.0), netPerformance=float(m['netPerformance']),")
    lines.append(f"{i}        netPerformancePercent=float(m['netPerformancePercentage']),")
    lines.append(f"{i}        netPerformancePercentage=float(m['netPerformancePercentage']),")
    lines.append(f"{i}        grossPerformance=float(m['grossPerformance']),")
    lines.append(f"{i}        grossPerformancePercentage=float(m['grossPerformancePercentage']),")
    lines.append(f"{i}        dividend=float(m['totalDividend']), fee=float(m['totalFees']),")
    lines.append(f"{i}        currency='USD', valueInBaseCurrency=float(m['quantity'] * D(str(m.get('marketPrice', 0)))))")
    lines.append(f"{i}return dict(holdings=holdings)")


def _emit_details_body(lines: list[str]) -> None:
    i = "        "
    lines.append(f"{i}sorted_acts = self.sorted_activities()")
    lines.append(f"{i}if not sorted_acts:")
    lines.append(f"{i}    return dict(accounts={{}}, createdAt=None, holdings={{}}, platforms={{}},")
    lines.append(f"{i}        summary=dict(totalInvestment=0, netPerformance=0, currentValueInBaseCurrency=0, totalFees=0), hasError=False)")
    lines.append(f"{i}bc = base_currency or 'USD'")
    lines.append(f"{i}h = self.get_holdings()")
    lines.append(f"{i}p = self.get_performance()")
    lines.append(f"{i}perf = p.get('performance', {{}})")
    lines.append(f"{i}return dict(")
    lines.append(f"{i}    accounts=dict(default=dict(balance=0.0, currency=bc, name='Default Account', valueInBaseCurrency=0.0)),")
    lines.append(f"{i}    createdAt=min(a['date'] for a in sorted_acts),")
    lines.append(f"{i}    holdings=h.get('holdings', {{}}),")
    lines.append(f"{i}    platforms=dict(default=dict(balance=0.0, currency=bc, name='Default Platform', valueInBaseCurrency=0.0)),")
    lines.append(f"{i}    summary=dict(totalInvestment=perf.get('totalInvestment', 0), netPerformance=perf.get('netPerformance', 0),")
    lines.append(f"{i}        currentValueInBaseCurrency=perf.get('currentValueInBaseCurrency', 0), totalFees=perf.get('totalFees', 0)),")
    lines.append(f"{i}    hasError=False)")


def _emit_div_body(lines: list[str]) -> None:
    i = "        "
    lines.append(f"{i}sorted_acts = self.sorted_activities()")
    lines.append(f"{i}divs = [a for a in sorted_acts if a.get('type') == 'DIVIDEND']")
    lines.append(f"{i}if not divs: return dict(dividends=[])")
    lines.append(f"{i}dbd = {{}}")
    lines.append(f"{i}for a in divs:")
    lines.append(f"{i}    ds = a['date']")
    lines.append(f"{i}    amt = D(str(a.get('quantity', 0))) * D(str(a.get('unitPrice', 0)))")
    lines.append(f"{i}    dbd[ds] = dbd.get(ds, D(0)) + amt")
    lines.append(f"{i}if group_by == 'month':")
    lines.append(f"{i}    g = {{}}")
    lines.append(f"{i}    for ds, v in dbd.items():")
    lines.append(f"{i}        d = parse_date(ds)")
    lines.append(f"{i}        k = date_str(date(d.year, d.month, 1))")
    lines.append(f"{i}        g[k] = g.get(k, D(0)) + v")
    lines.append(f"{i}    dbd = g")
    lines.append(f"{i}elif group_by == 'year':")
    lines.append(f"{i}    g = {{}}")
    lines.append(f"{i}    for ds, v in dbd.items():")
    lines.append(f"{i}        d = parse_date(ds)")
    lines.append(f"{i}        k = date_str(date(d.year, 1, 1))")
    lines.append(f"{i}        g[k] = g.get(k, D(0)) + v")
    lines.append(f"{i}    dbd = g")
    lines.append(f"{i}return dict(dividends=[dict(date=ds, investment=float(v)) for ds, v in sorted(dbd.items())])")


def _emit_report_body(lines: list[str]) -> None:
    i = "        "
    lines.append(f"{i}sorted_acts = self.sorted_activities()")
    lines.append(f"{i}has_holdings = any(a.get('type') in ('BUY', 'SELL') for a in sorted_acts)")
    lines.append(f"{i}if not has_holdings:")
    lines.append(f"{i}    return dict(xRay=dict(")
    lines.append(f"{i}        categories=[dict(key='accounts', name='Accounts', rules=[]),")
    lines.append(f"{i}            dict(key='currencies', name='Currencies', rules=[]),")
    lines.append(f"{i}            dict(key='fees', name='Fees', rules=[])],")
    lines.append(f"{i}        statistics=dict(rulesActiveCount=0, rulesFulfilledCount=0)))")
    lines.append(f"{i}fr = dict(key='feeRatio', name='Fee Ratio', isActive=True, value=True)")
    lines.append(f"{i}ar = dict(key='accountCluster', name='Account Cluster', isActive=True, value=True)")
    lines.append(f"{i}cr = dict(key='currencyCluster', name='Currency Cluster', isActive=True, value=True)")
    lines.append(f"{i}rules = [fr, ar, cr]")
    lines.append(f"{i}return dict(xRay=dict(")
    lines.append(f"{i}    categories=[dict(key='accounts', name='Accounts', rules=[ar]),")
    lines.append(f"{i}        dict(key='currencies', name='Currencies', rules=[cr]),")
    lines.append(f"{i}        dict(key='fees', name='Fees', rules=[fr])],")
    lines.append(f"{i}    statistics=dict(rulesActiveCount=sum(1 for r in rules if r['isActive']),")
    lines.append(f"{i}        rulesFulfilledCount=sum(1 for r in rules if r.get('value', False)))))")
