import json
import logging
from typing import List, Tuple

from app.core.llm_client import LLMClient, LLMClientError
from app.schemas.evaluation import EvaluationIntent, TaskType
from app.schemas.planner import (
    DownstreamContract,
    EvaluationDimension,
    EvaluationPlan,
    EvaluationPlannerInput,
    ScoringGuidance,
)

logger = logging.getLogger(__name__)

_CORE_DIMENSIONS: List[EvaluationDimension] = [
    EvaluationDimension(
        name="Faithfulness",
        type="core",
        description="The output contains only claims that are directly supported by the source document.",
        rationale="Unsupported claims are a primary source of LLM hallucination risk.",
        product_decision_use="not_safe_to_ship",
        scoring_guidance=ScoringGuidance(
            low_score_meaning="Multiple claims contradict or are absent from the source.",
            high_score_meaning="Every factual claim traces back to a specific passage in the source.",
            concrete_failure_example="Output states a contract end date that does not appear in the source document.",
        ),
    ),
    EvaluationDimension(
        name="Completeness",
        type="core",
        description="The output covers all material information required to satisfy the user goal.",
        rationale="Missing key information can lead to incorrect downstream decisions.",
        product_decision_use="human_review_required",
        scoring_guidance=ScoringGuidance(
            low_score_meaning="Several important items from the source are omitted.",
            high_score_meaning="All required information is present and nothing material is missing.",
            concrete_failure_example="A lease summary omits the security deposit amount and renewal terms.",
        ),
    ),
    EvaluationDimension(
        name="Traceability",
        type="core",
        description="Claims in the output can be traced to specific source passages or evidence.",
        rationale="Traceability enables human reviewers to verify correctness quickly.",
        product_decision_use="human_review_required",
        scoring_guidance=ScoringGuidance(
            low_score_meaning="Output makes assertions with no reference to source location.",
            high_score_meaning="Each key claim is accompanied by a source reference or verbatim evidence.",
            concrete_failure_example="Summary draws conclusions that cannot be located in any paragraph of the source.",
        ),
    ),
    EvaluationDimension(
        name="Relevance",
        type="core",
        description="The output directly addresses the user goal without irrelevant content.",
        rationale="Irrelevant content reduces usability and may obscure important information.",
        product_decision_use="prompt_improvement_needed",
        scoring_guidance=ScoringGuidance(
            low_score_meaning="Output answers a different question or includes substantial off-topic content.",
            high_score_meaning="Every sentence contributes directly to answering the stated goal.",
            concrete_failure_example="User asked for a risk summary but output contains general contract background only.",
        ),
    ),
    EvaluationDimension(
        name="Risk / Safety",
        type="core",
        description="The output does not introduce misleading, harmful, or legally problematic content.",
        rationale="High-risk outputs can cause downstream harm to users and the business.",
        product_decision_use="not_safe_to_ship",
        scoring_guidance=ScoringGuidance(
            low_score_meaning="Output contains misleading claims or omits critical risk information.",
            high_score_meaning="Output accurately represents risk, caveats uncertainties, and omits nothing safety-critical.",
            concrete_failure_example="Medical summary omits a documented contraindication from the source.",
        ),
    ),
    EvaluationDimension(
        name="Business Usefulness",
        type="core",
        description="The output is actionable and directly serves the stated business context.",
        rationale="An output that cannot be acted on provides no product value.",
        product_decision_use="further_experimentation_needed",
        scoring_guidance=ScoringGuidance(
            low_score_meaning="Output is technically correct but cannot be used to make a decision.",
            high_score_meaning="Output enables a clear, well-informed business decision.",
            concrete_failure_example="Legal risk assessment lists issues but provides no prioritization or recommended action.",
        ),
    ),
]

