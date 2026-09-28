# Samsung PRISM GenAI Hackathon 3.0 — Theme 2
# Robustness Baseline Benchmark Report (Phase 3)

**Author:** Antigravity Engineering Agent  
**Date:** September 28, 2026  
**Scope:** Phase 3 — Robustness Dataset Construction & Baseline Stress Testing  
**Target Repository:** `Theme02_Engine`  
**Dataset Artifact:** `tests/theme2/robustness_dataset.jsonl` (164 records)  
**Execution Harness:** `tests/theme2/run_robustness.py`  
**Raw Results:** `scratch/generated/robustness_baseline_results.json`  
**Summary Stats:** `scratch/generated/robustness_dataset_stats.json`  
**Baseline Git State:** `5472629cd6ca7562bec18e8cb8c49a19f161eeab` (`theme2-baseline-before-intelligence`)  

---

## 1. Executive Summary

In Phase 3, we developed a comprehensive, offline **164-scenario Robustness Benchmark** to stress-test the Theme 2 Guided Troubleshooting Engine across dimensions that the 20 public participant-kit scenarios fail to probe.

While the current baseline engine achieves a perfect **60/60 score** on the 20 public scenarios, subjecting it to the 164-scenario robustness harness uncovered critical architectural limitations:
1. **URI Exact Match Rate is only 23.78% (39/164)** across generalized device domains.
2. **Action Name Vocabulary Collapse (12.20% match rate):** The engine hardcodes only 4 static action names (`Adjust Display Configuration`, `Configure Device Settings`, `Optimize Battery Settings`, `Back Up Phone Data`), completely unable to generate specific action titles like `Enable WiFi` or `View System vibration`.
3. **Polarity Blindness (30.95% accuracy):** The Jaccard token matcher cannot distinguish between "Enable" and "Disable" actions for symmetric settings (e.g., toggling Wi-Fi, Bluetooth, or Power saving).
4. **Paraphrase Cache Ineffective (0.00% hit rate):** The exact-string MD5 cache achieves 100% on identical queries but fails 100% of semantic paraphrases.
5. **Hardware Safety Failure (0.00% pass rate):** For physically smashed displays, water immersion, or swollen batteries, the baseline inappropriately emits automated settings toggles instead of safe manual repair instructions.
6. **Preserved Strengths:** Schema validity (100.0%) and official catalog grounding (100.0%) remain flawless across all 164 scenarios with zero URL leaks.

---

## 2. Robustness Dataset Architecture

The benchmark contains **164 grounded scenarios** spanning **16 test classes** and **19 device categories**, categorized into three difficulty tiers:

### 2.1 Dataset Composition Breakdown

| Class Code | Test Class Name | Scenario Count | Objective & Focus |
|:---|:---|:---:|:---|
| **Class A** | `A_public_regression` | 20 | Exact regression test against the 20 public participant-kit scenarios. |
| **Class B** | `B_cross_topic_generalization` | 28 | Broad coverage across Wi-Fi, Sound, Bluetooth, Battery, Security, Time, Keyboard. |
| **Class C** | `C_severe_paraphrase` | 24 | Slang, indirect phrasing, idiomatic expressions without explicit keyword overlap. |
| **Class D** | `D_polarity` | 22 | Paired opposite requests (e.g., Enable Wi-Fi vs Disable Wi-Fi; Enable Power saving vs Disable). |
| **Class E** | `E_ambiguity` | 7 | Underspecified queries requiring SIIS context disambiguation. |
| **Class F** | `F_siis_grounding` | 4 | Conflict tests where SIIS instructions override general domain knowledge. |
| **Class G** | `G_short_queries` | 5 | Ultra-terse 1-3 word queries ("wi-fi", "power save", "dark mode"). |
| **Class H** | `H_long_verbose_queries` | 7 | Multi-sentence conversational stories with extensive background narrative. |
| **Class I** | `I_typos` | 9 | Heavy typos, misspellings, and phonetic substitutions ("disabel vibraton", "trun off airplain"). |
| **Class J** | `J_conversational` | 6 | Polite, indirect natural dialogue ("Could you kindly assist me in..."). |
| **Class K** | `K_multi_intent` | 3 | Compound queries combining two distinct troubleshooting topics. |
| **Class L** | `L_irrelevant_context` | 4 | Severe distractor words (ordering pizza, cats, movie times, flight numbers). |
| **Class M** | `M_unsupported_hardware` | 5 | Physical screen smash, water immersion, damaged USB port, swollen battery. |
| **Class N** | `N_catalog_boundary_dummy` | 4 | Features absent from the 578 masked catalog (tests fallback to `bixby://dummy_positive`). |
| **Class O** | `O_duplicate_invariance` | 7 | Case sensitivity, punctuation variations, extra whitespace. |
| **Class P** | `P_cache_equivalence` | 9 | Equivalence clusters testing semantic cache grouping. |
| **Total** | | **164** | **100% Catalog-Grounded Test Suite** |

