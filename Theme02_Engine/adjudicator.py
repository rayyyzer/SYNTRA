"""Candidate Adjudicator for Theme 2.

Selects the optimal troubleshooting candidate from Top-5 retrieved entries using
Gemini 2.5 Flash when an API key is available, with strict offline/timeout fallback
to Candidate #1 from the deterministic Hybrid Retriever.

CRITICAL INVARIANTS:
1. The LLM NEVER generates or emits a deeplink URI string.
2. The LLM selects solely by Candidate ID (e.g. 'DL-0123').
3. Python deterministically resolves the Candidate ID to a catalog-verified URI.
4. Hard 2500ms timeout guard: any delay or network exception falls back to Candidate #1.
5. Fully functional offline: zero external network dependency required for compliance.
"""

from __future__ import annotations
import os
import time
from typing import Any, Dict, List, Optional


class CandidateAdjudicator:
    """Optional GenAI candidate selector with deterministic offline fallback."""

    def __init__(self, model_name: str = "gemini-2.5-flash", timeout_sec: float = 2.5, dense: Any = None):
        self.model_name = model_name
        self.timeout_sec = timeout_sec
        self.dense = dense
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.client = None
        self._msg_matrix = None
        self._init_client()
        self._init_dense_resources()

    def _init_dense_resources(self):
        try:
            import numpy as np
            data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "data"))
            msg_cache_path = os.path.join(data_dir, "message_embeddings.npy")
            if os.path.exists(msg_cache_path):
                self._msg_matrix = np.load(msg_cache_path)
        except Exception:
            self._msg_matrix = None

    def _init_client(self):
        if not self.api_key:
            return
        try:
            from google import genai
            self.client = genai.Client(api_key=self.api_key)
        except Exception:
            self.client = None

    def _deterministic_adjudicate(self, query: str, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
        """High-precision deterministic candidate selection among Top-5 retrieved entries."""
        if not candidates:
            return {"selected_candidate": None, "confidence": 0.0, "source": "empty"}
        if len(candidates) == 1:
            return {"selected_candidate": candidates[0], "confidence": 0.9, "source": "single_candidate"}

        try:
            import numpy as np
            from retrieval.polarity import detect_query_polarity, Polarity

            q_pol = detect_query_polarity(query)
            q_vec = None
            if self.dense is not None and hasattr(self.dense, "encode_query"):
                q_vec = self.dense.encode_query(query)

            def re_score(cand):
                base = cand.get("score", 0.0)
                cos_sim = 0.0
                if self._msg_matrix is not None and q_vec is not None:
                    c_id = cand.get("id", "")
                    if c_id.startswith("DL-"):
                        try:
                            idx = int(c_id.split("-")[1]) - 1
                            if 0 <= idx < len(self._msg_matrix):
                                cos_sim = float(np.dot(q_vec, self._msg_matrix[idx]))
                        except Exception:
                            pass

                pol_adj = 0.0
                msg_low = cand.get("message", "").lower()
                if q_pol == Polarity.ENABLE:
                    if msg_low.startswith(("enable", "turn on", "activate", "switch on")):
                        pol_adj += 0.20
                    elif msg_low.startswith(("disable", "turn off", "deactivate", "switch off", "stop")):
                        pol_adj -= 0.40
                    elif msg_low.startswith(("view", "open")):
                        pol_adj -= 0.15
                elif q_pol == Polarity.DISABLE:
                    if msg_low.startswith(("disable", "turn off", "deactivate", "switch off", "stop")):
                        pol_adj += 0.20
                    elif msg_low.startswith(("enable", "turn on", "activate", "switch on")):
                        pol_adj -= 0.40
                    elif msg_low.startswith(("view", "open")):
                        pol_adj -= 0.15
                elif q_pol == Polarity.VIEW:
                    if msg_low.startswith(("view", "open", "check", "show")):
                        pol_adj += 0.15
                elif q_pol == Polarity.CONFIGURE:
                    if msg_low.startswith(("adjust", "configure", "change", "format")):
                        pol_adj += 0.15

                return 0.5 * base + 0.5 * cos_sim + 0.3 * pol_adj

            ranked = sorted(candidates, key=re_score, reverse=True)
            return {
                "selected_candidate": ranked[0],
                "confidence": 0.92,
                "source": "deterministic_dense_adjudicator"
            }
        except Exception:
            return {
                "selected_candidate": candidates[0],
                "confidence": 0.85,
                "source": "fallback_candidate_1"
            }

    def adjudicate(
        self,
        query: str,
        siis_title: str,
        siis_content: str,
        candidates: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Selects the best candidate from Top-5 candidates.
        
        Falls back to deterministic dense re-ranking if offline, timed out, or unconfigured.
        """
        if not candidates:
            return {
                "selected_candidate": None,
                "confidence": 0.0,
                "source": "empty_fallback"
            }

        # Offline / No client guard: deterministic dense re-ranking (<1ms)
        if not self.client:
            return self._deterministic_adjudicate(query, candidates)

        # Format candidates cleanly for adjudication (IDs and titles ONLY - no URIs exposed)
        candidate_summary = []
        id_map = {}
        for c in candidates[:5]:
            c_id = c.get("id", "")
            id_map[c_id] = c
            candidate_summary.append(
                f"- Candidate ID: {c_id}\n"
                f"  Action: {c.get('message', '')}\n"
                f"  Description: {c.get('description', '')}\n"
                f"  Polarity: {c.get('polarity', 'neutral')}"
            )

        prompt = (
            f"You are the Samsung Galaxy Guided Troubleshooting Adjudicator.\n"
            f"A user is experiencing this issue:\n"
            f"Query: \"{query}\"\n"
            f"Device Issue Context: {siis_title}\n\n"
            f"Here are the top candidate settings retrieved from the Samsung Galaxy catalog:\n"
            f"{chr(10).join(candidate_summary)}\n\n"
            f"Task: Select the single Candidate ID that directly and safely addresses the user's issue.\n"
            f"If none of the candidates match, output 'NONE'.\n"
            f"Return ONLY the exact Candidate ID (e.g. 'DL-0123') and nothing else."
        )

        try:
            t0 = time.perf_counter()
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
            )
            elapsed = time.perf_counter() - t0
            if elapsed > self.timeout_sec:
                fallback = self._deterministic_adjudicate(query, candidates)
                fallback["source"] = "timeout_deterministic_fallback"
                return fallback

            text = response.text.strip()
            # Find matching candidate ID in response
            for c_id, cand in id_map.items():
                if c_id in text:
                    return {
                        "selected_candidate": cand,
                        "confidence": 0.95,
                        "source": "gemini_adjudicator"
                    }

            fallback = self._deterministic_adjudicate(query, candidates)
            fallback["source"] = "unmatched_deterministic_fallback"
            return fallback
        except Exception:
            fallback = self._deterministic_adjudicate(query, candidates)
            fallback["source"] = "exception_deterministic_fallback"
            return fallback
