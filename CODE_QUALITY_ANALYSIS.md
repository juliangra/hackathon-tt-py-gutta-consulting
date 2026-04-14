# Code Quality Analysis

pyscn scoring breakdown and concrete refactoring targets. Run `make scoring_codequality` to refresh.

## Current Scores

| Component | Health | Complexity | Dead Code | Duplication | Coupling | Deps | Arch | Grade |
|---|---|---|---|---|---|---|---|---|
| Translated code (80% weight) | 59 | 40 | 100 | **0** | 100 | 85 | 100 | D |
| tt translator (20% weight) | 50 | 60 | 100 | **0** | 100 | 85 | 100 | D |
| **Weighted** | **57.2** | | | | | | | **D** |

## The Two Killers

### 1. Duplication: 0/100

pyscn found 8 code clones in the translated output. The root cause: `get_performance()`, `get_holdings()`, `get_investments()`, and `get_dividends()` all repeat the same pattern:

```python
# This pattern appears 4+ times with minor variations:
sorted_acts = self.sorted_activities()
symbols = {a.get('symbol') for a in sorted_acts if a.get('type') in ('BUY', 'SELL')}
first_date = parse_date(min(a['date'] for a in sorted_acts))
start = first_date - timedelta(days=1)
end = date.today()
# ... for sym in symbols: m = self._get_symbol_metrics(sym, start, end) ...
```

**Fix**: Extract a shared `_compute_all_symbol_metrics()` method that does the common work once. Each endpoint method calls it and then formats the result.

### 2. Complexity: 40/100 (translated), 60/100 (tt)

One function dominates everything:

```
_get_symbol_metrics()
  Lines:      193
  Cyclomatic: 40
  Cognitive:  77
  Branches:   39
  Loops:      8
  Risk:       HIGH (critical)
```

pyscn suggestion: "Extract loop bodies into named helper functions."

**Fix**: Split into smaller functions:

| New function | Responsibility | Lines |
|---|---|---|
| `_process_order()` | Handle BUY/SELL/DIVIDEND/FEE/LIABILITY branching | ~40 |
| `_compute_gross_performance()` | Running totals for gross/net performance | ~30 |
| `_build_chart_values()` | Assemble date-indexed value dicts | ~30 |
| `_compute_time_weighted_investment()` | TWI calculation with day counting | ~20 |

### Other functions (lower priority)

| Function | Complexity | Cognitive | Risk |
|---|---|---|---|
| `get_investments()` | 10 | 10 | medium |
| `get_dividends()` | 9 | 8 | low |
| `get_performance()` | 8 | 4 | low |
| `get_holdings()` | 5 | 2 | low |

## What NOT to Touch

These are already at or near max:

- Dead code: 100/100
- Coupling: 100/100
- Architecture: 100/100
- Dependencies: 85/100 (minor, not worth effort)

## Estimated Impact

| Fix | Metric | Before | After (est.) | Score gain |
|---|---|---|---|---|
| Extract shared symbol iteration | Duplication | 0 | 50-70 | +20 on translated |
| Split `_get_symbol_metrics` | Complexity | 40 | 70-80 | +15 on translated |
| Extract chart date helper | Both | - | - | +5-10 combined |
| **Combined** | **Weighted** | **57.2** | **75-85** | **+18 to +28** |

Moving from 57.2 to ~80 would change our grade from D to B and add ~11 points to overall score (quality is 50% of overall in the Supabase formula).

## Important: Changes Must Be in the Emitter

These refactoring targets are in the **generated Python output**, not hand-written code. The translator's emitter (`tt/tt/emitter.py`) must be updated to generate the refactored structure. You cannot edit the generated code directly because it gets overwritten on each `tt translate` run.

## Clone Detection Details (from pyscn)

| Clone ID | File | Lines | Size |
|---|---|---|---|
| 1 | portfolio_calculator.py | 12-392 | 381 lines (entire class) |
| 2 | portfolio_calculator.py | 15-207 | 193 lines (_get_symbol_metrics) |
| 3 | portfolio_calculator.py | 113-186 | 74 lines (inner loop) |
| 4 | portfolio_calculator.py | 219-275 | 57 lines (get_performance) |
| 5 | portfolio_calculator.py | 277-304 | 28 lines (get_investments) |
| 6 | portfolio_calculator.py | 347-371 | 25 lines (get_dividends) |
| 7 | current_rate_service.py | 7-63 | 57 lines (wrapper, immutable) |
| 8 | portfolio_service.py | 42-83 | 42 lines (wrapper, immutable) |

Clones 7 and 8 are in the immutable wrapper (cannot change). Clones 1-6 are all in the generated calculator and share the repeated symbol-iteration pattern.

## Line-Level Duplication

```
6x  sorted_acts = self.sorted_activities()
3x  symbols = {a.get('symbol') for a in sorted_acts if ...}
3x  start = first_date - timedelta(days=1)
2x  total_qty_from_buys = D(0)
2x  total_inv_from_buys = D(0)
2x  m = self._get_symbol_metrics(sym, start, end)
2x  last_avg_price = D(0)
```

All of these collapse to one occurrence each if the shared method is extracted.
