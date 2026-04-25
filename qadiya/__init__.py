"""qadiya (قضية) — Classify-then-Dispatch primitive.

The third + fourth primitives of the pattern: case classification under a
constraint set, and dispatch to a registered procedure for the matched case.

A `CaseRegistry` enumerates canonical cases generated from a constraint
set. A `Classifier` maps inputs to case IDs. A `Procedure` is the registered
function that handles a single case. `dispatch()` ties them together: classify
the input, look up the procedure, run it.

The architectural commitment is: an input that matches no case is escalated,
never silently handled by a fallback general procedure. This is what makes
the system 'constraint-complete' — every input is either handled by a
named procedure or surfaced for explicit review.
"""

from qadiya.core import (
    Case,
    Constraint,
    CaseRegistry,
    Procedure,
    Classifier,
    Dispatch,
    DispatchResult,
    DispatchOutcome,
    NoMatchingCase,
    AmbiguousCases,
    enumerate_cases,
)

__version__ = "0.1.0"
__all__ = [
    "Case",
    "Constraint",
    "CaseRegistry",
    "Procedure",
    "Classifier",
    "Dispatch",
    "DispatchResult",
    "DispatchOutcome",
    "NoMatchingCase",
    "AmbiguousCases",
    "enumerate_cases",
]
