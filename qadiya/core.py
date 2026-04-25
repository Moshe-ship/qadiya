"""Classify + Dispatch + constraint-driven case enumeration.

Three primitives:

  1. Constraint — a binary or enumerated dimension that partitions inputs.
  2. Case — a specific combination of constraint values; one canonical
     situation the agent recognizes.
  3. Procedure — a registered function that handles one case.

The CaseRegistry enumerates all combinations of constraint values, prunes
infeasible cases (caller-supplied predicate), and records the surviving
canonical cases. Each registered Procedure binds to one case.

dispatch() classifies an input by evaluating constraints against it,
matches the resulting case-tuple to a registered procedure, and runs the
procedure. If no case matches, NoMatchingCase is raised. If multiple cases
match (which should never happen with well-defined constraints),
AmbiguousCases is raised.
"""

from __future__ import annotations
import dataclasses
import itertools
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Generic, Optional, Protocol, TypeVar


I = TypeVar("I")  # Input type
O = TypeVar("O")  # Output type


class DispatchOutcome(Enum):
    """How dispatch resolved the input."""
    DISPATCHED = "dispatched"          # Procedure ran successfully
    NO_MATCH = "no_match"              # No case matched (escalate)
    AMBIGUOUS = "ambiguous"            # Multiple cases matched (specification bug)


class NoMatchingCase(Exception):
    """Raised by dispatch() when no registered case matches the input."""

    def __init__(self, message: str, evaluated: dict[str, Any]):
        super().__init__(message)
        self.evaluated_constraints = evaluated


class AmbiguousCases(Exception):
    """Raised when more than one registered case matches the input.

    This indicates the constraint set is non-discriminating. Cases must
    partition the input space, not overlap.
    """

    def __init__(self, message: str, matching_cases: list[str]):
        super().__init__(message)
        self.matching_cases = matching_cases


@dataclass(frozen=True)
class Constraint(Generic[I]):
    """A constraint is a named function that maps an input to a value.

    For binary constraints, the value is True/False. For enumerated
    constraints, it is one of a finite set of strings. The set of values
    a constraint produces is fixed at registration time as `values`.
    """

    name: str
    values: tuple[Any, ...]
    evaluate: Callable[[I], Any]

    def __post_init__(self):
        if not self.values:
            raise ValueError(f"Constraint {self.name} must have at least one value")

    def __call__(self, input: I) -> Any:
        v = self.evaluate(input)
        if v not in self.values:
            raise ValueError(
                f"Constraint {self.name} evaluated to {v!r}, "
                f"which is not in declared values {self.values}"
            )
        return v


@dataclass(frozen=True)
class Case:
    """A canonical case — a specific combination of constraint values.

    The case_id is a stable string formed by joining (constraint_name=value)
    pairs in declared order, e.g. "kind=read|target=user_file".
    """

    case_id: str
    assignment: tuple[tuple[str, Any], ...]  # ((constraint_name, value), ...)
    description: str = ""


def enumerate_cases(
    constraints: list[Constraint],
    feasible: Optional[Callable[[dict[str, Any]], bool]] = None,
    descriptions: Optional[dict[str, str]] = None,
) -> list[Case]:
    """Enumerate canonical cases from a constraint set.

    Computes the Cartesian product of constraint values, applies an optional
    feasibility predicate to prune impossible combinations, and returns one
    Case per surviving combination.

    Args:
        constraints: ordered list of Constraint definitions.
        feasible: predicate that returns False for infeasible combinations.
                  Receives a dict {constraint_name: value}.
        descriptions: optional dict mapping case_id to a human description.

    Returns:
        A list of Case objects in declared (Cartesian) order.
    """
    descriptions = descriptions or {}
    cases: list[Case] = []

    value_lists = [c.values for c in constraints]
    for combo in itertools.product(*value_lists):
        assignment = tuple(zip([c.name for c in constraints], combo))
        as_dict = dict(assignment)
        if feasible is not None and not feasible(as_dict):
            continue
        case_id = "|".join(f"{name}={value}" for name, value in assignment)
        cases.append(Case(
            case_id=case_id,
            assignment=assignment,
            description=descriptions.get(case_id, ""),
        ))
    return cases


# --------------------------------------------------------------------------- #
# Procedure registry
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Procedure(Generic[I, O]):
    """A registered procedure binding to one case.

    The function receives the input and returns an output. Side effects
    are caller-defined; the registry does not enforce purity.
    """

    case_id: str
    fn: Callable[[I], O]
    name: str = ""
    description: str = ""

    def __post_init__(self):
        if not self.name:
            object.__setattr__(self, "name", self.fn.__name__)


# --------------------------------------------------------------------------- #
# Classifier
# --------------------------------------------------------------------------- #


