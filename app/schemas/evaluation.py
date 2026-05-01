from typing import Literal

TaskType = Literal[
    "summary",
    "extraction",
    "question_answering",
    "comparison",
    "classification",
    "rewrite",
    "unknown",
]

EvaluationIntent = Literal[
    "quality_validation",
    "production_readiness",
    "model_comparison",
    "regression_detection",
    "risk_assessment",
]

ProductDecisionUse = Literal[
    "safe_to_ship",
    "not_safe_to_ship",
    "human_review_required",
    "further_experimentation_needed",
    "model_improvement_needed",
    "prompt_improvement_needed",
    "retrieval_improvement_needed",
]

FailureCategory = Literal[
    "missing_information",
    "hallucination_or_unsupported_claims",
    "incomplete_extraction",
    "misinterpretation_of_source",
    "poor_prompt_alignment",
    "retrieval_issues",
    "model_limitation",
    "output_formatting_issues",
]
