# PHASE 6A — DETAILED FAILURE ANALYSIS & CASE TRACE
**Samsung PRISM GenAI Hackathon 3.0 — Theme 2: Smart Guided Troubleshooting Engine**  
**Generated:** 2026-09-28  
**Dataset:** `tests/theme2/robustness_dataset.jsonl` (164 Scenarios)  
**Total Mismatches Analyzed:** 112 Scenarios  

---

## 1. Overview of Mismatches

Out of 164 scenarios evaluated in the offline robustness benchmark:
- **Exact URI Matches:** 52 cases (31.71%)
- **URI Mismatches:** 112 cases (68.29%)

Every single mismatch was individually traced through the execution pipeline (query $\to$ cache $\to$ safety router $\to$ hybrid retrieval $\to$ candidate adjudicator $\to$ output generator) and classified into exactly one mutually exclusive failure category:

| Category Code | Description | Count | % of All Mismatches | % of Actionable Mismatches |
| :---: | :--- | :---: | :---: | :---: |
| **A** | Retrieval Failure (Ranking or Recall) | 45 | 40.2% | **48.9%** |
| **B** | Polarity Failure (Directional Inversion) | 20 | 17.9% | **21.7%** |
| **I** | Benchmark Expectation Problem (Class A Artifact) | 20 | 17.9% | *Excluded* |
| **F** | Catalog Ambiguity (Duplicate Catalog URIs) | 12 | 10.7% | **13.0%** |
| **C** | Semantic Interpretation Failure (Metaphors / Slang) | 8 | 7.1% | **8.7%** |
| **H** | Unsupported Negative Control (Out-of-Catalog Dummy) | 4 | 3.6% | **4.3%** |
| **D** | SIIS Grounding Failure (Context Dependency) | 3 | 2.7% | **3.3%** |
| **E** | Adjudicator Failure (Active LLM Misclassification) | 0 | 0.0% | 0.0% |
| **G** | Cache Failure (Pure Cache Logic Breakdown) | 0 | 0.0% | 0.0% |
| **J** | Other | 0 | 0.0% | 0.0% |
| **TOTAL**| | **112** | **100.0%** | **100.0%** |

*Note: Category I comprises the 20 public regression scenarios where the benchmark expected the broken baseline's output (`bixby://masked/act/6ffc54f50d` "Lock screen wallpaper") for display issues. Subtracting Category I yields 92 genuine, actionable system mismatches.*

---

## 2. Category A: Retrieval Failures (45 Cases)

Category A is the single largest source of mismatches. A deep inspection reveals that Category A bifurcates into two distinct sub-phenomena:

### Sub-Type A1: Ranking Failure (Target in Top 5) — 22 Cases (48.9%)
In nearly half of all retrieval failures, **the retriever succeeded in finding the target in the Top 5 candidates**, but Candidate #1 had a higher fused score than the expected candidate. Because the Adjudicator was running in fallback mode, Candidate #1 was selected automatically.

#### Case Study A1-1: ROB-0021 (Wi-Fi)
- **Query:** `"How do I turn on Wi-Fi on my Samsung Galaxy?"`
- **Expected Action:** `'Enable WiFi'` (`bixby://masked/act/fdd7f62e24`)
- **Generated Action:** `'View WiFi Settings'` (`bixby://masked/act/a487becd3e`)
- **Top 5 Candidates:**
  1. `[DL-0453]` `bixby://masked/act/a487becd3e` | `'View WiFi Settings'` | Score: 1.0505
  2. `[DL-0452]` `bixby://masked/act/fdd7f62e24` | `'Enable WiFi'` | Score: 1.0423
- **Diagnosis:** The difference in score was only **0.0082**! Both BM25 and MiniLM scored `'View WiFi Settings'` slightly higher because of token overlap with "Settings" in the catalog description. A functioning adjudicator or a $+0.05$ imperative action bias would elevate Rank #2 to Rank #1.

#### Case Study A1-2: ROB-0029 (Sound)
- **Query:** `"Open volume settings to turn up media sound"`
- **Expected Action:** `'View Volume Settings'` (`bixby://masked/act/63ed0e1cc0`)
- **Generated Action:** `'Enable Use Volume buttons for media'` (`bixby://masked/act/3f6d0e79f8`)
- **Top 5 Candidates:**
  1. `[DL-0056]` `bixby://masked/act/3f6d0e79f8` | `'Enable Use Volume buttons for media'` | Score: 0.9632
  2. `[DL-0053]` `bixby://masked/act/63ed0e1cc0` | `'View Volume Settings'` | Score: 0.9412
