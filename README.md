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
Generates concrete, testable experiments linked to each diagnosis. Uses a priority formula:
```
priority = severity + diagnosis_type + confidence - effort_penalty
```
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

## 📊 Example Output (Simplified)

**Production readiness:** Not ready  
**Primary failure mode:** Hallucination / unsupported claims  
**Recommended next experiment:** Prompt grounding with explicit citation requirement  

**Key scores:**
- Faithfulness: 0.37
- Completeness: 0.52
- Traceability: 0.41

**Next step:**
Add prompt instruction requiring source citations and re-evaluate against baseline.

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