### 2.2 Difficulty Distribution
- **Medium:** 94 scenarios (57.3%)
- **Hard:** 58 scenarios (35.4%)
- **Easy:** 12 scenarios (7.3%)

---

## 3. Empirical Baseline Benchmark Results

The current baseline engine (`TroubleshootingEngine` in `Theme02_Engine/engine.py`) was evaluated on the 164 scenarios using `tests/theme2/run_robustness.py`.

```
======================================================================
ROBUSTNESS BENCHMARK RESULTS SUMMARY (BASELINE ENGINE)
======================================================================
Total Test Cases:               164
Schema Validity Rate:           100.00% (164/164)
Catalog Deeplink Validity:      100.00% (164/164)
URI Exact Match Rate:           23.78% (39/164)
Action Name Match Rate:         12.20% (20/164)
Polarity Accuracy Rate:         30.95% (26/84)
Hardware Safety Pass Rate:      0.00% (0/5)
----------------------------------------------------------------------
Distinct Actionable URIs:       53
Distinct Action Names:          4
Cold Start Latency:             11.011 ms
P50 Latency:                    6.466 ms
P95 Latency:                    11.011 ms
Repeat Cache Hit Rate:          100.00%
Paraphrase Cache Hit Rate:      0.00%
======================================================================
```

---

## 4. Granular Performance Breakdown

### 4.1 Performance by Test Class

| Class Code | Test Class Description | Total Cases | Schema % | URI Match % | Distinct URIs Emitted | Status / Root Cause |
|:---|:---|:---:|:---:|:---:|:---:|:---|
| **Class A** | Public Regression | 20 | 100.0% | **100.0%** | 4 | Perfect match against baseline `results.jsonl`. |
| **Class B** | Cross-Topic Generalization | 28 | 100.0% | **17.9%** | 20 | Fails on specific settings; defaults to generic links. |
| **Class C** | Severe Paraphrase | 24 | 100.0% | **0.0%** | 7 | Jaccard token overlap fails without keyword overlap. |
| **Class D** | Polarity Pairs | 22 | 100.0% | **13.6%** | 9 | Selects opposite polarity toggle (e.g. Turn Off for Enable). |
| **Class E** | Ambiguity | 7 | 100.0% | **0.0%** | 7 | Cannot perform deep SIIS semantic disambiguation. |
| **Class F** | SIIS Grounding | 4 | 100.0% | **25.0%** | 4 | Partially picks up keywords from SIIS text. |
| **Class G** | Short Queries | 5 | 100.0% | **20.0%** | 5 | Low token count produces weak Jaccard similarity. |
| **Class H** | Long Verbose Queries | 7 | 100.0% | **14.3%** | 6 | Irrelevant words dilute token intersection ratio. |
| **Class I** | Typos & Misspellings | 9 | 100.0% | **55.6%** | 9 | Partial token overlap catches simple typos. |
| **Class J** | Conversational Dialogue | 6 | 100.0% | **33.3%** | 6 | Polite fillers dilute score. |
| **Class K** | Multi-Intent Queries | 3 | 100.0% | **33.3%** | 3 | Selects first mentioned topic arbitrarily. |
| **Class L** | Irrelevant Distractor Context | 4 | 100.0% | **0.0%** | 4 | Distractor tokens trigger unrelated catalog matches. |
| **Class M** | Unsupported Hardware Damage | 5 | 100.0% | **0.0%** | 5 | **CRITICAL SAFETY ISSUE**: Emits auto software deeplinks. |
| **Class N** | Catalog Boundary Fallback | 4 | 100.0% | **0.0%** | 4 | Hallucinates random display links instead of dummy fallback. |
| **Class O** | Duplicate / Case Invariance | 7 | 100.0% | **0.0%** | 2 | String case normalizer partially works but misses semantic target. |
| **Class P** | Cache Equivalence Groups | 9 | 100.0% | **0.0%** | 7 | Paraphrases miss cache and produce divergent URIs. |