_CASE_SPECIFIC_DIMENSIONS: dict = {
    "summary": [
        EvaluationDimension(
            name="Information Prioritization",
            type="case_specific",
            description="The most important information appears first and is given appropriate weight.",
            rationale="Summaries must prioritize high-value content for the reader's needs.",
            product_decision_use="prompt_improvement_needed",
            scoring_guidance=ScoringGuidance(
                low_score_meaning="Low-value details are foregrounded while critical points are buried.",
                high_score_meaning="Critical findings lead; supporting detail follows in order of importance.",
                concrete_failure_example="Executive summary opens with background context instead of key risk findings.",
            ),
        ),
    ],
    "extraction": [
        EvaluationDimension(
            name="Field Accuracy",
            type="case_specific",
            description="Extracted field values match the source exactly, including format and precision.",
            rationale="Incorrect field values are a direct extraction failure.",
            product_decision_use="not_safe_to_ship",
            scoring_guidance=ScoringGuidance(
                low_score_meaning="Multiple fields contain values that differ from the source.",
                high_score_meaning="All extracted fields match the source verbatim or with correct normalization.",
                concrete_failure_example="Extracted rent amount is $1,500 but source states $1,450.",
            ),
        ),
        EvaluationDimension(
            name="Format Compliance",
            type="case_specific",
            description="The output structure matches the expected schema or output format.",
            rationale="Downstream systems depend on consistent output structure.",
            product_decision_use="further_experimentation_needed",
            scoring_guidance=ScoringGuidance(
                low_score_meaning="Output is missing required fields or uses incorrect data types.",
                high_score_meaning="All required fields are present with correct types and names.",
                concrete_failure_example="JSON output uses 'start_date' but schema expects 'lease_start'.",
            ),
        ),
    ],
    "question_answering": [
        EvaluationDimension(
            name="Answer Directness",
            type="case_specific",
            description="The output provides a direct, unambiguous answer to the question.",
            rationale="Indirect answers force users to infer the actual answer, introducing error risk.",
            product_decision_use="prompt_improvement_needed",
            scoring_guidance=ScoringGuidance(
                low_score_meaning="Output hedges excessively or restates the question without answering it.",
                high_score_meaning="The first sentence contains the direct answer to the question.",
                concrete_failure_example="Question: 'What is the notice period?' Answer: 'The contract discusses various terms...'",
            ),
        ),
        EvaluationDimension(
            name="Evidence Sufficiency",
            type="case_specific",
            description="The answer is supported by sufficient evidence from the source.",
            rationale="Unsupported answers in QA tasks are unreliable.",
            product_decision_use="human_review_required",
            scoring_guidance=ScoringGuidance(
                low_score_meaning="Answer is given with no reference to supporting source text.",
                high_score_meaning="Answer cites the specific clause or passage that supports it.",
                concrete_failure_example="Answer states '30 days notice required' without referencing Section 4.2 of the contract.",
            ),
        ),
    ],
    "comparison": [
        EvaluationDimension(
            name="Comparative Robustness",
            type="case_specific",
            description="The comparison is fair, systematic, and covers all relevant dimensions.",
            rationale="Biased comparisons lead to incorrect model selection decisions.",
            product_decision_use="further_experimentation_needed",
            scoring_guidance=ScoringGuidance(
                low_score_meaning="Comparison omits key dimensions or applies inconsistent criteria.",
                high_score_meaning="All models/options are evaluated on identical criteria with evidence for each.",
                concrete_failure_example="Model comparison evaluates precision for Model A but only recall for Model B.",
            ),
        ),
    ],
    "classification": [
        EvaluationDimension(
            name="Category Precision",
            type="case_specific",
            description="The assigned category accurately reflects the content based on the classification criteria.",
            rationale="Misclassification leads to incorrect routing or handling.",
            product_decision_use="not_safe_to_ship",
            scoring_guidance=ScoringGuidance(
                low_score_meaning="Category assigned does not match the dominant content of the source.",
                high_score_meaning="Category matches the content and aligns with the defined classification criteria.",
                concrete_failure_example="Complaint email classified as 'inquiry' when it contains an explicit refund demand.",
            ),
        ),
    ],
    "rewrite": [
        EvaluationDimension(
            name="Style Consistency",
            type="case_specific",
            description="The rewrite preserves the intended tone, register, and stylistic requirements.",
            rationale="Style mismatches reduce usability and brand consistency.",
            product_decision_use="prompt_improvement_needed",
            scoring_guidance=ScoringGuidance(
                low_score_meaning="Rewrite uses a noticeably different tone or register than specified.",
                high_score_meaning="Rewrite matches the target style throughout with no register inconsistencies.",
                concrete_failure_example="Formal legal document rewritten in casual conversational language.",
            ),
        ),
    ],
    "unknown": [],
}

_CRITICAL_DIMENSIONS = {"Faithfulness", "Traceability", "Risk / Safety"}


