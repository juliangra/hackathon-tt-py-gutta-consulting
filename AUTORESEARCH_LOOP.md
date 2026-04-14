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
| `results.tsv` (experiment ledger) | `results.tsv` (same format) |
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
   - results.tsv (what was tried, what worked)
   - Git log (what code changes have stuck)

2. ANALYZE FAILURES
   - Pick the highest-leverage failing test
   - Read the test assertion to understand what value is expected
   - Trace back to the TS source code path
   - Identify which transform is missing or broken

3. MUTATE
   - Edit one transform file in tt/tt/
   - git commit (tentative)

4. EVALUATE
   - make translate-and-test-ghostfolio_pytx
   - Extract: pass_count, fail_count, new_passes,
     new_failures, duration

5. DECIDE
   - pass_count > previous_best:       KEEP (advance branch)
   - pass_count == best, no regressions,
     code is simpler:                   KEEP
   - pass_count <= best OR regressions: DISCARD (git reset)

6. LOG to results.tsv

7. LOOP (never stop, never ask human)
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

## The Metrics

```
Primary:    pass_count   (higher is better, this IS the competition score)
Secondary:  fail_count   (should decrease monotonically on keeps)
Diagnostic: new_passes   (tests flipped green this experiment)
            new_failures (regressions, must be 0 on keeps)
            duration     (translate+test cycle time)
            code_quality (pyscn score, run less frequently)
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

## The Experiment Ledger (results.tsv)

Tab-separated, gitignored, cumulative record of every experiment:

```
commit    pass  fail  new_passes  new_fails  status    description
a1b2c3d   48    87    0           0          baseline  scaffold only
b2c3d4e   52    83    4           0          keep      Big.js .plus() transform
c3d4e5f   50    85    0           2          discard   broken .mul() logic
d4e5f6g   55    80    3           0          keep      fixed .mul() with Decimal
```

## The Outer Loop (Meta-Optimization)

After N experiments, the agent can analyze patterns in results.tsv:

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
- A `results.tsv` showing every experiment the agent ran
- A git history showing gradual improvement (satisfies Rule 8)
- Deep understanding of which transforms matter (for judge explanation)
- A working system that can keep iterating during the event

The competition becomes about polishing and the last 20-30 tests, not building from scratch.

## The Key Insight

From Karpathy's autoresearch:

> The human's role shifts from writing research code to writing the instructions for how an agent should research. You're programming program.md, not train.py.

Applied here: **you do not write the translator. You write PROGRAM.md, the instructions for how the agent should build and improve the translator.** Then you sleep while it runs 500 experiments.

## Implementation Deliverables

1. **`PROGRAM.md`**: The agent protocol (what to edit, how to evaluate, keep/discard rules, strategy hints)
2. **`scripts/evaluate.sh`**: Deterministic eval harness (runs translate+test, parses pytest output, extracts metrics)
3. **`scripts/experiment.sh`**: Single experiment runner (commit, evaluate, decide, log)
4. **`.gitignore` update**: For `results.tsv`
5. **Transform pipeline**: `tt/tt/transforms/` with one file per pattern type

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
                  results.tsv (log experiment)
                       |
                       v
                     LOOP (go to top, never stop)
```