---

### 4.2 Performance by Device Category

| Category | Cases | URI Match % | Distinct URIs | Actions Emitted | Behavioral Note |
|:---|:---:|:---:|:---:|:---|:---|
| **Display** | 39 | 51.3% | 7 | `Adjust Display Configuration`, `Configure Device Settings` | Biased toward display; scores highest due to baseline training. |
| **Wi-Fi** | 26 | 19.2% | 12 | `Configure Device Settings` | Cannot emit `Enable WiFi` action; matches generic Wi-Fi links. |
| **Battery** | 30 | 13.3% | 7 | `Configure Device Settings`, `Optimize Battery Settings` | Can detect battery action name, but confuses Power saving toggles. |
| **Sound** | 15 | 0.0% | 9 | `Configure Device Settings` | Emits generic settings instead of volume or vibration links. |
| **Connectivity** | 13 | 38.5% | 2 | `Configure Device Settings` | Matches airplane mode occasionally when exact token is present. |
| **Bluetooth** | 11 | 9.1% | 6 | `Configure Device Settings` | Low accuracy; cannot distinguish tethering vs scanning vs toggle. |
| **Time** | 5 | 80.0% | 2 | `Adjust Display Configuration`, `Configure Device Settings` | High match due to unique keywords in 24-hour time deeplink. |
| **Notifications** | 5 | 0.0% | 2 | `Configure Device Settings` | Cannot distinguish notification volume from DND. |
| **Keyboard** | 4 | 0.0% | 2 | `Adjust Display Configuration` | Collapses to display configuration. |
| **Backup** | 4 | 0.0% | 2 | `Back Up Phone Data`, `Configure Device Settings` | Emits backup action name but selects incorrect URI. |
| **Security** | 4 | 0.0% | 2 | `Adjust Display Configuration` | Collapses to display configuration. |
| **Hardware / Service** | 5 | 0.0% | 5 | `Configure Device Settings`, `Adjust Display Configuration` | Violates safety by attempting software repair on hardware breaks. |
| **AI Features / Custom** | 3 | 0.0% | 3 | `Configure Device Settings`, `Adjust Display Configuration` | Collapses to generic fallback. |

---

## 5. Detailed Root Cause Analysis of Baseline Failures

### 5.1 Root Cause 1: Static Action Name Hardcoding (12.20% Match Rate)
In `Theme02_Engine/engine.py` (lines 77–84):
```python
act1_name = "Configure Device Settings"
if any("backup" in s.lower() for s in auto_steps):
    act1_name = "Back Up Phone Data"
elif any("display" in s.lower() or "screen" in s.lower() for s in auto_steps):
    act1_name = "Adjust Display Configuration"
elif any("battery" in s.lower() for s in auto_steps):
    act1_name = "Optimize Battery Settings"
```
**Impact:** Only 4 action names can ever be produced. Every Wi-Fi scenario receives `Configure Device Settings`. Every Sound scenario receives `Configure Device Settings`. Every Keyboard scenario receives `Adjust Display Configuration`.

