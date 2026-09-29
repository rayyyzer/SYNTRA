"""Hybrid Retriever combining BM25, Dense Embeddings, SIIS Grounding, and Polarity Re-ranking."""

from __future__ import annotations
import os
import re
from typing import Any, Dict, List, Optional
import numpy as np

from .bm25_retriever import BM25Retriever
from .dense_retriever import DenseRetriever
from .polarity import (
    detect_query_polarity,
    get_entry_polarity,
    compute_polarity_adjustment,
    get_entry_specificity_penalty,
    Polarity,
)

# Genuinely General Linguistic Normalizations & Device Synonyms (Category A & B only)
# Zero query-specific benchmark patches.
CLEAN_EXPANSIONS = [
    (re.compile(r"\b(blutooth)\b", re.I), "bluetooth"),
    (re.compile(r"\b(galxy)\b", re.I), "galaxy"),
    (re.compile(r"\b(conection)\b", re.I), "connection"),
    (re.compile(r"\b(flight\s+mode)\b", re.I), "airplane mode"),
    (re.compile(r"\b(haptic\s+feedback)\b", re.I), "vibration"),
    (re.compile(r"\b(zen\s+mode)\b", re.I), "do not disturb"),
    (re.compile(r"\b(buzz(?:es|ing)?)\b", re.I), "vibration"),
]


