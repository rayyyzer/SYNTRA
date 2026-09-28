# Official Submission Requirements Specification

**Samsung PRISM GenAI Hackathon 3.0 — 2026–27 Edition**  
*Document Generated: Phase 0 Compliance Audit*  
*Primary Sources: `Samsung PRISM_Y2026_GenAI_Hackathon_3rd_Edition.V2(2).pdf`, `Samsung_PRISM_GenAI_Hackathon_3_FAQ_v4.docx` (`faq.txt`), `LangAI3.0_AI_Disclosure.docx` (`disclosure.txt`), `CollegeName_TeamName_Submission.pptx`*

---

## 1. High-Level Submission Checklist

| Deliverable | Format / Naming | Destination | Official Source | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Working Prototype Code** | Git repo (public/shared) with Git tag `PRISM_GENAI_HACKATHON_Y2026` | GitHub + Google Form URL | Overview p. 11, 13; FAQ Q17, Q19 | **MANDATORY** |
| **Reproducible README** | `README.md` with setup steps, Docker, & env setup | Root of GitHub Repo | Overview p. 11, 13; FAQ Q17 | **MANDATORY** |
| **Demo Video** | Video ≤ 5 minutes (walkthrough + demo) | YouTube or Google Drive link | Overview p. 11, 12, 13; FAQ Q17 | **MANDATORY** |
| **Presentation Deck** | `CollegeName_TeamName.pptx` or `.pdf` (12 slides) | GitHub repo + Google Form | Overview p. 12, 13; Template PPT | **MANDATORY** |
| **AI Disclosure Form** | Completed `LangAI3.0_AI_Disclosure.docx` (or PDF) | GitHub repo + Google Form | Disclosure Form; Overview p. 13 | **MANDATORY** |
| **Theme 2 Offline Results** | `results.jsonl` (1 JSON per line with query variations) | Root of GitHub repo | FAQ Theme 2 Q16, Q17 | **MANDATORY** |
| **Live API Service** | Running REST endpoints (`/health` & `/v1/troubleshoot`) | Accessible host during judging | FAQ Theme 2 Q9, Q19, Q21, Q22 | **MANDATORY** |

---

## 2. Git Repository & Tagging Contract

### A. Git Release Tag
- **Tag Name (Exact):** `PRISM_GENAI_HACKATHON_Y2026`
- **Official Rule:** "For your final submission: Create a release tag named `PRISM_GENAI_HACKATHON_Y2026` on your final commit. The tagged commit is what gets judged... Make sure everything referenced in your submission—PPT, demo video, documentation, etc.—is present in the tagged commit." (Source: Overview p. 13; FAQ Q19–Q20).
- **Commands:**
  ```bash
  git tag -a PRISM_GENAI_HACKATHON_Y2026 -m "PRISM Gen AI Hackathon Y2026 Final Submission"
  git push origin PRISM_GENAI_HACKATHON_Y2026
  ```

### B. Repository Structure Requirements
```text
<repository-root>/
├── README.md                          # Comprehensive setup, run, and reproduction guide
├── requirements.txt                   # Public PyPI dependencies (Python 3.10+)
├── Dockerfile                         # (Or docker-compose.yml) containerized runtime
├── .env.example                       # Template for environment variables (NO SECRETS)
├── results.jsonl                      # Pre-generated Theme 2 evaluation results
├── CollegeName_TeamName_Submission.pptx # Completed presentation deck
├── AI_Disclosure_Form.docx/.pdf       # Signed LangAI 3.0 AI Disclosure Form
├── app/ (or Theme02_Engine/)          # Source code for FastAPI REST service
└── docs/                              # Architecture, compliance, and design documents
```

---

## 3. Presentation Requirements (`CollegeName_TeamName.pptx`)

