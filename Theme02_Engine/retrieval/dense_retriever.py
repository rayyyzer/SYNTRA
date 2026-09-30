"""Dense Semantic Vector Retriever using all-MiniLM-L6-v2."""

from __future__ import annotations
import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple


_MODEL_CACHE: Dict[str, Any] = {}


def get_sentence_transformer(model_name: str = "all-MiniLM-L6-v2") -> Any:
    """Singleton getter for SentenceTransformer with local_files_only priority to eliminate cold-start network stalls."""
    if model_name in _MODEL_CACHE:
        return _MODEL_CACHE[model_name]
    from sentence_transformers import SentenceTransformer  # type: ignore
    try:
        model = SentenceTransformer(model_name, local_files_only=True)
    except Exception:
        model = SentenceTransformer(model_name)
    _MODEL_CACHE[model_name] = model
    return model


class DenseRetriever:
    """In-memory dense semantic vector retriever with sub-millisecond dot-product scoring."""

    def __init__(self, catalog_entries: List[Dict[str, Any]], model_name: str = "all-MiniLM-L6-v2"):
        self.entries = catalog_entries
        self.model_name = model_name
        self.model = None
        self.catalog_matrix = None  # Shape: (578, 384)
        self.is_available = False
        self._query_vec_cache: Dict[str, Any] = {}
        self._init_model()

    def _init_model(self):
        try:
            import numpy as np  # type: ignore

            t0 = time.perf_counter()
            self.model = get_sentence_transformer(self.model_name)
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
        """Encodes query into a 384-dimensional normalized vector with in-memory caching."""
        if not self.is_available or self.model is None or not query:
            return None
        if query in self._query_vec_cache:
            return self._query_vec_cache[query]
        vec = self.model.encode([query], normalize_embeddings=True, show_progress_bar=False)[0]
        if len(self._query_vec_cache) >= 500:
            self._query_vec_cache.pop(next(iter(self._query_vec_cache)))
        self._query_vec_cache[query] = vec
        return vec

    def encode_queries(self, queries: List[str]) -> List[Any]:
        """Encodes multiple queries in a single batched tensor forward pass."""
        if not self.is_available or self.model is None or not queries:
            return []
        results = [None] * len(queries)
        missing_indices = []
        missing_texts = []
        for idx, q in enumerate(queries):
            if q in self._query_vec_cache:
                results[idx] = self._query_vec_cache[q]
            else:
                missing_indices.append(idx)
                missing_texts.append(q)
        if missing_texts:
            encoded_batch = self.model.encode(missing_texts, normalize_embeddings=True, show_progress_bar=False)
            for m_idx, text, vec in zip(missing_indices, missing_texts, encoded_batch):
                if len(self._query_vec_cache) >= 500:
                    self._query_vec_cache.pop(next(iter(self._query_vec_cache)))
                self._query_vec_cache[text] = vec
                results[m_idx] = vec
        return results

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
