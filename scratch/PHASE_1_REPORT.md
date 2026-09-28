# Phase 1: Data Preparation & Retrieval Prototype Report

**Samsung PRISM GenAI Hackathon 3.0 — Theme 2**  
*Artifact Date: 2026-09-28*

---

## 1. Dataset Structure & Core Metadata

The authoritative catalog file is located at:
`participant-kit-all-themes/participant-kit/Theme02_Input_Kit/student_kit/deeplinks.json`

### Root Structure
```json
{
  "_readme": "Catalog of Galaxy Settings deeplinks for the hackathon. URIs are MASKED placeholders: match on description, message, qna_description and originalType, then copy the URI verbatim. bixby://dummy_positive is the only generic placeholder; see its entry.",
  "count": 578,
  "deeplinks": [ ... ]
}
```

### Entry Schema Fields
Each entry in the `deeplinks` list contains 8 fields:
1. `id` (`str`): Unique identifier (e.g., `"DL-0001"` through `"DL-0577"`, plus `"DL-DUMMY"`).
2. `deeplink` (`str`): The exact masked Bixby URI (e.g., `"bixby://masked/act/aa73a35e8d"` or `"bixby://dummy_positive"`). **Must never be altered or hallucinated.**
3. `message` (`str`): Short action / button text (e.g., `"Switch Time Format"`, `"Enable Power saving"`).
4. `description` (`str`): Setting location description (e.g., `"Opens the 24-hour time format settings page in device Settings on the device."`).
5. `qna_description` (`str` | `null`): Functional description explaining purpose and symptoms (e.g., `"Switches between 12-hour and 24-hour time format..."`).
6. `originalType` (`str` | `null`): Action URL type (`"onClickURL"`, `"onURL"`, `"offURL"`, `"updateURL"`, `"placeholder"`, or `null`).
7. `control_type` (`int` | `null`): UI control mapping (`null`, `2`, `3`, `5`).
8. `validation` (`dict` | `null`): Verification criteria dictionary containing:
   - `deeplink`: Corresponding validation URI (e.g., `"bixby://masked/val/..."`).
   - `key`: Setting key name (e.g., `"Use 24-hour format"`).
   - Optional: `resultType` (`"boolean"`), `condition` (`"equal"`), `value` (`"True"`).

---

## 2. Data-Quality Findings & Statistics

Through deep automated inspection (`scratch/prepare_deeplinks.py`), we determined the following facts:

| Metric | Measured Value | Notes |
| :--- | :--- | :--- |
| **Total Entries** | **578** | Matches declared `count` exactly |
| **Unique IDs** | **578** | **0 duplicate IDs** |
| **Unique URIs** | **578** | **0 duplicate URIs** (Every action has a unique URI) |
| **Missing IDs** | **0** | All entries have valid IDs |
| **Missing URIs** | **0** | All entries have valid URIs |
| **Missing Descriptions** | **0** | 100% of entries have non-empty `description` |
| **Missing Messages** | **0** | 100% of entries have non-empty `message` |
| **Missing `qna_description`** | **10** | 10 entries have null/empty `qna_description` (DL-0474, DL-0475, DL-0520 to DL-0527) |
| **Entries with `validation`** | **570** | 98.6% of entries contain validation specs |
| **Entries without `validation`**| **8** | 8 entries have `validation: null` (including DL-DUMMY) |
| **Special/Fallback Entry** | **1 (`DL-DUMMY`)** | `bixby://dummy_positive` — Official generic fallback for unmapped settings |

### Distribution of `originalType`
- `onClickURL`: 254 (43.9%) — Navigational clicks to settings sub-pages
- `offURL`: 138 (23.9%) — Toggle switches turning settings OFF
- `onURL`: 138 (23.9%) — Toggle switches turning settings ON
- `updateURL`: 36 (6.2%) — Sliders / value inputs (e.g., brightness levels)
- `None`: 11 (1.9%) — Diagnostic or unclassified actions
- `placeholder`: 1 (0.2%) — `DL-DUMMY`

---

## 3. Chosen Retrieval Method: Multi-Field BM25 with Phrase Boosting

### Method Description
We implemented a zero-dependency, high-speed **Multi-Field Okapi BM25** search index in pure Python (`scratch/search_deeplinks.py`).

### Why We Chose This Method for Phase 1
1. **Zero External Dependencies:** Runs natively with standard library and existing environment. No PyTorch, no heavy model weights (~1GB+), no network calls, and no Docker/C-extension requirements.
2. **Deterministic & Non-Hallucinating:** Candidate URIs are looked up directly by index. It is structurally impossible for this retriever to hallucinate, corrupt, or truncate a `bixby://` URI.
3. **Sub-Millisecond Speed:** Indexing takes ~15ms, and query latency is `<0.8ms` for the entire 578-item corpus, easily satisfying the hackathon's strict sub-300ms caching and response constraints.
4. **Multi-Field Differential Weighting:**
   - `message` (Action/Button name): weight **2.5x**
   - `qna_description` (Symptom & purpose): weight **1.5x**
   - `description` (Settings path): weight **1.0x**
   - Full phrase & bigram exact match: **+8.0 / +3.0 score boost**

---

## 4. Benchmark Results on Test Queries