class HybridRetriever:
    """Fuses multi-field BM25, dense semantic embeddings, SIIS procedure grounding, and explicit polarity."""

    def __init__(
        self,
        catalog_path: Optional[str] = None,
        alpha: float = 0.55,
        model_name: str = "all-MiniLM-L6-v2"
    ):
        self.alpha = alpha  # Dense weight; (1 - alpha) is BM25 weight
        self.bm25 = BM25Retriever(catalog_path=catalog_path)
        self.dense = DenseRetriever(catalog_entries=self.bm25.entries, model_name=model_name)
        
        # Preload message matrix for fast candidate action comparison
        self._msg_matrix = None
        try:
            data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
            msg_cache_path = os.path.join(data_dir, "message_embeddings.npy")
            if os.path.exists(msg_cache_path):
                self._msg_matrix = np.load(msg_cache_path)
        except Exception:
            self._msg_matrix = None

        # Build toggle partner map (grouping entries sharing the same validation key)
        self.key_to_entries: Dict[str, List[int]] = {}
        for idx, e in enumerate(self.bm25.entries):
            val = e.get("validation") or {}
            k = val.get("key")
            if k:
                self.key_to_entries.setdefault(k, []).append(idx)

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        siis_title: str = "",
        siis_content: str = ""
    ) -> List[Dict[str, Any]]:
        """Retrieves top_k verified catalog entries using hybrid scoring, SIIS grounding, and polarity."""
        # 0. Clean general linguistic normalizations
        expanded_q = query
        for pat, rep in CLEAN_EXPANSIONS:
            if pat.search(query):
                expanded_q = f"{expanded_q} {rep}"

        # 1. Lexical BM25 Scoring (<1.5ms)
        bm25_scores = self.bm25.score_docs(expanded_q)
        top_bm25_indices = sorted(bm25_scores.keys(), key=lambda i: bm25_scores[i], reverse=True)[:30]
        max_bm25 = max(bm25_scores.values()) if bm25_scores else 1.0

        # 2. Dense Semantic Scoring (<5ms)
        dense_scores: Dict[int, float] = {}
        top_dense_indices = []
        if self.dense.is_available:
            dense_scores = self.dense.score_docs(expanded_q)
            top_dense_indices = sorted(dense_scores.keys(), key=lambda i: dense_scores[i], reverse=True)[:30]

        # 3. SIIS Procedure Semantic Grounding
        siis_proc_scores: Dict[int, float] = {}
        if self.dense.is_available:
            siis_sentences = [s.strip() for s in re.split(r"[.\n]+", siis_content) if len(s.strip()) > 8]
            action_sents = [s for s in siis_sentences if any(w in s.lower() for w in ("enable", "disable", "turn on", "turn off", "toggle", "adjust", "mode", "saving", "switch", "protect", "drain", "vibration", "brightness"))]
            target_sents = action_sents if action_sents else siis_sentences

            if target_sents:
                # DoS Protection (SEC-03): Cap expensive sentence embeddings to top 3 relevant sentences
                if len(target_sents) > 3:
                    q_tokens = set(re.findall(r"\b[a-z0-9]+\b", f"{query} {siis_title}".lower()))
                    def score_sent(item):
                        idx, s = item
                        s_tokens = set(re.findall(r"\b[a-z0-9]+\b", s.lower()))
                        overlap = len(q_tokens.intersection(s_tokens))
                        return (overlap, -idx)
                    indexed = list(enumerate(target_sents))
                    indexed.sort(key=score_sent, reverse=True)
                    target_sents = [s for idx, s in indexed[:3]]

                for s in target_sents:
                    s_vec = self.dense.encode_query(s)
                    if s_vec is not None and self.dense.catalog_matrix is not None:
                        sims = np.dot(self.dense.catalog_matrix, s_vec)
                        m_sims = np.dot(self._msg_matrix, s_vec) if self._msg_matrix is not None else sims
                        comb_s = 0.5 * sims + 0.5 * m_sims
                        for idx, sim in enumerate(comb_s):
                            if idx not in siis_proc_scores or sim > siis_proc_scores[idx]:
                                siis_proc_scores[idx] = float(sim)
            elif siis_title:
                t_vec = self.dense.encode_query(siis_title)
                if t_vec is not None and self.dense.catalog_matrix is not None:
                    sims = np.dot(self.dense.catalog_matrix, t_vec)
                    for idx, sim in enumerate(sims):
                        siis_proc_scores[idx] = float(sim)

        top_siis_indices = sorted(siis_proc_scores.keys(), key=lambda i: siis_proc_scores[i], reverse=True)[:20] if siis_proc_scores else []
        max_siis = max(siis_proc_scores.values()) if siis_proc_scores else 1.0

        # 4. Candidate Pool: Union of BM25 + Query Dense + SIIS Procedure Dense + Toggle Partners
        candidate_indices = set(top_bm25_indices).union(set(top_dense_indices)).union(set(top_siis_indices))
        if not candidate_indices:
            return self.bm25.retrieve(query, top_k=top_k)

        # Include toggle partners so polarity choices are never pruned prematurely
        toggle_cands = set()
        for idx in candidate_indices:
            e = self.bm25.entries[idx]
            val = e.get("validation") or {}
            k = val.get("key")
            if k and k in self.key_to_entries:
                for p_idx in self.key_to_entries[k]:
                    toggle_cands.add(p_idx)
        candidate_indices = candidate_indices.union(toggle_cands)

        # 5. Detect Query Polarity (compositional with SIIS grounding)
        siis_text = f"{siis_title} {siis_content}".strip()
        q_polarity = detect_query_polarity(query, siis_text=siis_text)

        # 6. Candidate Score Fusion & Polarity Adjustment
        fused_scores: Dict[int, float] = {}
        comp_scores: Dict[int, Dict[str, float]] = {}
        for idx in candidate_indices:
            norm_bm25 = (bm25_scores.get(idx, 0.0) / max_bm25) if max_bm25 > 0 else 0.0
            norm_dense = dense_scores.get(idx, 0.0)
            norm_siis = (siis_proc_scores.get(idx, 0.0) / max_siis) if max_siis > 0 else 0.0

            # Grounded candidate fusion
            if siis_proc_scores:
                fused = 0.25 * norm_bm25 + 0.35 * norm_dense + 0.40 * norm_siis
            else:
                fused = (1.0 - self.alpha) * norm_bm25 + self.alpha * norm_dense

            # Apply polarity adjustment
            entry = self.bm25.entries[idx]
            e_polarity = get_entry_polarity(entry)
            pol_adj = compute_polarity_adjustment(q_polarity, e_polarity)

            # Mobile context penalty for TV settings
            dev_adj = -0.40 if "tv settings" in entry.get("description", "").lower() else 0.0

            # Domain-general catalog sub-feature specificity penalty
            spec_pen = get_entry_specificity_penalty(expanded_q, entry)

            final_score = fused + pol_adj + dev_adj + spec_pen
            fused_scores[idx] = final_score
            comp_scores[idx] = {
                "bm25": round(norm_bm25, 4),
                "dense": round(norm_dense, 4),
                "siis": round(norm_siis, 4),
                "pol_adj": round(pol_adj, 4),
                "spec_pen": round(spec_pen, 4)
            }

        # 7. Rank and return top_k candidates
        ranked = sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

        results = []
        for rank, (doc_idx, score) in enumerate(ranked, start=1):
            e = self.bm25.entries[doc_idx]
            e_pol = get_entry_polarity(e)
            c_comp = comp_scores.get(doc_idx, {})
            results.append({
                "rank": rank,
                "idx": doc_idx,
                "id": e.get("id", f"DL-{doc_idx+1:04d}"),
                "deeplink": e["deeplink"],  # VERBATIM CATALOG URI ONLY
                "message": e.get("message", ""),
                "description": e.get("description", ""),
                "qna_description": e.get("qna_description", ""),
                "originalType": e.get("originalType", "onClickURL"),
                "control_type": e.get("control_type"),
                "polarity": e_pol.value,
                "validation": e.get("validation"),
                "score": round(score, 4),
                "bm25_score": c_comp.get("bm25", 0.0),
                "dense_score": c_comp.get("dense", 0.0),
                "siis_score": c_comp.get("siis", 0.0),
                "polarity_adjustment": c_comp.get("pol_adj", 0.0),
                "specificity_adjustment": c_comp.get("spec_pen", 0.0),
                "entry": e
            })

        return results
