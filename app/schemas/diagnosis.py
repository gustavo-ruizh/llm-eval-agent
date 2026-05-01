from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel

from .evaluation import FailureCategory
from .planner import EvaluationPlan
from .scoring import QualityScoringOutput


class RootCauseDiagnosis(BaseModel):
    diagnosis_type: Literal["observed_failure", "hypothesized_root_cause"]
    failure_category: FailureCategory
    severity: Literal["low", "medium", "high", "critical"]
    root_cause_summary: str
    supporting_evidence: List[str]
    confidence: Literal["low", "medium", "high"]
    evidence_needed: Optional[str] = None
    recommended_experiment_signals: List[str]


class FailureDiagnosisInput(BaseModel):
    quality_scoring_output: QualityScoringOutput
    evaluation_plan: EvaluationPlan
    retrieval_metadata_available: bool
    retrieval_metadata: Optional[Dict[str, Any]] = None
    prompt_version: Optional[str] = None
    model_version: Optional[str] = None


class FailureDiagnosisOutput(BaseModel):
    diagnoses: List[RootCauseDiagnosis]
    primary_failure_mode: Optional[str] = None
    diagnosis_notes: Optional[str] = None
