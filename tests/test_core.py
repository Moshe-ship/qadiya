"""qadiya core tests."""

from __future__ import annotations
import pytest

from qadiya import (
    Constraint, Case, CaseRegistry, Classifier, Dispatch,
    DispatchOutcome, NoMatchingCase, AmbiguousCases,
    enumerate_cases,
)
from qadiya.core import CompletenessError


# --- Cartesian product enumeration ---------------------------------------


def test_enumerate_cases_2x2():
    c1 = Constraint("op", values=("read", "write"), evaluate=lambda x: x["op"])
    c2 = Constraint("target", values=("user", "system"),
                    evaluate=lambda x: x["target"])
    cases = enumerate_cases([c1, c2])
    assert len(cases) == 4
    case_ids = {c.case_id for c in cases}
    assert case_ids == {
        "op=read|target=user",
        "op=read|target=system",
        "op=write|target=user",
        "op=write|target=system",
    }


def test_enumerate_cases_with_feasibility_predicate():
    """Caller can prune infeasible combinations."""
    c1 = Constraint("op", ("read", "write"), evaluate=lambda x: x["op"])
    c2 = Constraint("target", ("readonly", "readwrite"),
                    evaluate=lambda x: x["target"])
    # Pruning: write to readonly is infeasible
    feasible = lambda d: not (d["op"] == "write" and d["target"] == "readonly")
    cases = enumerate_cases([c1, c2], feasible=feasible)
    assert len(cases) == 3
    case_ids = {c.case_id for c in cases}
    assert "op=write|target=readonly" not in case_ids


def test_enumerate_cases_3_constraints():
    c1 = Constraint("op", ("read", "write"), evaluate=lambda x: x["op"])
    c2 = Constraint("target", ("user", "system"), evaluate=lambda x: x["target"])
    c3 = Constraint("rev", (True, False), evaluate=lambda x: x["rev"])
    cases = enumerate_cases([c1, c2, c3])
    # 2 × 2 × 2 = 8 cases
    assert len(cases) == 8


# --- Classifier ----------------------------------------------------------


def test_classifier_deterministic():
    c1 = Constraint("op", ("read", "write"), evaluate=lambda x: x["op"])
    c2 = Constraint("target", ("user", "system"), evaluate=lambda x: x["target"])
    clf = Classifier([c1, c2])
    case_id, evaluated = clf.classify({"op": "read", "target": "user"})
    assert case_id == "op=read|target=user"
    assert evaluated == {"op": "read", "target": "user"}


def test_classifier_raises_on_invalid_value():
    c1 = Constraint("op", ("read", "write"), evaluate=lambda x: x["op"])
    clf = Classifier([c1])
    with pytest.raises(ValueError):
        clf.classify({"op": "delete"})  # 'delete' not in declared values


# --- Registry registration -----------------------------------------------


def test_register_procedure():
    c1 = Constraint("op", ("read", "write"), evaluate=lambda x: x["op"])
    reg = CaseRegistry(constraints=[c1])
    reg.register("op=read", lambda x: f"reading {x}")
    reg.register("op=write", lambda x: f"writing {x}")
    assert reg.case_count() == 2


def test_register_invalid_case_raises():
    c1 = Constraint("op", ("read", "write"), evaluate=lambda x: x["op"])
    reg = CaseRegistry(constraints=[c1])
    with pytest.raises(ValueError):
        reg.register("op=delete", lambda x: x)


def test_verify_complete_raises_on_unhandled():
    c1 = Constraint("op", ("read", "write"), evaluate=lambda x: x["op"])
    reg = CaseRegistry(constraints=[c1])
    reg.register("op=read", lambda x: x)
    # op=write is unhandled
    with pytest.raises(CompletenessError) as exc:
        reg.verify_complete()
    assert "op=write" in exc.value.unhandled


def test_verify_complete_ok_when_all_handled():
    c1 = Constraint("op", ("read", "write"), evaluate=lambda x: x["op"])
    reg = CaseRegistry(constraints=[c1])
    reg.register("op=read", lambda x: x)
    reg.register("op=write", lambda x: x)
    reg.verify_complete()  # No exception


def test_verify_complete_ok_with_escalation():
    c1 = Constraint("op", ("read", "write"), evaluate=lambda x: x["op"])
    reg = CaseRegistry(constraints=[c1])
    reg.register("op=read", lambda x: x)
    reg.escalate("op=write")
    reg.verify_complete()  # No exception


# --- Dispatch ------------------------------------------------------------


