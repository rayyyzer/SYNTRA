# Theme 2 Project State & Baseline Tracker

**Samsung PRISM GenAI Hackathon 3.0 — Theme 2**  
*Document Generated: Phase 0/1 Handoff*  
*Last Updated: 2026-09-28*

---

## 1. Project Overview & Target
- **Theme:** Theme 02 — Smart Guided Troubleshooting Engine
- **Core Problem:** Translating natural-language Galaxy device complaints into grounded, step-by-step troubleshooting guides with exact, un-hallucinated Samsung Galaxy Settings deeplinks.
- **Deliverable:** 
  1. Live REST API (`GET /health` and `POST /v1/troubleshoot`)
  2. Pre-generated offline results (`results.jsonl`) with 8–10 paraphrases per query
  3. Git repository tagged `PRISM_GENAI_HACKATHON_Y2026` with reproducible Docker setup, 5-minute video, 12-slide PPT, and completed AI Disclosure.

---

## 2. Current Architecture Snapshot

```text
User Query + SIIS Response Payload
           │
           ▼
     [ app.py ] (FastAPI REST service: /health, /troubleshoot)
           │
           ▼
    [ engine.py ] (TroubleshootingEngine controller)
     ├── 1. cache.py (Exact MD5/string query lookup)
     ├── 2. normalizer.py (Scrub URLs, format Goal regex, word counts)
     ├── 3. deeplink_matcher.py (Static keyword lookup dictionary)
     └── 4. schema.py (Official Pydantic v2 ContextDeeplinkResponse validation)
```

---

## 3. Inventory of Relevant Files

### Official Student Kit (`Theme02_Input_Kit/student_kit/`)
- `schema.py`: Official Pydantic v2 response models (`ContextDeeplinkResponse`, `Goal`, `Action`, `StepGroup`, `Deeplink`, `ValidationDeepLink`).
- `deeplinks.json`: 578 masked Galaxy Settings deeplink entries + `DL-DUMMY` fallback.
- `siis_responses.json`: 20 official training/testing troubleshooting scenarios.
- `sample_output.json`: Canonical reference JSON response.
- `input.txt`: 20 natural-language device issue queries.

### Existing Implementation (`Theme02_Engine/`)
- `app.py`: FastAPI application exposing `GET /health` and `POST /troubleshoot`.
- `engine.py`: Core controller assembling `ContextDeeplinkResponse` via heuristic branching.
- `cache.py`: Python dictionary-based exact query cache.
- `normalizer.py`: Regex sanitizers enforcing Goal regex, title (2-3 words), and description (5-7 words, "It will").
- `deeplink_matcher.py`: Heuristic keyword-to-URI index for display, battery, and backup.
- `generate_results.py`: Batch runner generating `results.jsonl` over the 20 kit scenarios.
- `results.jsonl`: 20-line offline results file with 8 paraphrases per scenario.
- `test_suite.py`: Local automated scorer checking Gates G2–G5 and Blocks A1, A2, A3, A5.

### Standalone Prototypes & Exploration (`scratch/`)
- `scratch/prepare_deeplinks.py`: Statistical audit, cleaner, and exporter for `deeplinks.json`.
- `scratch/search_deeplinks.py`: Multi-field Okapi BM25 candidate retriever (<1ms latency).
- `scratch/generated/cleaned_deeplinks.json`: Cleaned, validated copy of the 578 entries.
- `scratch/generated/stats.json`: Formal dataset statistics.
- `scratch/PHASE_1_REPORT.md`: Comprehensive data quality & BM25 benchmark findings.

### Official Compliance Documents (`docs/`)
- `docs/COMPLIANCE_MATRIX.md`: 31-point official requirement traceability matrix.
- `docs/SUBMISSION_REQUIREMENTS.md`: Complete guide to Git tagging, deck structure, video, and formats.
- `docs/PROJECT_STATE.md`: This tracking document.

---

