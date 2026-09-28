# Theme 2 Evaluator Specification

**Samsung PRISM GenAI Hackathon 3.0 — 2026–27 Edition**  
*Document Generated: Phase 2 Evaluator Reverse Engineering*  
*Primary Source Documents: `faq.txt` (Theme 2 Q1–Q23), `schema.py`, `Main_Hackathon_Overview.txt` (p. 5, 11), `results.jsonl`, `test_suite.py`*

---

## 1. Scope

This specification defines the exact operational, structural, and mathematical contract enforced by the Samsung automated evaluator and live judging harness for **Theme 2 (Smart Guided Troubleshooting Engine)**. It maps every gate, scoring block, performance threshold, and data schema against the authoritative project files.

---

## 2. Official Scoring Overview

The automated evaluation accounts for **60 points** towards the 30% "Working prototype & functionality" judging category (`Main_Hackathon_Overview.txt`, p. 11; `faq.txt`, Q22).

| Category / Block | Max Points | Core Focus | Authoritative Source |
| :--- | :---: | :--- | :--- |
| **Must-Pass Gates** | **Pass/Fail** | Pre-conditions for score to count (G2, G3, G4, G5) | `faq.txt`, lines 336–347 |
| **Block A1** | **15 pts** | Schema validity, Goal regex, Title & Description word counts, URL scrub, score range | `faq.txt`, lines 352–354 |
| **Block A2** | **15 pts** | Deeplink catalog existence, auto-action actionable deeplink coverage | `faq.txt`, lines 355–361 |
| **Block A3** | **15 pts** | Cold-start latency (≤8s), repeat query latency (p95 ≤300ms, ≥90% hit), paraphrase hit (≥80%) | `faq.txt`, lines 362–364 |
| **Block A4** | **10 pts** | Generalization on unseen scenarios with new SIIS payloads | `faq.txt`, lines 365–367, 374–379 |
| **Block A5** | **5 pts** | Query variation diversity (strictly 8–10 unique paraphrases per query in `results.jsonl`) | `faq.txt`, lines 368–370, 403–408 |
| **TOTAL** | **60 pts** | **Automated Component Score** | `faq.txt`, line 348 |

---

## 3. A1 — Schema & Formatting (15 Points)

*Source: `faq.txt`, lines 150–235, 278–294, 352–354, 436–447; `schema.py`, lines 1–68.*

### Evaluator Checks
1. **Pydantic Deserialization:** The response payload must cleanly validate into `schema.ContextDeeplinkResponse`. Malformed JSON or type mismatches fail validation.
2. **Goal Regex Match:** Every `Goal.goal` string must match the exact regular expression:
   ```regex
   ^Follow these steps to perform this .* (Troubleshooting|Configuration)\.$
   ```
   *Citation:* `faq.txt`, lines 164–165, 281–282. Failure to match regex loses A1 points (line 437).
3. **Title Word Count:** `Goal.title` must be strictly **2 to 3 words**. Truncated, single-word, or 4+ word titles lose points (line 283–284, 441–443).
4. **Action Description Rules:** Every `Action.description` must be strictly **5 to 7 words** and **must start with `"It will"`** (lines 195–199, 285–286, 445–447).
5. **Score Value Range:** `Goal.score` must be a floating-point number between `0.0` and `1.0` (lines 175–179, 287–288, 354).
6. **Zero URL Leaks:** No `http://`, `https://`, `www.`, `.com`, `.html`, markdown links `[text](url)`, or image tags `<img...>` anywhere in any text field (lines 289–290, 426–429).
7. **Steps Requirement:** `StepGroup.steps` must be a non-empty list of strings derived strictly from the SIIS text (lines 221, 291–292).

### Scoring Calculation
- **Max Points:** 15.
- **Formula:** *NOT DETERMINABLE FROM AVAILABLE MATERIAL.* The FAQ does not provide an explicit mathematical sub-weighting per check (e.g. 3 pts per rule). In `test_suite.py`, all checks are tallied collectively.

---

## 4. A2 — Deeplink Validity & Auto-Action Coverage (15 Points)

*Source: `faq.txt`, lines 236–277, 295–320, 355–361, 430–435; `deeplinks.json`.*

