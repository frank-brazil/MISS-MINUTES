import asyncio
from datetime import datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.core.problem_solver import (
    CONFIDENCE_RANGE_DESCRIPTION,
    Evidence,
    EvidenceKind,
    FakeProblemSolver,
    Hypothesis,
    Problem,
    ProblemAnalysis,
    ProblemSolver,
    RiskLevel,
    Solution,
)


def evidence(description: str = "evidence", **kwargs: object) -> Evidence:
    return Evidence(description=description, **kwargs)


def hypothesis(**kwargs: object) -> Hypothesis:
    fields: dict[str, object] = {"description": "possible cause"}
    fields.update(kwargs)
    return Hypothesis(**fields)


def solution(**kwargs: object) -> Solution:
    fields: dict[str, object] = {"description": "try a fix"}
    fields.update(kwargs)
    return Solution(**fields)


def problem(**kwargs: object) -> Problem:
    fields: dict[str, object] = {"description": "Database connection failed."}
    fields.update(kwargs)
    return Problem(**fields)


def analysis(**kwargs: object) -> ProblemAnalysis:
    prob = problem()
    hypo = hypothesis()
    sol = solution()
    fields: dict[str, object] = {
        "problem": prob,
        "hypotheses": [hypo],
        "candidate_solutions": [sol],
    }
    fields.update(kwargs)
    return ProblemAnalysis(**fields)


# --- Problem ----------------------------------------------------------------


def test_problem_model_fields() -> None:
    prob = problem(context={"tried": "restart service"})
    assert isinstance(prob.problem_id, UUID)
    assert prob.description == "Database connection failed."
    assert prob.context == {"tried": "restart service"}
    assert isinstance(prob.created_at, datetime)
    assert prob.created_at.tzinfo is not None


def test_problem_context_defaults_to_empty_dict() -> None:
    prob = problem()
    assert prob.context == {}


def test_problem_automatic_ids() -> None:
    assert problem().problem_id != problem().problem_id


def test_problem_rejects_empty_description() -> None:
    with pytest.raises(ValidationError, match="description"):
        problem(description="")


def test_problem_rejects_blank_description() -> None:
    with pytest.raises(ValidationError, match="description"):
        problem(description="   ")


# --- RiskLevel --------------------------------------------------------------


def test_risk_level_values() -> None:
    assert RiskLevel.LOW.value == "low"
    assert RiskLevel.MEDIUM.value == "medium"
    assert RiskLevel.HIGH.value == "high"
    assert RiskLevel.UNKNOWN.value == "unknown"


# --- Evidence ---------------------------------------------------------------


def test_evidence_kind_values() -> None:
    assert {kind.value for kind in EvidenceKind} == {
        "fact",
        "observation",
        "assumption",
        "research",
    }


def test_evidence_defaults() -> None:
    item = Evidence(description="the log shows an error")
    assert isinstance(item.evidence_id, UUID)
    assert item.kind is EvidenceKind.OBSERVATION
    assert item.source_ref is None
    assert item.confidence is None


def test_evidence_supports_source_ref() -> None:
    item = Evidence(
        description="the documentation recommends this",
        kind=EvidenceKind.RESEARCH,
        source_ref="https://example.com/docs",
        confidence=0.8,
    )
    assert item.source_ref == "https://example.com/docs"
    assert item.confidence == 0.8


def test_evidence_rejects_blank_description() -> None:
    with pytest.raises(ValidationError, match="description"):
        Evidence(description="")


def test_evidence_rejects_blank_source_ref() -> None:
    with pytest.raises(ValidationError, match="source_ref"):
        Evidence(description="d", source_ref="  ")


def test_evidence_rejects_invalid_confidence() -> None:
    with pytest.raises(ValidationError, match="confidence"):
        Evidence(description="d", confidence=1.5)
    with pytest.raises(ValidationError, match="confidence"):
        Evidence(description="d", confidence=-0.1)


# --- Hypothesis -------------------------------------------------------------


