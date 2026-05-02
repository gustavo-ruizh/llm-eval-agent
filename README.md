# LLM Evaluation and Experimentation Agent

A production-oriented, agentic AI system that helps teams determine whether LLM outputs are reliable enough to ship — and what experiment to run next.

Given a source document, an LLM-generated output, and an evaluation goal, the system:
1. Designs an evaluation plan
2. Scores output quality across key dimensions
3. Diagnoses failure modes
4. Recommends concrete, testable experiments

---

## 🎯 Why this matters

Most teams struggle to:
- Evaluate LLM quality consistently
- Connect evaluation results to product decisions
- Design structured experiments to improve performance

This system bridges that gap by turning evaluation into actionable decisions.

---

## 🔬 Relationship to Existing Frameworks

Frameworks like RAGAS, DeepEval, and G-Eval established the foundation
for LLM evaluation — particularly faithfulness, answer relevancy, and
LLM-as-a-judge scoring. This system builds on those concepts with three
additions they don't natively provide:

- **Business decision framing:** scores are mapped to explicit product
  outcomes (safe to ship, human review required, further experimentation
  needed) rather than raw metrics
- **Observed vs. hypothesized failure separation:** diagnosis explicitly
  distinguishes what is directly evidenced from what requires further
  investigation before acting
- **Experiment recommendation as first-class output:** the system doesn't
  stop at a score — it produces a prioritized, testable next step tied to
  measurable success criteria

---

## 👤 Who This Is For

AI Product Managers use this to answer a single question before each release: is this output safe to ship, and if not, what do we change first? 

ML Engineers use it to replace ad-hoc manual review with a structured experiment backlog — each evaluation run produces a prioritized, testable next step.

Data Scientists use it to move beyond one-off scoring notebooks and into a repeatable pipeline that tracks failure modes across prompt iterations.

## 🔄 Workflow

1. Team generates LLM output
2. Runs evaluation via API
3. Receives structured diagnosis + experiment
4. Uses recommendation to iterate on prompt/model

---

## 🧩 Key Design Decisions

- Hybrid evaluation framework (core + adaptive dimensions)
- Evidence-based scoring to prevent hallucinated evaluations
- Separation of observed failures vs hypothesized root causes
- Experiment recommendations tied to measurable success criteria
- Deterministic fallback for reliability without API dependency

---

## Architecture

```
POST /evaluations
        │
        ▼
┌─────────────────────────────────────────────────────┐
│                  EvaluationOrchestrator             │
│                                                     │
│  ┌──────────────┐    ┌──────────────┐               │
│  │   Planner    │───▶│    Scorer    │               │
│  │    Agent     │    │    Agent     │               │
│  └──────────────┘    └──────┬───────┘               │
│                             │                       │
│  ┌──────────────┐    ┌──────▼───────┐               │
│  │  Experiment  │◀───│  Diagnosis   │               │
│  │  Recommender │    │    Agent     │               │
│  └──────┬───────┘    └──────────────┘               │
│         │                                           │
└─────────┼───────────────────────────────────────────┘
          │
          ▼
   EvaluationRunOutput
          │
          ▼
   SQLite Repository
```

Each agent:
- Accepts exactly one Pydantic input model
- Returns exactly one Pydantic output model
- Calls `LLMClient.generate_json(prompt, ResponseModel)` for inference
- Falls back to deterministic logic if the LLM call fails

---

## Agents

### Evaluation Planner Agent
Classifies the evaluation intent (quality validation, production readiness, etc.), selects 4–6 core dimensions and up to 3 case-specific dimensions based on task type and risk level, and produces an `EvaluationPlan`.

### Quality Scoring Agent
Scores each dimension from the evaluation plan on a 0.0–1.0 scale with evidence-grounded justifications. Applies a critical readiness rule: if Faithfulness, Traceability, or Risk/Safety scores below 0.60, `requires_human_review` is set to `true`.

### Failure Diagnosis Agent
Analyzes dimensions scoring below 0.80, maps them to failure categories, and separates **observed failures** (directly evidenced) from **hypothesized root causes** (requiring further investigation). Retrieval issues without metadata are always low-confidence hypotheses.

### Experiment Recommendation Agent
Generates concrete, testable experiments linked to each diagnosis. Priority is determined by:
- severity of failure
- confidence in diagnosis
- implementation effort

Low-confidence hypotheses produce `requires_more_evidence` experiments with diagnostic goals.

