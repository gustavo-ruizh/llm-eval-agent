from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel

from .diagnosis import FailureDiagnosisOutput
from .evaluation import FailureCategory
from .planner import EvaluationPlan
from .scoring import QualityScoringOutput

ExperimentType = Literal[
    "prompt_change",
    "retrieval_tuning",
    "model_comparison",
    "human_review_threshold",
    "evaluation_set_expansion",
    "output_schema_change",
    "source_chunking_review",
]


class SuccessCriterion(BaseModel):
    metric_name: str
    baseline_value: Optional[float] = None
    target_value: float
    comparison_type: Literal["absolute", "relative_improvement", "threshold"]
    measurement_method: str


class Experiment(BaseModel):
    experiment_id: str
    linked_failure_category: FailureCategory
    linked_diagnosis_type: Literal["observed_failure", "hypothesized_root_cause"]
    validates_failure_mode: str
    experiment_type: ExperimentType
    scope: Literal["prompt_only", "retrieval_only", "model_only", "schema_only", "hybrid"]
    priority: Literal["low", "medium", "high", "critical"]
    effort: Literal["low", "medium", "high"]
    status: Literal["recommended", "requires_more_evidence"]
    depends_on_experiment_id: Optional[str] = None
    baseline_reference: Optional[str] = None
    diagnostic_goal: Optional[str] = None
    recommendation: str
    test_design: str
    expected_outcome: str
    success_criteria: List[SuccessCriterion]
    risk_if_not_done: str


class ExperimentRecommendationInput(BaseModel):
    failure_diagnosis_output: FailureDiagnosisOutput
    evaluation_plan: EvaluationPlan
    quality_scoring_output: QualityScoringOutput
    product_context: Optional[str] = None
    baseline_reference: Optional[str] = None


class ExperimentRecommendationOutput(BaseModel):
    experiments: List[Experiment]
    top_priority_experiment_id: Optional[str] = None
    recommendation_notes: Optional[str] = None