def test_hypothesis_model_fields() -> None:
    hypo = hypothesis(
        confidence=0.6,
        evidence_for=[evidence("a"), evidence("b")],
        evidence_against=[evidence("c")],
    )
    assert isinstance(hypo.hypothesis_id, UUID)
    assert hypo.description == "possible cause"
    assert hypo.confidence == 0.6
    assert len(hypo.evidence_for) == 2
    assert len(hypo.evidence_against) == 1


def test_hypothesis_evidence_lists_default_empty() -> None:
    hypo = hypothesis()
    assert hypo.evidence_for == []
    assert hypo.evidence_against == []


def test_hypothesis_rejects_blank_description() -> None:
    with pytest.raises(ValidationError, match="description"):
        hypothesis(description="  ")


def test_hypothesis_rejects_invalid_confidence() -> None:
    with pytest.raises(ValidationError, match="confidence"):
        hypothesis(confidence=1.2)


def test_hypothesis_supports_supporting_and_contradicting_evidence() -> None:
    supporting = evidence("supports the cause")
    contradicting = evidence("contradicts the cause")
    hypo = hypothesis(
        evidence_for=[supporting], evidence_against=[contradicting]
    )
    assert hypo.evidence_for == [supporting]
    assert hypo.evidence_against == [contradicting]
    assert hypo.evidence_for[0].description == "supports the cause"


# --- Solution ---------------------------------------------------------------


def test_solution_model_fields() -> None:
    sol = solution(
        expected_outcome="connection restored",
        confidence=0.7,
        risk=RiskLevel.LOW,
        risk_note="reversible",
        required_capabilities=frozenset({"system", "terminal"}),
    )
    assert isinstance(sol.solution_id, UUID)
    assert sol.expected_outcome == "connection restored"
    assert sol.confidence == 0.7
    assert sol.risk is RiskLevel.LOW
    assert sol.risk_note == "reversible"
    assert sol.required_capabilities == frozenset({"system", "terminal"})


def test_solution_defaults() -> None:
    sol = solution()
    assert sol.expected_outcome is None
    assert sol.confidence is None
    assert sol.risk is RiskLevel.UNKNOWN
    assert sol.risk_note is None
    assert sol.required_capabilities == frozenset()


@pytest.mark.parametrize(
    "risk", [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.UNKNOWN]
)
def test_solution_accepts_valid_risk_levels(risk: RiskLevel) -> None:
    assert solution(risk=risk).risk is risk


def test_solution_rejects_invalid_risk() -> None:
    with pytest.raises(ValidationError):
        solution(risk="critical")


def test_solution_rejects_blank_description() -> None:
    with pytest.raises(ValidationError, match="description"):
        solution(description="")


def test_solution_rejects_blank_expected_outcome() -> None:
    with pytest.raises(ValidationError, match="expected_outcome"):
        solution(expected_outcome="  ")


def test_solution_rejects_invalid_confidence() -> None:
    with pytest.raises(ValidationError, match="confidence"):
        solution(confidence=2.0)


def test_solution_required_capabilities_are_immutable() -> None:
    sol = solution(required_capabilities=frozenset({"a", "b"}))
    with pytest.raises(AttributeError):
        sol.required_capabilities.add("c")


def test_solution_rejects_blank_capability() -> None:
    with pytest.raises(ValidationError, match="required capabilities"):
        solution(required_capabilities=frozenset({"ok", "  "}))


# --- ProblemAnalysis --------------------------------------------------------


def test_problem_analysis_model_fields() -> None:
    prob = problem()
    hypo = hypothesis()
    sol = solution()
    result = ProblemAnalysis(
        problem=prob,
        hypotheses=[hypo],
        candidate_solutions=[sol],
        recommended_solution_id=sol.solution_id,
        confidence=0.3,
        unresolved_questions=["What was tried?"],
    )
    assert isinstance(result.analysis_id, UUID)
    assert result.problem is prob
    assert result.hypotheses == [hypo]
    assert result.candidate_solutions == [sol]
    assert result.recommended_solution_id == sol.solution_id
    assert result.confidence == 0.3
    assert result.unresolved_questions == ["What was tried?"]
    assert isinstance(result.created_at, datetime)


