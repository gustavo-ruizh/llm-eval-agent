import json
import logging
import uuid
from typing import List, Optional

from app.core.llm_client import LLMClient
from app.schemas.diagnosis import RootCauseDiagnosis
from app.schemas.experiments import (
    Experiment,
    ExperimentRecommendationInput,
    ExperimentRecommendationOutput,
    ExperimentType,
    SuccessCriterion,
)

logger = logging.getLogger(__name__)

_SEVERITY_SCORE = {"critical": 4, "high": 3, "medium": 2, "low": 1}
_DIAGNOSIS_TYPE_SCORE = {"observed_failure": 2, "hypothesized_root_cause": 1}
_CONFIDENCE_SCORE = {"high": 3, "medium": 2, "low": 1}
_EFFORT_PENALTY = {"low": 0, "medium": 1, "high": 2}

_CATEGORY_TO_EXPERIMENT_TYPE: dict = {
    "hallucination_or_unsupported_claims": "prompt_change",
    "missing_information": "prompt_change",
    "incomplete_extraction": "output_schema_change",
    "misinterpretation_of_source": "prompt_change",
    "poor_prompt_alignment": "prompt_change",
    "retrieval_issues": "retrieval_tuning",
    "model_limitation": "model_comparison",
    "output_formatting_issues": "output_schema_change",
}

_CATEGORY_TO_SCOPE: dict = {
    "hallucination_or_unsupported_claims": "prompt_only",
    "missing_information": "prompt_only",
    "incomplete_extraction": "schema_only",
    "misinterpretation_of_source": "prompt_only",
    "poor_prompt_alignment": "prompt_only",
    "retrieval_issues": "retrieval_only",
    "model_limitation": "model_only",
    "output_formatting_issues": "schema_only",
}


def _compute_priority_score(diag: RootCauseDiagnosis, effort: str) -> int:
    return (
        _SEVERITY_SCORE.get(diag.severity, 1)
        + _DIAGNOSIS_TYPE_SCORE.get(diag.diagnosis_type, 1)
        + _CONFIDENCE_SCORE.get(diag.confidence, 1)
        - _EFFORT_PENALTY.get(effort, 0)
    )


def _priority_band(score: int) -> str:
    if score >= 8:
        return "critical"
    if score >= 6:
        return "high"
    if score >= 4:
        return "medium"
    return "low"


