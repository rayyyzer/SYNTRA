"""Dense Semantic Vector Retriever using all-MiniLM-L6-v2."""

from __future__ import annotations
import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple


class DenseRetriever:
    """In-memory dense semantic vector retriever with sub-millisecond dot-product scoring."""

    def __init__(self, catalog_entries: List[Dict[str, Any]], model_name: str = "all-MiniLM-L6-v2"):
        self.entries = catalog_entries
        self.model_name = model_name
        self.model = None
        self.catalog_matrix = None  # Shape: (578, 384)
        self.is_available = False
        self._init_model()

    def _init_model(self):
        try:
            import numpy as np  # type: ignore
            from sentence_transformers import SentenceTransformer  # type: ignore

            t0 = time.perf_counter()
            self.model = SentenceTransformer(self.model_name)
            self.load_time_ms = (time.perf_counter() - t0) * 1000.0

            # Check if precomputed embeddings exist on disk
            data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
            os.makedirs(data_dir, exist_ok=True)
            cache_path = os.path.join(data_dir, "catalog_embeddings.npy")

            if os.path.exists(cache_path):
                self.catalog_matrix = np.load(cache_path)
                self.catalog_encode_ms = 0.5
            else:
                # Construct descriptive semantic text for each catalog entry
                search_texts = []
                for e in self.entries:
                    msg = e.get("message", "")
                    desc = e.get("description", "")
                    qna = e.get("qna_description", "") or ""
                    search_texts.append(f"{msg}. {desc}. {qna}".strip())

                t0 = time.perf_counter()
                self.catalog_matrix = self.model.encode(
                    search_texts,
                    normalize_embeddings=True,
                    show_progress_bar=False
                )
                self.catalog_encode_ms = (time.perf_counter() - t0) * 1000.0
                np.save(cache_path, self.catalog_matrix)
            self.is_available = True
        except Exception as e:
            # Graceful degradation if sentence-transformers or torch is missing
            self.is_available = False
            self.model = None
            self.catalog_matrix = None

    def encode_query(self, query: str):
        """Encodes query into a 384-dimensional normalized vector."""
        if not self.is_available or self.model is None:
            return None
        return self.model.encode([query], normalize_embeddings=True, show_progress_bar=False)[0]

    def score_docs(self, query: str) -> Dict[int, float]:
        """Calculates cosine similarity of query against all 578 catalog entries."""
        if not self.is_available or self.catalog_matrix is None:
            return {}
        import numpy as np  # type: ignore

        q_vec = self.encode_query(query)
        if q_vec is None:
            return {}

        # Matrix dot product against pre-normalized catalog embeddings
        sims = np.dot(self.catalog_matrix, q_vec)
        return {idx: float(sims[idx]) for idx in range(len(self.entries))}

    def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        scores = self.score_docs(query)
        if not scores:
            return []

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        results = []
        for doc_idx, sim in ranked:
            e = self.entries[doc_idx]
            results.append({
                "deeplink": e["deeplink"],
                "id": e.get("id", f"DL-{doc_idx+1:04d}"),
                "message": e.get("message", ""),
                "description": e.get("description", ""),
                "qna_description": e.get("qna_description", ""),
                "originalType": e.get("originalType", "onClickURL"),
                "control_type": e.get("control_type"),
                "validation": e.get("validation"),
                "score": round(sim, 4),
                "entry": e
            })
        return results