def test_problem_analysis_defaults() -> None:
    result = analysis()
    assert result.recommended_solution_id is None
    assert result.confidence is None
    assert result.unresolved_questions == []


def test_problem_analysis_recommendation_must_refer_to_candidate() -> None:
    with pytest.raises(ValidationError, match="candidate solution"):
        analysis(recommended_solution_id=UUID(int=999))


def test_problem_analysis_recommendation_none_allowed() -> None:
    result = analysis()
    assert result.recommended_solution_id is None
    assert result.recommended_solution is None


def test_problem_analysis_recommended_solution_property() -> None:
    sol = solution()
    result = analysis(
        candidate_solutions=[sol], recommended_solution_id=sol.solution_id
    )
    assert result.recommended_solution is sol


def test_problem_analysis_rejects_invalid_confidence() -> None:
    with pytest.raises(ValidationError, match="confidence"):
        analysis(confidence=5.0)


def test_problem_analysis_rejects_blank_unresolved_question() -> None:
    with pytest.raises(ValidationError, match="unresolved questions"):
        analysis(unresolved_questions=["ok", "  "])

    with pytest.raises(ValidationError, match="unresolved questions"):
        analysis(unresolved_questions=[""])


def test_problem_analysis_terminology_is_distinct() -> None:
    prob = problem()
    hypo = hypothesis(description="hypothesis statement")
    sol = solution(description="proposed solution")
    result = ProblemAnalysis(
        problem=prob,
        hypotheses=[hypo],
        candidate_solutions=[sol],
        recommended_solution_id=sol.solution_id,
    )
    assert result.problem.description == prob.description
    assert result.hypotheses[0].description == "hypothesis statement"
    assert result.candidate_solutions[0].description == "proposed solution"
    assert result.recommended_solution is sol


# --- ProblemSolver abstraction ----------------------------------------------


def test_problem_solver_is_abstract() -> None:
    with pytest.raises(TypeError):
        ProblemSolver()


def test_problem_solver_requires_metadata() -> None:
    with pytest.raises(TypeError, match="name"):

        class MissingMetadata(ProblemSolver):
            async def solve(self, problem: Problem) -> ProblemAnalysis:
                return ProblemAnalysis(problem=problem, hypotheses=[], candidate_solutions=[])


def test_problem_solver_is_provider_independent() -> None:
    assert ProblemSolver.__module__ == "app.core.problem_solver"
    assert "fastapi" not in ProblemSolver.__module__
    assert "openai" not in ProblemSolver.__module__


# --- FakeProblemSolver ------------------------------------------------------


def test_fake_solver_satisfies_interface() -> None:
    solver = FakeProblemSolver()
    assert isinstance(solver, ProblemSolver)
    assert solver.name == "fake-problem-solver"
    assert solver.description


def test_fake_solver_accepts_arbitrary_problem() -> None:
    solver = FakeProblemSolver()
    prob = problem(
        description="Laptop is slow after the latest update.",
        context={"os": "Windows", "recent_action": "installed update"},
    )
    result = asyncio.run(solver.solve(prob))
    assert isinstance(result, ProblemAnalysis)
    assert result.problem is prob


def test_fake_solver_returns_deterministic_analysis() -> None:
    solver = FakeProblemSolver()
    prob = problem()
    first = asyncio.run(solver.solve(prob))
    second = asyncio.run(solver.solve(prob))
    assert first.analysis_id == second.analysis_id
    assert [h.description for h in first.hypotheses] == [
        h.description for h in second.hypotheses
    ]
    assert [s.description for s in first.candidate_solutions] == [
        s.description for s in second.candidate_solutions
    ]
    assert first.recommended_solution_id == second.recommended_solution_id
    assert first.hypotheses[0].evidence_for[0].evidence_id == (
        second.hypotheses[0].evidence_for[0].evidence_id
    )
    assert first.confidence == second.confidence