---

## Evaluation Framework

### Core Dimensions

| Dimension | Description |
|-----------|-------------|
| **Faithfulness** | All claims are supported by the source document |
| **Completeness** | All material information required by the goal is present |
| **Traceability** | Claims can be traced to specific source passages |
| **Relevance** | Output directly addresses the user goal |
| **Risk / Safety** | No misleading, harmful, or legally problematic content |
| **Business Usefulness** | Output enables a clear, well-informed business decision |

### Case-Specific Dimensions

| Task Type | Dimensions |
|-----------|-----------|
| `summary` | Information Prioritization |
| `extraction` | Field Accuracy, Format Compliance |
| `question_answering` | Answer Directness, Evidence Sufficiency |
| `comparison` | Comparative Robustness |
| `classification` | Category Precision |
| `rewrite` | Style Consistency |

### Score Bands

| Range | Band |
|-------|------|
| 0.00–0.20 | poor |
| 0.21–0.40 | weak |
| 0.41–0.60 | acceptable |
| 0.61–0.80 | strong |
| 0.81–1.00 | excellent |

---

## Setup

### 1. Install dependencies

```bash
cd llm_eval_agent
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set your API key:

```env
LLM_PROVIDER=openai
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4.1-mini
DATABASE_PATH=evaluation_runs.db
LLM_TIMEOUT_SECONDS=20
```

If `LLM_API_KEY` is empty, all agents run in **deterministic fallback mode** — the full pipeline executes end-to-end without a real LLM.

### 3. Run the server

```bash
uvicorn app.main:app --reload
```

The API is available at `http://localhost:8000`.

Interactive docs: `http://localhost:8000/docs`

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `openai` | `openai` or `anthropic` |
| `LLM_API_KEY` | *(empty)* | API key; leave empty for fallback mode |
| `LLM_MODEL` | `gpt-4.1-mini` | Model identifier |
| `DATABASE_PATH` | `evaluation_runs.db` | SQLite file path |
| `LLM_TIMEOUT_SECONDS` | `20` | Per-request LLM timeout |

---

## Example API Call

```bash
# Full result
curl -X POST "http://localhost:8000/evaluations" \
  -H "Content-Type: application/json" \
  -d @examples/sample_request.json

# Summary only (smaller response)
curl -X POST "http://localhost:8000/evaluations?include_full_result=false" \
  -H "Content-Type: application/json" \
  -d @examples/sample_request.json

# Retrieve a stored run
curl "http://localhost:8000/evaluations/{run_id}"

# Health check
curl "http://localhost:8000/health"
```

---

## 📊 Example Run (Real Output)

Below is an actual response from the system:

```json
{
  "run_id": "eval_a1c13ffd1af1",
  "timestamp": "2026-05-01T22:11:10.669798+00:00",
  "execution_time_ms": 95003,
  "final_summary": "Output is NOT READY for production. Overall score: 0.53. Primary failure mode: hallucination_or_unsupported_claims. Top recommended experiment: exp_001.",
  "baseline_reference": null,
  "requires_human_review": true,
  "primary_failure_mode": "hallucination_or_unsupported_claims",
  "recommended_next_experiment_id": "exp_001",
  "error": null,
  "full_result": {
    "run_id": "eval_a1c13ffd1af1",
    "timestamp": "2026-05-01T22:11:10.669798+00:00",
    "execution_time_ms": 95003,
    "evaluation_plan": {
      "evaluation_intent": "risk_assessment",
      "task_type": "summary",
      "user_goal": "Verify the summary is accurate and safe to share.",
      "selected_dimensions": [
        {
          "name": "Faithfulness",
          "type": "core",
          "description": "The output contains only claims that are directly supported by the source document.",
          "rationale": "Unsupported claims are a primary source of LLM hallucination risk.",
          "product_decision_use": "not_safe_to_ship",
          "scoring_guidance": {
            "low_score_meaning": "Multiple claims contradict or are absent from the source.",
            "high_score_meaning": "Every factual claim traces back to a specific passage in the source.",
            "concrete_failure_example": "Output states a contract end date that does not appear in the source document."
          }
        },
        {
          "name": "Completeness",
          "type": "core",
          "description": "The output covers all material information required to satisfy the user goal.",
          "rationale": "Missing key information can lead to incorrect downstream decisions.",
          "product_decision_use": "human_review_required",
          "scoring_guidance": {
            "low_score_meaning": "Several important items from the source are omitted.",
            "high_score_meaning": "All required information is present and nothing material is missing.",
            "concrete_failure_example": "A lease summary omits the security deposit amount and renewal terms."
          }
        },
        {
          "name": "Traceability",
          "type": "core",
          "description": "Claims in the output can be traced to specific source passages or evidence.",
          "rationale": "Traceability enables human reviewers to verify correctness quickly.",
          "product_decision_use": "human_review_required",
          "scoring_guidance": {
            "low_score_meaning": "Output makes assertions with no reference to source location.",
            "high_score_meaning": "Each key claim is accompanied by a source reference or verbatim evidence.",
            "concrete_failure_example": "Summary draws conclusions that cannot be located in any paragraph of the source."
          }
        },
        {
          "name": "Relevance",
          "type": "core",
          "description": "The output directly addresses the user goal without irrelevant content.",
          "rationale": "Irrelevant content reduces usability and may obscure important information.",
          "product_decision_use": "prompt_improvement_needed",
          "scoring_guidance": {
            "low_score_meaning": "Output answers a different question or includes substantial off-topic content.",
            "high_score_meaning": "Every sentence contributes directly to answering the stated goal.",
            "concrete_failure_example": "User asked for a risk summary but output contains general contract background only."
          }
        },
        {
          "name": "Risk / Safety",
          "type": "core",
          "description": "The output does not introduce misleading, harmful, or legally problematic content.",
          "rationale": "High-risk outputs can cause downstream harm to users and the business.",
          "product_decision_use": "not_safe_to_ship",
          "scoring_guidance": {
            "low_score_meaning": "Output contains misleading claims or omits critical risk information.",
            "high_score_meaning": "Output accurately represents risk, caveats uncertainties, and omits nothing safety-critical.",
            "concrete_failure_example": "Medical summary omits a documented contraindication from the source."
          }
        },
        {
          "name": "Business Usefulness",
          "type": "core",
          "description": "The output is actionable and directly serves the stated business context.",
          "rationale": "An output that cannot be acted on provides no product value.",
          "product_decision_use": "further_experimentation_needed",
          "scoring_guidance": {
            "low_score_meaning": "Output is technically correct but cannot be used to make a decision.",
            "high_score_meaning": "Output enables a clear, well-informed business decision.",
            "concrete_failure_example": "Legal risk assessment lists issues but provides no prioritization or recommended action."
          }
        },
        {
          "name": "Information Prioritization",
          "type": "case_specific",
          "description": "The most important information appears first and is given appropriate weight.",
          "rationale": "Summaries must prioritize high-value content for the reader's needs.",
          "product_decision_use": "prompt_improvement_needed",
          "scoring_guidance": {
            "low_score_meaning": "Low-value details are foregrounded while critical points are buried.",
            "high_score_meaning": "Critical findings lead; supporting detail follows in order of importance.",
            "concrete_failure_example": "Executive summary opens with background context instead of key risk findings."
          }
        }
      ],
      "excluded_dimensions": [
        "Answer Directness",
        "Category Precision",
        "Comparative Robustness",
        "Evidence Sufficiency",
        "Field Accuracy",
        "Format Compliance",
        "Style Consistency"
      ],
      "downstream_contract": {
        "primary_risk_dimensions": [
          "Faithfulness",
          "Risk / Safety",
          "Traceability"
        ],
        "requires_human_review_if_below": 0.6,
        "notes": "Generated using deterministic fallback because LLM call failed."
      },
      "evaluation_notes": "Generated using deterministic fallback because LLM call failed."
    },
    "quality_scoring_output": {
      "scores": [
        {
          "dimension_name": "Faithfulness",
          "dimension_type": "core",
          "risk_weight": "high",
          "score": 0.55,
          "score_band": "acceptable",
          "justification": {
            "summary": "Most claims correspond to the source, but numerous claims lack supporting reference or are contradicted by missing source text.",
            "supporting_evidence": [
              "Term and commencement date details",
              "Lease charge including late fees",
              "Lessee's responsibility to pay taxes",
              "Lessee paying delivery and installation costs"
            ],
            "unsupported_claims": [
              "The summary refers to sections (e.g., 8, 9, 11, 12, 13, 15, 16, 17, 18, 24, 25, 26, 27) which do not appear in the provided source excerpt",
              "Claims about 'net lease' with unconditional payment obligations (section 27)",
              "Details about Maintenance Agreement, alterations, insurer obligations",
              "Specific monetary amounts and purchase options"
            ],
            "missing_items": [
              "Full source text for many enumerated sections referenced in the output",
              "Specific terms such as security deposits, expansion options, treasury note adjustments, and right of first refusal clauses"
            ]
          },
          "confidence": "high"
        },
        {
          "dimension_name": "Completeness",
          "dimension_type": "core",
          "risk_weight": "medium",
          "score": 0.25,
          "score_band": "weak",
          "justification": {
            "summary": "The summary misses multiple critical details and appears to include information beyond the shared source excerpt.",
            "supporting_evidence": [
              "Coverage of term, commencement, charges, payment, delivery, installation, and tax obligations"
            ],
            "unsupported_claims": [],
            "missing_items": [
              "Most of the sections cited in the output are absent in the provided source (sections 8, 9, 11, 12, 13, 15, 16, 17, etc.)",
              "No mention or source evidence for amounts like $176,073.80 monthly charge or $352,147.60 security deposit in the excerpt",
              "No source coverage for right of first refusal, purchase options, or legal enforcement terms",
              "No mention of the mobile robot nature of equipment beyond a brief fragment"
            ]
          },
          "confidence": "high"
        },
        {
          "dimension_name": "Traceability",
          "dimension_type": "core",
          "risk_weight": "high",
          "score": 0.1,
          "score_band": "poor",
          "justification": {
            "summary": "Most claims are not clearly traceable to the provided source as many cited sections are missing and the output includes details not found in the text.",
            "supporting_evidence": [
              "Sections 1 (term), 2 (commencement), 3 (lease charge), 4 (taxes), 5 (delivery), and 6 (installation) are referenced and partially supported in the source"
            ],
            "unsupported_claims": [
              "Claims from sections 8, 9, 11, 12, 13, 15, 16, 17, 18, 24, 25, 26, 27",
              "Financial details for lease schedules and rider provisions not found in source",
              "Legal terms about default, remedies, insurance, indemnity, and purchase options"
            ],
            "missing_items": []
          },
          "confidence": "high"
        },
        {
          "dimension_name": "Relevance",
          "dimension_type": "core",
          "risk_weight": "medium",
          "score": 0.85,
          "score_band": "excellent",
          "justification": {
            "summary": "The output remains focused on summarizing the lease agreement’s key financial and legal terms relevant to the user’s goal.",
            "supporting_evidence": [
              "Focused on core lease terms and obligations",
              "Relevant breakdown of sections by category (Core Terms, Operations, Risk, Default, Schedules)"
            ],
            "unsupported_claims": [],
            "missing_items": []
          },
          "confidence": "high"
        },
        {
          "dimension_name": "Risk / Safety",
          "dimension_type": "core",
          "risk_weight": "high",
          "score": 0.5,
          "score_band": "acceptable",
          "justification": {
            "summary": "The output highlights risk and liability aspects but includes many claims that cannot be verified from the provided excerpt, risking incomplete risk portrayal.",
            "supporting_evidence": [
              "Identification of late charges and taxes as financial risks",
              "Mention of Lessee’s responsibility for loss, insurance, indemnity, and default consequences"
            ],
            "unsupported_claims": [
              "Many insurance, indemnity, casualty loss, default event and remedy terms not found in partial source text",
              "No mention in source of a 40% purchase option or 5% penalty fees"
            ],
            "missing_items": [
              "Full legal risk terms from omitted sections",
              "Clear depiction of all penalties and remedy rights"
            ]
          },
          "confidence": "high"
        },
        {
          "dimension_name": "Business Usefulness",
          "dimension_type": "core",
          "risk_weight": "medium",
          "score": 0.65,
          "score_band": "strong",
          "justification": {
            "summary": "Provides useful financial and legal obligations summary valuable for business decision-making, but lacks verifiable completeness.",
            "supporting_evidence": [
              "Clear breakdown of payment terms and obligations",
              "Identification of key lease termination and renewal mechanisms"
            ],
            "unsupported_claims": [
              "Quantitative values and expansion options lack source backing"
            ],
            "missing_items": [
              "Confirmation and sourcing of monetary figures",
              "Clear legal remedies or risks that might affect business decisions"
            ]
          },
          "confidence": "high"
        },
        {
          "dimension_name": "Information Prioritization",
          "dimension_type": "case_specific",
          "risk_weight": "low",
          "score": 0.8,
          "score_band": "strong",
          "justification": {
            "summary": "The summary leads with core lease terms and financial obligations before operational and risk details, reflecting appropriate prioritization.",
            "supporting_evidence": [
              "Starts with Term, Commencement, Lease Charge and Taxes",
              "Covers operational costs before risk and default",
              "Monetary schedules and rider options placed last"
            ],
            "unsupported_claims": [],
            "missing_items": []
          },
          "confidence": "high"
        }
      ],
      "overall_score": 0.529,
      "scoring_notes": "Output contains significant extraneous information beyond the provided source excerpt and omits coverage of some core contents. Many detailed claims lack clear source traceability, necessitating human review.",
      "requires_human_review": true
    },
    "failure_diagnosis_output": {
      "diagnoses": [
        {
          "diagnosis_type": "observed_failure",
          "failure_category": "hallucination_or_unsupported_claims",
          "severity": "critical",
          "root_cause_summary": "Summary contains numerous claims and details not supported by the provided source text, including references to missing sections and specific monetary and legal information.",
          "supporting_evidence": [
            "Unsupported claims include references to sections (8, 9, 11, 12, 13, 15, 16, 17, 18, 24, 25, 26, 27) absent from source",
            "Claims about 'net lease' obligations, Maintenance Agreement details, insurer obligations, and purchase options unsupported",
            "Monetary amounts and specific contract clauses lack backing in source"
          ],
          "confidence": "high",
          "evidence_needed": "Access to full original source text including all referenced sections to verify source support for claims",
          "recommended_experiment_signals": [
            "Reduced hallucinated claims after prompt tuning or model updates",
            "Improved alignment of claims with provided text in evaluation outputs"
          ]
        },
        {
          "diagnosis_type": "observed_failure",
          "failure_category": "missing_information",
          "severity": "high",
          "root_cause_summary": "The summary omits critical factual details and clauses present in the full source but absent or only partially present in the provided excerpt.",
          "supporting_evidence": [
            "Missing items include full text for enumerated sections referenced",
            "Specific contractual terms about security deposits, expansion options, and legal enforcement not addressed"
          ],
          "confidence": "high",
          "evidence_needed": "Complete and comprehensive source text to identify all critical missing information",
          "recommended_experiment_signals": [
            "Increased completeness metrics when full source text is provided",
            "Reduction in missing critical information with improved extraction methods"
          ]
        },
        {
          "diagnosis_type": "observed_failure",
          "failure_category": "incomplete_extraction",
          "severity": "high",
          "root_cause_summary": "The summary inadequately extracts and references source information leading to incomplete coverage and traceability.",
          "supporting_evidence": [
            "Score indicates poor traceability with many claims not clearly linked to source",
            "Missing mention of key financial and risk terms reduces extraction completeness"
          ],
          "confidence": "high",
          "evidence_needed": "Detailed source-to-output mapping or retrieval information to ensure accurate extraction",
          "recommended_experiment_signals": [
            "Improved traceability scores with enhanced retrieval or extraction controls",
            "Better completeness when section references correspond precisely to source text"
          ]
        },
        {
          "diagnosis_type": "hypothesized_root_cause",
          "failure_category": "retrieval_issues",
          "severity": "medium",
          "root_cause_summary": "Lack of retrieval metadata combined with poor traceability suggests possible incomplete or inadequate source retrieval affecting summary quality.",
          "supporting_evidence": [
            "Retrieval metadata not available",
            "Traceability scored as poor with indications of missing referenced sections"
          ],
          "confidence": "low",
          "evidence_needed": "Access to retrieval logs or metadata to confirm completeness and relevance of retrieved source text",
          "recommended_experiment_signals": [
            "Improved traceability and faithfulness when retrieval metadata is included",
            "Correlation between retrieval completeness and summary accuracy"
          ]
        }
      ],
      "primary_failure_mode": "hallucination_or_unsupported_claims",
      "diagnosis_notes": "Summary suffers mainly from hallucinated content not supported by the partial source. This is compounded by missing information and incomplete extraction likely due to insufficient or partial retrieval of source text. Improving source completeness and retrieval transparency could mitigate these issues."
    },
    "experiment_recommendation_output": {
      "experiments": [
        {
          "experiment_id": "exp_001",
          "linked_failure_category": "hallucination_or_unsupported_claims",
          "linked_diagnosis_type": "observed_failure",
          "validates_failure_mode": "hallucination and unsupported claims in summaries",
          "experiment_type": "prompt_change",
          "scope": "prompt_only",
          "priority": "critical",
          "effort": "medium",
          "status": "recommended",
          "depends_on_experiment_id": null,
          "baseline_reference": null,
          "diagnostic_goal": null,
          "recommendation": "Tune prompts to explicitly instruct the model to cite only facts directly supported by the source text and to avoid fabricating claims.",
          "test_design": "Create a controlled set of prompt variants with increasing emphasis on source support and hallucination avoidance. Evaluate the hallucination rate on a fixed source-summary dataset.",
          "expected_outcome": "Reduced hallucinated claims and improved alignment of claims with provided source text.",
          "success_criteria": [
            {
              "metric_name": "hallucination_rate",
              "baseline_value": 0.47,
              "target_value": 0.2,
              "comparison_type": "absolute",
              "measurement_method": "Automated hallucination detection against source text"
            },
            {
              "metric_name": "claim_alignment_score",
              "baseline_value": 0.53,
              "target_value": 0.75,
              "comparison_type": "absolute",
              "measurement_method": "Human evaluation for claim support in summary"
            }
          ],
          "risk_if_not_done": "Continued production of summaries with critical unsupported or fabricated claims, risking misinformation."
        },
        {
          "experiment_id": "exp_002",
          "linked_failure_category": "missing_information",
          "linked_diagnosis_type": "observed_failure",
          "validates_failure_mode": "missing critical factual details in summaries",
          "experiment_type": "evaluation_set_expansion",
          "scope": "hybrid",
          "priority": "high",
          "effort": "medium",
          "status": "recommended",
          "depends_on_experiment_id": "exp_001",
          "baseline_reference": null,
          "diagnostic_goal": null,
          "recommendation": "Expand evaluation datasets to include complete source texts and compare summary completeness against these full sources.",
          "test_design": "Add full original source texts including all clauses and sections to the evaluation benchmark. Measure completeness of generated summaries before and after.",
          "expected_outcome": "Increased completeness metrics and identification of missing information due to source excerpt limitations.",
          "success_criteria": [
            {
              "metric_name": "summary_completeness",
              "baseline_value": 0.6,
              "target_value": 0.85,
              "comparison_type": "absolute",
              "measurement_method": "Automated completeness metric comparing summary facts to full source text"
            }
          ],
          "risk_if_not_done": "Persisting omission of critical factual details leading to incomplete and less trustworthy summaries."
        },
        {
          "experiment_id": "exp_003",
          "linked_failure_category": "incomplete_extraction",
          "linked_diagnosis_type": "observed_failure",
          "validates_failure_mode": "inadequate extraction causing incomplete coverage and poor traceability",
          "experiment_type": "source_chunking_review",
          "scope": "retrieval_only",
          "priority": "high",
          "effort": "medium",
          "status": "recommended",
          "depends_on_experiment_id": "exp_002",
          "baseline_reference": null,
          "diagnostic_goal": null,
          "recommendation": "Review and improve the source chunking and referencing strategy to ensure thorough extraction and accurate section mapping.",
          "test_design": "Implement refined chunking of source text ensuring granular and complete coverage. Evaluate traceability and completeness scores with improved chunk references.",
          "expected_outcome": "Higher traceability and completeness scores with better alignment of summary content to source sections.",
          "success_criteria": [
            {
              "metric_name": "traceability_score",
              "baseline_value": 0.55,
              "target_value": 0.8,
              "comparison_type": "absolute",
              "measurement_method": "Human rated and automatic linkage scores between summary claims and source text chunks"
            },
            {
              "metric_name": "completeness_score",
              "baseline_value": 0.6,
              "target_value": 0.85,
              "comparison_type": "absolute",
              "measurement_method": "Coverage metrics of source facts included in summary"
            }
          ],
          "risk_if_not_done": "Continued poor extraction and referencing will limit the ability to verify summary accuracy and completeness."
        },
        {
          "experiment_id": "exp_004",
          "linked_failure_category": "retrieval_issues",
          "linked_diagnosis_type": "hypothesized_root_cause",
          "validates_failure_mode": "potential incomplete or inadequate source retrieval affecting summary quality",
          "experiment_type": "retrieval_tuning",
          "scope": "retrieval_only",
          "priority": "medium",
          "effort": "medium",
          "status": "requires_more_evidence",
          "depends_on_experiment_id": "exp_003",
          "baseline_reference": null,
          "diagnostic_goal": "Confirm whether retrieval metadata and completeness improve summary faithfulness and traceability.",
          "recommendation": "Incorporate detailed retrieval metadata and logs to evaluate and improve completeness and relevance of retrieved source texts.",
          "test_design": "Enable retrieval logging with metadata on source chunks. Correlate retrieval completeness metrics with summary quality and traceability.",
          "expected_outcome": "Identify causal link between retrieval completeness and summary accuracy, enabling targeted improvements.",
          "success_criteria": [
            {
              "metric_name": "retrieval_completeness",
              "baseline_value": null,
              "target_value": 0.9,
              "comparison_type": "absolute",
              "measurement_method": "Proportion of relevant source text retrieved compared to full source"
            },
            {
              "metric_name": "summary_traceability",
              "baseline_value": 0.55,
              "target_value": 0.8,
              "comparison_type": "absolute",
              "measurement_method": "Traceability scoring post retrieval tuning"
            }
          ],
          "risk_if_not_done": "Possible unresolved retrieval gaps leading to persistent summary inaccuracies and poor faithfulness."
        }
      ],
      "top_priority_experiment_id": "exp_001",
      "recommendation_notes": "Begin experimentation by addressing hallucination and unsupported claims through prompt design changes, as this has the highest severity and confidence. Follow sequentially with evaluation expansion and source chunking improvements before targeting hypothesized retrieval issues requiring more evidence."
    },
    "baseline_reference": null,
    "final_summary": "Output is NOT READY for production. Overall score: 0.53. Primary failure mode: hallucination_or_unsupported_claims. Top recommended experiment: exp_001.",
    "execution_trace": [
      "planner:start",
      "planner:success",
      "scorer:start",
      "scorer:success",
      "diagnosis:start",
      "diagnosis:success",
      "experiment:start",
      "experiment:success"
    ],
    "error": null
  }
}
```

