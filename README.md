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

> **Note:** The evaluation planner ran in deterministic fallback mode
> (LLM call failed on first agent); scoring, diagnosis, and experiment
> recommendation were fully LLM-generated. The pipeline handles partial
> failures gracefully — downstream agents received the fallback plan
> and produced context-sensitive output regardless.

Below is an actual response from the system:

```json
{
  "run_id": "eval_7d0d11857f10",
  "timestamp": "2026-05-03T00:08:03.628781+00:00",
  "execution_time_ms": 84866,
  "final_summary": "Output is NOT READY for production. Overall score: 0.29. Primary failure mode: hallucination_or_unsupported_claims. Top recommended experiment: exp_001.",
  "baseline_reference": null,
  "requires_human_review": true,
  "primary_failure_mode": "hallucination_or_unsupported_claims",
  "recommended_next_experiment_id": "exp_001",
  "error": null,
  "full_result": {
    "run_id": "eval_7d0d11857f10",
    "timestamp": "2026-05-03T00:08:03.628781+00:00",
    "execution_time_ms": 84866,
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
          "Traceability",
          "Faithfulness",
          "Risk / Safety"
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
          "score": 0.15,
          "score_band": "poor",
          "justification": {
            "summary": "The output contains multiple factual inaccuracies and contradicts the source document.",
            "supporting_evidence": [
              "Mangoceuticals announced the sale of its core patents to Intramont for $2 million in cash, with no stock involved.",
              "The agreement gives Mangoceuticals a royalty-free license to continue using the patents.",
              "Intramont receives full control without restrictions.",
              "Series C Preferred Stock pays a 12% non-cumulative dividend and has full voting rights equal to common stock.",
              "The preferred shares automatically convert into common stock after one year at a premium conversion rate.",
              "They rank senior to all other securities in liquidation.",
              "The company cannot redeem these shares under any circumstances."
            ],
            "unsupported_claims": [
              "Sale price is $2 million cash with no stock (source states $20 million payable mainly by stock with $400k cash).",
              "Mangoceuticals has royalty-free license (source says Intramont has a 10% royalty payment obligation to Mangoceuticals).",
              "Intramont receives full control without restrictions (source describes a co-exclusive, irrevocable license with restrictions).",
              "Series C Preferred Stock pays 12% dividend (source says 6% dividend).",
              "Full voting rights equal to common stock (source does not specify voting rights here).",
              "Automatic conversion after one year at premium conversion rate (no such detail in source).",
              "Ranking senior to all other securities in liquidation and no redemption rights (source mentions rights and preferences are detailed elsewhere but no such claims made here)."
            ],
            "missing_items": []
          },
          "confidence": "high"
        },
        {
          "dimension_name": "Completeness",
          "dimension_type": "core",
          "risk_weight": "medium",
          "score": 0.3,
          "score_band": "weak",
          "justification": {
            "summary": "The output omits many critical terms of the IP Purchase Agreement and misrepresents key financial and license aspects.",
            "supporting_evidence": [
              "Output mentions Series C Preferred Stock creation.",
              "Output mentions some terms of stock and licenses."
            ],
            "unsupported_claims": [],
            "missing_items": [
              "Total consideration amount and structure ($20 million total with 980,000 shares of Series C Preferred Stock and $400,000 cash payments with detailed schedule).",
              "Details on cash payment schedule and cure/extension options.",
              "Grant back license terms including 10% royalty payments to Mangoceuticals starting April 24, 2025.",
              "Right of first refusal granted to Intramont for sale of patents until April 24, 2027.",
              "Description of wholly owned subsidiary MangoRx IP Holdings, LLC as purchaser.",
              "The fact that the issuance of Series C Shares was exempt from registration and related transfer restrictions."
            ]
          },
          "confidence": "high"
        },
        {
          "dimension_name": "Traceability",
          "dimension_type": "core",
          "risk_weight": "high",
          "score": 0.2,
          "score_band": "poor",
          "justification": {
            "summary": "Many claims in the output cannot be traced or are contradicted by the source document.",
            "supporting_evidence": [
              "Statements about the sale price and payment method are contradicted by source text in Item 1.01.",
              "Royalty and license conditions described in the source differ from output assertions.",
              "Dividend rate and rights of Series C Preferred Stock in output differ from those noted in source."
            ],
            "unsupported_claims": [
              "The $2 million cash consideration with no stock.",
              "Royalty-free license granted to Mangoceuticals.",
              "Full voting rights equal to common stock with 12% dividend.",
              "Automatic conversion and senior liquidation preference features."
            ],
            "missing_items": [
              "Reference to the exact source paragraphs or exhibit citations is missing from the output."
            ]
          },
          "confidence": "high"
        },
        {
          "dimension_name": "Relevance",
          "dimension_type": "core",
          "risk_weight": "low",
          "score": 0.65,
          "score_band": "strong",
          "justification": {
            "summary": "The output generally addresses the user goal of summarizing the Form 8-K but includes inaccurate content.",
            "supporting_evidence": [
              "The output focuses on the patent sale and Series C Preferred Stock terms.",
              "Mentions licensing aspects and payment terms."
            ],
            "unsupported_claims": [
              "Inaccurate financial and licensing details detract from relevance but overall on-topic."
            ],
            "missing_items": []
          },
          "confidence": "high"
        },
        {
          "dimension_name": "Risk / Safety",
          "dimension_type": "core",
          "risk_weight": "high",
          "score": 0.1,
          "score_band": "poor",
          "justification": {
            "summary": "The output is misleading about financial terms, ownership rights, and royalties, potentially causing harmful misunderstandings.",
            "supporting_evidence": [
              "Misstates purchase price and payment method.",
              "Incorrect royalty licensing details.",
              "Wrong dividend rate and stock rights.",
              "Claims about control and redemption rights that are unsupported."
            ],
            "unsupported_claims": [
              "Sale price and payment type.",
              "License terms as royalty-free to Mangoceuticals.",
              "Preferred stock dividend, conversion, and voting rights.",
              "Claim that company cannot redeem shares."
            ],
            "missing_items": [
              "Disclosure of obligations to make royalty payments to Mangoceuticals.",
              "Details about cure periods for missed cash payments.",
              "Restrictions on stock transfer and registration exemptions."
            ]
          },
          "confidence": "high"
        },
        {
          "dimension_name": "Business Usefulness",
          "dimension_type": "core",
          "risk_weight": "medium",
          "score": 0.25,
          "score_band": "weak",
          "justification": {
            "summary": "Due to multiple inaccuracies and omissions, the output is of limited utility for making informed business decisions.",
            "supporting_evidence": [
              "Incorrect financial summary impairs valuation assessment.",
              "Misstated license terms affect understanding of IP control and revenue.",
              "Inaccurate stock terms diminish ability to assess equity impact."
            ],
            "unsupported_claims": [],
            "missing_items": [
              "Clear and accurate breakdown of payment terms and stock issuance.",
              "Royalty obligations and rights of first refusal important for risk assessment.",
              "Full rights and preferences of Series C stock as outlined in source."
            ]
          },
          "confidence": "high"
        },
        {
          "dimension_name": "Information Prioritization",
          "dimension_type": "case_specific",
          "risk_weight": "low",
          "score": 0.4,
          "score_band": "weak",
          "justification": {
            "summary": "The output prioritizes some stock details before correctly summarizing the core patent purchase agreement, but critical errors reduce its effectiveness.",
            "supporting_evidence": [
              "First paragraph addresses the patent sale (although inaccurately).",
              "Second paragraph describes preferred stock terms."
            ],
            "unsupported_claims": [],
            "missing_items": [
              "Correct prioritization of accurate financial terms first.",
              "Clear explanation of licensing and royalty obligations.",
              "Mention of subsidiary purchaser and right of first refusal."
            ]
          },
          "confidence": "high"
        }
      ],
      "overall_score": 0.293,
      "scoring_notes": "The output contains numerous factual errors and omissions that undermine faithfulness, traceability and risk safety, requiring human review before use.",
      "requires_human_review": true
    },
    "failure_diagnosis_output": {
      "diagnoses": [
        {
          "diagnosis_type": "observed_failure",
          "failure_category": "hallucination_or_unsupported_claims",
          "severity": "critical",
          "root_cause_summary": "The output contains multiple unsupported and factually incorrect claims about financial terms, license conditions, and stock rights that contradict the source document.",
          "supporting_evidence": [
            "Sale price is $2 million cash with no stock (source states $20 million payable mainly by stock with $400k cash).",
            "Mangoceuticals has royalty-free license (source says Intramont has a 10% royalty payment obligation to Mangoceuticals).",
            "Intramont receives full control without restrictions (source describes a co-exclusive, irrevocable license with restrictions).",
            "Series C Preferred Stock pays 12% dividend (source says 6% dividend).",
            "Full voting rights equal to common stock (source does not specify voting rights here).",
            "Automatic conversion after one year at premium conversion rate (no such detail in source).",
            "Ranking senior to all other securities in liquidation and no redemption rights (source mentions rights and preferences are detailed elsewhere but no such claims made here)."
          ],
          "confidence": "high",
          "evidence_needed": "Access to the original source document or Form 8-K disclosures to validate all financial and license related claims.",
          "recommended_experiment_signals": [
            "Reduced hallucinated financial figures or licensing terms in the output.",
            "Improved alignment of summarized terms with source document content."
          ]
        },
        {
          "diagnosis_type": "observed_failure",
          "failure_category": "missing_information",
          "severity": "high",
          "root_cause_summary": "Critical terms and details from the IP Purchase Agreement are omitted, including payment schedules, license royalties, rights of first refusal, subsidiary purchaser details, and registration exemption disclosures.",
          "supporting_evidence": [
            "Total consideration amount and structure ($20 million total with 980,000 shares of Series C Preferred Stock and $400,000 cash payments with detailed schedule).",
            "Details on cash payment schedule and cure/extension options.",
            "Grant back license terms including 10% royalty payments to Mangoceuticals starting April 24, 2025.",
            "Right of first refusal granted to Intramont for sale of patents until April 24, 2027.",
            "Description of wholly owned subsidiary MangoRx IP Holdings, LLC as purchaser.",
            "The fact that the issuance of Series C Shares was exempt from registration and related transfer restrictions."
          ],
          "confidence": "high",
          "evidence_needed": "Complete source contract or summary document listing these provisions.",
          "recommended_experiment_signals": [
            "Increase in inclusion of detailed payment and license terms.",
            "Improved inclusion of purchaser entity and transfer restriction details."
          ]
        },
        {
          "diagnosis_type": "observed_failure",
          "failure_category": "incomplete_extraction",
          "severity": "high",
          "root_cause_summary": "Important financial and licensing information was incompletely extracted or omitted from the summary, limiting completeness and utility.",
          "supporting_evidence": [
            "Missing payment terms and stock issuance details critical for understanding the deal structure.",
            "Omission of royalty obligations and right of first refusal reduces completeness.",
            "Absence of Series C stock rights and preferences as outlined in source."
          ],
          "confidence": "high",
          "evidence_needed": "Verification with original documents to identify all expected extraction fields.",
          "recommended_experiment_signals": [
            "Expanded coverage of extracted fields matching the source.",
            "Reduction in omitted key contractual provisions."
          ]
        },
        {
          "diagnosis_type": "hypothesized_root_cause",
          "failure_category": "retrieval_issues",
          "severity": "medium",
          "root_cause_summary": "Low traceability combined with lack of retrieval metadata suggests the model may have generated unsupported information in absence of appropriate source references.",
          "supporting_evidence": [
            "Traceability scored 0.2 with multiple claims untraceable or contradicted by source.",
            "No retrieval metadata available making source referencing impossible."
          ],
          "confidence": "low",
          "evidence_needed": "Access to model retrieval logs or source citations for output claims.",
          "recommended_experiment_signals": [
            "Improved source referencing and claim traceability with retrieval metadata.",
            "Reduction in hallucinations linked to retrieval capability improvements."
          ]
        }
      ],
      "primary_failure_mode": "hallucination_or_unsupported_claims",
      "diagnosis_notes": "The most critical issue is the presence of multiple unsupported claims that contradict the source, severely undermining the summary's faithfulness and business usefulness. Missing critical contract details further compound this failure, affecting completeness and safety. Improving retrieval traceability and robust extraction processes could mitigate hallucinations and missing information."
    },
    "experiment_recommendation_output": {
      "experiments": [
        {
          "experiment_id": "exp_001",
          "linked_failure_category": "hallucination_or_unsupported_claims",
          "linked_diagnosis_type": "observed_failure",
          "validates_failure_mode": "generation of unsupported and factually incorrect claims",
          "experiment_type": "prompt_change",
          "scope": "prompt_only",
          "priority": "critical",
          "effort": "medium",
          "status": "recommended",
          "depends_on_experiment_id": null,
          "baseline_reference": null,
          "diagnostic_goal": null,
          "recommendation": "Redesign prompt to explicitly instruct the model to only produce information directly supported by the source document and request citations for all claims.",
          "test_design": "Develop a controlled prompt variant emphasizing strict adherence to source content and requiring explicit referencing of claims. Compare output against the original prompt outputs for hallucination reduction.",
          "expected_outcome": "Significant reduction in unsupported and factually incorrect financial and license claims, verified by increased alignment with source document contents.",
          "success_criteria": [
            {
              "metric_name": "Rate of hallucinated claims in output",
              "baseline_value": 0.35,
              "target_value": 0.05,
              "comparison_type": "absolute",
              "measurement_method": "Manual annotation or automated hallucination detection comparing outputs against source text"
            },
            {
              "metric_name": "Alignment of summarized terms with source document",
              "baseline_value": 0.55,
              "target_value": 0.9,
              "comparison_type": "absolute",
              "measurement_method": "Content overlap scoring or expert review"
            }
          ],
          "risk_if_not_done": "Continued dissemination of inaccurate or misleading financial and licensing information that could impact business decisions."
        },
        {
          "experiment_id": "exp_002",
          "linked_failure_category": "missing_information",
          "linked_diagnosis_type": "observed_failure",
          "validates_failure_mode": "omission of critical payment schedules, royalties, and transfer restriction details",
          "experiment_type": "source_chunking_review",
          "scope": "hybrid",
          "priority": "high",
          "effort": "medium",
          "status": "recommended",
          "depends_on_experiment_id": "exp_001",
          "baseline_reference": null,
          "diagnostic_goal": null,
          "recommendation": "Review and optimize source chunking strategy to ensure all critical contractual provisions are included in the model input context.",
          "test_design": "Modify chunking parameters to preserve continuity of critical clauses and compare the presence of payment, license, and entity details in generated summaries.",
          "expected_outcome": "Greater inclusion of payment schedule, license royalties, rights of first refusal, subsidiary purchaser details, and registration exemption disclosures in outputs.",
          "success_criteria": [
            {
              "metric_name": "Coverage rate of critical contractual provisions",
              "baseline_value": 0.5,
              "target_value": 0.85,
              "comparison_type": "absolute",
              "measurement_method": "Manual or automated checklist verification against source documents"
            }
          ],
          "risk_if_not_done": "Persistent omission of vital contract details reduces the usefulness and trustworthiness of the summary for business audiences."
        },
        {
          "experiment_id": "exp_003",
          "linked_failure_category": "incomplete_extraction",
          "linked_diagnosis_type": "observed_failure",
          "validates_failure_mode": "incomplete or omitted financial and licensing information extraction",
          "experiment_type": "output_schema_change",
          "scope": "schema_only",
          "priority": "high",
          "effort": "low",
          "status": "recommended",
          "depends_on_experiment_id": "exp_002",
          "baseline_reference": null,
          "diagnostic_goal": null,
          "recommendation": "Introduce a structured output schema requiring explicit extraction fields for all expected financial and licensing information.",
          "test_design": "Implement and enforce a standardized output schema during inference that forces model outputs to explicitly include all key financial and licensing provisions.",
          "expected_outcome": "Improved completeness and structured extraction of all relevant contractual details with less omission.",
          "success_criteria": [
            {
              "metric_name": "Completeness score of extracted financial and licensing fields",
              "baseline_value": 0.6,
              "target_value": 0.9,
              "comparison_type": "absolute",
              "measurement_method": "Automated schema validation and manual spot checks"
            }
          ],
          "risk_if_not_done": "Summaries remain incomplete and lack critical details necessary for accurate interpretation by business users."
        },
        {
          "experiment_id": "exp_004",
          "linked_failure_category": "retrieval_issues",
          "linked_diagnosis_type": "hypothesized_root_cause",
          "validates_failure_mode": "lack of retrieval metadata leading to unsupported generation",
          "experiment_type": "retrieval_tuning",
          "scope": "retrieval_only",
          "priority": "medium",
          "effort": "medium",
          "status": "requires_more_evidence",
          "depends_on_experiment_id": null,
          "baseline_reference": null,
          "diagnostic_goal": "Determine if improving retrieval metadata and traceability reduces hallucinations and improves source referencing in summaries.",
          "recommendation": "Enhance retrieval system to include source citations and metadata linkage to each fragment of information provided to the model.",
          "test_design": "Tune retrieval parameters to add explicit metadata and traceability to retrieved document chunks; evaluate impact on hallucination and referencing quality.",
          "expected_outcome": "Better traceability of claims to source documents, reduced hallucination rate linked to retrieval quality improvements, and clearer source attributions.",
          "success_criteria": [
            {
              "metric_name": "Frequency of source citations in output",
              "baseline_value": 0.1,
              "target_value": 0.7,
              "comparison_type": "absolute",
              "measurement_method": "Automated detection of in-text citation presence"
            },
            {
              "metric_name": "Hallucination rate linked to retrieval issues",
              "baseline_value": 0.3,
              "target_value": 0.1,
              "comparison_type": "absolute",
              "measurement_method": "Manual or automated hallucination analysis"
            }
          ],
          "risk_if_not_done": "Retrieval deficiencies remain unaddressed, potentially perpetuating unsupported generation and undermining trustworthiness."
        }
      ],
      "top_priority_experiment_id": "exp_001",
      "recommendation_notes": "Start with prompt redesign to reduce hallucinations, then improve source chunking and structured schema extraction to enhance completeness, followed by retrieval tuning after sufficient evidence is gathered."
    },
    "baseline_reference": null,
    "final_summary": "Output is NOT READY for production. Overall score: 0.29. Primary failure mode: hallucination_or_unsupported_claims. Top recommended experiment: exp_001.",
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

---

## 🧠 AI-Assisted Development Approach

This project was built using a structured AI-assisted workflow, combining deliberate system design with LLM-supported implementation.

### Approach

- **Design (ChatGPT)**
  - Defined architecture, agent responsibilities, and evaluation framework
  - Designed schema contracts and orchestration logic
  - Framed the product problem and differentiation from existing approaches (e.g., RAGAS, G-Eval)

- **Implementation (Claude Code)**
  - Generated Python modules based on a strict implementation prompt
  - Produced initial Pydantic schemas and agent scaffolding

- **Review & Refinement (ChatGPT)**
  - Reviewed code for structural consistency and clarity
  - Identified and corrected issues such as missing dependencies and over-complexity
  - Ensured the system remained modular, explainable, and aligned with the design

I can explain and justify every design decision in this system end-to-end. I cannot claim to have written every line of Python from scratch.