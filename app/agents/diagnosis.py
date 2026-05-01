import json
import logging
from typing import List, Optional

from app.core.llm_client import LLMClient
from app.schemas.diagnosis import (
    FailureDiagnosisInput,
    FailureDiagnosisOutput,
    RootCauseDiagnosis,
)
from app.schemas.evaluation import FailureCategory
from app.schemas.scoring import DimensionScore

logger = logging.getLogger(__name__)

_DIMENSION_TO_CATEGORY: dict = {
    "Faithfulness": "hallucination_or_unsupported_claims",
    "Completeness": "missing_information",
    "Traceability": "retrieval_issues",
    "Relevance": "poor_prompt_alignment",
    "Risk / Safety": "hallucination_or_unsupported_claims",
    "Business Usefulness": "poor_prompt_alignment",
    "Information Prioritization": "poor_prompt_alignment",
    "Field Accuracy": "incomplete_extraction",
    "Format Compliance": "output_formatting_issues",
    "Answer Directness": "poor_prompt_alignment",
    "Evidence Sufficiency": "missing_information",
    "Comparative Robustness": "model_limitation",
    "Category Precision": "misinterpretation_of_source",
    "Style Consistency": "poor_prompt_alignment",
}

_OBSERVED_FAILURE_CATEGORIES = {
    "missing_information",
    "hallucination_or_unsupported_claims",
    "incomplete_extraction",
    "misinterpretation_of_source",
    "output_formatting_issues",
}