We tested the retrieval engine across both exact-terminology queries and paraphrased natural-language queries.

### Test 1: `"power saving mode"` (Exact Terminology)
- **Rank 1 (Score 32.53):** `DL-0411` | *Disable Power saving* (`bixby://masked/act/71c2ec6d04`)
- **Rank 2 (Score 32.53):** `DL-0412` | *Enable Power saving* (`bixby://masked/act/75cb6916fd`)
- **Rank 3 (Score 29.58):** `DL-0519` | *Check Battery Performance* (`bixby://masked/act/7bebf18037`)
- **Quality Analysis:** **Flawless.** Both enable and disable variants retrieved at top rank with high confidence.

### Test 2: `"screen brightness"` (Exact Terminology)
- **Rank 1 (Score 20.81):** `DL-0232` | *Adjust Brightness* (`bixby://masked/act/e26224271b`)
- **Rank 2 (Score 20.65):** `DL-0496` | *View Adjust Brightness* (`bixby://masked/act/afbc80006a`)
- **Rank 3 (Score 19.86):** `DL-0104` | *Disable Adaptive Display* (`bixby://masked/act/6ddfdb39ee`)
- **Quality Analysis:** **Flawless.** Direct brightness slider and settings page returned at Ranks 1 and 2.

### Test 3: `"my battery drains quickly"` (Paraphrased Symptom)
- **Rank 1 (Score 16.48):** `DL-0474` | *Diagnose Battery Drain* (`bixby://masked/act/4b4df06e4c`)
  - Description: *"Diagnoses excessive battery drain to identify power-hungry apps and suggest fixes..."*
- **Rank 2 (Score 6.86):** `DL-0515` | *Check Battery Performance* (Fast wireless charging)
- **Rank 4 (Score 5.35):** `DL-0409` | *Disable Battery protection*
- **Quality Analysis:** **Excellent.** Stemmed match on "drain" directly targeted the dedicated battery drain diagnostic tool.

### Test 4: `"display is too dim"` (Paraphrased Symptom)
- **Rank 1 (Score 11.01):** `DL-0401` | *Disable Auto dim screen* (`bixby://masked/act/2445235301`)
- **Rank 2 (Score 11.01):** `DL-0402` | *Enable Auto dim screen* (`bixby://masked/act/45eaaed1d3`)
- **Rank 3 (Score 10.92):** `DL-0488` | *Disable Auto Screen Dim* (`bixby://masked/act/dad7677982`)
- **Quality Analysis:** **Good.** Auto-dim screen setting retrieved directly via symptom keyword "dim".

### Test 5: `"save battery"` (Generic Verb + Noun)
- **Rank 1 (Score 8.21):** `DL-0367` | *Disable Save original screenshots* (`bixby://masked/act/3bcc582dab`)
- **Rank 4 (Score 7.61):** `DL-0078` | *Adjust Dark mode settings* (QnA: *"saves battery on OLED screens"*)
- **Quality Analysis:** **Near-Match Failure.** "Save" matched "save screenshots" because "save original screenshots" has a higher density of the term "save". The battery-saving intent was degraded to Rank 4.

### Test 6: `"turn on battery saver"` (Colloquial Phrasing)
- **Rank 1 (Score 14.06):** `DL-0079` | *Disable Turn on now* (Data Saver)
- **Rank 2 (Score 14.06):** `DL-0080` | *Enable Turn on now* (Data Saver)
- **Rank 4 (Score 11.00):** `DL-0507` | *Disable Energy Saving Solution*
- **Quality Analysis:** **Lexical Confusion.** Samsung's catalog calls this feature "Power saving" or "Energy Saving Solution", while mobile data uses "Data Saver" with message "Turn on now". The terms "turn on" + "saver" favored Data Saver over Power saving.

---

## 5. Known Weaknesses of Lexical Retrieval Alone

1. **Synonym Gap:** If a user says "battery saver", but Samsung's catalog says "Power saving", pure lexical match loses to exact token overlaps like "Data Saver".
2. **Verb Noise:** Frequent utility verbs ("save", "turn on", "check", "view") can artificially boost irrelevant settings that share those verbs (e.g. "Save screenshots").
3. **Action Polarity:** The catalog contains paired entries (e.g. `DL-0411` *Disable Power saving* vs `DL-0412` *Enable Power saving*). A retriever without reasoning does not know whether the user wants to *turn on* or *turn off* the feature.

---

## 6. Recommendations for Phase 2

1. **Candidate Retrieval Layer:** Keep BM25 as the fast First-Stage Retriever to instantly produce Top-10 candidates in `<1ms`.
2. **SIIS Guidance:** When the evaluator provides the SIIS text document, extract key phrases from SIIS (e.g., "Power saving mode", "Eye comfort shield") rather than raw user slang. SIIS uses official Samsung terminology!
3. **LLM Re-ranking & Disambiguation (Phase 2/3):** An LLM or lightweight cross-encoder should inspect the Top-10 candidates from the retriever and select the exact matching entry based on user intent and polarity (Enable vs Disable).
4. **Deterministic Gate:** The final selected URI must ALWAYS be validated against `cleaned_deeplinks.json`'s set of known URIs before emitting.
