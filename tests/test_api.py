"""
Tests for the FastAPI layer using TestClient.
LLMClient is patched to force deterministic fallback behavior.
"""

import os
import tempfile
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


_SAMPLE_PAYLOAD = {
    "source_document": (
        "The lease agreement is effective January 1, 2024. "
        "Monthly rent is $2,500 due on the 1st. "
        "Tenant must provide 60 days written notice before vacating."
    ),
    "llm_output": (
        "Lease starts January 1, 2024. Rent: $2,500/month. "
        "60-day notice required before vacating."
    ),
    "user_goal": "Confirm the lease summary is accurate for tenant communication.",
    "task_type": "summary",
    "risk_level": "medium",
    "model_version": "gpt-4.1-mini",
}


@pytest.fixture(autouse=True)
def patch_llm_and_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    with (
        patch("app.core.llm_client.LLMClient.generate_json", side_effect=Exception("mocked")),
        patch("app.storage.repository.settings") as mock_settings,
        patch("app.api.routes._repository") as mock_repo,
    ):
        from app.storage.repository import EvaluationRunRepository
        real_repo = EvaluationRunRepository(db_path=db_path)
        mock_repo.save.side_effect = real_repo.save
        mock_repo.get.side_effect = real_repo.get
        yield


@pytest.fixture()
def client():
    return TestClient(app)


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_evaluation_returns_201(client):
    response = client.post("/evaluations", json=_SAMPLE_PAYLOAD)
    assert response.status_code == 201


def test_create_evaluation_response_fields_always_present(client):
    response = client.post("/evaluations", json=_SAMPLE_PAYLOAD)
    assert response.status_code == 201
    data = response.json()

    required_fields = [
        "run_id",
        "timestamp",
        "execution_time_ms",
        "final_summary",
        "baseline_reference",
        "requires_human_review",
        "primary_failure_mode",
        "recommended_next_experiment_id",
        "error",
        "full_result",
    ]
    for field in required_fields:
        assert field in data, f"Missing field: {field}"


def test_create_evaluation_exclude_full_result(client):
    response = client.post("/evaluations?include_full_result=false", json=_SAMPLE_PAYLOAD)
    assert response.status_code == 201
    data = response.json()
    assert data["full_result"] is None


def test_create_evaluation_include_full_result(client):
    response = client.post("/evaluations?include_full_result=true", json=_SAMPLE_PAYLOAD)
    assert response.status_code == 201
    data = response.json()
    assert data["full_result"] is not None
    assert "run_id" in data["full_result"]


def test_get_evaluation_not_found(client):
    response = client.get("/evaluations/eval_doesnotexist")
    assert response.status_code == 404


def test_create_then_retrieve(client):
    create_response = client.post("/evaluations", json=_SAMPLE_PAYLOAD)
    assert create_response.status_code == 201
    run_id = create_response.json()["run_id"]

    get_response = client.get(f"/evaluations/{run_id}")
    assert get_response.status_code == 200
    assert get_response.json()["run_id"] == run_id


def test_empty_source_document_rejected(client):
    payload = {**_SAMPLE_PAYLOAD, "source_document": "   "}
    response = client.post("/evaluations", json=payload)
    assert response.status_code == 422


def test_empty_llm_output_rejected(client):
    payload = {**_SAMPLE_PAYLOAD, "llm_output": ""}
    response = client.post("/evaluations", json=payload)
    assert response.status_code == 422


def test_run_id_has_eval_prefix(client):
    response = client.post("/evaluations", json=_SAMPLE_PAYLOAD)
    assert response.status_code == 201
    assert response.json()["run_id"].startswith("eval_")
