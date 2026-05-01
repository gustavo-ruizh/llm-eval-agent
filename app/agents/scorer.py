import logging
from typing import List, Set

from app.core.llm_client import LLMClient
from app.schemas.planner import EvaluationDimension, EvaluationPlan
from app.schemas.scoring import (
    DimensionScore,
    QualityScoringInput,
    QualityScoringOutput,
    ScoreJustification,
)

logger = logging.getLogger(__name__)

_CRITICAL_DIMENSIONS: Set[str] = {"Faithfulness", "Traceability", "Risk / Safety"}
_FALLBACK_SCORE = 0.50


def _score_band(score: float) -> str:
    if score <= 0.20:
        return "poor"
    if score <= 0.40:
        return "weak"
    if score <= 0.60:
        return "acceptable"
    if score <= 0.80:
        return "strong"
    return "excellent"


class QualityScoringAgent:
    def __init__(self) -> None:
        self._llm = LLMClient()

    def run(self, input_data: QualityScoringInput) -> QualityScoringOutput:
        logger.info("QualityScoringAgent: scoring %d dimensions", len(input_data.evaluation_plan.selected_dimensions))
        try:
            prompt = self._build_prompt(input_data)
            raw_output = self._llm.generate_json(prompt, QualityScoringOutput)
            validated = self._reconcile_with_plan(raw_output, input_data.evaluation_plan)
            logger.info("QualityScoringAgent: LLM scoring completed, overall=%.2f", validated.overall_score)
            return validated
        except Exception as exc:
            logger.warning("QualityScoringAgent: falling back to deterministic scoring — %s", exc)
            return self._deterministic_fallback(input_data.evaluation_plan)

    def _build_prompt(self, input_data: QualityScoringInput) -> str:
        source_preview = input_data.source_document[:8000]
        output_preview = input_data.llm_output[:8000]
        dims_json = [
            {
                "name": d.name,
                "type": d.type,
                "description": d.description,
                "scoring_guidance": {
                    "low_score_meaning": d.scoring_guidance.low_score_meaning,
                    "high_score_meaning": d.scoring_guidance.high_score_meaning,
                    "concrete_failure_example": d.scoring_guidance.concrete_failure_example,
                },
            }
            for d in input_data.evaluation_plan.selected_dimensions
        ]
        import json
        dims_str = json.dumps(dims_json, indent=2)

        critical = list(_CRITICAL_DIMENSIONS & {d.name for d in input_data.evaluation_plan.selected_dimensions})

        return f"""You are an expert LLM output quality evaluator.

## Task
Evaluate the LLM output against the source document for each dimension below.
Score each dimension on a scale of 0.0 (worst) to 1.0 (best).

## Source Document (excerpt)
{source_preview}

## LLM Output (excerpt)
{output_preview}

## Evaluation Goal
{input_data.evaluation_plan.user_goal}

## Dimensions to Score
{dims_str}

## Score Bands
0.00–0.20 = poor | 0.21–0.40 = weak | 0.41–0.60 = acceptable | 0.61–0.80 = strong | 0.81–1.00 = excellent

## Critical Rule
If any of these dimensions score below 0.60, requires_human_review must be true: {critical}

## Required JSON Schema
Return a JSON object matching exactly:
{{
  "scores": [
    {{
      "dimension_name": "<exact name from dimensions list>",
      "dimension_type": "<core|case_specific>",
      "risk_weight": "<low|medium|high>",
      "score": <0.0 to 1.0>,
      "score_band": "<poor|weak|acceptable|strong|excellent>",
      "justification": {{
        "summary": "<one sentence summary>",
        "supporting_evidence": ["<specific text from output that supports the score>"],
        "unsupported_claims": ["<claims in output not supported by source>"],
        "missing_items": ["<items expected but absent from output>"]
      }},
      "confidence": "<low|medium|high>"
    }}
  ],
  "overall_score": <weighted average 0.0 to 1.0>,
  "scoring_notes": "<optional notes>",
  "requires_human_review": <true|false>
}}

Score ONLY the dimensions listed. Return ONLY the JSON object."""

    def _reconcile_with_plan(
        self, output: QualityScoringOutput, plan: EvaluationPlan
    ) -> QualityScoringOutput:
        plan_names = {d.name: d for d in plan.selected_dimensions}
        reconciled: List[DimensionScore] = []

        for score in output.scores:
            if score.dimension_name in plan_names:
                reconciled.append(score)

        for dim in plan.selected_dimensions:
            if not any(s.dimension_name == dim.name for s in reconciled):
                logger.warning("QualityScoringAgent: dimension %s missing from LLM output, using fallback score", dim.name)
                reconciled.append(self._fallback_dimension_score(dim))

        overall = sum(s.score for s in reconciled) / len(reconciled) if reconciled else 0.0
        requires_human_review = self._check_human_review(reconciled)

        return QualityScoringOutput(
            scores=reconciled,
            overall_score=round(overall, 3),
            scoring_notes=output.scoring_notes,
            requires_human_review=requires_human_review,
        )

    def _check_human_review(self, scores: List[DimensionScore]) -> bool:
        for score in scores:
            if score.dimension_name in _CRITICAL_DIMENSIONS and score.score < 0.60:
                return True
        return False

    def _fallback_dimension_score(self, dim: EvaluationDimension) -> DimensionScore:
        return DimensionScore(
            dimension_name=dim.name,
            dimension_type=dim.type,
            risk_weight="medium",
            score=_FALLBACK_SCORE,
            score_band=_score_band(_FALLBACK_SCORE),
            justification=ScoreJustification(
                summary="Generated using deterministic fallback because LLM call failed.",
                supporting_evidence=[],
                unsupported_claims=[],
                missing_items=[],
            ),
            confidence="low",
        )

    def _deterministic_fallback(self, plan: EvaluationPlan) -> QualityScoringOutput:
        scores = [self._fallback_dimension_score(dim) for dim in plan.selected_dimensions]
        overall = _FALLBACK_SCORE
        requires_human_review = any(s.dimension_name in _CRITICAL_DIMENSIONS for s in scores)

        return QualityScoringOutput(
            scores=scores,
            overall_score=overall,
            scoring_notes="Generated using deterministic fallback because LLM call failed.",
            requires_human_review=requires_human_review,
        )