@dataclass
class Classifier(Generic[I]):
    """Maps inputs to a case_id by evaluating each constraint in turn.

    The Classifier is *deterministic*: for the same input, it returns the
    same case_id (or raises the same exception). It is also *constraint-
    driven*: the case_id is generated from constraint evaluations, never
    inferred or guessed.
    """

    constraints: list[Constraint]

    def classify(self, input: I) -> tuple[str, dict[str, Any]]:
        """Return (case_id, evaluated_constraints).

        evaluated_constraints is a dict mapping constraint name to its value.
        It is returned alongside case_id for debugging and tracing.
        """
        evaluated: dict[str, Any] = {}
        for c in self.constraints:
            evaluated[c.name] = c(input)
        case_id = "|".join(
            f"{c.name}={evaluated[c.name]}" for c in self.constraints
        )
        return case_id, evaluated


# --------------------------------------------------------------------------- #
# CaseRegistry & Dispatch
# --------------------------------------------------------------------------- #


@dataclass
class CaseRegistry(Generic[I, O]):
    """The complete registry of canonical cases and their procedures.

    Construction:
        registry = CaseRegistry(
            constraints=[c1, c2, ...],
            feasible=lambda d: d['x'] != 'y',  # optional prune predicate
        )
        registry.register('case_id', my_function)
        ...

    All cases enumerated by the constraint set must be either registered
    or explicitly marked as escalation-only. Otherwise CaseRegistry.verify()
    raises a CompletenessError.
    """

    constraints: list[Constraint]
    feasible: Optional[Callable[[dict[str, Any]], bool]] = None
    descriptions: dict[str, str] = field(default_factory=dict)
    _procedures: dict[str, Procedure] = field(default_factory=dict)
    _escalations: set[str] = field(default_factory=set)
    _cases: list[Case] = field(default_factory=list)

    def __post_init__(self):
        self._cases = enumerate_cases(
            self.constraints, self.feasible, self.descriptions
        )

    @property
    def cases(self) -> list[Case]:
        return list(self._cases)

    def register(
        self,
        case_id: str,
        fn: Callable[[I], O],
        name: str = "",
        description: str = "",
    ) -> None:
        """Register a procedure for a case. The case_id must match an
        enumerated case."""
        valid_ids = {c.case_id for c in self._cases}
        if case_id not in valid_ids:
            raise ValueError(
                f"case_id {case_id!r} is not in the enumerated case set. "
                f"Valid case_ids: {sorted(valid_ids)}"
            )
        self._procedures[case_id] = Procedure(
            case_id=case_id, fn=fn, name=name, description=description,
        )

    def escalate(self, case_id: str) -> None:
        """Mark a case as explicit escalation-only — no automatic procedure
        will run; dispatch() raises NoMatchingCase for that case_id."""
        valid_ids = {c.case_id for c in self._cases}
        if case_id not in valid_ids:
            raise ValueError(
                f"case_id {case_id!r} is not in the enumerated case set."
            )
        self._escalations.add(case_id)

    def verify_complete(self) -> None:
        """Raise CompletenessError if any enumerated case is neither
        registered nor explicitly marked as escalation."""
        unhandled = []
        for case in self._cases:
            if case.case_id in self._procedures:
                continue
            if case.case_id in self._escalations:
                continue
            unhandled.append(case.case_id)
        if unhandled:
            raise CompletenessError(
                f"Unhandled cases: {unhandled}. Register a procedure or "
                f"call .escalate() for each.",
                unhandled,
            )

    def case_count(self) -> int:
        return len(self._cases)


class CompletenessError(Exception):
    """Raised by verify_complete() when cases are unhandled."""

    def __init__(self, message: str, unhandled: list[str]):
        super().__init__(message)
        self.unhandled = unhandled


@dataclass(frozen=True)
class DispatchResult(Generic[O]):
    """Result of dispatch() — the outcome plus details."""

    outcome: DispatchOutcome
    case_id: str
    evaluated_constraints: dict[str, Any]
    output: Optional[O] = None
    procedure_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "case_id": self.case_id,
            "evaluated_constraints": self.evaluated_constraints,
            "procedure_name": self.procedure_name,
            # output may not be JSON-serializable; caller handles it
        }


@dataclass
class Dispatch(Generic[I, O]):
    """Tie a Classifier and a CaseRegistry together; dispatch inputs."""

    registry: CaseRegistry[I, O]
    classifier: Optional[Classifier[I]] = None

    def __post_init__(self):
        if self.classifier is None:
            self.classifier = Classifier(constraints=self.registry.constraints)

    def __call__(self, input: I) -> DispatchResult[O]:
        case_id, evaluated = self.classifier.classify(input)

        # Marked-escalation cases never run automatically
        if case_id in self.registry._escalations:
            return DispatchResult(
                outcome=DispatchOutcome.NO_MATCH,
                case_id=case_id,
                evaluated_constraints=evaluated,
            )

        proc = self.registry._procedures.get(case_id)
        if proc is None:
            raise NoMatchingCase(
                f"No registered procedure for case {case_id!r}. "
                f"Either register one, call .escalate({case_id!r}), or "
                f"verify your constraint enumeration is correct.",
                evaluated,
            )

        output = proc.fn(input)
        return DispatchResult(
            outcome=DispatchOutcome.DISPATCHED,
            case_id=case_id,
            evaluated_constraints=evaluated,
            output=output,
            procedure_name=proc.name,
        )
