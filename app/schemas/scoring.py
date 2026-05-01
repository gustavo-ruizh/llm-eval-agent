from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, field_validator

from .planner import EvaluationPlan


class ScoreJustification(BaseModel):
    summary: str
    supporting_evidence: List[str]
    unsupported_claims: List[str]
    missing_items: List[str]


class DimensionScore(BaseModel):
    dimension_name: str
    dimension_type: Literal["core", "case_specific"]
    risk_weight: Literal["low", "medium", "high"]
    score: float
    score_band: str
    justification: ScoreJustification
    confidence: Literal["low", "medium", "high"]

    @field_validator("score")
    @classmethod
    def score_in_range(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("score must be between 0.0 and 1.0")
        return v

    @field_validator("score_band", mode="before")
    @classmethod
    def derive_score_band(cls, v: str, info) -> str:
        score = info.data.get("score")
        if score is None:
            return v
        if score <= 0.20:
            return "poor"
        if score <= 0.40:
            return "weak"
        if score <= 0.60:
            return "acceptable"
        if score <= 0.80:
            return "strong"
        return "excellent"


class QualityScoringInput(BaseModel):
    source_document: str
    llm_output: str
    evaluation_plan: EvaluationPlan


class QualityScoringOutput(BaseModel):
    scores: List[DimensionScore]
    overall_score: float
    scoring_notes: Optional[str] = None
    requires_human_review: bool