- **Diagnosis:** MiniLM rewarded "media sound" and mapped directly to the dedicated "media volume buttons" toggle rather than the generic volume page. The target was retrieved at Rank #2.

---

### Sub-Type A2: Recall Failure (Target NOT in Top 5) — 23 Cases (51.1%)
In these cases, vocabulary mismatch, missing domain synonyms, or high density of unrelated tokens prevented the expected candidate from reaching the Top 5.

#### Case Study A2-1: ROB-0030 (Sound / Haptics)
- **Query:** `"Enable system vibration feedback for typing and taps"`
- **Expected Action:** `'View System vibration'` (`bixby://masked/act/3d8fd23e82`)
- **Generated Action:** `'Enable Samsung Keyboard'` (`bixby://masked/act/ae50b1f15f`)
- **Diagnosis:** "typing" strongly pulled Candidate `Samsung Keyboard` into Rank #1 ($0.8872$), while "system vibration" was diluted. `View System vibration` scored outside the top 5.

---

## 3. Category B: Polarity Failures (20 Cases)

Polarity failure occurs when a user requests an ENABLE operation and the engine emits a DISABLE action, or vice versa.

### Root Cause 1: Cross-Query Cache Collisions (7 Cases)
In the sequential benchmark, when an "Enable X" query was evaluated, the engine correctly generated the enable response and cached its semantic signature (`__enable__ __feature__`). When the subsequent "Disable X" query arrived, Tier 3 token overlap ($4/5 \text{ tokens} = 80\% \ge 55\%$) caused the cache to falsely return the cached ENABLE response!

- **ROB-0067:** `"Turn off Power saving on my phone"` $\to$ Cache returned cached response from ROB-0066 (`Enable Power saving`).
- **ROB-0069:** `"Turn off Battery protection on my phone"` $\to$ Cache returned cached `Enable Battery protection`.
- **ROB-0075:** `"Turn off Airplane mode on my phone"` $\to$ Cache returned cached `Enable Airplane mode`.
- **ROB-0079:** `"Turn off Auto dim screen on my phone"` $\to$ Cache returned cached `Enable Auto dim screen`.
- **ROB-0081:** `"Turn off Always On Display on my phone"` $\to$ Cache returned cached `Enable Always On Display`.
- **ROB-0083:** `"Turn off Accidental touch protection on my phone"` $\to$ Cache returned cached `Enable Accidental touch protection`.
- **ROB-0085:** `"Turn off App icon badges on my phone"` $\to$ Cache returned cached `Enable App icon badges`.

### Root Cause 2: Naive Phrasal False-Triggers (13 Cases)
The token-level fallback in `detect_query_polarity` matched the isolated word `"off"` inside common English phrases, overriding the actual intent:
- **ROB-0061:** `"About to take off, need flight mode"` $\to$ contains `"take off"` $\to$ flagged as `DISABLE` $\to$ selected `Disable Airplane mode` instead of `Enable Airplane mode`!
- **ROB-0048:** `"Stop my device from eating up battery so fast"` $\to$ contains `"stop"` $\to$ flagged as `DISABLE` $\to$ selected `Disable Battery protection` instead of `Enable Power saving`!
- **ROB-0032:** `"Mute calls and messages during sleep with Do Not Disturb"` $\to$ contains `"mute"` $\to$ flagged as `DISABLE` $\to$ selected `Disable Do not disturb`!

---

## 4. Category F: Catalog Ambiguity & Duplication (12 Cases)

In 12 cases, **the engine emitted the 100% correct setting action**, but the exact-match URI test evaluated to False because the Samsung Galaxy Settings catalog contains multiple distinct deeplink URIs for the exact same message and setting!