### Evaluator Checks
1. **Catalog Existence:** Every emitted `actionableDeeplink.deeplink` must match an existing masked URI verbatim from the 578 entries in `deeplinks.json` (lines 251–255, 359).
2. **Auto-Action Coverage:** Any action with `category == actionCategory.auto` **must** have a non-null `actionableDeeplink` with a non-empty `deeplink` string (lines 300–304, 314–318). Leaving deeplink null for an auto action loses points (line 431–435).
3. **Manual / Critical Actions:** `category == actionCategory.manual` or `actionCategory.critical` does not require an actionable deeplink; `actionableDeeplink` may be `null` (lines 305–313).
4. **Validation Deeplink:** If the matched catalog entry contains a `validation` object, it should be populated in `validationDeeplink` with matching `key`, `resultType`, `condition`, and `value` (lines 270–274, 321–335).
5. **Fallback Entry (`DL-DUMMY`):** If no catalog entry matches, `bixby://dummy_positive` is the only approved placeholder. The system must write its own 5–7 word description and message naming the concrete screen (lines 255, 275–277, 398–402).

### Scoring Calculation
- **Max Points:** 15.
- **Formula:** *NOT DETERMINABLE FROM AVAILABLE MATERIAL.* Exact deduction per missing deeplink is not explicitly published.

---

## 5. A3 — Cache & Latency (15 Points)

*Source: `faq.txt`, lines 362–364, 371–373, 453–455, 476–483; `Main_Hackathon_Overview.txt`, p. 5.*

### Evaluator Methodology
The live scorer queries the running API over HTTP in four distinct stages:
1. **Cold-Start Probe:** Judges send a canonical query from the kit and measure total round-trip response time.
   - **Threshold:** Cold-start p95 **≤ 8.0 seconds** (`faq.txt`, line 364).
2. **Repeat Query Probe:** The scorer sends the exact same query a second time.
   - **Threshold:** Repeat query p95 **≤ 300 ms** with **≥ 90% cache hit rate** (line 364).
   - "No caching → A3 score will be 0 (repeat queries too slow)" (line 454).
3. **Paraphrase Query Probe:** The scorer sends a semantically identical paraphrase of the query.
   - **Threshold:** Paraphrase cache hit rate **≥ 80%** (line 364).
   - "Paraphrases of the original query should also hit the cache (semantic matching). This tests whether your system recognizes that different phrasings map to the same troubleshooting scenario." (lines 372–373).

### Scoring Calculation
- **Max Points:** 15.
- **Formula:** *NOT DETERMINABLE FROM AVAILABLE MATERIAL.* The exact curve between 300ms and 8000ms is not published. If caching is absent, A3 receives 0 points (line 454).

---

## 6. A4 — Generalization / Unseen Scenarios (10 Points)

*Source: `faq.txt`, lines 365–367, 374–379, 482.*

### Evaluator Checks
1. **Unseen Inputs:** Judges transmit test queries not present in the 20-scenario kit, accompanied by new `siis_response` payloads (lines 375–377).
2. **Response Expectation:** The API must produce a **valid, non-empty `ContextDeeplinkResponse`** for these unseen scenarios (lines 367, 377–378).
3. **Purpose:** Tests whether the architecture generalizes across diverse device issues rather than memorizing the 20 public kit scenarios.

### Scoring Calculation
- **Max Points:** 10.
- **Evaluation Criteria:**
  - FACT: `faq.txt` line 367 specifies producing "valid non-empty responses".
  - INFERENCE: Human review will verify that the actions logically correspond to the new SIIS content and do not return generic hardcoded display defaults (`faq.txt`, line 449–451).

---

## 7. A5 — Query Variation Diversity (5 Points)

*Source: `faq.txt`, lines 368–370, 403–408, 461–463; `Theme02_Engine/generate_results.py`.*

### Evaluator Checks
1. **Count Constraint:** In `results.jsonl`, each scenario line must include strictly **between 8 and 10 query variations** in the `query_variations` array (lines 370, 406–407).
   - Penalty: *"Fewer than 8 or more than 10 query variations → lose A5 points"* (line 461–463).
2. **Lexical Diversity:** Variations must exhibit linguistic diversity (vocabulary, sentence structure, formality level) as measured by a lexical diversity scorer (lines 370, 408).

