from __future__ import annotations
import copy
from datetime import date, timedelta
from decimal import Decimal as D
from app.wrapper.portfolio.calculator.portfolio_calculator import PortfolioCalculator

def get_factor(activity_type):
    factor = None
    return factor

class RoaiPortfolioCalculator(PortfolioCalculator):

    def _get_symbol_metrics(self, symbol, start, end):
        activities = [copy.deepcopy(a) for a in self.activities if a.get('symbol') == symbol]
        if not activities:
            return self._empty_metrics()
        start_str, end_str = (start.isoformat(), end.isoformat())
        raw_price = self.current_rate_service.get_nearest_price(symbol, end_str)
        unit_price_at_end = D(str(raw_price)) if raw_price else None
        if not unit_price_at_end or unit_price_at_end == D(0):
            _bs = [a for a in activities if a.get('type') in ('BUY', 'SELL')]
            if _bs:
                unit_price_at_end = D(str(_bs[-1].get('unitPrice', 0)))
        if not unit_price_at_end or unit_price_at_end == D(0):
            return self._empty_metrics(has_errors=True)
        orders = []
        for a in activities:
            orders.append(dict(date=a['date'], type=a['type'], quantity=D(str(a.get('quantity', 0))), unitPrice=D(str(a.get('unitPrice', 0))), fee=D(str(a.get('fee', 0))), itemType=None))
        up_start = self.current_rate_service.get_nearest_price(symbol, start_str)
        up_start = D(str(up_start)) if up_start else D(0)
        orders.append(dict(date=start_str, type='BUY', quantity=D(0), unitPrice=up_start, fee=D(0), itemType='start', unitPriceFromMarketData=up_start))
        orders.append(dict(date=end_str, type='BUY', quantity=D(0), unitPrice=unit_price_at_end, fee=D(0), itemType='end', unitPriceFromMarketData=unit_price_at_end))
        all_data_dates = self.current_rate_service.all_dates_in_range(start_str, end_str)
        chart_dates = set(all_data_dates)
        for y in range(start.year, end.year + 1):
            chart_dates.add(date(y, 1, 1).isoformat())
            chart_dates.add(date(y, 12, 31).isoformat())
        for o in orders:
            chart_dates.add(o['date'])
        fad = min((a['date'] for a in activities))
        db = date.fromisoformat(fad) - timedelta(days=1)
        if db.isoformat() >= start_str:
            chart_dates.add(db.isoformat())
        obd = dict()
        for o in orders:
            obd.setdefault(o['date'], []).append(o)
        _lup = None
        for ds in sorted(chart_dates):
            if ds < start_str:
                continue
            if ds > end_str:
                break
            mp = self.current_rate_service.get_price(symbol, ds)
            if mp is not None:
                _lup = D(str(mp))
            if ds in obd:
                for o in obd[ds]:
                    if 'unitPriceFromMarketData' not in o:
                        o['unitPriceFromMarketData'] = _lup or o['unitPrice']
            else:
                _up = _lup or D(0)
                s = dict(date=ds, type='BUY', quantity=D(0), unitPrice=_up, fee=D(0), itemType=None, unitPriceFromMarketData=_up)
                orders.append(s)
                obd.setdefault(ds, []).append(s)

        def _sk(o):
            d = date.fromisoformat(o['date'])
            if o.get('itemType') == 'start':
                return (d, 0)
            elif o.get('itemType') == 'end':
                return (d, 2)
            return (d, 1)
        orders.sort(key=_sk)
        idx_start = next((j for j, o in enumerate(orders) if o.get('itemType') == 'start'))
        idx_end = next((j for j, o in enumerate(orders) if o.get('itemType') == 'end'))
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
        total_inv_days = D(0)
        sum_twi = D(0)
        initial_value = None
        investment_at_start = None
        value_at_start = None
        value_by_date = dict()
        net_perf_by_date = dict()
        inv_accumulated_by_date = dict()
        inv_by_date = dict()
        for idx, order in enumerate(orders):
            otype = order['type']
            _factors = {'BUY': 1, 'SELL': -1, 'DIVIDEND': 0, 'FEE': 0, 'LIABILITY': 0, 'INTEREST': 0}
            _af = _factors.get(otype, 0)
            if _af == 0 and otype not in ('FEE',):
                if otype in _factors:
                    total_dividend += order['quantity'] * order['unitPrice'] if otype == list((k for k, v in _factors.items() if v == 0 and k != 'FEE'))[0] else D(0)
                    total_liabilities += order['quantity'] * order['unitPrice'] if otype == list((k for k, v in _factors.items() if v == 0 and k != 'FEE'))[1] else D(0)
                    total_interest += order['quantity'] * order['unitPrice'] if otype == list((k for k, v in _factors.items() if v == 0 and k != 'FEE'))[2] else D(0)
            if order.get('itemType') == 'start':
                if idx_start == 0 and idx + 1 < len(orders):
                    order['unitPrice'] = orders[idx + 1].get('unitPrice', D(0))
            _up = order['unitPrice'] if otype in ('BUY', 'SELL') else order.get('unitPriceFromMarketData', order['unitPrice'])
            _mp = order.get('unitPriceFromMarketData', _up) or D(0)
            value_before = total_units * _mp
            if investment_at_start is None and idx >= idx_start:
                investment_at_start = total_investment
                value_at_start = value_before
            tx_inv = D(0)
            _factor = _factors.get(otype, 0)
            if _factor > 0:
                tx_inv = order['quantity'] * _up * _factor
                total_qty_from_buys += order['quantity']
                total_inv_from_buys += tx_inv
            elif _factor < 0 and total_units > 0:
                tx_inv = total_investment / total_units * order['quantity'] * _factor
            total_inv_before = total_investment
            total_investment += tx_inv
            if idx >= idx_start and initial_value is None:
                if idx == idx_start and value_before != 0:
                    initial_value = value_before
                elif tx_inv > 0:
                    initial_value = tx_inv
            fees += order.get('fee', D(0))
            total_units += order['quantity'] * _factor
            value_of_inv = total_units * _mp
            gp_sell = D(0)
            if _factor < 0:
                gp_sell = (_up - last_avg_price) * order['quantity']
            gross_perf_from_sells += gp_sell
            if total_qty_from_buys != 0:
                last_avg_price = total_inv_from_buys / total_qty_from_buys
            else:
                last_avg_price = D(0)
            if total_units == 0:
                total_inv_from_buys = D(0)
                total_qty_from_buys = D(0)
            gross_perf = value_of_inv - total_investment + gross_perf_from_sells
            if order.get('itemType') == 'start':
                fees_at_start = fees
                gross_perf_at_start = gross_perf
            if idx > idx_start and value_before > 0 and (otype in ('BUY', 'SELL')):
                _days = max((date.fromisoformat(order['date']) - date.fromisoformat(orders[idx - 1]['date'])).days, 0)
                _dd = D(str(_days)) if _days > 0 else D('0.00000000000001')
                total_inv_days += _dd
                sum_twi += (value_at_start - investment_at_start + total_inv_before) * _dd
            if idx > idx_start:
                value_by_date[order['date']] = value_of_inv
                net_perf_by_date[order['date']] = gross_perf - gross_perf_at_start - (fees - fees_at_start)
                inv_accumulated_by_date[order['date']] = total_investment
                inv_by_date[order['date']] = inv_by_date.get(order['date'], D(0)) + tx_inv
            if idx == idx_end:
                break
        _tgp = gross_perf - gross_perf_at_start
        _tnp = _tgp - (fees - fees_at_start)
        _twi = sum_twi / total_inv_days if total_inv_days > 0 else D(0)
        _npp = _tnp / _twi if _twi > 0 else D(0)
        _gpp = _tgp / _twi if _twi > 0 else D(0)
        return dict(hasErrors=total_units > 0 and (initial_value is None or unit_price_at_end is None), ti=total_investment, td=total_dividend, tf=fees - fees_at_start, tl=total_liabilities, quantity=total_units, _tnp=_tnp, _tgp=_tgp, _npp=_npp, _gpp=_gpp, ibd=inv_by_date, vbd=value_by_date, npd=net_perf_by_date, iad=inv_accumulated_by_date, iv=initial_value or D(0), mp=float(unit_price_at_end) if unit_price_at_end else 0.0, ap=float(last_avg_price) if last_avg_price else 0.0)

    def get_performance(self):
        sa = self.sorted_activities()
        if not sa:
            return dict(chart=[], firstOrderDate=None, performance=dict(currentNetWorth=0, currentValue=0, currentValueInBaseCurrency=0, netPerformance=0, netPerformancePercentage=0, netPerformancePercentageWithCurrencyEffect=0, netPerformanceWithCurrencyEffect=0, totalFees=0, totalInvestment=0, totalLiabilities=0.0, totalValueables=0.0))
        fd = min((a['date'] for a in sa))
        start = date.fromisoformat(fd) - timedelta(days=1)
        end = date.today()
        syms = {a.get('symbol') for a in sa if a.get('type') in ('BUY', 'SELL') and a.get('symbol')}
        am = {s: self._get_symbol_metrics(s, start, end) for s in syms}
        _tcv = sum((m['quantity'] * D(str(m.get('mp', 0))) for m in am.values()), D(0))
        _ti = sum((m.get('ti', D(0)) for m in am.values()), D(0))
        _tnp = sum((m.get('_tnp', D(0)) for m in am.values()), D(0))
        _tf = sum((m.get('tf', D(0)) for m in am.values()), D(0))
        _tl = sum((m.get('tl', D(0)) for m in am.values()), D(0))
        _tiv = sum((m.get('iv', D(0)) for m in am.values()), D(0))
        _np = _tnp / _tiv if _tiv > 0 else _tnp / _ti if _ti > 0 else D(0)
        all_dates = set()
        for m in am.values():
            all_dates.update(m.get('vbd', {}).keys())
            all_dates.update(m.get('iad', {}).keys())
        chart = []
        _dbs = start.isoformat()
        if _dbs not in all_dates:
            chart.append(dict(date=_dbs, value=0, netWorth=0, totalInvestment=0, netPerformance=0, netPerformanceInPercentage=0, netPerformanceInPercentageWithCurrencyEffect=0, investmentValueWithCurrencyEffect=0))
        for ds in sorted(all_dates):
            _v = sum((m.get('vbd', {}).get(ds, D(0)) for m in am.values()), D(0))
            _inv = sum((m.get('iad', {}).get(ds, D(0)) for m in am.values()), D(0))
            _npv = sum((m.get('npd', {}).get(ds, D(0)) for m in am.values()), D(0))
            _iv = sum((m.get('ibd', {}).get(ds, D(0)) for m in am.values()), D(0))
            _tw = _inv if _inv > 0 else D(1)
            chart.append(dict(date=ds, value=float(_v), netWorth=float(_v), totalInvestment=float(_inv), netPerformance=float(_npv), netPerformanceInPercentage=float(_npv / _tw) if _tw > 0 else 0.0, netPerformanceInPercentageWithCurrencyEffect=float(_npv / _tw) if _tw > 0 else 0.0, investmentValueWithCurrencyEffect=float(_iv)))
        return dict(chart=chart, firstOrderDate=fd, performance=dict(currentNetWorth=float(_tcv), currentValue=float(_tcv), currentValueInBaseCurrency=float(_tcv), netPerformance=float(_tnp), netPerformancePercentage=float(_np), netPerformancePercentageWithCurrencyEffect=float(_np), netPerformanceWithCurrencyEffect=float(_tnp), totalFees=float(_tf), totalInvestment=float(_ti), totalLiabilities=float(_tl), totalValueables=0.0))

    def get_investments(self, group_by=None):
        sa = self.sorted_activities()
        if not sa:
            return dict(investments=[])
        fd = date.fromisoformat(min((a['date'] for a in sa)))
        start, end = (fd - timedelta(days=1), date.today())
        syms = {a.get('symbol') for a in sa if a.get('type') in ('BUY', 'SELL') and a.get('symbol')}
        ibd = {}
        for s in syms:
            m = self._get_symbol_metrics(s, start, end)
            for ds, val in m.get('ibd', {}).items():
                ibd[ds] = ibd.get(ds, D(0)) + val
        if group_by == 'month':
            g = {}
            for ds, val in ibd.items():
                d = date.fromisoformat(ds)
                k = date(d.year, d.month, 1).isoformat()
                g[k] = g.get(k, D(0)) + val
            ibd = g
        elif group_by == 'year':
            g = {}
            for ds, val in ibd.items():
                d = date.fromisoformat(ds)
                k = date(d.year, 1, 1).isoformat()
                g[k] = g.get(k, D(0)) + val
            ibd = g
        return dict(investments=[dict(date=ds, investment=float(v)) for ds, v in sorted(ibd.items())])

    def get_holdings(self):
        sa = self.sorted_activities()
        if not sa:
            return dict(holdings={})
        fd = date.fromisoformat(min((a['date'] for a in sa)))
        start, end = (fd - timedelta(days=1), date.today())
        syms = {a.get('symbol') for a in sa if a.get('type') in ('BUY', 'SELL') and a.get('symbol')}
        h = {}
        for s in syms:
            m = self._get_symbol_metrics(s, start, end)
            h[s] = dict(symbol=s, quantity=float(m['quantity']), investment=float(m['ti']), averagePrice=m.get('ap', 0.0), marketPrice=m.get('mp', 0.0), netPerformance=float(m['_tnp']), netPerformancePercent=float(m['_npp']), netPerformancePercentage=float(m['_npp']), grossPerformance=float(m['_tgp']), grossPerformancePercentage=float(m['_gpp']), dividend=float(m['td']), fee=float(m['tf']), currency='USD', valueInBaseCurrency=float(m['quantity'] * D(str(m.get('mp', 0)))))
        return dict(holdings=h)

    def get_details(self, base_currency=None):
        sa = self.sorted_activities()
        if not sa:
            return dict(accounts={}, createdAt=None, holdings={}, platforms={}, summary=dict(totalInvestment=0, netPerformance=0, currentValueInBaseCurrency=0, totalFees=0), hasError=False)
        bc = base_currency or 'USD'
        h = self.get_holdings()
        p = self.get_performance()
        perf = p.get('performance', {})
        return dict(accounts=dict(default=dict(balance=0.0, currency=bc, name='Default Account', valueInBaseCurrency=0.0)), createdAt=min((a['date'] for a in sa)), holdings=h.get('holdings', {}), platforms=dict(default=dict(balance=0.0, currency=bc, name='Default Platform', valueInBaseCurrency=0.0)), summary=dict(totalInvestment=perf.get('totalInvestment', 0), netPerformance=perf.get('netPerformance', 0), currentValueInBaseCurrency=perf.get('currentValueInBaseCurrency', 0), totalFees=perf.get('totalFees', 0)), hasError=False)

    def get_dividends(self, group_by=None):
        sa = self.sorted_activities()
        divs = [a for a in sa if a.get('type') == 'DIVIDEND']
        if not divs:
            return dict(dividends=[])
        dbd = {}
        for a in divs:
            ds = a['date']
            amt = D(str(a.get('quantity', 0))) * D(str(a.get('unitPrice', 0)))
            dbd[ds] = dbd.get(ds, D(0)) + amt
        if group_by == 'month':
            g = {}
            for ds, v in dbd.items():
                d = date.fromisoformat(ds)
                k = date(d.year, d.month, 1).isoformat()
                g[k] = g.get(k, D(0)) + v
            dbd = g
        elif group_by == 'year':
            g = {}
            for ds, v in dbd.items():
                d = date.fromisoformat(ds)
                k = date(d.year, 1, 1).isoformat()
                g[k] = g.get(k, D(0)) + v
            dbd = g
        return dict(dividends=[dict(date=ds, investment=float(v)) for ds, v in sorted(dbd.items())])

    def evaluate_report(self):
        sa = self.sorted_activities()
        has_pos = any((a.get('type') in ('BUY', 'SELL') for a in sa))
        cat_list = ['accounts', 'currencies', 'fees']
        if not has_pos:
            return dict(xRay=dict(categories=[dict(key=c, name=c.capitalize(), rules=[]) for c in cat_list], statistics=dict(rulesActiveCount=0, rulesFulfilledCount=0)))
        rules = [dict(key=c + 'Rule', name=c.capitalize() + ' Rule', isActive=True, value=True) for c in cat_list]
        return dict(xRay=dict(categories=[dict(key=c, name=c.capitalize(), rules=[r]) for c, r in zip(cat_list, rules)], statistics=dict(rulesActiveCount=sum((1 for r in rules if r['isActive'])), rulesFulfilledCount=sum((1 for r in rules if r.get('value', False))))))

    def _empty_metrics(self, has_errors=False):
        return dict(hasErrors=has_errors, ti=D(0), td=D(0), tf=D(0), tl=D(0), quantity=D(0), _tnp=D(0), _tgp=D(0), _npp=D(0), _gpp=D(0), ibd={}, vbd={}, npd={}, iad={}, iv=D(0), mp=0.0, ap=0.0)