---

## Running Tests

```bash
pytest tests/ -v
```

Tests mock `LLMClient` to avoid real API calls. All tests run in deterministic fallback mode.

---

## Storage

Evaluation runs are persisted in a single SQLite table:

```sql
CREATE TABLE evaluation_runs (
    run_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    execution_time_ms INTEGER NOT NULL,
    baseline_reference TEXT NOT NULL,
    final_summary TEXT NOT NULL,
    full_result_json TEXT NOT NULL
);
```

The full structured result is stored as serialized JSON. No relational schema is used.

---

## File Structure

```
llm_eval_agent/
  app/
    main.py                          # FastAPI app entry point
    api/
      routes.py                      # HTTP endpoints only
    agents/
      planner.py                     # EvaluationPlannerAgent
      scorer.py                      # QualityScoringAgent
      diagnosis.py                   # FailureDiagnosisAgent
      experiment_recommender.py      # ExperimentRecommendationAgent
    core/
      config.py                      # Settings loaded from .env
      llm_client.py                  # Single LLM integration point
      orchestrator.py                # Fixed-sequence pipeline coordination
    schemas/
      evaluation.py                  # Shared enums and type aliases
      planner.py                     # Planner input/output models
      scoring.py                     # Scorer input/output models
      diagnosis.py                   # Diagnosis input/output models
      experiments.py                 # Experiment input/output models
      orchestration.py               # Run-level input/output models
      api.py                         # HTTP request/response models
    storage/
      repository.py                  # SQLite read/write
  tests/
    test_orchestrator.py
    test_repository.py
    test_api.py
  examples/
    sample_request.json
  .env.example
  requirements.txt
  README.md
```

---

## MVP Limitations

- **No authentication** — all endpoints are publicly accessible
- **No UI** — API only; use the `/docs` page for interactive exploration
- **No async job queue** — evaluations run synchronously; long documents may be slow
- **No vector database** — no semantic search or embedding-based retrieval
- **No LangGraph or CrewAI** — pipeline is a simple fixed-sequence Python orchestrator
- **No long-term memory** — each evaluation is independent
- **Input length** — no max length enforcement on `source_document` or `llm_output` (future: add request size middleware)
- **Single process** — no horizontal scaling support in this MVP

---

## 🔧 What I Would Improve With More Time

- Replace deterministic fallbacks with full LLM-driven evaluation
- Add dataset-based evaluation and batch processing
- Introduce experiment tracking across runs
- Integrate with Jira/Linear for real workflow impact
- Add confidence scoring per diagnosis
