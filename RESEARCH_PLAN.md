# Research Plan (parallel to P0 build)

Work to do while the tree-sitter parser and Big.js transforms are being built. Ordered by impact.

## 1. Map the wrapper-to-TS interface gap

**Why:** The Python wrapper expects 6 methods but the TS ROAI file only has 3. The missing link is `computeSnapshot()` in the base class.

**What to do:**
- Read `projects/ghostfolio/apps/api/src/app/portfolio/calculator/portfolio-calculator.ts` lines 179-500
- Document what `computeSnapshot()` does: builds chart date map, iterates symbols, calls `getSymbolMetrics()`, aggregates results
- Figure out how the Python calculator should replicate this orchestration using `self.activities` and `self.current_rate_service`

**Interface mapping:**

| Python method | TS source |
|---|---|
| `get_performance()` | `computeSnapshot()` -> `calculateOverallPerformance()` -> format chart + performance dict |
| `get_holdings()` | `computeSnapshot()` -> positions array -> format as holdings dict |
| `get_investments(group_by)` | Transaction point accumulation + grouping (base class) |
| `get_details(base_currency)` | Positions + accounts + summary assembly |
| `get_dividends(group_by)` | Dividend tracking from `getSymbolMetrics()` + grouping |
| `evaluate_report()` | Rule evaluation engine (separate logic) |

## 2. Reverse-engineer exact test contracts

**Why:** Knowing the exact expected values tells you whether the arithmetic is correct, not just "close enough."

**What to do:**
- Read `projecttests/ghostfolio_api/mock_prices.py` to get the exact price data
- For `test_btcusd.py` (simplest case: 1 BUY), build the full input/output table:

```
Input:
  1 BUY, 1 BTCUSD, 2021-12-12, unitPrice=44558.42, fee=4.46, currency=USD
  Market data: BTCUSD closing prices from mock_prices.py

Expected get_performance():
  chart must include:
    2021-12-11: {netWorth: 0, totalInvestment: 0, value: 0, netPerformanceInPercentage: 0}
    2021-12-12: {netWorth: 50098.3, totalInvestment: 44558.42, value: 50098.3,
                 netPerformanceInPercentage: 0.12422837255001412}
    2021-12-31: present (year boundary)
    2022-01-01: present (year boundary)

Expected get_holdings():
  holdings["BTCUSD"]: {quantity: 1, investment: 44558.42}

Expected get_investments():
  [{date: "2021-12-12", investment: 44558.42}]
  grouped by month: [{date: "2021-12-01", investment: 44558.42}]
  grouped by year: [{date: "2021-01-01", investment: 44558.42}]
```

- Repeat for `test_btcusd_buy_and_sell_partially.py` (BUY then partial SELL, tests realized P&L)
- Repeat for `test_short_cover.py` (SELL before BUY)

## 3. Chart date generation logic

**Why:** Many tests assert specific dates appear in the chart. Wrong dates = failed tests even if arithmetic is correct.

**What to do:**
- Find `getChartDateMap()` in the base class
- Document the date selection algorithm:
  - Day before first activity (all-zero entry)
  - The activity dates themselves
  - Year boundaries via `eachYearOfInterval({start, end})`
  - Regular interval sampling for long ranges (`step = daysInMarket / MAX_CHART_ITEMS`)
  - Account balance dates
- The chart dates are sorted and shared across all symbols via `this.chartDates`

**Key tests that depend on this:**
- `test_btcusd_chart_includes_year_boundary` (2021-12-31 and 2022-01-01 must be present)
- `test_btcusd_chart_day_before_first_activity` (2021-12-11 must be present with zeros)
- `test_btcusd_chart_excludes_dates_before_first_activity` (2021-01-01 must NOT be present)

## 4. The `getFactor()` helper

**Why:** Called on every BUY/SELL transaction. Wrong factor = every investment calculation is wrong.

**What to do:**
- Find `getFactor()` in `projects/ghostfolio/apps/api/helper/portfolio.helper.ts`
- Verify: BUY returns 1, SELL returns -1
- Add this to the scaffold as a helper function

## 5. Edge cases to document

| Edge case | Where it matters | Risk |
|---|---|---|
| `Decimal(0)` is falsy in Python, `Big(0)` is truthy in JS | `if (currentPosition.investment)` checks | Skips zero investments incorrectly |
| Exchange rate = 1.0 for same-currency | All currencyEffect calculations | Tests use USD/USD so this should be 1.0 |
| `sorted()` stability | Sorting orders with synthetic start/end markers | Wrong order = wrong running totals |
| Division by zero | `totalUnits.div(totalUnits)` when fully closed | Need guards matching TS exactly |
| Date strings vs date objects | `"2021-12-11" < "2021-12-12"` | String comparison works but mixing types doesn't |
| `Number.EPSILON` in Python | Time-weighted investment day count | Use `sys.float_info.epsilon` |

## 6. The `group_by` logic for investments and dividends

**Why:** ~20 tests check grouped investments (by month, by year).

**What to do:**
- Find the grouping logic in the TS base class
- Document the rules:
  - `group_by=None`: each activity date gets its own entry
  - `group_by="month"`: accumulate to first of month (e.g., "2021-12-01")
  - `group_by="year"`: accumulate to first of year (e.g., "2021-01-01")
- Net investment per period: BUY adds, SELL subtracts (using getFactor)

## 7. Draft scaffold helpers

**Why:** The translated calculator will need utility functions. These go in `tt/tt/scaffold/ghostfolio_pytx/` and get copied into the output.

**What to create:**
- `helpers.py`: `get_factor(order_type)` returns 1 for BUY, -1 for SELL
- `date_utils.py`: chart date generation, year interval calculation, date formatting
- These are general financial calculation helpers, not project-specific logic (Rule 9 compliant)

## Work order

| Priority | Task | Time est. | Unlocks |
|---|---|---|---|
| 1 | Read `mock_prices.py`, build input/output table for test_btcusd | 15 min | Validates P0 arithmetic |
| 2 | Read base class `computeSnapshot()` lines 179-500, document flow | 30 min | Translator knows what orchestration to generate |
| 3 | Draft scaffold helpers (`get_factor`, date utils) | 20 min | Translator can emit code that imports these |
| 4 | Map chart date generation from `getChartDateMap()` | 20 min | Chart tests pass |
| 5 | Document group_by logic | 15 min | Investment/dividend grouping tests pass |
| 6 | Build edge case test table | 15 min | Prevents subtle bugs |
| 7 | Map the full interface gap (all 6 Python methods) | 30 min | Translator produces complete calculator |