## 4. Working Features (Verified)
- ✅ Gate G2 compliance: `GET /health` returns `{"status": "ok"}`.
- ✅ Gate G4 compliance: 100% (20/20) responses validate against Pydantic schema.
- ✅ Gate G5 compliance: Zero URL leaks (`http://`, `https://`, `www.`, `.com`, `.html` completely scrubbed).
- ✅ Block A1 compliance: Goal regex `^Follow these steps to perform this .* (Troubleshooting|Configuration)\.$` passes 100%; titles are strictly 2–3 words; action descriptions strictly 5–7 words starting with "It will".
- ✅ Block A2 compliance: Auto actions always contain non-null actionable deeplinks.
- ✅ Block A3 (Repeat Latency): Cold-start ~1.2ms, repeat query p95 < 0.05ms (sub-300ms requirement comfortably met).
- ✅ Block A5 compliance: Every entry in `results.jsonl` contains exactly 8 diverse query variations.
- ✅ Phase 1 BM25 Candidate Retrieval: Zero-dependency search runs in `<0.8ms` with 100% exact URI preservation.

---

## 5. Known Bugs, Weaknesses & Risks

1. **Endpoint Route Discrepancy:**
   - `app.py` currently binds `POST /troubleshoot`.
   - Official FAQ (Theme 2 Q1, Q2, Q499) specifies **`POST /v1/troubleshoot`**.
   - *Impact:* Official evaluators querying `/v1/troubleshoot` will receive 404 Not Found.
2. **Hardcoded / Heuristic Logic in `engine.py`:**
   - The current engine uses static string checks (`"battery"`, `"display"`, `"backup"`).
   - *Impact:* 100% failure on Block A4 (Generalization on Unseen Scenarios - 10 pts).
3. **Pseudo-Semantic Cache:**
   - `cache.py` only hashes exact raw query strings.
   - In `test_suite.py`, paraphrase cache testing was mocked (`para_hit = (para_res is not None)`), hiding the fact that paraphrased queries actually miss the cache!
   - *Impact:* Evaluator checking semantic cache hit rate (≥80%) will fail Block A3.
4. **No LLM Reasoning or Dynamic Step Extraction:**
   - Steps are currently sliced by regex from SIIS content without semantic comprehension of the specific fault.
   - *Impact:* Fails human judging on technical depth (25%) and innovation (20%).
5. **Polarity Blindness in BM25:**
   - "Enable power saving" and "Disable power saving" share identical lexical scores.
   - *Impact:* Retrieval alone cannot select between toggle-on (`onURL`) and toggle-off (`offURL`).

---

## 6. Official Evaluator Score Baseline (Phase 1 Verified)
- **Local Test Suite (`test_suite.py`):** **60 / 60 points** (against the 20 public kit scenarios).
- **Gate G3 Coverage:** 100% (20/20)
- **Gate G4 Schema Validity:** 100% (20/20)
- **Gate G5 URL Leaks:** 0 leaks
- **Cold-Start p95:** 6.63 ms (cap ≤ 8,000 ms)
- **Warm Repeat p95:** 0.003 ms (cap ≤ 300 ms)
- **Repeat-Cache Hit Rate:** 100%
- **Paraphrase-Cache Hit Rate:** **0% (Defect uncovered)**
- **Distinct Deeplinks Emitted:** 4 / 578
- **Baseline Report:** Tracked in `docs/BASELINE_REPORT.md`

---