### Scoring Calculation
- **Max Points:** 5.
- **Formula:** *NOT DETERMINABLE FROM AVAILABLE MATERIAL.* The exact mathematical metric for lexical diversity (e.g. Type-Token Ratio, distinct-2, BLEU distance) is not published.

---

## 8. Gates (Must-Pass Pre-Conditions)

*Source: `faq.txt`, lines 336–347, 426–429, 457–460.*

All gates must pass for the automated score to count. Failing any single gate voids the 60-point automated score (`faq.txt`, line 347).

| Gate ID | Condition / Threshold | Verification Method | Consequence of Failure |
| :---: | :--- | :--- | :--- |
| **G1** | *NOT SPECIFIED IN FAQ* | Not listed in official FAQ table (FAQ starts directly at G2). | Unknown. |
| **G2** | `GET /health` returns `{"status": "ok"}` | Scorer calls `/health` at start of evaluation window. | **All live evaluation checks are skipped.** Automated score = 0 (`faq.txt`, line 459). |
| **G3** | `≥ 95%` of test queries covered in results file | Check line count in `results.jsonl` against test suite. | Automated score does not count (`faq.txt`, line 347). |
| **G4** | `≥ 90%` of responses are schema-valid | Pydantic validation across all output responses. | Automated score does not count (`faq.txt`, line 347). |
| **G5** | **Zero URL leaks** in entire output | Regex search for `http://`, `https://`, `www.`, `.com`, `.html`, markdown links. | **Direct gate failure. Score does not count.** (`faq.txt`, line 346, 427–429). |

---

## 9. `results.jsonl` Contract

*Source: `faq.txt`, lines 146–148, 406–424; `Theme02_Engine/results.jsonl`.*

### File Specifications
- **File Name:** `results.jsonl` (placed at the project root or top-level submission directory).
- **Format:** JSON Lines (UTF-8, one JSON record per line).
- **Line Structure:**
  ```json
  {
    "query": "<original_query_string>",
    "query_variations": [
      "<variation_1>",
      "<variation_2>",
      "<variation_3>",
      "<variation_4>",
      "<variation_5>",
      "<variation_6>",
      "<variation_7>",
      "<variation_8>",
      "<variation_9>"
    ],
    "response": {
      "contexts": [ ... ]
    }
  }
  ```
- **Line Count:** Must cover at least 95% of test scenarios (19 of 20 kit scenarios to satisfy Gate G3).
- **Independence from Live Latency:** `results.jsonl` is a static pre-computed submission deliverable. Caching and latency (Block A3) are evaluated separately by live HTTP calls against the running API (`faq.txt`, lines 476–483).

---

## 10. Endpoint Contract

*Source: `faq.txt`, lines 118, 133, 340, 458, 478, 499–500; `Theme02_Engine/app.py`.*

| Endpoint | HTTP Method | Request Body | Expected Response | Official Requirement | Current Engine Status |
| :--- | :---: | :--- | :--- | :--- | :--- |
| **`/health`** | `GET` | *None* | `{"status": "ok"}` (HTTP 200) | **Mandatory** (Gate G2) | **IMPLEMENTED** |
| **`/v1/troubleshoot`** | `POST` | `{"query": str, "siis_response": {"title": str, "content": str}}` | `ContextDeeplinkResponse` (HTTP 200) | **Mandatory** (`faq.txt` Q1, Q2, Q499) | **MISSING** (Exposes `/troubleshoot`) |
| **`/troubleshoot`** | `POST` | Same as above | Same as above | Legacy / Alias route | **IMPLEMENTED** |

> [!CAUTION]
> **Identified Endpoint Discrepancy:**
> Official FAQ lines 118, 133, and 499 explicitly require `POST /v1/troubleshoot`. The existing implementation in `Theme02_Engine/app.py` only binds `/troubleshoot`. An official evaluator calling `/v1/troubleshoot` will receive HTTP 404 Not Found, failing Gate G2/live checks. This must be addressed in Phase 10 by providing `/v1/troubleshoot` alongside `/troubleshoot` as an alias.

---

## 11. Performance Measurement Methodology

*Source: `faq.txt`, lines 362–364, 371–373, 476–483; `scratch/benchmark_baseline.py`.*

