# Oslo Enhanced Hackathon 2026

**Organizer:** Knowit (AWS Partner)
**Format:** Program and rules

---

## Practical Information

- Join the Slack (QR code provided in presentation)
- Questions? Ask your contact person or in the generativKI Slack channel **#oslo-enhanced-hackathon-2026**
- Technical information details are shared in **#oslo-enhanced-hackathon-2026**, incl. access to AWS models
  - FAQ canvas in the Slack channel
  - Shared token budget used until it is empty
  - Links to dashboards for token usage, test completion, etc. will be shared
- Let's have fun!

---

## Challenge Overview

- Build a **Translation Tool (TT)** that converts TypeScript to Python
- **Case:** Translate [ghostfolio](https://github.com/ghostfolio/ghostfolio), a financial portfolio management system
- **Time:** 3 hours of coding (15:30 - 18:30)
- **Judged by:** correctness, code quality, and understanding
- **No LLMs for translation** , but you can use them to build the TT!
- First time running this competition, so judging is best effort
- **Sponsored by AWS**, providing Bedrock credits

---

## Solution Submission

- Set your main branch to your final commit at **18:30**
- Must include:
  - Runnable implementation of TT
  - `SOLUTION.md` explaining your approach
  - Can include visualizations
- Present your solution to judges
- 3 finalists present 3 minutes each from stage, after 18:30

---

## Judges

*(5 judges shown in presentation, photos only, no names listed on the slide)*

---

## Judging Criteria

### 1. Rule Compliance

- Must follow all competition rules

### 2. Correctness (85%)

- Translated Python passes official API test suite
- Number of tests passed matters

### 3. Python Code Quality (15%)

- Readability
- Maintainability
- Mixed static and human evaluation of quality

### 4. Best Engineering Under Constraints

- Very short time for assignment
- Expectation is a prototype, not perfect code

### 5. Understanding

- Can you explain what your TT does?

### 6. Completion Time

- Tie breaker if two teams solved the same number of tests

### Scoring

- **Formula:** tests + code quality + judge review
- Tests are weighted internally, so more challenging tests weigh more than simpler tests

---

## Core Rules

### Rule 0: Build a Python tool (TT) which:

- Can translate ghostfolio from TypeScript to Python
- The translated version should pass as many of the API tests as possible

### Rule 1

You may use the API tests to verify correctness of the translated code.

### Rule 2

TT must not have project-specific logic which it simply copies into the translation. The translated code must be actually translated code, not pregenerated logic.

### Rule 3

You may use AST (abstract syntax trees) libraries in Python.

### Rule 4

Your Python code may not call node/js-tools or other external tools to translate the code. The translation should happen in Python.

### Rule 5

The judges will have a one week period to detect cheating or other rule breaches. This might change the final winner.

### Rule 6

We expect the git commit log to reflect a gradual development of the solution, so do frequent commits.

> See `COMPETITION_RULES.md` in the repo for more details.

---

## Judging Process and Timeline

| Time          | Activity                                      |
| ------------- | --------------------------------------------- |
| 15:15 - 15:30 | Instructions and briefing                     |
| 15:30 - 18:30 | Coding time (GitHub access provided at 15:30) |
| 17:30 - 18:30 | Coding + judge visits (3-min explanation to judges; keep coding!) |
| 18:30          | **ALL CODING STOPS** , commit to main          |
| 18:30 - 19:00 | Judges select 3 finalists                     |
| 19:10 - 19:20 | Finalist presentations                        |
| 19:30          | Winner announced                              |

---

## Prizes and Awards

| Place / Category                        | Prize       |
| --------------------------------------- | ----------- |
| 1st place (winning team)                | 30.000 NOK  |
| 2nd place                               | 7.500 NOK   |
| 3rd place                               | 5.000 NOK   |
| Most innovative workflow/agent setup    | 2.500 NOK   |
| Best team cooperation                   | 2.500 NOK   |
| Special jury award                      | 2.500 NOK   |

- Gift cards mailed after one week

---

## Solution Layout

```
translations/ghostfolio_pytx/app/
├── wrapper/          # provided by original repo (DO NOT MODIFY)
└── implementation/   # TT-generated (your output goes here)
```

- You only modify the `implementation/` directory!

---

## Workflow Suggestion

1. Generate translator TT with Claude Code, etc.
2. Run `make evaluate_tt_ghostfolio`
3. Publish results with `make publish_results`
4. Verify test performance and investigate possible rule breaches
5. Inspect code manually?
6. Iterate on translator

---

## Setup

1. Join the Slack space if you haven't yet
   - Send PM to **Pal de Vibe** to join channel **#oslo-enhanced-hackathon-2026**
2. Fork https://github.com/knowit-enhanced-coding-comp/hackathon-tt-py
3. Give **knowit-enhanced-coding-comp** read access to your fork
4. Add token usage snippet to `.claude` config so we can visualize your token usage

*(Join via GenerativKI-slack)*

---

## Automated Rule Checks

- An imperfect tool to help you solve the solution correctly
- Run: `make detect_rule_breaches`
- Green checks does not mean you aren't cheating

**Checks enforce:**

- No LLM usage in TT
- No project-specific mappings in TT
- No pre-translated logic inside TT
- Wrapper not modified
- ...and more
