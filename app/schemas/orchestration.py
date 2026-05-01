from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel

from .diagnosis import FailureDiagnosisOutput
from .evaluation import TaskType
from .experiments import ExperimentRecommendationOutput
from .planner import EvaluationPlan
from .scoring import QualityScoringOutput


class EvaluationRunInput(BaseModel):
    source_document: str
    llm_output: str
    user_goal: str
    source_document_type: Optional[str] = None
    task_type: TaskType = "unknown"
    expected_output_format: Optional[str] = None
    business_context: Optional[str] = None
    risk_level: Literal["low", "medium", "high"] = "medium"
    baseline_reference: Optional[str] = None
    retrieval_metadata_available: bool = False
    retrieval_metadata: Optional[Dict[str, Any]] = None
    prompt_version: Optional[str] = None
    model_version: Optional[str] = None


class EvaluationPipelineError(BaseModel):
    error_stage: Literal["planner", "scorer", "diagnosis", "experiment"]
    error_message: str


class EvaluationRunOutput(BaseModel):
    run_id: str
    timestamp: str
    execution_time_ms: int
    evaluation_plan: Optional[EvaluationPlan] = None
    quality_scoring_output: Optional[QualityScoringOutput] = None
    failure_diagnosis_output: Optional[FailureDiagnosisOutput] = None
    experiment_recommendation_output: Optional[ExperimentRecommendationOutput] = None
    baseline_reference: Optional[str] = None
    final_summary: str
    execution_trace: List[str]
    error: Optional[EvaluationPipelineError] = None
