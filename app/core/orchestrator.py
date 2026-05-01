import logging
import time
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from app.agents.diagnosis import FailureDiagnosisAgent
from app.agents.experiment_recommender import ExperimentRecommendationAgent
from app.agents.planner import EvaluationPlannerAgent
from app.agents.scorer import QualityScoringAgent
from app.schemas.diagnosis import FailureDiagnosisInput, FailureDiagnosisOutput
from app.schemas.experiments import ExperimentRecommendationInput, ExperimentRecommendationOutput
from app.schemas.orchestration import (
    EvaluationPipelineError,
    EvaluationRunInput,
    EvaluationRunOutput,
)
from app.schemas.planner import EvaluationPlan, EvaluationPlannerInput
from app.schemas.scoring import QualityScoringInput, QualityScoringOutput

logger = logging.getLogger(__name__)

_PREVIEW_LEN = 200


def _preview(text: str) -> str:
    return text[:_PREVIEW_LEN] + ("..." if len(text) > _PREVIEW_LEN else "")


class EvaluationOrchestrator:
    def __init__(self) -> None:
        self._planner = EvaluationPlannerAgent()
        self._scorer = QualityScoringAgent()
        self._diagnosis = FailureDiagnosisAgent()
        self._experiment = ExperimentRecommendationAgent()

    def run(self, input_data: EvaluationRunInput) -> EvaluationRunOutput:
        run_id = f"eval_{uuid.uuid4().hex[:12]}"
        timestamp = datetime.now(timezone.utc).isoformat()
        start_ms = time.monotonic()
        trace: List[str] = []

        logger.info(
            "Orchestrator run_id=%s starting | source_preview=%r | output_preview=%r",
            run_id,
            _preview(input_data.source_document),
            _preview(input_data.llm_output),
        )

        plan: Optional[EvaluationPlan] = None
        scoring: Optional[QualityScoringOutput] = None
        diag_output: Optional[FailureDiagnosisOutput] = None
        exp_output: Optional[ExperimentRecommendationOutput] = None
        pipeline_error: Optional[EvaluationPipelineError] = None

        # Stage 1: Planner
        trace.append("planner:start")
        logger.info("Orchestrator run_id=%s stage=planner start", run_id)
        try:
            planner_input = EvaluationPlannerInput(
                source_document_type=input_data.source_document_type,
                task_type=input_data.task_type,
                user_goal=input_data.user_goal,
                expected_output_format=input_data.expected_output_format,
                business_context=input_data.business_context,
                risk_level=input_data.risk_level,
            )
            plan = self._planner.run(planner_input)
            EvaluationPlan.model_validate(plan.model_dump())
            trace.append("planner:success")
            logger.info("Orchestrator run_id=%s stage=planner success intent=%s", run_id, plan.evaluation_intent)
        except Exception as exc:
            trace.append(f"planner:failure:{exc}")
            logger.error("Orchestrator run_id=%s stage=planner failure: %s", run_id, exc)
            pipeline_error = EvaluationPipelineError(error_stage="planner", error_message=str(exc))
            return self._partial_output(run_id, timestamp, start_ms, trace, input_data, plan, scoring, diag_output, exp_output, pipeline_error)

        # Stage 2: Scorer
        trace.append("scorer:start")
        logger.info("Orchestrator run_id=%s stage=scorer start", run_id)
        try:
            scorer_input = QualityScoringInput(
                source_document=input_data.source_document,
                llm_output=input_data.llm_output,
                evaluation_plan=plan,
            )
            scoring = self._scorer.run(scorer_input)
            QualityScoringOutput.model_validate(scoring.model_dump())
            trace.append("scorer:success")
            logger.info("Orchestrator run_id=%s stage=scorer success overall=%.2f", run_id, scoring.overall_score)
        except Exception as exc:
            trace.append(f"scorer:failure:{exc}")
            logger.error("Orchestrator run_id=%s stage=scorer failure: %s", run_id, exc)
            pipeline_error = EvaluationPipelineError(error_stage="scorer", error_message=str(exc))
            return self._partial_output(run_id, timestamp, start_ms, trace, input_data, plan, scoring, diag_output, exp_output, pipeline_error)

        # Stage 3: Diagnosis
        trace.append("diagnosis:start")
        logger.info("Orchestrator run_id=%s stage=diagnosis start", run_id)
        try:
            diag_input = FailureDiagnosisInput(
                quality_scoring_output=scoring,
                evaluation_plan=plan,
                retrieval_metadata_available=input_data.retrieval_metadata_available,
                retrieval_metadata=input_data.retrieval_metadata,
                prompt_version=input_data.prompt_version,
                model_version=input_data.model_version,
            )
            diag_output = self._diagnosis.run(diag_input)
            FailureDiagnosisOutput.model_validate(diag_output.model_dump())
            trace.append("diagnosis:success")
            logger.info("Orchestrator run_id=%s stage=diagnosis success diagnoses=%d", run_id, len(diag_output.diagnoses))
        except Exception as exc:
            trace.append(f"diagnosis:failure:{exc}")
            logger.error("Orchestrator run_id=%s stage=diagnosis failure: %s", run_id, exc)
            pipeline_error = EvaluationPipelineError(error_stage="diagnosis", error_message=str(exc))
            return self._partial_output(run_id, timestamp, start_ms, trace, input_data, plan, scoring, diag_output, exp_output, pipeline_error)

        # Stage 4: Experiment Recommender
        trace.append("experiment:start")
        logger.info("Orchestrator run_id=%s stage=experiment start", run_id)
        try:
            exp_input = ExperimentRecommendationInput(
                failure_diagnosis_output=diag_output,
                evaluation_plan=plan,
                quality_scoring_output=scoring,
                product_context=input_data.business_context,
                baseline_reference=input_data.baseline_reference,
            )
            exp_output = self._experiment.run(exp_input)
            ExperimentRecommendationOutput.model_validate(exp_output.model_dump())
            trace.append("experiment:success")
            logger.info("Orchestrator run_id=%s stage=experiment success experiments=%d", run_id, len(exp_output.experiments))
        except Exception as exc:
            trace.append(f"experiment:failure:{exc}")
            logger.error("Orchestrator run_id=%s stage=experiment failure: %s", run_id, exc)
            pipeline_error = EvaluationPipelineError(error_stage="experiment", error_message=str(exc))
            return self._partial_output(run_id, timestamp, start_ms, trace, input_data, plan, scoring, diag_output, exp_output, pipeline_error)

        execution_time_ms = int((time.monotonic() - start_ms) * 1000)
        summary = self._build_summary(scoring, diag_output, exp_output, input_data.baseline_reference)

        logger.info("Orchestrator run_id=%s completed execution_time_ms=%d", run_id, execution_time_ms)

        return EvaluationRunOutput(
            run_id=run_id,
            timestamp=timestamp,
            execution_time_ms=execution_time_ms,
            evaluation_plan=plan,
            quality_scoring_output=scoring,
            failure_diagnosis_output=diag_output,
            experiment_recommendation_output=exp_output,
            baseline_reference=input_data.baseline_reference,
            final_summary=summary,
            execution_trace=trace,
            error=None,
        )

    def _partial_output(
        self,
        run_id: str,
        timestamp: str,
        start_ms: float,
        trace: List[str],
        input_data: EvaluationRunInput,
        plan: Optional[EvaluationPlan],
        scoring: Optional[QualityScoringOutput],
        diag_output: Optional[FailureDiagnosisOutput],
        exp_output: Optional[ExperimentRecommendationOutput],
        error: EvaluationPipelineError,
    ) -> EvaluationRunOutput:
        execution_time_ms = int((time.monotonic() - start_ms) * 1000)
        summary = (
            f"Evaluation pipeline stopped at stage '{error.error_stage}': {error.error_message}. "
            "Partial results are available for completed stages."
        )
        return EvaluationRunOutput(
            run_id=run_id,
            timestamp=timestamp,
            execution_time_ms=execution_time_ms,
            evaluation_plan=plan,
            quality_scoring_output=scoring,
            failure_diagnosis_output=diag_output,
            experiment_recommendation_output=exp_output,
            baseline_reference=input_data.baseline_reference,
            final_summary=summary,
            execution_trace=trace,
            error=error,
        )

    def _build_summary(
        self,
        scoring: QualityScoringOutput,
        diag: FailureDiagnosisOutput,
        exp: ExperimentRecommendationOutput,
        baseline_reference: Optional[str],
    ) -> str:
        readiness = "NOT READY for production" if scoring.requires_human_review else "conditionally production-ready"
        score_str = f"Overall score: {scoring.overall_score:.2f}."
        failure_str = (
            f"Primary failure mode: {diag.primary_failure_mode}."
            if diag.primary_failure_mode
            else "No critical failure modes detected."
        )
        exp_str = (
            f"Top recommended experiment: {exp.top_priority_experiment_id}."
            if exp.top_priority_experiment_id
            else "No experiments recommended."
        )
        baseline_str = f"Baseline reference: {baseline_reference}." if baseline_reference else ""
        parts = [f"Output is {readiness}.", score_str, failure_str, exp_str]
        if baseline_str:
            parts.append(baseline_str)
        return " ".join(parts)
