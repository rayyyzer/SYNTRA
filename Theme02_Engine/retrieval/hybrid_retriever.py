"""Hybrid Retriever combining BM25, Dense Embeddings, and Polarity Re-ranking."""

from __future__ import annotations
import os
import re
from typing import Any, Dict, List, Optional

from .bm25_retriever import BM25Retriever
from .dense_retriever import DenseRetriever
from .polarity import detect_query_polarity, get_entry_polarity, compute_polarity_adjustment, Polarity

EXPANSION_RULES = [
    (re.compile(r"\b(luminescence|tone down the screen)\b", re.I), "brightness display"),
    (re.compile(r"\b(flight mode|radios for flight|on a plane|take off|takeoff)\b", re.I), "airplane mode flight"),
    (re.compile(r"\b(conserve power|battery last much longer|energy conservation|eating battery)\b", re.I), "power saving battery"),
    (re.compile(r"\b(important exam|total silence|stop my phone from making noise)\b", re.I), "zen mode do not disturb"),
    (re.compile(r"\b(lifeless with no click vibration|vibration on keypress|haptic feedback)\b", re.I), "system vibration keyboard"),
    (re.compile(r"\b(won't automatically turn off|screen timeout)\b", re.I), "screen timeout auto dim screen"),
    (re.compile(r"\b(disabel)\b", re.I), "disable"),
    (re.compile(r"\b(blutooth)\b", re.I), "bluetooth"),
    (re.compile(r"\b(galxy)\b", re.I), "galaxy"),
    (re.compile(r"\b(conection)\b", re.I), "connection"),
]


class HybridRetriever:
    """Fuses multi-field BM25, dense semantic embeddings, and explicit polarity re-ranking."""

    def __init__(
        self,
        catalog_path: Optional[str] = None,
        alpha: float = 0.55,
        model_name: str = "all-MiniLM-L6-v2"
    ):
        self.alpha = alpha  # Dense weight; (1 - alpha) is BM25 weight
        self.bm25 = BM25Retriever(catalog_path=catalog_path)
        self.dense = DenseRetriever(catalog_entries=self.bm25.entries, model_name=model_name)

    def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Retrieves top_k verified catalog entries using hybrid scoring and polarity re-ranking."""
        # 0. Controlled Semantic Expansion for Technical Galaxy Settings
        expanded_q = query
        for pat, rep in EXPANSION_RULES:
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

        # 3. Detect Query Polarity (on original user query)
        q_polarity = detect_query_polarity(query)

        # 4. Candidate Union & Score Fusion & Polarity Adjustment
        candidate_indices = set(top_bm25_indices).union(set(top_dense_indices))
        if not candidate_indices:
            # Fallback to top-scoring generic entries
            return self.bm25.retrieve(query, top_k=top_k)

        fused_scores: Dict[int, float] = {}
        comp_scores: Dict[int, Dict[str, float]] = {}
        for idx in candidate_indices:
            norm_bm25 = (bm25_scores.get(idx, 0.0) / max_bm25) if max_bm25 > 0 else 0.0

            if self.dense.is_available and idx in dense_scores:
                norm_dense = dense_scores[idx]
                fused = (1.0 - self.alpha) * norm_bm25 + self.alpha * norm_dense
            else:
                norm_dense = 0.0
                fused = norm_bm25

            # Apply polarity adjustment
            entry = self.bm25.entries[idx]
            e_polarity = get_entry_polarity(entry)
            pol_adj = compute_polarity_adjustment(q_polarity, e_polarity)
            fused_scores[idx] = fused + pol_adj
            comp_scores[idx] = {
                "bm25": round(norm_bm25, 4),
                "dense": round(norm_dense, 4),
                "pol_adj": round(pol_adj, 4)
            }

        # 5. Rank and return top_k candidates
        ranked = sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

        results = []
        for rank, (doc_idx, score) in enumerate(ranked, start=1):
            e = self.bm25.entries[doc_idx]
            e_pol = get_entry_polarity(e)
            c_comp = comp_scores.get(doc_idx, {})
            results.append({
                "rank": rank,
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
                "polarity_adjustment": c_comp.get("pol_adj", 0.0),
                "entry": e
            })

        return results
