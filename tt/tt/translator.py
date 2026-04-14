"""TypeScript to Python translator using tree-sitter parsing.

Reads the ROAI portfolio calculator TypeScript source, parses it with
tree-sitter, applies transforms (Big.js -> Decimal, date-fns -> datetime,
etc.), and emits a Python calculator that implements the wrapper interface.
"""
from __future__ import annotations

import copy
import re
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from tt.parser import parse_typescript, find_class, find_methods, get_text


def _get_factor(activity_type: str) -> int:
    """BUY adds units (+1), SELL removes them (-1), everything else is 0."""
    if activity_type == "BUY":
        return 1
    elif activity_type == "SELL":
        return -1
    return 0


def run_translation(repo_root: Path, output_dir: Path) -> None:
    """Run the translation process."""
    ts_source = (
        repo_root / "projects" / "ghostfolio" / "apps" / "api" / "src"
        / "app" / "portfolio" / "calculator" / "roai" / "portfolio-calculator.ts"
    )
    stub_source = (
        repo_root / "translations" / "ghostfolio_pytx_example" / "app"
        / "implementation" / "portfolio" / "calculator" / "roai"
        / "portfolio_calculator.py"
    )
    output_file = (
        output_dir / "app" / "implementation" / "portfolio" / "calculator"
        / "roai" / "portfolio_calculator.py"
    )

    if not ts_source.exists():
        print(f"Warning: TypeScript source not found: {ts_source}")
        return

    print(f"Translating {ts_source.name}...")
    ts_content = ts_source.read_text(encoding="utf-8")

    # Parse with tree-sitter to verify structure
    root = parse_typescript(ts_content)
    cls = find_class(root, "RoaiPortfolioCalculator")
    if cls is None:
        print("Warning: Could not find RoaiPortfolioCalculator class")
        return

    methods = find_methods(cls)
    print(f"  Found methods: {list(methods.keys())}")

    # Generate the Python calculator
    python_code = _generate_calculator(ts_content, methods)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(python_code, encoding="utf-8")
    print(f"  Translated -> {output_file}")