| Metric | Target / Threshold | Measurement Mechanism | Scorer Tolerance |
| :--- | :---: | :--- | :--- |
| **Cold-Start p95** | **≤ 8,000 ms** | HTTP round-trip on initial fresh query | Hard cap (Block A3) |
| **Repeat Query p95** | **≤ 300 ms** | HTTP round-trip on immediately repeated query | Target ≤ 300 ms (Block A3) |
| **Repeat Cache Hit Rate** | **≥ 90%** | Fraction of identical queries served from cache | Must be ≥ 90% |
| **Paraphrase Cache Hit Rate**| **≥ 80%** | Fraction of semantic paraphrases served from cache | Must be ≥ 80% |
| **Schema Validity** | **≥ 90%** | Fraction of responses passing `ContextDeeplinkResponse` | Gate G4 must pass |
| **URL Leaks** | **Exactly 0** | Global string search for web protocols/domains | Gate G5 instant failure |

---

## 12. Public vs Hidden Evaluation

| Dimension | Public Evaluation Kit | Official Live Evaluation (Judges) | Status / Evidence |
| :--- | :--- | :--- | :--- |
| **Corpus Scenarios** | 20 public scenarios in `siis_responses.json` | 20 public + undisclosed hidden scenarios | **FACT** (`faq.txt`, lines 375, 482) |
| **Knowledge Base** | 578 masked deeplinks in `deeplinks.json` | Same catalog (unless extended in hidden set) | **FACT** (`faq.txt`, lines 251–255) |
| **Execution Environment**| Local Python script (`test_suite.py`) | Remote HTTP requests to participant server | **FACT** (`faq.txt`, lines 476–483) |
| **Authentication** | None | No headers, no auth tokens | **FACT** (`faq.txt`, lines 499–500) |
| **Paraphrase Testing** | Tested via mock check in `test_suite.py` | Scorer sends real paraphrases over HTTP | **FACT** (`faq.txt`, lines 372, 481) |
| **Hidden Scenario Details**| Inaccessible / undisclosed | Tested during live evaluation window | **UNKNOWN** (Hidden from teams) |

---

## 13. Known Unknowns (Forensic Disclosure)

1. **Gate G1 Identity:** Gate G1 is omitted from the FAQ table (`faq.txt`, lines 339–346). Whether G1 was Git repository cloning, YAML parsing, or a typographical omission is **UNKNOWN**.
2. **A1 Sub-point Allocation:** The exact point breakdown for Goal regex vs Title length vs Description word count within the 15 points of Block A1 is **NOT DETERMINABLE FROM AVAILABLE MATERIAL**.
3. **Lexical Diversity Metric:** The exact formula (TTR, n-gram entropy, edit distance) used by the automated scorer to assess Block A5 query variations is **NOT DETERMINABLE FROM AVAILABLE MATERIAL**.
4. **Number of Judge Evaluation Requests:** The total number of repeat and paraphrase calls executed during the live judge window is **NOT SPECIFIED**.

---

## 14. Baseline Risks Identified in Current Codebase

1. **Paraphrase Cache Failure:** Current `QueryCache` uses exact-string key hashing. Paraphrases suffer a 0% hit rate, failing Block A3.
2. **Missing Endpoint `/v1/troubleshoot`:** Calling judges will receive HTTP 404 unless the route alias is added.
3. **Topic Memorization:** All 20 public responses currently emit `"Adjust Display Configuration"`, using only 4 of 578 deeplinks. Any hidden test in Block A4 involving Wi-Fi, Audio, Battery, or Accounts will be evaluated incorrectly.
4. **Regex Slicing without Grounded Extraction:** Current steps are mechanically chopped from SIIS text using regex rather than extracting coherent instructions.

---

## 15. Implications for Phase 3 (Robustness Testing)

Before any code modification or LLM integration:
1. **Test Suite Expansion:** Phase 3 must construct an adversarial test suite covering multi-topic queries (Wi-Fi, Battery, Sound, Camera, Reset), polarity opposites (Enable vs Disable), and severe paraphrases.
2. **Semantic Cache Verification:** Phase 3 must implement an explicit cache hit verification check (inspecting cache state directly) rather than relying on `para_res is not None`.
3. **Endpoint Aliasing Test:** Phase 3 must include automated HTTP integration tests verifying both `/health` and `/v1/troubleshoot`.
