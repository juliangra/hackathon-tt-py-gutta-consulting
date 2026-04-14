# Autoresearch Loop for TT

Inspired by [karpathy/autoresearch](https://github.com/karpathy/autoresearch): autonomous hill-climbing over a mutable artifact, guided by a quantitative objective function. The agent modifies the translator, runs tests, keeps improvements, discards regressions, and loops forever.

## The Core Mapping

| Autoresearch | TT Hackathon |
|---|---|
| `train.py` (single mutable artifact) | `tt/tt/` (translator code) |
| `prepare.py` (immutable eval harness) | Test suite + wrapper layer (frozen, byte-for-byte) |
| `val_bpb` (single metric, lower is better) | **Test fail count** (lower is better) |
| `program.md` (human-written agent protocol) | Our `PROGRAM.md` (agent research protocol) |
| 5-min wall-clock budget | Full translate+test cycle (~30-60 seconds) |
| `results.csv` (experiment ledger) | `results.csv` (same format) |
| Git ratchet (commit on improve, reset on regress) | Same |
| ~12 experiments/hour | ~60-120 experiments/hour (cycles are faster) |

## Why This Fits Better Than ML Training

1. **Faster feedback loop**: translate+test takes ~30-60 seconds, not 5 minutes. That is 60-120 experiments per hour, not 12. Overnight = 500-1000 experiments.

2. **Richer signal**: Unlike `val_bpb` (one number), we get *which specific tests* pass or fail. The agent can trace a failing assertion to the exact TS code path that needs a transform fix. This turns blind hill-climbing into informed, targeted improvement.

3. **Discrete, decomposable problem**: Each failing test maps to a specific missing or broken transform. The agent does not need to guess randomly. It can read the failing test, understand what value is expected, find the TS code that computes it, and fix the transform.

4. **Bounded mutation surface**: The transforms are modular (one file per pattern type). The agent edits one transform at a time, making diffs small and reviewable.

## The Three-File Structure

```
PROGRAM.md          # Human-written agent protocol (YOU write this)
tt/tt/              # Mutable artifact (agent modifies this)
projecttests/       # Immutable eval (agent CANNOT touch this)
```

This mirrors autoresearch exactly: `program.md` / `train.py` / `prepare.py`.

## The Inner Loop (per experiment)

```
1. READ STATE
   - Current test results (which pass, which fail)
   - results.csv (what was tried, what worked)
   - Rule violation count (make detect_rule_breaches)
   - Git log (what code changes have stuck)

2. ANALYZE (depends on phase)
   Phase 1: Pick highest-leverage failing test, trace to TS code
   Phase 2: Pick highest-leverage rule violation, read the check script
   Phase 3: Pick lowest quality sub-score, identify generated code to improve

3. MUTATE
   - Edit one file in tt/tt/
   - git commit (tentative)

4. EVALUATE
   - python scripts/evaluate.py "description"      (always: tests)
   - make detect_rule_breaches 2>&1 | tail -5       (Phase 2+: rules)
   - make scoring_codequality                        (Phase 3: quality)

5. DECIDE (composite)
   Phase 1: pass_count improved, no regressions           -> KEEP
   Phase 2: rule_violations decreased, tests still 135    -> KEEP
   Phase 3: quality improved, still legal, tests still 135 -> KEEP
   Any test regression                                    -> DISCARD

6. LOG to results.csv
   - python scripts/mark.py keep|discard

7. PUBLISH (when significant improvement)
   - make publish_results
   - python scripts/leaderboard.py --us

8. LOOP (never stop, never ask human)
```

## Informed Hill-Climbing (Not Blind Search)

Autoresearch does *blind* hill-climbing: the agent guesses what might help. Our system has a massive advantage: **failing tests tell you exactly what is wrong**.

```
Test: test_btcusd_chart_on_buy_date
Expected: netWorth == 50098.3
Got:      netWorth == 0

-> The translated calculator returns 0 for netWorth
-> That means get_performance() returns empty chart
-> That means getSymbolMetrics() is not translated
-> The agent should add Big.js arithmetic transforms
```

This turns random search into directed graph traversal. Each failing test is a signpost pointing to the missing transform.

## The Metrics (Multi-Objective)

The loop optimizes a composite score, not just test count. Once tests are maxed, the focus shifts to rule compliance and code quality.

```
PRIMARY METRICS (check every experiment):
  pass_count       Tests passing (higher is better, 85% of competition score)
  fail_count       Tests failing (should decrease monotonically)
  rule_violations  Count of failing rule checks (lower is better, 0 = legal)

SECONDARY METRICS (check every ~5 experiments):
  quality_pct      pyscn code quality score (15% of competition score)
  overall_score    Combined: 50% tests + 50% quality (Supabase leaderboard formula)
  legal            Boolean: all rule checks pass?

DIAGNOSTIC:
  new_passes       Tests flipped green this experiment
  new_failures     Regressions (must be 0 on keeps)
  duration         Translate+test cycle time
```

### Phase transitions

The loop automatically shifts focus based on current state:

```
Phase 1 (pass_count < 135):  Optimize for test count
  -> Metric: pass_count
  -> Keep if: more tests pass, no regressions

Phase 2 (pass_count == 135, rule_violations > 0):  Fix rule violations
  -> Metric: rule_violations
  -> Keep if: fewer violations, no test regressions
  -> Run: make detect_rule_breaches

Phase 3 (pass_count == 135, rule_violations == 0):  Optimize code quality
  -> Metric: quality_pct
  -> Keep if: quality improves, still legal, no test regressions
  -> Run: make scoring_codequality
```

### Leaderboard check (every experiment in Phase 2+)

```bash
# Quick rule check (fast, run every experiment)
make detect_rule_breaches 2>&1 | grep -c "FAIL"

# Full scoring (slower, run every ~5 experiments)
python scripts/leaderboard.py --us

# Publish to leaderboard after a significant improvement
make publish_results
```

## The Git Ratchet

Git is dual-use: version control AND system memory. Only successful experiments move the branch forward.

```
experiment 1: add Big.js .plus() transform    52/135 (+4)  KEEP
experiment 2: add .mul() transform            55/135 (+3)  KEEP
experiment 3: try .div() with wrong logic     53/135 (-2)  DISCARD (git reset)
experiment 4: fix .div() transform            58/135 (+3)  KEEP
```

The branch only ever moves forward. The ledger remembers what was tried and discarded.

## The Experiment Ledger (results.csv)

Tab-separated, gitignored, cumulative record of every experiment:

```
commit    pass  fail  new_passes  new_fails  status    description
a1b2c3d   48    87    0           0          baseline  scaffold only
b2c3d4e   52    83    4           0          keep      Big.js .plus() transform
c3d4e5f   50    85    0           2          discard   broken .mul() logic
d4e5f6g   55    80    3           0          keep      fixed .mul() with Decimal
```

## The Outer Loop (Meta-Optimization)

After N experiments, the agent can analyze patterns in results.csv:

1. **What categories of transforms improve test count?**
   - "All Big.js transforms improved pass count by 3-5 tests"
   - "Date-fns transforms had the biggest single improvement"
   - "Lodash transforms did not move the needle much"

2. **Update search strategy:**
   - Prioritize patterns similar to what worked
   - Deprioritize patterns that consistently fail
   - Try combinations of successful transforms

3. **Read failing test output more deeply:**
   - Cluster failures by root cause
   - Estimate how many tests each fix would unlock
   - Attack the highest-leverage cluster next

## Expected Throughput

| Timeframe | Experiments | Expected Progress |
|---|---|---|
| 1 hour active work | 30-60 | Find and fix the 3-4 highest-leverage transforms |
| Overnight (8 hours) | 200-400 | Exhaust the easy wins, start attacking edge cases |
| 2 days pre-hackathon | 500-1000 | Approach the ceiling of what automated transforms can achieve |

## What This Means for the Hackathon

If you run this loop for even one night before the hackathon, you walk in with:

- A translator that already passes 100+ tests
- A `results.csv` showing every experiment the agent ran
- A git history showing gradual improvement (satisfies Rule 8)
- Deep understanding of which transforms matter (for judge explanation)
- A working system that can keep iterating during the event

The competition becomes about polishing and the last 20-30 tests, not building from scratch.

## The Key Insight

From Karpathy's autoresearch:

> The human's role shifts from writing research code to writing the instructions for how an agent should research. You're programming program.md, not train.py.

Applied here: **you do not write the translator. You write PROGRAM.md, the instructions for how the agent should build and improve the translator.** Then you sleep while it runs 500 experiments.

## Implementation Deliverables (all built)

1. **`PROGRAM.md`**: Agent protocol (what to edit, how to evaluate, keep/discard rules)
2. **`scripts/evaluate.py`**: Translate+test, parse pytest, append to results.csv
3. **`scripts/mark.py`**: Update last experiment status (keep/discard/baseline)
4. **`scripts/stats.py`**: Improvement timeline, hit rate, score estimates
5. **`scripts/leaderboard.py`**: Query Supabase for live standings, gap analysis, quality comparison
6. **`results.csv`**: Experiment ledger (gitignored)
7. **`runs/`**: Per-run pytest logs (gitignored)

## Architecture Diagram

```
YOU (human)
  |
  v
PROGRAM.md  ------>  AGENT (Claude Code)
                       |
                       |  reads program, analyzes failures
                       v
                     tt/tt/  (mutate one transform)
                       |
                       |  git commit (tentative)
                       v
                     make translate-and-test-ghostfolio_pytx
                       |
                       |  extract metrics
                       v
                     DECIDE: pass_count improved?
                      / \
                   YES   NO
                    |     |
                  KEEP  DISCARD
                    |     |
                  advance git reset
                  branch  HEAD~1
                    |     |
                    v     v
                  results.csv (log experiment)
                       |
                       v
                     LOOP (go to top, never stop)
```