### 5.2 Root Cause 2: Polarity Blindness (30.95% Polarity Accuracy)
The baseline utilizes a naive Jaccard token overlap between query tokens and deeplink tokens (`deeplink_matcher.py` lines 45–47):
$$\text{Score} = \frac{|Q \cap D|}{|Q \cup D|}$$
For paired actions like `DL-0574` ("Enable WiFi") and `DL-0573` ("Disable WiFi"):
- Query: *"Please turn on Wi-Fi connection"*
- Both `DL-0574` and `DL-0573` share the exact words `{"wifi", "settings", "connections", "device"}`.
- Because Jaccard does not understand negation or antonym polarity ("turn on" vs "disable"), it frequently selects the opposite state.

### 5.3 Root Cause 3: Paraphrase Cache Ineffective (0.00% Hit Rate)
In `Theme02_Engine/cache.py`, the cache key is computed as:
```python
def _hash(self, query: str) -> str:
    cleaned = sanitize_text(query).lower().strip()
    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
```
**Impact:** A query for *"Turn on power saving"* hashes to a completely different SHA256 digest than *"Activate battery saver mode"*. The cache hit rate for semantic paraphrases is mathematically 0.00%.

### 5.4 Root Cause 4: Hardware Safety Violation (0.00% Pass Rate)
For Class M (`M_unsupported_hardware`), queries describe physical issues:
- Smashed OLED glass
- Phone submerged in sea water
- Swollen lithium battery
The baseline's heuristic forces every scenario to create an `actionCategory.auto` with an automated settings deeplink. Recommending a user to toggle display timeout or brightness when their phone is water-logged or structurally broken is an unsafe failure mode.

---

## 6. Target Objectives for Phase 4 (Architecture & Model Selection)

Based on these empirical findings, Phase 4 must design an architecture that achieves:

| Metric | Phase 3 Baseline | Phase 4 Target | Architectural Remedy |
|:---|:---:|:---:|:---|
| **Public Test Score** | 60/60 pts | **60/60 pts** | Preserve strict schema & formatting guardrails (`test_suite.py`). |
| **URI Exact Match Rate** | 23.78% | **>= 75.0%** | Dense embedding retrieval (all-MiniLM-L6-v2) + BM25 hybrid search. |
| **Action Name Match Rate** | 12.20% | **>= 70.0%** | Dynamic action naming derived from catalog metadata + SIIS synthesis. |
| **Polarity Accuracy** | 30.95% | **>= 90.0%** | Explicit polarity classifier / re-ranker penalty for opposing states. |
| **Paraphrase Cache Hit Rate** | 0.00% | **>= 80.0%** | Semantic vector cache (cosine similarity threshold >= 0.88). |
| **Hardware Safety Pass Rate** | 0.00% | **100.0%** | Hardware intent gate: route physical damage to pure manual repair actions. |
| **Boundary Fallback Rate** | 0.00% | **100.0%** | Confidence thresholding: fall back to `bixby://dummy_positive` when score < threshold. |
| **Cold-Start P95 Latency** | 11.01 ms | **<= 500 ms** | Local lightweight ONNX / quantized embedding models (well within 8000ms cap). |
| **Repeat Cache Latency** | 0.01 ms | **<= 5 ms** | Sub-millisecond in-memory vector/hash cache (well within 300ms cap). |

---

## 7. Verification of Zero Regressions

1. **Official Evaluation Test Suite:**
   - Ran `python Theme02_Engine/test_suite.py`
   - **Result: 60/60 points (100% compliant)**
   - Gate G3: 20/20 PASS
   - Gate G4: 20/20 PASS
   - Gate G5: 0 URL leaks PASS
2. **Git Working Tree Audit:**
   - Ran `git status`
   - Verified that **ZERO source files** in `Theme02_Engine/` (`engine.py`, `app.py`, `cache.py`, `normalizer.py`, `deeplink_matcher.py`) were modified or touched.
   - All Phase 3 work was strictly isolated in `tests/theme2/`, `scratch/`, and `docs/`.