## 7. Current Project Phase
- **Completed:** 
  - **PHASE 0 — COMPLIANCE** (`docs/COMPLIANCE_MATRIX.md`, `docs/SUBMISSION_REQUIREMENTS.md`)
  - **PHASE 1 — BASELINE** (`docs/BASELINE_REPORT.md`, Git tag `theme2-baseline-before-intelligence`)
  - **PHASE 2 — EVALUATOR REVERSE ENGINEERING** (`docs/EVALUATOR_SPEC.md`, `scratch/generated/evaluator_spec.json`)
  - **PHASE 3 — ROBUSTNESS DATASET & TESTING** (`tests/theme2/robustness_dataset.jsonl`, `tests/theme2/run_robustness.py`, `docs/ROBUSTNESS_BASELINE.md`, `scratch/generated/robustness_baseline_results.json`, `scratch/generated/robustness_dataset_stats.json`)
  - **PHASE 4 — ARCHITECTURE & MODEL SELECTION** (`docs/ARCHITECTURE_PROPOSAL.md`, `scratch/generated/retrieval_benchmark.json`, `scratch/generated/model_selection.json`, `scratch/benchmark_retrievers.py`)
- **Phase 4 Retrieval Benchmark Findings (on 164 Robustness Cases):**
  - **Baseline Jaccard:** 15.85% Top-1, 15.85% Top-3, 26.19% Polarity, 5.62 ms latency
  - **Pure Multi-Field BM25:** 16.46% Top-1, 38.41% Top-3, 33.33% Polarity, 1.25 ms latency
  - **BM25 + Polarity Re-ranking:** 25.61% Top-1, 41.46% Top-3, 65.48% Polarity, 2.24 ms latency
  - **Dense Embedding (all-MiniLM-L6-v2):** 30.49% Top-1, 53.05% Top-3, 46.43% Polarity, 25.0% Severe Paraphrase, 9.50 ms latency
  - **Hybrid (Dense + BM25 + Polarity):** 32.93% Top-1, 48.78% Top-3, 71.43% Polarity, 29.2% Severe Paraphrase, 12.17 ms latency
- **Selected Target Architecture:**
  - **Hybrid Retrieval:** Multi-Field BM25 + all-MiniLM-L6-v2 + Polarity Re-ranker (<15ms)
  - **Adjudication Engine:** Single Post-Retrieval LLM Call (`gemini-2.5-flash`) with Pydantic JSON schema & 2500ms timeout guard
  - **Zero-Outage Resilience:** Top-1 candidate from Hybrid Retriever acts as automatic instant fallback if LLM is unavailable
  - **Two-Tier Cache:** Tier 1 Exact Hash (<0.01ms) + Tier 2 Semantic Cosine Vector Cache (<2ms, threshold=0.88)
  - **Safety Router:** Pre-retrieval hardware/physical damage triage routing to manual repair service
- **Current Phase:** **PHASE 5 — IMPLEMENTATION (NEXT)**
- **Next Step:** Execute Phase 5 implementation according to the 5-step roadmap: bind `/v1/troubleshoot`, integrate Hybrid Retriever + Polarity Re-ranker + Two-Tier Cache, integrate Gemini 2.5 Flash adjudicator with fallback, and regenerate `results.jsonl`.

---

## 5. Phase 5 Production Implementation Status (Completed)

- **Official Scorer Conformance:** 60/60 points maintained on `Theme02_Engine/test_suite.py`.
- **Offline Robustness Benchmark (164 Scenarios):**
  - **Schema Validity:** 100.0% (164/164)
  - **URI Match Rate:** 31.71% (52/164) — up from 23.78% baseline
  - **Action Match Rate:** 40.24% (66/164) — up from 12.20% baseline (>3.3x)
  - **Polarity Match Rate:** 64.29% (54/84) — up from 30.95% baseline (>2.0x)
  - **Hardware Safety:** 100.0% (5/5) — up from 0.0% baseline
  - **Paraphrase Cache Hit Rate:** 100.0% (6/6) — up from 0.0% baseline
  - **Repeat Query P95 Latency:** 0.02 ms (sub-300ms cap passed)
  - **Cold-Start Response Latency:** 74.36 ms (sub-8000ms cap passed)
  - **Emitted Deeplink Diversity:** 87 distinct URIs (collapse warning eliminated)
- **Detailed Report:** See `docs/PHASE_5_IMPLEMENTATION_REPORT.md`
