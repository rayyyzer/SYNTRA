# Theme 2 Baseline Report

**Samsung PRISM GenAI Hackathon 3.0 — 2026–27 Edition**  
*Document Generated: Phase 1 Baseline Execution*  
*Execution Timestamp: 2026-09-28*

---

## 1. Baseline Commit
- **Git Branch:** `main`
- **Initial Checkpoint Tag:** `theme2-baseline-before-intelligence`
- **Scope of Checkpoint:** Captures the pre-intelligence baseline codebase (`Theme02_Engine/`), data preparation exploration (`scratch/`), and Phase 0/1 compliance documentation (`docs/`).

---

## 2. Environment
- **Operating System:** Windows 11 (64-bit)
- **Python Version:** Python 3.14 (compatible with required 3.10–3.12/3.14 environment)
- **Primary Dependencies:**
  - `fastapi==0.141.1`
  - `uvicorn==0.52.4`
  - `pydantic==2.13.5`
  - `pydantic_core==2.46.5`
  - `numpy==2.5.3`
  - `httpx==0.28.1`
  - `pytest==9.1.1`
- **Hardware Profile:** Local CPU execution; no GPU utilized.

---

## 3. Current Architecture

The baseline system consists of a lightweight FastAPI REST wrapper coupled with static text processing and heuristic mapping:

```text
Incoming HTTP Request (POST /troubleshoot)
  │
  ├── 1. QueryCache (cache.py)
  │      └── Exact string lookup (.strip().lower())
  │
  ├── 2. Sanitizer & Formatter (normalizer.py)
  │      ├── Regex URL scrubber (Gate G5 compliance)
  │      ├── Goal regex formatter ("Follow these steps to perform this <Name> Troubleshooting.")
  │      ├── Title word-count formatter (strictly 2–3 words)
  │      └── Description formatter (strictly 5–7 words, starts with "It will")
  │
  ├── 3. Heuristic Controller (engine.py)
  │      ├── Splits SIIS content by punctuation/newlines
  │      ├── Partitions sentences into auto vs manual steps via keyword checks
  │      └── Calls DeeplinkIndex
  │
  ├── 4. Static Deeplink Matcher (deeplink_matcher.py)
  │      └── Hardcoded dictionary matching "backup", "screen"/"display", "battery", or generic settings
  │
  └── 5. Pydantic Response Serialization (schema.py)
         └── Validates ContextDeeplinkResponse before HTTP 200 return
```

---

## 4. Official Evaluator Results

Running the official baseline test suite (`Theme02_Engine/test_suite.py`) over all 20 public scenarios yields:

```text
==================================================
THEME 2 AUTOMATED EVALUATION REPORT
==================================================
Scenarios evaluated: 20

--- MUST-PASS GATES ---
Gate G3 (>=95% coverage):       [PASS] (20/20 scenarios covered)
Gate G4 (>=90% schema valid):    [PASS] (20/20 valid Pydantic models)
Gate G5 (Zero URL leaks):        [PASS] (0 leaks detected)

--- SCORING BLOCKS ---
A1: Schema & Formatting:
    - Goal Regex Valid:         20/20 (100.0%)
    - Title (2-3 words):        20/20 (100.0%)
    - Description Rules:        40 actions validated (100.0%)
A2: Deeplink Coverage:
    - Auto actions with DL:     20/20 (100.0%)
A5: Query Variations:           20/20 (100.0% have 8 variations)

--- A3: CACHING & LATENCY BENCHMARK ---
Cold-start latency:             6.63 ms (Cap: <= 8000 ms) -> [PASS]
Repeat query p95 latency:       0.00 ms (Requirement: <= 300 ms) -> [PASS]
Paraphrase query latency:       5.95 ms (Reported as [PASS] via mock truthy check)

==================================================
VERDICT: ALL GATES PASSED & 100% COMPLIANT (60/60 pts)
==================================================
```

---

## 5. Cold Start Latency

Measured across 20 independent fresh instantiations (`scratch/benchmark_baseline.py`):

| Operation | Min | Median | p95 | Max |
| :--- | :---: | :---: | :---: | :---: |
| **Engine `__init__()`** | 0.992 ms | 1.156 ms | 1.294 ms | 1.294 ms |
| **First Request (Cold Start)** | 5.372 ms | 6.138 ms | 6.627 ms | 6.627 ms |

- **Observations:**
  - Files and dictionary indexes are loaded eagerly in memory during startup.
  - No network calls or heavy external models are initialized.
  - Well within the official cold-start limit of ≤ 8,000 ms.

---

## 6. Warm Request Latency

Measured across 100 iterations of repeat cached queries and 20 uncached fresh compute queries:

| Request Type | Min | p50 | p95 | p99 | Max |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Repeat Request (Cache Hit)** | 0.003 ms | 0.003 ms | 0.003 ms | 0.004 ms | 0.004 ms |
| **Uncached Fresh Compute** | 4.467 ms | 5.367 ms | 8.966 ms | 8.966 ms | 8.966 ms |

- **Observations:**
  - Repeat queries hit the in-memory dictionary in under 4 microseconds (`0.003 ms`), far below the ≤ 300 ms threshold.
  - Uncached heuristic string processing completes in under 9 ms.

---

## 7. Exact Cache Performance

Tested across query normalization variants:
- **Case A: Exact identical query:** **HIT** (0.004 ms)
- **Case B: Exact query + identical SIIS:** **HIT** (0.003 ms)
- **Case C: Identical query with UPPERCASE:** **HIT** (0.003 ms) — handled by `.lower()`
- **Case D: Identical query with extra whitespace:** **HIT** (0.003 ms) — handled by `.strip()`

---

## 8. Paraphrase Cache Performance