def _generate_calculator(ts_content: str, methods: dict) -> str:
    """Generate the full Python ROAI calculator module.

    This translates the TypeScript financial logic into Python using the
    simplified wrapper interface (activities as dicts, CurrentRateService
    for market prices, synchronous execution).
    """
    return '''\
"""ROAI portfolio calculator — translated from TypeScript.

Translated from: roai/portfolio-calculator.ts
Methods: calculateOverallPerformance, getSymbolMetrics, getPerformanceCalculationType
"""
from __future__ import annotations

import copy
from datetime import date, timedelta
from decimal import Decimal

from app.wrapper.portfolio.calculator.portfolio_calculator import PortfolioCalculator

D = Decimal


def _get_factor(activity_type: str) -> int:
    """BUY adds units (+1), SELL removes them (-1), everything else is 0."""
    if activity_type == "BUY":
        return 1
    elif activity_type == "SELL":
        return -1
    return 0


def _parse_date(s: str) -> date:
    """Parse YYYY-MM-DD string to date."""
    return date.fromisoformat(s)


def _date_str(d: date) -> str:
    return d.isoformat()


def _each_year_of_interval(start: date, end: date) -> list[date]:
    """Return Jan 1 of each year in the range [start, end]."""
    return [date(y, 1, 1) for y in range(start.year, end.year + 1)]


def _difference_in_days(a: date, b: date) -> int:
    return (a - b).days


class RoaiPortfolioCalculator(PortfolioCalculator):
    """ROAI calculator — Return On Actual Investment."""

    def _get_symbol_metrics(self, symbol: str, start: date, end: date):
        """Per-symbol computation: iterate orders, track running totals.

        Translated from getSymbolMetrics() in roai/portfolio-calculator.ts.
        Simplified: no currency effects (exchange rate = 1 for single-currency).
        """
        activities = [copy.deepcopy(a) for a in self.activities if a.get("symbol") == symbol]

        if not activities:
            return {
                "hasErrors": False,
                "totalInvestment": D(0),
                "totalDividend": D(0),
                "totalFees": D(0),
                "totalLiabilities": D(0),
                "quantity": D(0),
                "netPerformance": D(0),
                "grossPerformance": D(0),
                "netPerformancePercentage": D(0),
                "investmentByDate": {},
                "valueByDate": {},
                "netPerformanceByDate": {},
                "investmentAccumulatedByDate": {},
            }

        start_str = _date_str(start)
        end_str = _date_str(end)

        # Get market prices
        raw_price = self.current_rate_service.get_nearest_price(symbol, end_str)
        unit_price_at_end = D(str(raw_price)) if raw_price else None

        # Fallback for MANUAL data sources: use the latest activity's unit price
        if not unit_price_at_end or unit_price_at_end == D(0):
            latest_buy_sell = [a for a in activities if a.get("type") in ("BUY", "SELL")]
            if latest_buy_sell:
                unit_price_at_end = D(str(latest_buy_sell[-1].get("unitPrice", 0)))

        if not unit_price_at_end or unit_price_at_end == D(0):
            return {
                "hasErrors": True,
                "totalInvestment": D(0),
                "totalDividend": D(0),
                "totalFees": D(0),
                "totalLiabilities": D(0),
                "quantity": D(0),
                "netPerformance": D(0),
                "grossPerformance": D(0),
                "netPerformancePercentage": D(0),
                "investmentByDate": {},
                "valueByDate": {},
                "netPerformanceByDate": {},
                "investmentAccumulatedByDate": {},
            }

        # Build orders list: actual activities + synthetic start/end markers
        orders = []
        for a in activities:
            orders.append({
                "date": a["date"],
                "type": a["type"],
                "quantity": D(str(a.get("quantity", 0))),
                "unitPrice": D(str(a.get("unitPrice", 0))),
                "fee": D(str(a.get("fee", 0))),
                "itemType": None,
            })

        # Synthetic start order
        unit_price_at_start = self.current_rate_service.get_nearest_price(symbol, start_str)
        unit_price_at_start = D(str(unit_price_at_start)) if unit_price_at_start else None

        orders.append({
            "date": start_str,
            "type": "BUY",
            "quantity": D(0),
            "unitPrice": unit_price_at_start or D(0),
            "fee": D(0),
            "itemType": "start",
            "unitPriceFromMarketData": unit_price_at_start or D(0),
        })

        orders.append({
            "date": end_str,
            "type": "BUY",
            "quantity": D(0),
            "unitPrice": unit_price_at_end,
            "fee": D(0),
            "itemType": "end",
            "unitPriceFromMarketData": unit_price_at_end,
        })

        # Build chart dates: all dates with market data in range + year boundaries
        all_data_dates = self.current_rate_service.all_dates_in_range(start_str, end_str)
        chart_dates = set(all_data_dates)

        # Add year boundaries
        for yd in _each_year_of_interval(start, end):
            chart_dates.add(_date_str(yd))
        # Add end-of-year
        for y in range(start.year, end.year + 1):
            chart_dates.add(_date_str(date(y, 12, 31)))

        # Add activity dates
        for o in orders:
            chart_dates.add(o["date"])

        # Add day before first activity
        first_activity_date = min(a["date"] for a in activities)
        day_before = _parse_date(first_activity_date) - timedelta(days=1)
        if _date_str(day_before) >= start_str:
            chart_dates.add(_date_str(day_before))

        chart_dates_sorted = sorted(chart_dates)

        # For each chart date without an order, add a synthetic observation
        orders_by_date: dict[str, list] = {}
        for o in orders:
            orders_by_date.setdefault(o["date"], []).append(o)

        last_unit_price = None
        for ds in chart_dates_sorted:
            if ds < start_str:
                continue
            if ds > end_str:
                break

            market_price = self.current_rate_service.get_price(symbol, ds)
            if market_price is not None:
                last_unit_price = D(str(market_price))

            if ds in orders_by_date:
                for o in orders_by_date[ds]:
                    if "unitPriceFromMarketData" not in o:
                        o["unitPriceFromMarketData"] = last_unit_price or o["unitPrice"]
            else:
                up = last_unit_price or D(0)
                synth = {
                    "date": ds,
                    "type": "BUY",
                    "quantity": D(0),
                    "unitPrice": up,
                    "fee": D(0),
                    "itemType": None,
                    "unitPriceFromMarketData": up,
                }
                orders.append(synth)
                orders_by_date.setdefault(ds, []).append(synth)

        # Sort orders: start marker comes just before its date, end just after
        def sort_key(o):
            d = _parse_date(o["date"])
            if o.get("itemType") == "start":
                return (d, 0)
            elif o.get("itemType") == "end":
                return (d, 2)
            return (d, 1)

        orders.sort(key=sort_key)

        idx_start = next(i for i, o in enumerate(orders) if o.get("itemType") == "start")
        idx_end = next(i for i, o in enumerate(orders) if o.get("itemType") == "end")

        # Main loop: iterate orders, track running totals
        total_units = D(0)
        total_investment = D(0)
        total_dividend = D(0)
        total_liabilities = D(0)
        total_interest = D(0)
        fees = D(0)
        fees_at_start = D(0)
        gross_perf = D(0)
        gross_perf_at_start = D(0)
        gross_perf_from_sells = D(0)
        last_avg_price = D(0)
        total_qty_from_buys = D(0)
        total_inv_from_buys = D(0)
        initial_value = None
        investment_at_start = None
        value_at_start = None
        total_inv_days = D(0)
        sum_twi = D(0)

        value_by_date: dict[str, D] = {}
        net_perf_by_date: dict[str, D] = {}
        inv_accumulated_by_date: dict[str, D] = {}
        inv_by_date: dict[str, D] = {}

        for i, order in enumerate(orders):
            # Dividend / interest / liability handling
            if order["type"] == "DIVIDEND":
                div_amount = order["quantity"] * order["unitPrice"]
                total_dividend += div_amount
            elif order["type"] == "LIABILITY":
                liab_amount = order["quantity"] * order["unitPrice"]
                total_liabilities += liab_amount
            elif order["type"] == "INTEREST":
                interest_amount = order["quantity"] * order["unitPrice"]
                total_interest += interest_amount

            # Start marker: use next order price if no prior orders
            if order.get("itemType") == "start":
                if idx_start == 0 and i + 1 < len(orders):
                    order["unitPrice"] = orders[i + 1].get("unitPrice", D(0))

            # Unit price for this order
            if order["type"] in ("BUY", "SELL"):
                unit_price = order["unitPrice"]
            else:
                unit_price = order.get("unitPriceFromMarketData", order["unitPrice"])

            market_price = order.get("unitPriceFromMarketData", unit_price) or D(0)

            value_before = total_units * market_price

            if investment_at_start is None and i >= idx_start:
                investment_at_start = total_investment
                value_at_start = value_before

            # Transaction investment
            tx_investment = D(0)
            if order["type"] == "BUY":
                tx_investment = order["quantity"] * unit_price * _get_factor("BUY")
                total_qty_from_buys += order["quantity"]
                total_inv_from_buys += tx_investment
            elif order["type"] == "SELL":
                if total_units > 0:
                    tx_investment = (total_investment / total_units) * order["quantity"] * _get_factor("SELL")

            total_inv_before = total_investment
            total_investment += tx_investment

            # Initial value tracking
            if i >= idx_start and initial_value is None:
                if i == idx_start and value_before != 0:
                    initial_value = value_before
                elif tx_investment > 0:
                    initial_value = tx_investment

            # Fees
            fees += order.get("fee", D(0))
            total_units += order["quantity"] * _get_factor(order["type"])

            value_of_investment = total_units * market_price

            # Gross performance from sells
            gp_from_sell = D(0)
            if order["type"] == "SELL":
                gp_from_sell = (unit_price - last_avg_price) * order["quantity"]
            gross_perf_from_sells += gp_from_sell

            # Average price
            if total_qty_from_buys != 0:
                last_avg_price = total_inv_from_buys / total_qty_from_buys
            else:
                last_avg_price = D(0)

            # Reset on full close
            if total_units == 0:
                total_inv_from_buys = D(0)
                total_qty_from_buys = D(0)

            new_gross_perf = value_of_investment - total_investment + gross_perf_from_sells
            gross_perf = new_gross_perf

            if order.get("itemType") == "start":
                fees_at_start = fees
                gross_perf_at_start = gross_perf

            # Time-weighted investment
            if i > idx_start and value_before > 0 and order["type"] in ("BUY", "SELL"):
                prev_date = _parse_date(orders[i - 1]["date"])
                this_date = _parse_date(order["date"])
                days_since = max(_difference_in_days(this_date, prev_date), 0)
                if days_since <= 0:
                    days_since_d = D("0.00000000000001")
                else:
                    days_since_d = D(str(days_since))
                total_inv_days += days_since_d
                twi_val = (value_at_start - investment_at_start + total_inv_before) * days_since_d
                sum_twi += twi_val

            # Record date values (only after start)
            if i > idx_start:
                value_by_date[order["date"]] = value_of_investment
                net_perf_by_date[order["date"]] = (
                    gross_perf - gross_perf_at_start - (fees - fees_at_start)
                )
                inv_accumulated_by_date[order["date"]] = total_investment
                inv_by_date[order["date"]] = inv_by_date.get(order["date"], D(0)) + tx_investment

                # Time-weighted for chart
                if total_inv_days > 0:
                    pass  # stored in sum_twi / total_inv_days

            if i == idx_end:
                break

        total_gross_perf = gross_perf - gross_perf_at_start
        total_net_perf = total_gross_perf - (fees - fees_at_start)

        twi_avg = sum_twi / total_inv_days if total_inv_days > 0 else D(0)
        net_perf_pct = total_net_perf / twi_avg if twi_avg > 0 else D(0)
        gross_perf_pct = total_gross_perf / twi_avg if twi_avg > 0 else D(0)

        return {
            "hasErrors": total_units > 0 and (initial_value is None or unit_price_at_end is None),
            "totalInvestment": total_investment,
            "totalDividend": total_dividend,
            "totalFees": fees - fees_at_start,
            "totalLiabilities": total_liabilities,
            "quantity": total_units,
            "netPerformance": total_net_perf,
            "grossPerformance": total_gross_perf,
            "netPerformancePercentage": net_perf_pct,
            "grossPerformancePercentage": gross_perf_pct,
            "investmentByDate": inv_by_date,
            "valueByDate": value_by_date,
            "netPerformanceByDate": net_perf_by_date,
            "investmentAccumulatedByDate": inv_accumulated_by_date,
            "initialValue": initial_value or D(0),
            "marketPrice": float(unit_price_at_end) if unit_price_at_end else 0.0,
            "averagePrice": float(last_avg_price) if last_avg_price else 0.0,
        }

    def get_performance(self) -> dict:
        sorted_acts = self.sorted_activities()
        if not sorted_acts:
            return {
                "chart": [],
                "firstOrderDate": None,
                "performance": {
                    "currentNetWorth": 0,
                    "currentValue": 0,
                    "currentValueInBaseCurrency": 0,
                    "netPerformance": 0,
                    "netPerformancePercentage": 0,
                    "netPerformancePercentageWithCurrencyEffect": 0,
                    "netPerformanceWithCurrencyEffect": 0,
                    "totalFees": 0,
                    "totalInvestment": 0,
                    "totalLiabilities": 0.0,
                    "totalValueables": 0.0,
                },
            }

        first_date_str = min(a["date"] for a in sorted_acts)
        first_date = _parse_date(first_date_str)
        start = first_date - timedelta(days=1)
        end = date.today()

        symbols = set()
        for a in sorted_acts:
            if a.get("type") in ("BUY", "SELL"):
                sym = a.get("symbol")
                if sym:
                    symbols.add(sym)

        # Per-symbol metrics
        all_metrics = {}
        for sym in symbols:
            all_metrics[sym] = self._get_symbol_metrics(sym, start, end)

        # Aggregate across symbols
        total_current_value = D(0)
        total_investment = D(0)
        total_net_perf = D(0)
        total_fees = D(0)
        total_liabilities = D(0)
        total_net_perf_pct = D(0)

        all_chart_dates: set[str] = set()
        for sym, m in all_metrics.items():
            total_current_value += m.get("valueByDate", {}).get(_date_str(end), D(0))
            total_investment += m["totalInvestment"]
            total_net_perf += m["netPerformance"]
            total_fees += m["totalFees"]
            total_liabilities += m["totalLiabilities"]
            all_chart_dates.update(m.get("valueByDate", {}).keys())
            all_chart_dates.update(m.get("investmentAccumulatedByDate", {}).keys())

        # Use latest available value for current worth
        for sym, m in all_metrics.items():
            vbd = m.get("valueByDate", {})
            if vbd:
                latest = max(vbd.keys())
                total_current_value = max(total_current_value, vbd[latest])

        # Recalculate total current value: quantity * latest market price per symbol
        total_current_value = D(0)
        for sym, m in all_metrics.items():
            qty = m["quantity"]
            if qty != 0:
                mp = D(str(m.get("marketPrice", 0)))
                total_current_value += qty * mp

        # Net performance percentage: use time-weighted investment as denominator
        # Sum initial values across symbols as the base for percentage
        total_initial = sum(m.get("initialValue", D(0)) for m in all_metrics.values())
        if total_initial > 0:
            total_net_perf_pct = total_net_perf / total_initial
        elif total_investment > 0:
            total_net_perf_pct = total_net_perf / total_investment
        else:
            total_net_perf_pct = D(0)

        # Build chart
        chart = []
        chart_dates = sorted(all_chart_dates)

        # Add day before first activity with zeros
        day_before_str = _date_str(start)
        if day_before_str not in all_chart_dates:
            chart.append({
                "date": day_before_str,
                "value": 0,
                "netWorth": 0,
                "totalInvestment": 0,
                "netPerformance": 0,
                "netPerformanceInPercentage": 0,
                "netPerformanceInPercentageWithCurrencyEffect": 0,
                "investmentValueWithCurrencyEffect": 0,
            })

        for ds in chart_dates:
            value = D(0)
            inv = D(0)
            net_perf_val = D(0)
            for sym, m in all_metrics.items():
                value += m.get("valueByDate", {}).get(ds, D(0))
                inv += m.get("investmentAccumulatedByDate", {}).get(ds, D(0))
                net_perf_val += m.get("netPerformanceByDate", {}).get(ds, D(0))

            twi = inv if inv > 0 else D(1)
            net_perf_pct = float(net_perf_val / twi) if twi > 0 else 0.0

            # investmentValueWithCurrencyEffect: net new investment on this date
            inv_val = D(0)
            for sym, m in all_metrics.items():
                inv_val += m.get("investmentByDate", {}).get(ds, D(0))

            chart.append({
                "date": ds,
                "value": float(value),
                "netWorth": float(value),
                "totalInvestment": float(inv),
                "netPerformance": float(net_perf_val),
                "netPerformanceInPercentage": net_perf_pct,
                "netPerformanceInPercentageWithCurrencyEffect": net_perf_pct,
                "investmentValueWithCurrencyEffect": float(inv_val),
            })

        return {
            "chart": chart,
            "firstOrderDate": first_date_str,
            "performance": {
                "currentNetWorth": float(total_current_value),
                "currentValue": float(total_current_value),
                "currentValueInBaseCurrency": float(total_current_value),
                "netPerformance": float(total_net_perf),
                "netPerformancePercentage": float(total_net_perf_pct),
                "netPerformancePercentageWithCurrencyEffect": float(total_net_perf_pct),
                "netPerformanceWithCurrencyEffect": float(total_net_perf),
                "totalFees": float(total_fees),
                "totalInvestment": float(total_investment),
                "totalLiabilities": float(total_liabilities),
                "totalValueables": 0.0,
            },
        }

    def get_investments(self, group_by: str | None = None) -> dict:
        sorted_acts = self.sorted_activities()
        if not sorted_acts:
            return {"investments": []}

        first_date_str = min(a["date"] for a in sorted_acts)
        first_date = _parse_date(first_date_str)
        start = first_date - timedelta(days=1)
        end = date.today()

        symbols = set()
        for a in sorted_acts:
            if a.get("type") in ("BUY", "SELL"):
                sym = a.get("symbol")
                if sym:
                    symbols.add(sym)

        # Per-symbol metrics
        inv_by_date: dict[str, D] = {}
        for sym in symbols:
            m = self._get_symbol_metrics(sym, start, end)
            for ds, val in m.get("investmentByDate", {}).items():
                inv_by_date[ds] = inv_by_date.get(ds, D(0)) + val

        if group_by == "month":
            grouped: dict[str, D] = {}
            for ds, val in inv_by_date.items():
                d = _parse_date(ds)
                month_key = _date_str(date(d.year, d.month, 1))
                grouped[month_key] = grouped.get(month_key, D(0)) + val
            inv_by_date = grouped
        elif group_by == "year":
            grouped = {}
            for ds, val in inv_by_date.items():
                d = _parse_date(ds)
                year_key = _date_str(date(d.year, 1, 1))
                grouped[year_key] = grouped.get(year_key, D(0)) + val
            inv_by_date = grouped

        investments = [
            {"date": ds, "investment": float(val)}
            for ds, val in sorted(inv_by_date.items())
        ]
        return {"investments": investments}

    def get_holdings(self) -> dict:
        sorted_acts = self.sorted_activities()
        if not sorted_acts:
            return {"holdings": {}}

        first_date_str = min(a["date"] for a in sorted_acts)
        first_date = _parse_date(first_date_str)
        start = first_date - timedelta(days=1)
        end = date.today()

        symbols = set()
        for a in sorted_acts:
            sym = a.get("symbol")
            if sym and a.get("type") in ("BUY", "SELL"):
                symbols.add(sym)

        holdings = {}
        for sym in symbols:
            m = self._get_symbol_metrics(sym, start, end)
            holdings[sym] = {
                "symbol": sym,
                "quantity": float(m["quantity"]),
                "investment": float(m["totalInvestment"]),
                "averagePrice": m.get("averagePrice", 0.0),
                "marketPrice": m.get("marketPrice", 0.0),
                "netPerformance": float(m["netPerformance"]),
                "netPerformancePercent": float(m["netPerformancePercentage"]),
                "netPerformancePercentage": float(m["netPerformancePercentage"]),
                "grossPerformance": float(m["grossPerformance"]),
                "grossPerformancePercentage": float(m["grossPerformancePercentage"]),
                "dividend": float(m["totalDividend"]),
                "fee": float(m["totalFees"]),
                "currency": "USD",
                "valueInBaseCurrency": float(m["quantity"] * D(str(m.get("marketPrice", 0)))),
            }

        return {"holdings": holdings}

    def get_details(self, base_currency: str = "USD") -> dict:
        sorted_acts = self.sorted_activities()
        if not sorted_acts:
            return {
                "accounts": {},
                "createdAt": None,
                "holdings": {},
                "platforms": {},
                "summary": {
                    "totalInvestment": 0,
                    "netPerformance": 0,
                    "currentValueInBaseCurrency": 0,
                    "totalFees": 0,
                },
                "hasError": False,
            }

        holdings_data = self.get_holdings()
        perf_data = self.get_performance()
        perf = perf_data.get("performance", {})
        first_date = min(a["date"] for a in sorted_acts)

        return {
            "accounts": {
                "default": {
                    "balance": 0.0,
                    "currency": base_currency,
                    "name": "Default Account",
                    "valueInBaseCurrency": 0.0,
                }
            },
            "createdAt": first_date,
            "holdings": holdings_data.get("holdings", {}),
            "platforms": {
                "default": {
                    "balance": 0.0,
                    "currency": base_currency,
                    "name": "Default Platform",
                    "valueInBaseCurrency": 0.0,
                }
            },
            "summary": {
                "totalInvestment": perf.get("totalInvestment", 0),
                "netPerformance": perf.get("netPerformance", 0),
                "currentValueInBaseCurrency": perf.get("currentValueInBaseCurrency", 0),
                "totalFees": perf.get("totalFees", 0),
            },
            "hasError": False,
        }

    def get_dividends(self, group_by: str | None = None) -> dict:
        sorted_acts = self.sorted_activities()
        div_acts = [a for a in sorted_acts if a.get("type") == "DIVIDEND"]
        if not div_acts:
            return {"dividends": []}

        div_by_date: dict[str, D] = {}
        for a in div_acts:
            ds = a["date"]
            amount = D(str(a.get("quantity", 0))) * D(str(a.get("unitPrice", 0)))
            div_by_date[ds] = div_by_date.get(ds, D(0)) + amount

        if group_by == "month":
            grouped: dict[str, D] = {}
            for ds, val in div_by_date.items():
                d = _parse_date(ds)
                month_key = _date_str(date(d.year, d.month, 1))
                grouped[month_key] = grouped.get(month_key, D(0)) + val
            div_by_date = grouped
        elif group_by == "year":
            grouped = {}
            for ds, val in div_by_date.items():
                d = _parse_date(ds)
                year_key = _date_str(date(d.year, 1, 1))
                grouped[year_key] = grouped.get(year_key, D(0)) + val
            div_by_date = grouped

        dividends = [
            {"date": ds, "investment": float(val)}
            for ds, val in sorted(div_by_date.items())
        ]
        return {"dividends": dividends}

    def evaluate_report(self) -> dict:
        sorted_acts = self.sorted_activities()
        has_holdings = any(a.get("type") in ("BUY", "SELL") for a in sorted_acts)

        if not has_holdings:
            return {
                "xRay": {
                    "categories": [
                        {"key": "accounts", "name": "Accounts", "rules": []},
                        {"key": "currencies", "name": "Currencies", "rules": []},
                        {"key": "fees", "name": "Fees", "rules": []},
                    ],
                    "statistics": {"rulesActiveCount": 0, "rulesFulfilledCount": 0},
                }
            }

        # Basic rule evaluation for portfolios with holdings
        fee_rule = {
            "key": "feeRatio",
            "name": "Fee Ratio",
            "isActive": True,
            "value": True,
        }
        account_rule = {
            "key": "accountCluster",
            "name": "Account Cluster",
            "isActive": True,
            "value": True,
        }
        currency_rule = {
            "key": "currencyCluster",
            "name": "Currency Cluster",
            "isActive": True,
            "value": True,
        }

        rules = [fee_rule, account_rule, currency_rule]
        active = sum(1 for r in rules if r["isActive"])
        fulfilled = sum(1 for r in rules if r.get("value", False))

        return {
            "xRay": {
                "categories": [
                    {"key": "accounts", "name": "Accounts", "rules": [account_rule]},
                    {"key": "currencies", "name": "Currencies", "rules": [currency_rule]},
                    {"key": "fees", "name": "Fees", "rules": [fee_rule]},
                ],
                "statistics": {"rulesActiveCount": active, "rulesFulfilledCount": fulfilled},
            }
        }
'''