def test_dispatch_runs_registered_procedure():
    c1 = Constraint("op", ("read", "write"), evaluate=lambda x: x["op"])
    reg = CaseRegistry(constraints=[c1])
    reg.register("op=read", lambda x: f"read:{x['target']}", name="read_proc")
    reg.register("op=write", lambda x: f"write:{x['target']}", name="write_proc")
    dispatch = Dispatch(registry=reg)

    result = dispatch({"op": "read", "target": "foo"})
    assert result.outcome == DispatchOutcome.DISPATCHED
    assert result.output == "read:foo"
    assert result.procedure_name == "read_proc"
    assert result.case_id == "op=read"


def test_dispatch_escalation_returns_no_match():
    c1 = Constraint("op", ("read", "write"), evaluate=lambda x: x["op"])
    reg = CaseRegistry(constraints=[c1])
    reg.register("op=read", lambda x: x)
    reg.escalate("op=write")
    dispatch = Dispatch(registry=reg)

    result = dispatch({"op": "write"})
    assert result.outcome == DispatchOutcome.NO_MATCH
    assert result.case_id == "op=write"


def test_dispatch_unregistered_case_raises():
    c1 = Constraint("op", ("read", "write"), evaluate=lambda x: x["op"])
    reg = CaseRegistry(constraints=[c1])
    reg.register("op=read", lambda x: x)
    # op=write is neither registered nor escalated
    dispatch = Dispatch(registry=reg)
    with pytest.raises(NoMatchingCase):
        dispatch({"op": "write"})


# --- End-to-end worked example: code-editing-agent case table ------------


def test_code_editing_agent_full_pipeline():
    """A realistic example: 4 binary constraints → 16 Cartesian cases →
    pruned by feasibility → registered procedures → dispatch."""

    c_op = Constraint(
        "op", ("read", "write"),
        evaluate=lambda r: r["op"],
    )
    c_scope = Constraint(
        "scope", ("user_file", "system_file"),
        evaluate=lambda r: r["scope"],
    )
    c_in_repo = Constraint(
        "in_repo", (True, False),
        evaluate=lambda r: r["in_repo"],
    )
    c_reversible = Constraint(
        "reversible", (True, False),
        evaluate=lambda r: r["reversible"],
    )

    # Pruning: writes to system files require admin (escalate, not feasible
    # in normal flow); writes to non-reversible non-tracked files are also
    # exceptional.
    def feasible(d):
        # Reads always feasible
        if d["op"] == "read":
            return True
        # Writes: must be in_repo (otherwise escalate)
        if d["op"] == "write" and not d["in_repo"]:
            return False
        return True

    reg = CaseRegistry(
        constraints=[c_op, c_scope, c_in_repo, c_reversible],
        feasible=feasible,
    )

    # The feasibility predicate prunes "write outside repo" combinations.
    # That should leave: 2 (read × user/system) × 2 (in_repo) × 2 (rev) = 8
    # for read; plus 2 (write × user/system) × 1 (in_repo=True) × 2 (rev) = 4
    # total 12 cases.
    assert reg.case_count() == 12

    # Register procedures for all 12
    def make_handler(label):
        return lambda r: f"{label}:{r.get('path','?')}"

    for case in reg.cases:
        reg.register(case.case_id, make_handler(case.case_id))

    reg.verify_complete()

    dispatch = Dispatch(registry=reg)

    # Read a user file in repo, reversible
    r = dispatch({
        "op": "read", "scope": "user_file",
        "in_repo": True, "reversible": True,
        "path": "main.py",
    })
    assert r.outcome == DispatchOutcome.DISPATCHED
    assert "op=read" in r.case_id
    assert "scope=user_file" in r.case_id
    assert "in_repo=True" in r.case_id

    # Write to system file in repo (allowed by feasibility)
    r = dispatch({
        "op": "write", "scope": "system_file",
        "in_repo": True, "reversible": True,
        "path": "/etc/foo",
    })
    assert r.outcome == DispatchOutcome.DISPATCHED


def test_code_editing_pruned_case_raises():
    """A case that was pruned by feasibility should raise on dispatch."""
    c_op = Constraint("op", ("read", "write"), evaluate=lambda r: r["op"])
    c_in_repo = Constraint("in_repo", (True, False),
                            evaluate=lambda r: r["in_repo"])
    feasible = lambda d: not (d["op"] == "write" and not d["in_repo"])
    reg = CaseRegistry(constraints=[c_op, c_in_repo], feasible=feasible)
    reg.register("op=read|in_repo=True", lambda r: r)
    reg.register("op=read|in_repo=False", lambda r: r)
    reg.register("op=write|in_repo=True", lambda r: r)
    # op=write|in_repo=False was pruned, so it's not in the registry's cases

    reg.verify_complete()  # OK

    # If the user provides input matching a pruned case, classifier produces
    # the case_id but no procedure is registered.
    dispatch = Dispatch(registry=reg)
    with pytest.raises(NoMatchingCase):
        dispatch({"op": "write", "in_repo": False})