class EvaluationPlannerAgent:
    def __init__(self) -> None:
        self._llm = LLMClient()

    def run(self, input_data: EvaluationPlannerInput) -> EvaluationPlan:
        logger.info("EvaluationPlannerAgent: building evaluation plan")
        try:
            prompt = self._build_prompt(input_data)
            llm_plan = self._llm.generate_json(prompt, EvaluationPlan)
            self._validate_dimension_counts(llm_plan)
            logger.info("EvaluationPlannerAgent: LLM plan generated successfully")
            return llm_plan
        except Exception as exc:
            logger.warning("EvaluationPlannerAgent: falling back to deterministic plan — %s", exc)
            return self._deterministic_fallback(input_data)

    def _build_prompt(self, input_data: EvaluationPlannerInput) -> str:
        core_names = [d.name for d in _CORE_DIMENSIONS]
        case_names = [d.name for d in _CASE_SPECIFIC_DIMENSIONS.get(input_data.task_type, [])]
        return f"""You are an LLM evaluation planning expert.

Given the following evaluation request, produce a structured EvaluationPlan JSON object.

## Request
- task_type: {input_data.task_type}
- user_goal: {input_data.user_goal}
- risk_level: {input_data.risk_level}
- source_document_type: {input_data.source_document_type or "not specified"}
- expected_output_format: {input_data.expected_output_format or "not specified"}
- business_context: {input_data.business_context or "not specified"}

## Evaluation Dimensions Available
Core dimensions (choose 4–6): {core_names}
Case-specific dimensions for task_type="{input_data.task_type}" (choose up to 3): {case_names}
Total selected must not exceed 9.

## Required JSON Schema
Return a JSON object matching exactly:
{{
  "evaluation_intent": "<one of: quality_validation|production_readiness|model_comparison|regression_detection|risk_assessment>",
  "task_type": "{input_data.task_type}",
  "user_goal": "{input_data.user_goal}",
  "selected_dimensions": [
    {{
      "name": "<dimension name>",
      "type": "<core|case_specific>",
      "description": "<description>",
      "rationale": "<why selected for this task>",
      "product_decision_use": "<one of the ProductDecisionUse values>",
      "scoring_guidance": {{
        "low_score_meaning": "<what low score means>",
        "high_score_meaning": "<what high score means>",
        "concrete_failure_example": "<specific failure example>"
      }}
    }}
  ],
  "excluded_dimensions": ["<names of dimensions not selected>"],
  "downstream_contract": {{
    "primary_risk_dimensions": ["Faithfulness", "Traceability", "Risk / Safety"],
    "requires_human_review_if_below": 0.60,
    "notes": "<optional notes>"
  }},
  "evaluation_notes": "<optional notes>"
}}

Rules:
- Always include Faithfulness, Relevance, and Risk/Safety in selected_dimensions.
- For risk_level=high, include Traceability as well.
- Enrich descriptions and rationales to be specific to the user_goal and task_type.
- Return ONLY the JSON object, no markdown, no explanation."""

    def _validate_dimension_counts(self, plan: EvaluationPlan) -> None:
        total = len(plan.selected_dimensions)
        if total > 9:
            raise ValueError(f"Too many dimensions: {total}")
        core_count = sum(1 for d in plan.selected_dimensions if d.type == "core")
        if core_count < 4:
            raise ValueError(f"Too few core dimensions: {core_count}")

    def _deterministic_fallback(self, input_data: EvaluationPlannerInput) -> EvaluationPlan:
        intent = self._classify_intent(input_data)
        selected = self._select_dimensions(input_data)
        selected_names = {d.name for d in selected}
        all_names = {d.name for d in _CORE_DIMENSIONS}
        for dims in _CASE_SPECIFIC_DIMENSIONS.values():
            for d in dims:
                all_names.add(d.name)
        excluded = sorted(all_names - selected_names)

        return EvaluationPlan(
            evaluation_intent=intent,
            task_type=input_data.task_type,
            user_goal=input_data.user_goal,
            selected_dimensions=selected,
            excluded_dimensions=excluded,
            downstream_contract=DownstreamContract(
                primary_risk_dimensions=list(_CRITICAL_DIMENSIONS),
                requires_human_review_if_below=0.60,
                notes="Generated using deterministic fallback because LLM call failed.",
            ),
            evaluation_notes="Generated using deterministic fallback because LLM call failed.",
        )

    def _classify_intent(self, input_data: EvaluationPlannerInput) -> EvaluationIntent:
        goal_lower = input_data.user_goal.lower()
        if input_data.risk_level == "high" or any(
            kw in goal_lower for kw in ("risk", "safety", "critical", "harm", "danger")
        ):
            return "risk_assessment"
        if any(kw in goal_lower for kw in ("compar", " vs ", " versus ", "better")):
            return "model_comparison"
        if any(kw in goal_lower for kw in ("regression", "behavior", "same as before", "consistent")):
            return "regression_detection"
        if any(kw in goal_lower for kw in ("production", "ship", "deploy", "ready", "launch")):
            return "production_readiness"
        return "quality_validation"

    def _select_dimensions(self, input_data: EvaluationPlannerInput) -> List[EvaluationDimension]:
        always_include = {"Faithfulness", "Relevance", "Risk / Safety", "Business Usefulness"}
        if input_data.risk_level in ("medium", "high"):
            always_include.add("Traceability")
        if input_data.risk_level == "high":
            always_include.add("Completeness")

        selected: List[EvaluationDimension] = []
        for dim in _CORE_DIMENSIONS:
            if dim.name in always_include:
                selected.append(dim)
        for dim in _CORE_DIMENSIONS:
            if dim.name not in always_include and len(selected) < 6:
                selected.append(dim)

        case_dims = _CASE_SPECIFIC_DIMENSIONS.get(input_data.task_type, [])
        for dim in case_dims[:3]:
            if len(selected) < 9:
                selected.append(dim)

        return selected
