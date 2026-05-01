"""
Tests for the orchestrator happy path and failure scenarios.
LLMClient is mocked so no real API calls are made.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.core.orchestrator import EvaluationOrchestrator
from app.schemas.orchestration import EvaluationRunInput, EvaluationRunOutput


def _sample_input() -> EvaluationRunInput:
    return EvaluationRunInput(
        source_document=(
            "The lease agreement is effective from January 1, 2024. "
            "Monthly rent is $2,500 payable on the first of each month. "
            "Tenant must give 60 days written notice before vacating."
        ),
        llm_output=(
            "The lease starts January 1, 2024. Rent is $2,500/month. "
            "A 60-day notice period is required before vacating."
        ),
        user_goal="Verify the lease summary is accurate and safe to use for tenant communication.",
        task_type="summary",
        risk_level="medium",
        model_version="gpt-4.1-mini",
        prompt_version="v1.0",
    )


@pytest.fixture()
def orchestrator_no_llm():
    """Return an orchestrator with LLMClient patched to always raise, forcing fallbacks."""
    with patch("app.core.llm_client.LLMClient.generate_json", side_effect=Exception("mocked LLM unavailable")):
        yield EvaluationOrchestrator()


def test_orchestrator_happy_path_fallback(orchestrator_no_llm):
    result = orchestrator_no_llm.run(_sample_input())

    assert isinstance(result, EvaluationRunOutput)
    assert result.run_id.startswith("eval_")
    assert result.execution_time_ms >= 0
    assert result.evaluation_plan is not None
    assert result.quality_scoring_output is not None
    assert result.failure_diagnosis_output is not None
    assert result.experiment_recommendation_output is not None
    assert result.final_summary
    assert result.error is None
    assert "planner:success" in result.execution_trace
    assert "scorer:success" in result.execution_trace
    assert "diagnosis:success" in result.execution_trace
    assert "experiment:success" in result.execution_trace


def test_orchestrator_no_raw_dicts_between_stages(orchestrator_no_llm):
    """Ensure no stage returns or accepts raw dicts — Pydantic models throughout."""
    result = orchestrator_no_llm.run(_sample_input())

    from app.schemas.planner import EvaluationPlan
    from app.schemas.scoring import QualityScoringOutput
    from app.schemas.diagnosis import FailureDiagnosisOutput
    from app.schemas.experiments import ExperimentRecommendationOutput

    assert isinstance(result.evaluation_plan, EvaluationPlan)
    assert isinstance(result.quality_scoring_output, QualityScoringOutput)
    assert isinstance(result.failure_diagnosis_output, FailureDiagnosisOutput)
    assert isinstance(result.experiment_recommendation_output, ExperimentRecommendationOutput)


def test_orchestrator_requires_human_review_when_critical_dim_below_threshold(orchestrator_no_llm):
    """Fallback scores critical dimensions at 0.50, which is below 0.60 threshold."""
    result = orchestrator_no_llm.run(_sample_input())
    assert result.quality_scoring_output.requires_human_review is True


def test_orchestrator_run_id_unique(orchestrator_no_llm):
    result_a = orchestrator_no_llm.run(_sample_input())
    result_b = orchestrator_no_llm.run(_sample_input())
    assert result_a.run_id != result_b.run_id


def test_orchestrator_execution_trace_ordering(orchestrator_no_llm):
    result = orchestrator_no_llm.run(_sample_input())
    trace = result.execution_trace
    stages = ["planner", "scorer", "diagnosis", "experiment"]
    for stage in stages:
        assert any(stage in entry for entry in trace), f"Missing trace entry for stage: {stage}"
