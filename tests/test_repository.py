"""
Tests for EvaluationRunRepository: save, get, and round-trip fidelity.
Uses an in-memory SQLite path (:memory:) via a temp file.
"""

import os
import tempfile

import pytest

from app.storage.repository import EvaluationRunRepository
from app.schemas.orchestration import EvaluationRunOutput, EvaluationPipelineError


def _make_minimal_result(run_id: str = "eval_test001") -> EvaluationRunOutput:
    return EvaluationRunOutput(
        run_id=run_id,
        timestamp="2026-01-01T00:00:00+00:00",
        execution_time_ms=123,
        evaluation_plan=None,
        quality_scoring_output=None,
        failure_diagnosis_output=None,
        experiment_recommendation_output=None,
        baseline_reference="baseline_v1",
        final_summary="Test summary.",
        execution_trace=["planner:start", "planner:success"],
        error=None,
    )


@pytest.fixture()
def tmp_repo():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    repo = EvaluationRunRepository(db_path=db_path)
    yield repo
    os.unlink(db_path)


def test_save_and_get_round_trip(tmp_repo):
    result = _make_minimal_result()
    tmp_repo.save(result)
    retrieved = tmp_repo.get(result.run_id)

    assert retrieved is not None
    assert retrieved.run_id == result.run_id
    assert retrieved.final_summary == result.final_summary
    assert retrieved.baseline_reference == result.baseline_reference
    assert retrieved.execution_time_ms == result.execution_time_ms
    assert retrieved.execution_trace == result.execution_trace


def test_get_nonexistent_returns_none(tmp_repo):
    result = tmp_repo.get("eval_doesnotexist")
    assert result is None


def test_save_overwrites_existing(tmp_repo):
    original = _make_minimal_result()
    tmp_repo.save(original)

    updated = EvaluationRunOutput(
        run_id=original.run_id,
        timestamp=original.timestamp,
        execution_time_ms=999,
        baseline_reference=original.baseline_reference,
        final_summary="Updated summary.",
        execution_trace=original.execution_trace,
        error=None,
    )
    tmp_repo.save(updated)

    retrieved = tmp_repo.get(original.run_id)
    assert retrieved is not None
    assert retrieved.execution_time_ms == 999
    assert retrieved.final_summary == "Updated summary."


def test_retrieved_result_is_pydantic_model(tmp_repo):
    result = _make_minimal_result()
    tmp_repo.save(result)
    retrieved = tmp_repo.get(result.run_id)

    assert isinstance(retrieved, EvaluationRunOutput)


def test_save_result_with_error(tmp_repo):
    result = _make_minimal_result()
    result = result.model_copy(
        update={
            "error": EvaluationPipelineError(
                error_stage="planner",
                error_message="Something went wrong",
            )
        }
    )
    tmp_repo.save(result)
    retrieved = tmp_repo.get(result.run_id)

    assert retrieved is not None
    assert retrieved.error is not None
    assert retrieved.error.error_stage == "planner"
    assert retrieved.error.error_message == "Something went wrong"