Tested against semantic reformulations of public queries:
- **Case E: Semantic paraphrase (different wording):** **MISS** (5.216 ms cold compute)
- **Case F: Semantic paraphrase + same SIIS:** **MISS** (5.182 ms cold compute)
- **Measured Paraphrase Cache Hit Rate:** **0% (0 / 2)**

> [!WARNING]
> In `Theme02_Engine/test_suite.py` line 144, paraphrase cache verification was evaluated with:
> `para_hit = (para_res is not None)`
> This masked the fact that paraphrased queries triggered an uncached compute execution rather than an actual cache hit. The current `QueryCache` has zero semantic capability.

---

## 9. Schema Validation

Validated 100% of all 20 generated responses against official `schema.py`:
- **Total Responses Validated:** 20 / 20 (100%)
- **Validation Failures:** 0
- **Enum Failures:** 0
- **Word-Count Failures:** 0
- **Regex Failures:** 0
- **Missing Required Fields:** 0
- **Nullability Violations:** 0

---

## 10. Deeplink Integrity

Audited against the 578 entries in Samsung's official `deeplinks.json`:
- **Total Actions Generated:** 40 actions (20 Auto, 20 Manual)
- **Actionable Deeplinks Emitted:** 20 (100% valid masked Samsung URIs)
- **Invalid / Hallucinated Deeplinks:** 0
- **Validation Deeplinks Emitted:** 17 valid
- **External URL Leaks:** 0
- **Distinct Actionable URIs Emitted:** **Only 4 distinct URIs** across all 20 scenarios:
  1. `bixby://masked/act/6ffc54f50d` (Display settings default)
  2. `bixby://masked/act/98efd3ab4c` (Display touch settings)
  3. `bixby://masked/act/be0a067b61` (Display brightness settings)
  4. `bixby://masked/act/fd2b86fdd3` (Display refresh/flicker settings)

---

## 11. Public Scenario Results

All 20 public scenarios in `input.txt` concern screen, display, or tablet hardware/software issues. Due to keyword branching in `engine.py`, the baseline implementation produced identical high-level action structures for every scenario:
- **Action 1 (Auto):** `"Adjust Display Configuration"`
- **Action 2 (Manual):** `"Schedule Device Repair Service"`

While this passed the public evaluation rubric, it demonstrates complete lack of topic differentiation.

---

## 12. Confirmed Weaknesses

1. **Hardcoded Topic Assumptions:** The engine branches on hardcoded keywords (`"battery"`, `"display"`, `"backup"`). Any hidden scenario covering Wi-Fi, Sound, Bluetooth, Accounts, or Camera will either fall back to display settings or fail.
2. **False Paraphrase Caching:** The cache has no semantic intent mapping; paraphrases cause a cache miss (0% true hit rate).
3. **Missing Route Alias:** `app.py` exposes `/troubleshoot`, whereas the official FAQ (Theme 2 Q1, Q2, Q499) specifies `/v1/troubleshoot`.
4. **No LLM Intelligence:** Steps are mechanically extracted using regular expressions without understanding the root cause or instructions in the SIIS text.
5. **Polarity Blindness:** The keyword matcher cannot distinguish between requests to turn a feature ON vs turn it OFF.

---

## 13. Facts vs Inferences

### Facts (Directly Verified from Files)
- The baseline passes all 20 public test cases in `Theme02_Engine/test_suite.py` with 60/60 points.
- The baseline repeat query latency is 0.003 ms (p95 ≤ 300 ms).
- The baseline cold-start latency is 6.6 ms (limit ≤ 8,000 ms).
- The baseline emits zero external URLs, passing Gate G5.
- The baseline only uses 4 distinct deeplinks out of 578 available.
- `cache.py` uses exact string key hashing; semantic paraphrases miss the cache.

### Inferences (Engineering Analysis)
- The 60/60 score on the public kit will collapse on hidden tests that introduce non-display troubleshooting topics.
- An official evaluator checking paraphrase cache hits (target ≥ 80%) will fail Block A3 under the current exact-string cache.

---

## 14. Baseline Metrics Table

| Metric | Baseline Measurement | Official Requirement | Status |
| :--- | :---: | :---: | :---: |
| **Official Public Score** | **60 / 60** | 60 max automated | PASS (Public only) |
| **Schema Validity** | **100% (20/20)** | ≥ 90% (Gate G4) | PASS |
| **Deeplink Integrity** | **100% (20/20)** | 100% catalog match | PASS |
| **URL Leaks** | **0 leaks** | 0 leaks (Gate G5) | PASS |
| **Cold-Start p95** | **6.63 ms** | ≤ 8,000 ms | PASS |
| **Warm Request p95** | **0.003 ms** | ≤ 300 ms (Block A3) | PASS |
| **Repeat-Cache Hit Rate** | **100%** | ≥ 90% (Block A3) | PASS |
| **Paraphrase-Cache Hit Rate** | **0%** | ≥ 80% (Block A3) | **FAIL (Defect)** |
| **Startup / Init Time** | **1.16 ms** | Fast local init | PASS |
| **Distinct Deeplinks Used** | **4 / 578** | Semantic coverage | **POOR (Hardcoded)** |

---

## 15. What Must NOT Be Lost During Future Development

1. **Sub-300ms Repeat Latency:** The exact-string caching path must remain intact for identical repeat queries.
2. **Deterministic Schema Compliance:** Pydantic validation and strict regex/word-count normalizers (`normalizer.py`) must be preserved.
3. **Zero URL Leaks (Gate G5):** Aggressive regex sanitization must remain active on all output fields.
4. **Verbatim URI Integrity:** Deeplinks must always be retrieved from catalog constants, never generated by an LLM.
