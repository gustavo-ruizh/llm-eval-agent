import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.core.orchestrator import EvaluationOrchestrator
from app.schemas.api import EvaluationRequest, EvaluationResponse
from app.schemas.orchestration import EvaluationRunInput
from app.storage.repository import EvaluationRunRepository

logger = logging.getLogger(__name__)
router = APIRouter()

_orchestrator = EvaluationOrchestrator()
_repository = EvaluationRunRepository()


def _build_response(result, include_full_result: bool) -> EvaluationResponse:
    requires_human_review: Optional[bool] = None
    if result.quality_scoring_output is not None:
        requires_human_review = result.quality_scoring_output.requires_human_review

    primary_failure_mode: Optional[str] = None
    if result.failure_diagnosis_output is not None:
        primary_failure_mode = result.failure_diagnosis_output.primary_failure_mode

    recommended_next_experiment_id: Optional[str] = None
    if result.experiment_recommendation_output is not None:
        recommended_next_experiment_id = result.experiment_recommendation_output.top_priority_experiment_id

    error_dict = None
    if result.error is not None:
        error_dict = result.error.model_dump()

    full_result = None
    if include_full_result:
        full_result = result.model_dump(mode="json")

    return EvaluationResponse(
        run_id=result.run_id,
        timestamp=result.timestamp,
        execution_time_ms=result.execution_time_ms,
        final_summary=result.final_summary,
        baseline_reference=result.baseline_reference,
        requires_human_review=requires_human_review,
        primary_failure_mode=primary_failure_mode,
        recommended_next_experiment_id=recommended_next_experiment_id,
        error=error_dict,
        full_result=full_result,
    )


@router.post("/evaluations", response_model=EvaluationResponse, status_code=201)
def create_evaluation(
    request: EvaluationRequest,
    include_full_result: bool = Query(default=True),
) -> EvaluationResponse:
    run_input = EvaluationRunInput(
        source_document=request.source_document,
        llm_output=request.llm_output,
        user_goal=request.user_goal,
        source_document_type=request.source_document_type,
        task_type=request.task_type,
        expected_output_format=request.expected_output_format,
        business_context=request.business_context,
        risk_level=request.risk_level,
        baseline_reference=request.baseline_reference,
        retrieval_metadata_available=request.retrieval_metadata_available,
        retrieval_metadata=request.retrieval_metadata,
        prompt_version=request.prompt_version,
        model_version=request.model_version,
    )

    result = _orchestrator.run(run_input)
    _repository.save(result)
    logger.info("POST /evaluations run_id=%s stored", result.run_id)
    return _build_response(result, include_full_result)


@router.get("/evaluations/{run_id}", response_model=EvaluationResponse)
def get_evaluation(
    run_id: str,
    include_full_result: bool = Query(default=True),
) -> EvaluationResponse:
    result = _repository.get(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Evaluation run '{run_id}' not found")
    logger.info("GET /evaluations/%s retrieved", run_id)
    return _build_response(result, include_full_result)


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}
