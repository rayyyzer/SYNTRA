"""Hybrid Retriever combining BM25, Dense Embeddings, and Polarity Re-ranking."""

from __future__ import annotations
import os
from typing import Any, Dict, List, Optional

from .bm25_retriever import BM25Retriever
from .dense_retriever import DenseRetriever
from .polarity import detect_query_polarity, get_entry_polarity, compute_polarity_adjustment, Polarity


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
        # 1. Lexical BM25 Scoring (<1.5ms)
        bm25_scores = self.bm25.score_docs(query)
        max_bm25 = max(bm25_scores.values()) if bm25_scores else 1.0

        # 2. Dense Semantic Scoring (<5ms)
        dense_scores: Dict[int, float] = {}
        if self.dense.is_available:
            dense_scores = self.dense.score_docs(query)

        # 3. Detect Query Polarity
        q_polarity = detect_query_polarity(query)

        # 4. Score Fusion & Polarity Adjustment
        candidate_indices = set(bm25_scores.keys()).union(set(dense_scores.keys()))
        if not candidate_indices:
            # Fallback to top-scoring generic entries
            return self.bm25.retrieve(query, top_k=top_k)

        fused_scores: Dict[int, float] = {}
        for idx in candidate_indices:
            norm_bm25 = (bm25_scores.get(idx, 0.0) / max_bm25) if max_bm25 > 0 else 0.0

            if self.dense.is_available and idx in dense_scores:
                norm_dense = dense_scores[idx]
                fused = (1.0 - self.alpha) * norm_bm25 + self.alpha * norm_dense
            else:
                fused = norm_bm25

            # Apply polarity adjustment
            entry = self.bm25.entries[idx]
            e_polarity = get_entry_polarity(entry)
            pol_adj = compute_polarity_adjustment(q_polarity, e_polarity)
            fused_scores[idx] = fused + pol_adj

        # 5. Rank and return top_k candidates
        ranked = sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

        results = []
        for rank, (doc_idx, score) in enumerate(ranked, start=1):
            e = self.bm25.entries[doc_idx]
            e_pol = get_entry_polarity(e)
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
                "entry": e
            })

        return results
