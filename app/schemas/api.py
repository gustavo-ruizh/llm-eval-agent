from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, field_validator

from .evaluation import TaskType


class EvaluationRequest(BaseModel):
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

    @field_validator("source_document")
    @classmethod
    def source_document_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("source_document cannot be empty")
        return v

    @field_validator("llm_output")
    @classmethod
    def llm_output_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("llm_output cannot be empty")
        return v

    @field_validator("user_goal")
    @classmethod
    def user_goal_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("user_goal cannot be empty")
        return v


class EvaluationResponse(BaseModel):
    run_id: str
    timestamp: str
    execution_time_ms: int
    final_summary: str
    baseline_reference: Optional[str] = None
    requires_human_review: Optional[bool] = None
    primary_failure_mode: Optional[str] = None
    recommended_next_experiment_id: Optional[str] = None
    error: Optional[Dict[str, Any]] = None
    full_result: Optional[Dict[str, Any]] = None