| Case ID | Query | Expected URI | Generated URI | Shared Action Message |
| :---: | :--- | :---: | :---: | :--- |
| **ROB-0022** | Disable Wi-Fi connection | `.../act/2efbdb2164` | `.../act/5a1e8cb249` | **Disable WiFi** |
| **ROB-0026** | Turn off Bluetooth completely | `.../act/16e9d836c2` | `.../act/9869d41c47` | **Disable Bluetooth** |
| **ROB-0059** | I want to get on Wi-Fi instead of cellular | `.../act/fdd7f62e24` | `.../act/8ac075a869` | **Enable WiFi** |
| **ROB-0060** | Turn internet antenna on | `.../act/fdd7f62e24` | `.../act/2151a641ed` | **Enable WiFi** |
| **ROB-0073** | Turn off Bluetooth on my phone | `.../act/16e9d836c2` | `.../act/9869d41c47` | **Disable Bluetooth** |
| **ROB-0080** | Turn on Always On Display on my phone | `.../act/3fcf0b9ff3` | `.../act/078e18bf92` | **Enable Always On Display** |
| **ROB-0099** | Disabel wifi connection please | `.../act/2efbdb2164` | `.../act/5a1e8cb249` | **Disable WiFi** |
| **ROB-0102** | Turn off blutooth | `.../act/16e9d836c2` | `.../act/9869d41c47` | **Disable Bluetooth** |
| **ROB-0136** | turn off wi-fi | `.../act/2efbdb2164` | `.../act/5a1e8cb249` | **Disable WiFi** |
| **ROB-0137** | TURN OFF WI-FI | `.../act/2efbdb2164` | `.../act/5a1e8cb249` | **Disable WiFi** |
| **ROB-0142** | turn off bluetooth | `.../act/16e9d836c2` | `.../act/9869d41c47` | **Disable Bluetooth** |
| **ROB-0143** | TURN OFF BLUETOOTH | `.../act/16e9d836c2` | `.../act/9869d41c47` | **Disable Bluetooth** |

**Conclusion:** In all 12 cases, the user experience is flawless and correct. The failure is an artifact of evaluation strictly requiring one specific hash ID among redundant catalog clones.

---

## 5. Category I: Benchmark Expectation Problem (20 Cases)

All 20 cases are in Class A (`A_public_regression`, `ROB-0001` through `ROB-0020`).
- When the benchmark dataset was established in Phase 3, it recorded the broken baseline's emitted URI (`bixby://masked/act/6ffc54f50d` "View Show Lock screen wallpaper", `be0a067b61`, etc.) as the expected URI for the 20 public display scenarios.
- In Phase 5, our engine replaced the hardcoded display default with diverse, accurate settings:
  - `ROB-0007` ("phone screen stays small") $\to$ `Adjust Screen zoom` (`bixby://masked/act/e86867ad27`)
  - `ROB-0015` ("screen flashes when plugged into charger") $\to$ `Disable Charging Feedback` (`bixby://masked/act/961d54a710`)
  - `ROB-0018` ("distorted screen, need diagnostic test") $\to$ `View Send diagnostic data` (`bixby://masked/act/7db5280233`)
  - `ROB-0019` ("screen inputs are delayed, touch lag") $\to$ `View Touch and hold delay` (`bixby://masked/act/bbdd6f0f3e`)
- Because the benchmark expects the baseline's obsolete artifact (`6ffc54f50d`), all 20 count as "mismatches" despite being demonstrably superior.

---

## 6. Category H: Unsupported Boundary Controls (4 Cases)

Class N contains out-of-catalog test cases:
1. `ROB-0131`: Galaxy AI live translation settings
2. `ROB-0132`: Lock screen clock font customization
3. `ROB-0133`: Bixby text call automatic transcription
4. `ROB-0156`: Eye protection shield

In each case, the benchmark expected fallback to `bixby://dummy_positive`. However, because the similarity threshold in `engine.py` was set to `0.20`, the nearest semantic match (e.g. `View Galaxy Avatar` with score $0.6193$) exceeded the threshold, preventing dummy fallback.
- **Remedy:** Calibrating out-of-domain detection or raising the dummy threshold for queries containing uncatalogued feature tokens.

---

## 7. Category D: SIIS Grounding Failures (3 Cases)

In `ROB-0109`, `ROB-0110`, and `ROB-0112` (Class F: `siis_grounding`), the query is generic (e.g. "My phone has a problem"), and the specific troubleshooting action (e.g. clearing email cache or disabling battery saver) is contained solely within the `siis_response["content"]` document.
- In `engine.py`, retrieval currently searches only `query`:
  `candidates = self.retriever.retrieve(query, top_k=5)`
- Because `query` contained no topical keywords and `siis_content` was not fed to the retriever, the retriever had no way of knowing the topic.
- **Remedy:** Concatenate `siis_title` and key nouns from `siis_content` into the retrieval query.