class FailureDiagnosisAgent:
    def __init__(self) -> None:
        self._llm = LLMClient()

    def run(self, input_data: FailureDiagnosisInput) -> FailureDiagnosisOutput:
        failing = self._collect_failing_scores(input_data.quality_scoring_output.scores)
        if not failing:
            logger.info("FailureDiagnosisAgent: no dimensions below threshold, skipping LLM call")
            return FailureDiagnosisOutput(
                diagnoses=[],
                primary_failure_mode=None,
                diagnosis_notes="No dimensions scored below 0.80; no significant failure modes detected.",
            )

        logger.info("FailureDiagnosisAgent: diagnosing %d failing dimensions", len(failing))
        try:
            prompt = self._build_prompt(input_data, failing)
            output = self._llm.generate_json(prompt, FailureDiagnosisOutput)
            self._enforce_retrieval_hypothesis_rule(output, input_data.retrieval_metadata_available)
            output = self._select_primary_failure_mode(output)
            logger.info("FailureDiagnosisAgent: LLM diagnosis completed")
            return output
        except Exception as exc:
            logger.warning("FailureDiagnosisAgent: falling back to deterministic diagnosis — %s", exc)
            return self._deterministic_fallback(input_data, failing)

    def _collect_failing_scores(self, scores: List[DimensionScore]) -> List[DimensionScore]:
        return [s for s in scores if s.score < 0.80]

    def _build_prompt(self, input_data: FailureDiagnosisInput, failing: List[DimensionScore]) -> str:
        failing_summary = json.dumps(
            [
                {
                    "dimension_name": s.dimension_name,
                    "score": s.score,
                    "score_band": s.score_band,
                    "justification_summary": s.justification.summary,
                    "unsupported_claims": s.justification.unsupported_claims,
                    "missing_items": s.justification.missing_items,
                }
                for s in failing
            ],
            indent=2,
        )
        return f"""You are an LLM evaluation failure diagnosis expert.

## Failing Dimensions (scored below 0.80)
{failing_summary}

## Context
- evaluation_goal: {input_data.evaluation_plan.user_goal}
- task_type: {input_data.evaluation_plan.task_type}
- retrieval_metadata_available: {input_data.retrieval_metadata_available}
- prompt_version: {input_data.prompt_version or "unknown"}
- model_version: {input_data.model_version or "unknown"}

## Diagnosis Rules
1. Unsupported claims → failure_category = "hallucination_or_unsupported_claims", diagnosis_type = "observed_failure"
2. Missing items → failure_category = "missing_information", diagnosis_type = "observed_failure"
3. Completeness/field extraction missing items → failure_category = "incomplete_extraction", diagnosis_type = "observed_failure"
4. Formatting issues → failure_category = "output_formatting_issues", diagnosis_type = "observed_failure"
5. Low relevance → failure_category = "poor_prompt_alignment", diagnosis_type can be "observed_failure"
6. If retrieval_metadata_available=false and traceability is low → failure_category = "retrieval_issues", diagnosis_type = "hypothesized_root_cause", confidence = "low", evidence_needed required
7. Model limitations → always "hypothesized_root_cause" unless comparative evidence exists

## Failure Categories Available
missing_information | hallucination_or_unsupported_claims | incomplete_extraction |
misinterpretation_of_source | poor_prompt_alignment | retrieval_issues |
model_limitation | output_formatting_issues

## Required JSON Schema
{{
  "diagnoses": [
    {{
      "diagnosis_type": "<observed_failure|hypothesized_root_cause>",
      "failure_category": "<one of the categories above>",
      "severity": "<low|medium|high|critical>",
      "root_cause_summary": "<concise root cause statement>",
      "supporting_evidence": ["<evidence from scoring output>"],
      "confidence": "<low|medium|high>",
      "evidence_needed": "<what evidence would confirm this hypothesis — required for hypothesized_root_cause>",
      "recommended_experiment_signals": ["<signal to look for in experiments>"]
    }}
  ],
  "primary_failure_mode": "<name of the most critical failure>",
  "diagnosis_notes": "<optional notes>"
}}

Return ONLY the JSON object. Do not repeat every score — focus on root causes."""

    def _enforce_retrieval_hypothesis_rule(
        self, output: FailureDiagnosisOutput, retrieval_metadata_available: bool
    ) -> None:
        if retrieval_metadata_available:
            return
        for diag in output.diagnoses:
            if diag.failure_category == "retrieval_issues":
                object.__setattr__(diag, "diagnosis_type", "hypothesized_root_cause")
                object.__setattr__(diag, "confidence", "low")
                if not diag.evidence_needed:
                    object.__setattr__(
                        diag, "evidence_needed",
                        "Retrieve retrieval metadata to confirm whether retrieval gaps caused this failure."
                    )

    def _select_primary_failure_mode(self, output: FailureDiagnosisOutput) -> FailureDiagnosisOutput:
        if not output.diagnoses:
            return output

        observed = [d for d in output.diagnoses if d.diagnosis_type == "observed_failure"]
        candidates = observed if observed else output.diagnoses
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        primary = min(candidates, key=lambda d: severity_order.get(d.severity, 9))

        return FailureDiagnosisOutput(
            diagnoses=output.diagnoses,
            primary_failure_mode=primary.failure_category,
            diagnosis_notes=output.diagnosis_notes,
        )

    def _deterministic_fallback(
        self, input_data: FailureDiagnosisInput, failing: List[DimensionScore]
    ) -> FailureDiagnosisOutput:
        diagnoses: List[RootCauseDiagnosis] = []

        for score in failing:
            category: FailureCategory = _DIMENSION_TO_CATEGORY.get(
                score.dimension_name, "missing_information"
            )
            is_retrieval = category == "retrieval_issues"
            is_observed = category in _OBSERVED_FAILURE_CATEGORIES and not (
                is_retrieval and not input_data.retrieval_metadata_available
            )

            diagnosis_type = "observed_failure" if is_observed else "hypothesized_root_cause"
            confidence = "medium" if is_observed else "low"
            severity = "critical" if score.score < 0.40 else ("high" if score.score < 0.60 else "medium")
            evidence_needed: Optional[str] = None
            if diagnosis_type == "hypothesized_root_cause":
                evidence_needed = (
                    "Retrieve additional metadata or run controlled experiments to confirm this root cause."
                )

            diagnoses.append(
                RootCauseDiagnosis(
                    diagnosis_type=diagnosis_type,
                    failure_category=category,
                    severity=severity,
                    root_cause_summary=(
                        f"Dimension '{score.dimension_name}' scored {score.score:.2f} ({score.score_band}). "
                        "Generated using deterministic fallback because LLM call failed."
                    ),
                    supporting_evidence=[score.justification.summary] if score.justification.summary else [],
                    confidence=confidence,
                    evidence_needed=evidence_needed,
                    recommended_experiment_signals=[
                        f"Re-evaluate {score.dimension_name} after targeted intervention"
                    ],
                )
            )

        observed_failures = [d for d in diagnoses if d.diagnosis_type == "observed_failure"]
        candidates = observed_failures if observed_failures else diagnoses
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        primary = min(candidates, key=lambda d: severity_order.get(d.severity, 9)) if candidates else None

        return FailureDiagnosisOutput(
            diagnoses=diagnoses,
            primary_failure_mode=primary.failure_category if primary else None,
            diagnosis_notes="Generated using deterministic fallback because LLM call failed.",
        )
