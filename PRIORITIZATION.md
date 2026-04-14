# Prioritization Plan

## Scoring Model

- **85%** test pass rate (135 total tests across 13 files)
- **15%** code quality via pyscn
- Judge review adjusts final score (understanding is a multiplier)
- Completion time is tiebreaker between equal scores

**Current baseline:** 48/135 from scaffold alone (no real translation).

## Implementation Priority

### P0: Big.js Transform (unlocks everything)

Virtually every line of `getSymbolMetrics()` uses Big.js chaining. Without this transform, no calculator logic works.

| TS Pattern | Python Equivalent |
|---|---|
| `new Big(0)` | `Decimal("0")` |
| `.plus(x)` / `.minus(x)` | `+ x` / `- x` |
| `.mul(x)` / `.div(x)` | `* x` / `/ x` |
| `.eq(0)` / `.gt(0)` / `.lt(0)` | `== Decimal("0")` / `> Decimal("0")` / `< Decimal("0")` |
| `.toNumber()` | `float(x)` |

Gotcha: `Big(0)` is truthy in JS, `Decimal(0)` is falsy in Python.

### P1: `getSymbolMetrics()` (~50 tests)

The 350-line per-symbol arithmetic engine in `roai/portfolio-calculator.ts`. This is the single highest-leverage method. Getting it right unlocks chart data, performance calculations, and net worth tracking.

Key patterns inside this method:
- Date-indexed dictionaries of Big values
- Iterating over sorted orders with running totals
- Exchange rate multiplication
- Fee/dividend/liability accumulation
- Time-weighted investment calculation

Tests unlocked: `test_btcusd.py`, `test_btcusd_buy_and_sell_partially.py`, `test_short_cover.py`, `test_novn_buy_and_sell.py`, `test_advanced.py`, `test_deeper.py`, `test_remaining_specs.py`, `test_same_day_transactions.py` (chart and performance assertions).

### P2: `get_holdings()` + `get_investments()` (~45 tests)

These share the same position replay logic. Once `getSymbolMetrics()` works, these are assembly methods that package the data into the expected response shapes.

- `get_holdings()`: current quantity, investment, averagePrice per symbol
- `get_investments(group_by)`: investment timeline grouped by day/month/year

Tests: `test_btcusd.py` (holdings/investments), `test_msft_fractional.py`, `test_novn_buy_and_sell.py`, `test_dividends.py` (investment assertions).

### P3: `get_details()` + `get_dividends()` (~30 tests)

Lower complexity once P1 and P2 work.

- `get_details(base_currency)`: accounts, platforms, holdings dict, summary totals
- `get_dividends(group_by)`: dividend history, grouped by day/month/year

Tests: `test_details.py`, `test_dividends.py`.

### P4: `evaluate_report()` (~10 tests)

Lowest ROI. Complex rule engine (xRay categories, statistics). Only tackle if P0-P3 are solid.

Tests: `test_report.py`.

## Transform Pipeline (build order)

Build these tree-sitter transform passes in this order:

```
Pass 1: big_js.py        [P0 - do first, blocks everything]
Pass 2: classes.py        [structural: class/extends/methods/self]
Pass 3: expressions.py    [?., ??, destructuring, ternary, arrows]
Pass 4: date_fns.py       [format, differenceInDays, isBefore, eachYearOfInterval]
Pass 5: lodash.py         [cloneDeep, sortBy, isNumber, sum, uniqBy]
Pass 6: types.py          [Big -> Decimal, string -> str, number -> float]
Pass 7: imports.py        [resolve via tt_import_map.json]
```

## Date/stdlib Transforms (needed for P1)

| TS (date-fns) | Python |
|---|---|
| `format(date, 'yyyy-MM-dd')` | `date.strftime("%Y-%m-%d")` |
| `differenceInDays(a, b)` | `(a - b).days` |
| `isBefore(a, b)` / `isAfter(a, b)` | `a < b` / `a > b` |
| `addMilliseconds(d, n)` | `d + timedelta(milliseconds=n)` |
| `eachYearOfInterval({start, end})` | Jan 1 of each year in range |
| `startOfDay(d)` / `endOfDay(d)` | `d.replace(hour=0, ...)` / `d.replace(hour=23, ...)` |

| TS (lodash) | Python |
|---|---|
| `cloneDeep(x)` | `copy.deepcopy(x)` |
| `sortBy(arr, key)` | `sorted(arr, key=...)` |
| `isNumber(x)` | `isinstance(x, (int, float, Decimal))` |

## Realistic Milestones

| Milestone | Tests | Score |
|---|---|---|
| Scaffold baseline (current) | 48/135 | ~30% |
| P0 + P1 done | 95-100/135 | ~63% |
| P2 done | 115-120/135 | ~76% |
| P3 done | 125-130/135 | ~82% |
| + code quality polish | 125-130/135 | ~85-90% |

## What NOT to Spend Time On

- General-purpose transpiler features beyond the ~10 patterns that appear in ROAI source
- Perfect formatting (black handles it, only 15% of score)
- `evaluate_report()` before everything else is solid
- Comment preservation in translated output
- TS patterns that don't exist in this codebase

## Hackathon Day Timeline

| Time | Phase | Goal |
|---|---|---|
| 15:30-16:00 | Setup | Fresh clone, copy in TT, first translate+test, first commit |
| 16:00-17:30 | Core | Iterate on failing tests, commit after each batch unlocked |
| 17:30-18:15 | Polish | Full eval, rule compliance, code quality, SOLUTION.md |
| 18:15-18:30 | Lock | Final eval, final commit, no risky changes |