class ExperimentRecommendationAgent:
    def __init__(self) -> None:
        self._llm = LLMClient()

    def run(self, input_data: ExperimentRecommendationInput) -> ExperimentRecommendationOutput:
        diagnoses = input_data.failure_diagnosis_output.diagnoses
        if not diagnoses:
            logger.info("ExperimentRecommendationAgent: no diagnoses, returning empty recommendation")
            return ExperimentRecommendationOutput(
                experiments=[],
                top_priority_experiment_id=None,
                recommendation_notes="No failure modes detected; no experiments recommended.",
            )

        logger.info("ExperimentRecommendationAgent: generating experiments for %d diagnoses", len(diagnoses))
        try:
            prompt = self._build_prompt(input_data)
            output = self._llm.generate_json(prompt, ExperimentRecommendationOutput)
            output = self._enforce_hypothesis_rules(output)
            output = self._select_top_priority(output)
            logger.info("ExperimentRecommendationAgent: LLM experiments generated")
            return output
        except Exception as exc:
            logger.warning("ExperimentRecommendationAgent: falling back to deterministic experiments — %s", exc)
            return self._deterministic_fallback(input_data)

    def _build_prompt(self, input_data: ExperimentRecommendationInput) -> str:
        diagnoses_json = json.dumps(
            [
                {
                    "diagnosis_type": d.diagnosis_type,
                    "failure_category": d.failure_category,
                    "severity": d.severity,
                    "root_cause_summary": d.root_cause_summary,
                    "confidence": d.confidence,
                    "evidence_needed": d.evidence_needed,
                    "recommended_experiment_signals": d.recommended_experiment_signals,
                }
                for d in input_data.failure_diagnosis_output.diagnoses
            ],
            indent=2,
        )
        return f"""You are an LLM experimentation design expert.

## Failure Diagnoses
{diagnoses_json}

## Context
- user_goal: {input_data.evaluation_plan.user_goal}
- task_type: {input_data.evaluation_plan.task_type}
- product_context: {input_data.product_context or "not provided"}
- baseline_reference: {input_data.baseline_reference or "not provided"}
- overall_score: {input_data.quality_scoring_output.overall_score:.2f}

## Experiment Design Rules
1. Each experiment must link to exactly one diagnosis.
2. Isolate one variable per experiment where possible.
3. Low-confidence hypothesized_root_cause → status = "requires_more_evidence", set diagnostic_goal.
4. Observed failures with high/medium confidence → status = "recommended".
5. Use depends_on_experiment_id for sequentially dependent experiments.
6. Include measurable success_criteria with baseline and target values.

## Experiment Types Available
prompt_change | retrieval_tuning | model_comparison | human_review_threshold |
evaluation_set_expansion | output_schema_change | source_chunking_review

## Priority Formula
priority_score = severity_score + diagnosis_type_score + confidence_score - effort_penalty
severity: critical=4, high=3, medium=2, low=1
diagnosis_type: observed_failure=2, hypothesized_root_cause=1
confidence: high=3, medium=2, low=1
effort: low=0, medium=-1, high=-2
Priority bands: >=8 critical | >=6 high | >=4 medium | else low

## Required JSON Schema
{{
  "experiments": [
    {{
      "experiment_id": "<exp_001, exp_002, etc.>",
      "linked_failure_category": "<failure_category from diagnosis>",
      "linked_diagnosis_type": "<observed_failure|hypothesized_root_cause>",
      "validates_failure_mode": "<what failure mode this tests>",
      "experiment_type": "<one of experiment types>",
      "scope": "<prompt_only|retrieval_only|model_only|schema_only|hybrid>",
      "priority": "<low|medium|high|critical>",
      "effort": "<low|medium|high>",
      "status": "<recommended|requires_more_evidence>",
      "depends_on_experiment_id": "<experiment_id or null>",
      "baseline_reference": "<baseline or null>",
      "diagnostic_goal": "<goal for hypothesis experiments>",
      "recommendation": "<what to do>",
      "test_design": "<how to run the experiment>",
      "expected_outcome": "<what improvement is expected>",
      "success_criteria": [
        {{
          "metric_name": "<metric>",
          "baseline_value": <number or null>,
          "target_value": <number>,
          "comparison_type": "<absolute|relative_improvement|threshold>",
          "measurement_method": "<how to measure>"
        }}
      ],
      "risk_if_not_done": "<what happens if this is skipped>"
    }}
  ],
  "top_priority_experiment_id": "<experiment_id of highest priority>",
  "recommendation_notes": "<optional notes>"
}}

Return ONLY the JSON object."""

    def _enforce_hypothesis_rules(
        self, output: ExperimentRecommendationOutput
    ) -> ExperimentRecommendationOutput:
        for exp in output.experiments:
            if exp.linked_diagnosis_type == "hypothesized_root_cause" and exp.linked_failure_category == "retrieval_issues":
                if exp.status != "requires_more_evidence":
                    object.__setattr__(exp, "status", "requires_more_evidence")
        return output

    def _select_top_priority(self, output: ExperimentRecommendationOutput) -> ExperimentRecommendationOutput:
        if not output.experiments:
            return output
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        top = min(output.experiments, key=lambda e: priority_order.get(e.priority, 9))
        return ExperimentRecommendationOutput(
            experiments=output.experiments,
            top_priority_experiment_id=top.experiment_id,
            recommendation_notes=output.recommendation_notes,
        )

    def _deterministic_fallback(
        self, input_data: ExperimentRecommendationInput
    ) -> ExperimentRecommendationOutput:
        experiments: List[Experiment] = []
        seen_categories = set()

        for idx, diag in enumerate(input_data.failure_diagnosis_output.diagnoses):
            if diag.failure_category in seen_categories:
                continue
            seen_categories.add(diag.failure_category)

            exp_type: ExperimentType = _CATEGORY_TO_EXPERIMENT_TYPE.get(
                diag.failure_category, "prompt_change"
            )
            scope = _CATEGORY_TO_SCOPE.get(diag.failure_category, "prompt_only")
            effort = "medium" if exp_type in ("model_comparison", "retrieval_tuning") else "low"
            priority_score = _compute_priority_score(diag, effort)
            priority = _priority_band(priority_score)
            status = (
                "requires_more_evidence"
                if diag.diagnosis_type == "hypothesized_root_cause" and diag.confidence == "low"
                else "recommended"
            )
            exp_id = f"exp_{idx + 1:03d}"

            experiments.append(
                Experiment(
                    experiment_id=exp_id,
                    linked_failure_category=diag.failure_category,
                    linked_diagnosis_type=diag.diagnosis_type,
                    validates_failure_mode=diag.failure_category,
                    experiment_type=exp_type,
                    scope=scope,
                    priority=priority,
                    effort=effort,
                    status=status,
                    depends_on_experiment_id=None,
                    baseline_reference=input_data.baseline_reference,
                    diagnostic_goal=(
                        diag.evidence_needed
                        if diag.diagnosis_type == "hypothesized_root_cause"
                        else None
                    ),
                    recommendation=(
                        f"Address '{diag.failure_category}' detected in evaluation. "
                        "Generated using deterministic fallback because LLM call failed."
                    ),
                    test_design=(
                        f"Run a controlled {exp_type.replace('_', ' ')} experiment targeting "
                        f"the '{diag.failure_category}' failure mode. "
                        f"Compare against baseline on the same evaluation set."
                    ),
                    expected_outcome=f"Improvement in dimensions related to {diag.failure_category}.",
                    success_criteria=[
                        SuccessCriterion(
                            metric_name=f"{diag.failure_category}_score",
                            baseline_value=None,
                            target_value=0.75,
                            comparison_type="threshold",
                            measurement_method="Re-run evaluation pipeline after intervention.",
                        )
                    ],
                    risk_if_not_done=(
                        f"The '{diag.failure_category}' failure mode may persist in production, "
                        f"with severity: {diag.severity}."
                    ),
                )
            )

        if not experiments:
            top_id = None
        else:
            priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            top = min(experiments, key=lambda e: priority_order.get(e.priority, 9))
            top_id = top.experiment_id

        return ExperimentRecommendationOutput(
            experiments=experiments,
            top_priority_experiment_id=top_id,
            recommendation_notes="Generated using deterministic fallback because LLM call failed.",
        )
