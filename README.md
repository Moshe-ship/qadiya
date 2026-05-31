# qadiya (قضية) — Classify + Dispatch under Constraint-Driven Cases

> Part of the [**Mizan**](https://github.com/Moshe-ship/mizan) stack — the Arabic-first reliability scale for AI agents.


[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-green.svg)](https://python.org)
[![Tests: 15 passing](https://img.shields.io/badge/tests-15%20passing-green.svg)]()

The third + fourth primitives of the reversible-agent-operations pattern: **case classification** under a constraint set, and **dispatch** to registered procedures.

---

## What it does

Given a list of constraints (e.g., "operation type", "target scope", "reversibility"), `qadiya` enumerates the Cartesian product of constraint values, prunes infeasible combinations, and gives you a registry. You register one procedure per surviving case. `dispatch()` classifies an incoming input by evaluating constraints, then runs the registered procedure for the matching case. If no case matches, it raises — never silently falls through to a "general" handler.

```python
from qadiya import Constraint, CaseRegistry, Dispatch

c_op = Constraint("op", values=("read", "write"),
                   evaluate=lambda r: r["op"])
c_target = Constraint("target", values=("user_file", "system_file"),
                       evaluate=lambda r: r["target"])
c_in_repo = Constraint("in_repo", values=(True, False),
                        evaluate=lambda r: r["in_repo"])

# Pruning: writes outside the repo are infeasible (escalate path)
def feasible(d):
    return not (d["op"] == "write" and not d["in_repo"])

reg = CaseRegistry(constraints=[c_op, c_target, c_in_repo], feasible=feasible)

# 2 × 2 × 2 = 8 combinations; pruning leaves 6
assert reg.case_count() == 6

# Register a procedure for every surviving case
for case in reg.cases:
    reg.register(case.case_id, make_handler_for(case))
reg.verify_complete()  # raises if any case is unhandled

dispatch = Dispatch(registry=reg)
result = dispatch({"op": "read", "target": "user_file", "in_repo": True})
# DispatchResult(outcome=DISPATCHED, case_id="op=read|target=user_file|in_repo=True", output=...)
```

## Why this is the missing primitive

Agent frameworks have intent routers, skill registries, and tool-call dispatchers. They lack the *constraint-driven enumeration* step. With `qadiya`:

- Cases are **generated**, not invented. The constraint Cartesian product produces a complete, verifiable enumeration.
- Infeasible combinations are **explicitly pruned**, not silently merged with feasible ones.
- Every case must be **registered or escalated** — `verify_complete()` raises if any case is unhandled. There is no implicit "default fallback procedure."
- Classification is **deterministic** — same input always maps to the same case_id.

## Properties

1. **Determinism** — same input → same case_id every time.
2. **Completeness verification** — `verify_complete()` ensures no case is silently dropped.
3. **Explicit escalation** — cases that should not run automatically must be marked with `.escalate()`. Silent fallback is forbidden.
4. **No generation outside procedures** — `qadiya` itself produces no value. It only routes inputs to registered procedures.

## Install

```bash
pip install -e .
```

## Tests

```bash
pytest tests/ -v
```

15/15 pass on Python 3.10+, including a worked end-to-end example with 4 binary constraints, feasibility pruning, complete coverage verification, and round-trip dispatch.

## How it composes with `jabr` and `muqabalah`

The three libraries form the four primitives of the pattern:

```
input
  │
  ▼
jabr.restore()      ← Restore: insert missing terms (al-jabr)
  │
  ▼
muqabalah.balance() ← Balance: cancel duplicates, fail-loud on contradictions
  │
  ▼
qadiya.classify()   ← Classify: which canonical case is this?
  │
  ▼
qadiya.dispatch()   ← Dispatch: run the registered procedure for that case
  │
  ▼
output
```

Each stage is reversible (where applicable), audited, and independently testable. Together they implement the discipline: every transformation an agent performs is a Restore, a Balance, or a Dispatch; every Restore and Balance preserves the original meaning recoverably; every Dispatch is the only place new value is created.

## Failure modes

See `FAILURES.md`.

## License

MIT.