The presentation deck must strictly follow the official 12-slide master template (`CollegeName_TeamName_Submission.pptx`):
- **Slide 1:** Title Slide (Theme ID, Team Name, College Name, Member Names & Emails 1–4, GitHub Link).
- **Slide 2:** Theme Identification & Overview.
- **Slide 3:** Existing Solutions & Gaps.
- **Slide 4:** Our Solution & Architecture Diagram.
- **Slide 5:** Demo & Product Walkthrough.
- **Slide 6:** Tools and Tech Stack Used.
- **Slide 7:** Impact & Use Case.
- **Slide 8:** Innovation Highlights, Results, and Limitations.
- **Slide 9:** What's Next / Future Roadmap.
- **Slide 10:** Brownie Points Slide (Key Technical Differentiation).
- **Slide 11:** Checklist (Working code, README, Demo video, PPT status).
- **Slide 12:** Thank You & Acknowledgments.

---

## 4. Demo Video Requirements

- **Maximum Duration:** Exactly 5 minutes (strict cap; Overview p. 11, 12, 13; FAQ Q17).
- **Hosting:** Public or accessible unlisted YouTube link, or Google Drive link with open view permissions.
- **Content:**
  1. Concise problem explanation.
  2. Live walkthrough of the working prototype.
  3. Demonstration of `/health` and `/v1/troubleshoot` receiving real queries and returning valid deeplinks.
  4. Explanation of caching and latency results.

---

## 5. Theme 2 Specific Deliverable: `results.jsonl`

- **File Name:** `results.jsonl` (Source: FAQ Theme 2 Q16, Q17).
- **Format:** JSON Lines (one JSON object per line).
- **Line Schema:**
  ```json
  {
    "query": "original query text",
    "query_variations": [
      "paraphrase 1",
      "paraphrase 2",
      "paraphrase 3",
      "paraphrase 4",
      "paraphrase 5",
      "paraphrase 6",
      "paraphrase 7",
      "paraphrase 8",
      "paraphrase 9"
    ],
    "response": {
      "contexts": [ ... ]
    }
  }
  ```
- **Constraints on `query_variations`:**
  - Must contain between **8 and 10 unique variations** per query (fewer than 8 or more than 10 incurs point penalties; FAQ Q18, Block A5).
  - Must demonstrate lexical diversity across formality, vocabulary, and sentence structures.

---

## 6. Theme 2 Runtime REST API Contract

During live evaluation, the judges' automated scorer calls the participant's running server over HTTP (FAQ Theme 2 Q9, Q19, Q21, Q22).

- **Endpoints Required:**
  1. `GET /health` → Must return `{"status": "ok"}` (Gate G2).
  2. `POST /v1/troubleshoot` → Accepts JSON `{ "query": str, "siis_response": { "title": str, "content": str } }` and returns `ContextDeeplinkResponse`.
- **Authentication:** Must NOT require API keys, bearer tokens, or custom headers for judges. Keep the endpoint open (FAQ Q22).
- **Port / Host:** Must be publicly reachable or exposed via reverse proxy/tunnel during the evaluation window.

---

## 7. Security, Secrets & External Dependencies

1. **Zero Secret Leaks:** Never commit raw API keys (OpenAI, Gemini, Mistral, Anthropic) to the Git repository. Keys must be read from environment variables or a local `.env` file (FAQ Theme 2 Q22).
2. **PyPI Resolvability:** All third-party Python packages listed in `requirements.txt` must resolve from public PyPI without private wheels or proprietary mirrors.
3. **No Proprietary Data Misuse:** The team must confirm that no unauthorized internal data was used (`LangAI3.0_AI_Disclosure.docx` §5).

---

## 8. Judging & Evaluation Weighting

As published in Overview p. 11 and FAQ Q22:

- **Working Prototype & Functionality:** **30%**
- **Technical Depth & Feasibility:** **25%**
- **Innovation & Originality:** **20%**
- **Relevance to Theme:** **15%**
- **Presentation & Documentation:** **10%**

*(Theme 2 Automated Scorer contributes up to 60 points towards the prototype functionality score across Schema [15], Deeplinks [15], Latency/Cache [15], Generalization [10], and Query Variations [5]).*