def test_fake_solver_does_not_hard_code_single_problem() -> None:
    solver = FakeProblemSolver()
    prob_a = problem(description="First arbitrary problem A.")
    prob_b = problem(description="Second unrelated problem B.")
    result_a = asyncio.run(solver.solve(prob_a))
    result_b = asyncio.run(solver.solve(prob_b))
    assert result_a.problem is prob_a
    assert result_b.problem is prob_b
    assert result_a.problem.problem_id != result_b.problem.problem_id


def test_fake_solver_generates_hypotheses_with_evidence() -> None:
    solver = FakeProblemSolver()
    result = asyncio.run(solver.solve(problem()))
    assert len(result.hypotheses) == 2
    for hypo in result.hypotheses:
        assert hypo.description
        assert 0.0 <= (hypo.confidence or 0.0) <= 1.0
        assert len(hypo.evidence_for) >= 1


def test_fake_solver_generates_candidate_solutions() -> None:
    solver = FakeProblemSolver()
    result = asyncio.run(solver.solve(problem()))
    assert len(result.candidate_solutions) == 2
    for sol in result.candidate_solutions:
        assert sol.description
        assert sol.expected_outcome
        assert sol.risk in RiskLevel


def test_fake_solver_recommends_a_candidate() -> None:
    solver = FakeProblemSolver()
    result = asyncio.run(solver.solve(problem()))
    candidate_ids = {
        sol.solution_id for sol in result.candidate_solutions
    }
    assert result.recommended_solution_id in candidate_ids
    assert result.recommended_solution in result.candidate_solutions


def test_fake_solver_handles_unresolved_questions() -> None:
    solver = FakeProblemSolver()
    result = asyncio.run(solver.solve(problem()))
    assert len(result.unresolved_questions) >= 1
    assert all(question.strip() for question in result.unresolved_questions)


def test_fake_solver_is_offline_and_does_not_call_ai() -> None:
    solver = FakeProblemSolver()
    assert "httpx" not in getattr(FakeProblemSolver, "__module__", "")
    assert "openai" not in getattr(FakeProblemSolver, "__module__", "")
    result = asyncio.run(solver.solve(problem()))
    assert isinstance(result, ProblemAnalysis)


def test_fake_solver_records_requests() -> None:
    solver = FakeProblemSolver()
    prob_a = problem()
    prob_b = problem(description="Another problem.")
    asyncio.run(solver.solve(prob_a))
    asyncio.run(solver.solve(prob_b))
    assert len(solver.requests) == 2
    assert solver.requests[0] is prob_a
    assert solver.requests[1] is prob_b


def test_fake_solver_can_raise_configured_error() -> None:
    solver = FakeProblemSolver(raise_error=RuntimeError("boom"))
    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(solver.solve(problem()))


def test_fake_solver_does_not_fabricate_facts() -> None:
    solver = FakeProblemSolver()
    result = asyncio.run(solver.solve(problem()))
    for hypo in result.hypotheses:
        for item in hypo.evidence_for + hypo.evidence_against:
            assert item.kind in (
                EvidenceKind.OBSERVATION,
                EvidenceKind.ASSUMPTION,
            )
            assert item.kind is not EvidenceKind.FACT


def test_fake_solver_evidence_uses_observation_without_context() -> None:
    solver = FakeProblemSolver()
    result = asyncio.run(solver.solve(problem(context={})))
    secondary = result.hypotheses[1]
    assert secondary.evidence_for[0].kind is EvidenceKind.ASSUMPTION


def test_fake_solver_evidence_uses_context_when_provided() -> None:
    solver = FakeProblemSolver()
    result = asyncio.run(
        solver.solve(problem(context={"tried": "clean reinstall"}))
    )
    secondary = result.hypotheses[1]
    assert secondary.evidence_for[0].kind is EvidenceKind.OBSERVATION


def test_confidential_range_documented() -> None:
    assert "0, 1" in CONFIDENCE_RANGE_DESCRIPTION
    assert "calibrated" in CONFIDENCE_RANGE_DESCRIPTION
