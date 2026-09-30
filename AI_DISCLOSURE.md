# Samsung PRISM GenAI Hackathon 3.0 — AI Usage Disclosure Form

**Form Reference:** `LangAI3.0_AI_Disclosure`  
**Compliance Standard:** Mandatory Submission Asset  

---

## 1. Team & Project Details

| Field | Detail |
| :--- | :--- |
| **Team / Contributor Name** | SYNTRA Team |
| **Project / Product Name** | **SYNTRA — Samsung Galaxy Smart Guided Troubleshooting Engine** |
| **Theme** | Theme 2 (Smart Guided Troubleshooting Engine) |
| **Organization / Institution** | **SRMIST (SRM Institute of Science and Technology)** |
| **Submission Date** | September 30, 2026 |

---

## 2. AI Usage Declaration

**Did your team use any Artificial Intelligence (AI) in developing this project?**  
> **[X] YES** &nbsp;&nbsp;&nbsp;&nbsp; [ ] NO

---

## 3. Purpose of AI Usage

| Purpose Area | AI Assistance Applied | Summary of Details |
| :--- | :---: | :--- |
| **Idea Generation / Brainstorming** | **YES** | Explored hybrid retrieval architectures (combining lexical BM25 with dense semantic vector embeddings) and context-isolated 3-tier caching strategies. |
| **Code Generation or Assistance** | **YES** | Scaffolding for FastAPI REST endpoints, rank-BM25 integration, regex pattern compilation, and vector normalization helpers. |
| **UI / UX Design** | **YES** | Styling suggestions adhering to Samsung One UI design philosophy (calm typography, rounded pill badges, diagnostic telemetry layouts). |
| **Content Creation** | **YES** | Paraphrased user query variations for robustness stress-testing, automated evaluation report formatting, and technical documentation drafting. |
| **Data Analysis** | **YES** | Latency profiling (cold-start vs. p95 cache hit), Jaccard vs. containment similarity metrics, and score margin distributions. |
| **Testing / Debugging** | **YES** | Writing unit tests covering boundary conditions, prompt injection defense, hardware safety triage, and Gemini HTTP 429 quota exhaustion fallbacks. |
| **Other (Production Engine)** | **YES** | Integration of Gemini 2.5 Flash / 3.5 Flash-Lite as an active runtime semantic adjudicator for resolving low-confidence or ambiguous candidate actions. |

---

## 4. Feature Origin Classification

### Feature 1: Three-Tier Context-Isolated Query Cache
- **Classification:** `Both (Self-Architected & AI-Assisted Implementation)`
- **Tools / Platforms Used:** Google Antigravity, Gemini models
- **Description:** Designed a 3-tier cache structure (Exact Hash $\to$ Polarity Intent Signature $\to$ Context Containment) operating within SHA-256 SIIS context boundaries to achieve sub-2ms query response times. Code generation assisted in pre-compiled regex optimization and bounded FIFO eviction logic.

### Feature 2: Hardware Damage & Battery Hazard Safety Router
- **Classification:** `Both (Self-Architected & AI-Assisted Implementation)`
- **Tools / Platforms Used:** Google Antigravity, Gemini models
- **Description:** Rule-based lexical and heuristic classifier intercepting physical damage (cracked screens, bent chassis, liquid submersion, thermal/smoke hazards) and routing immediately to authorized service repair centers before executing software settings.

### Feature 3: SIIS-Grounded Hybrid Retrieval Engine
- **Classification:** `Both (Self-Architected & AI-Assisted Implementation)`
- **Tools / Platforms Used:** Google Antigravity, SentenceTransformers (`all-MiniLM-L6-v2`), Rank-BM25
- **Description:** Combines BM25 lexical relevance against Samsung's 578-entry One UI catalog with dense semantic dot-product similarity and batched sentence embedding grounding against SIIS article steps.

### Feature 4: Selective Gemini Candidate Adjudicator & Fallback Hierarchy
- **Classification:** `Both (Self-Architected & AI-Assisted Implementation)`
- **Tools / Platforms Used:** Google GenAI SDK (`google-genai`), Gemini 2.5 Flash
- **Description:** Selective reasoning layer invoked only when ambiguity signals trigger (score margin $<0.08$, candidate confidence $<0.40$, or duplicate title actions). Employs strict Candidate ID whitelisting to eliminate URI hallucinations, with automatic fallback to deterministic scoring on timeout or HTTP 429 quota exhaustion.

### Feature 5: SYNTRA Samsung One UI Interactive Playground
- **Classification:** `Both (Self-Architected & AI-Assisted Implementation)`
- **Tools / Platforms Used:** Google Antigravity
- **Description:** Real-time web demonstration interface built with vanilla HTML5/CSS/JS, featuring live execution tracing, stage latency meters, toggleable Gemini adjudication, and automated test scenario playback.

---

## 5. Ethical & Compliance Confirmation

- **AI usage complies with guidelines and competition policies:**  
  > **[X] YES**
- **No proprietary or copyrighted data misused:**  
  > **[X] I AGREE**
- **Sole Catalog Authority:**  
  > All deeplinks and settings actions are strictly grounded in the official Samsung 578-entry catalog. No synthetic URIs or hallucinations are permitted into runtime responses.

---

## 6. Declaration & Sign-Off

- **Name of Team Representative:** SYNTRA Lead / Representative  
- **Role:** Technical Lead & Developer  
- **Institution:** SRMIST (SRM Institute of Science and Technology)  
- **Date:** September 30, 2026  
- **Git Release Tag:** `PRISM_GENAI_HACKATHON_Y2026`  
