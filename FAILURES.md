# FAILURES.md

> Inspired by Abū Bakr al-Rāzī, who wrote a separate book listing his own
> medical failures.

Known limitations of `qadiya`.

---

## Things this library deliberately does NOT do

- **No statistical/learned classification.** Classification is rule-based via constraint evaluation. If your domain needs a learned classifier (embedding-based, fine-tuned head), implement the `Classifier` protocol with your model and pass it to `Dispatch(registry=..., classifier=your_classifier)`.

- **No procedure synthesis.** Procedures must be hand-written and registered. There is no automatic procedure generation from constraints.

- **No multi-case fan-out.** Each input matches exactly one case (or none). If your domain has inputs that should run multiple procedures, register a single procedure that orchestrates the fan-out.

- **No fallback / catch-all procedure.** This is intentional. Falls-through must be explicit (`.escalate()`).

---

## Known limitations

### v0.1.0

- **Constraints are evaluated in order, with no caching.** For expensive constraint evaluations, callers should memoize.

- **No support for ordinal/numeric ranges.** Constraint values are a finite set of strings or simple values (booleans, ints). For continuous values, callers must bucket into discrete bands themselves.

- **No partial classification.** All constraints in the constraint list are evaluated for every input. There is no early-exit when a single constraint definitively determines the case.

- **No async procedures.** Registered procedures are synchronous functions. For async, wrap with `asyncio.run()` or build an async-aware `Dispatch` subclass.

- **Case IDs are strings constructed from constraint values.** If your constraint values contain `|` or `=` characters, the case_id format breaks. Mitigation: use values that avoid these characters (e.g., snake_case identifiers).

---

## Errors discovered post-release

*(empty — first release)*

---

## How to report

If `qadiya` produces an incorrect case_id or fails to dispatch correctly:

1. Open a GitHub issue with the constraint definitions, the input, and the expected case.
2. Mark `bug:wrong-classification` or `bug:dispatch-error`.
