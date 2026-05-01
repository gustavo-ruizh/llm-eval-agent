from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel

from .evaluation import EvaluationIntent, ProductDecisionUse, TaskType


class ScoringGuidance(BaseModel):
    low_score_meaning: str
    high_score_meaning: str
    concrete_failure_example: str


class EvaluationDimension(BaseModel):
    name: str
    type: Literal["core", "case_specific"]
    description: str
    rationale: str
    product_decision_use: ProductDecisionUse
    scoring_guidance: ScoringGuidance


class DownstreamContract(BaseModel):
    primary_risk_dimensions: List[str]
    requires_human_review_if_below: float = 0.60
    notes: Optional[str] = None


class EvaluationPlannerInput(BaseModel):
    source_document_type: Optional[str] = None
    task_type: TaskType
    user_goal: str
    expected_output_format: Optional[str] = None
    business_context: Optional[str] = None
    risk_level: Literal["low", "medium", "high"]


class EvaluationPlan(BaseModel):
    evaluation_intent: EvaluationIntent
    task_type: TaskType
    user_goal: str
    selected_dimensions: List[EvaluationDimension]
    excluded_dimensions: List[str]
    downstream_contract: DownstreamContract
    evaluation_notes: Optional[str] = None
