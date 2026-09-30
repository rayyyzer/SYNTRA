"""Multi-Field BM25 Lexical Retriever for Samsung Galaxy Settings Catalog."""

from __future__ import annotations
import json
import math
import os
import re
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

SUFFIXES = ("ing", "edly", "ed", "ly", "tion", "tions", "ness", "s", "er", "ers", "es")


def stem_token(token: str) -> str:
    t = token.lower()
    if len(t) <= 3:
        return t
    for s in SUFFIXES:
        if t.endswith(s) and len(t) - len(s) >= 3:
            return t[:-len(s)]
    return t


def tokenize(text: str) -> List[str]:
    if not text:
        return []
    cleaned = re.sub(r"[^\w\s-]", " ", text.lower())
    return [t for t in re.split(r"[\s-]+", cleaned) if len(t) > 1]


class BM25Retriever:
    """In-memory multi-field Okapi BM25 engine optimized for settings catalogs."""

    def __init__(self, catalog_path: Optional[str] = None, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.entries: List[Dict[str, Any]] = []
        self.total_docs: int = 0
        self.doc_len: List[int] = []
        self.avg_doc_len: float = 1.0
        self.inverted_index: Dict[str, Dict[int, float]] = defaultdict(dict)
        self.df: Dict[str, int] = defaultdict(int)
        self.idf: Dict[str, float] = {}

        # Resolve catalog path
        if not catalog_path:
            cand_paths = [
                os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "student_kit", "deeplinks.json")),
                os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "student_kit", "deeplinks.json")),
                os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scratch", "generated", "cleaned_deeplinks.json")),
                os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "participant-kit-all-themes", "participant-kit", "Theme02_Input_Kit", "student_kit", "deeplinks.json")),
            ]
            catalog_path = next((p for p in cand_paths if os.path.exists(p)), cand_paths[0])

        self._load_and_index(catalog_path)

    def _load_and_index(self, path: str):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.entries = data if isinstance(data, list) else data.get("deeplinks", [])

        self.total_docs = len(self.entries)
        if self.total_docs == 0:
            return

        total_tokens = 0
        for idx, entry in enumerate(self.entries):
            # Differential field weighting:
            # - message (action title): 2.5
            # - qna_description (symptoms & intent): 1.5
            # - description (settings navigation path): 1.0
            msg_tokens = [stem_token(t) for t in tokenize(entry.get("message", ""))]
            desc_tokens = [stem_token(t) for t in tokenize(entry.get("description", ""))]
            qna_tokens = [stem_token(t) for t in tokenize(entry.get("qna_description", "") or "")]

            counts: Dict[str, float] = defaultdict(float)
            for t in msg_tokens:
                counts[t] += 2.5
            for t in desc_tokens:
                counts[t] += 1.0
            for t in qna_tokens:
                counts[t] += 1.5

            d_len = len(msg_tokens) + len(desc_tokens) + len(qna_tokens)
            self.doc_len.append(d_len)
            total_tokens += d_len

            for token, w_tf in counts.items():
                self.inverted_index[token][idx] = w_tf
                self.df[token] += 1

        self.avg_doc_len = total_tokens / self.total_docs if self.total_docs > 0 else 1.0
        for token, freq in self.df.items():
            val = (self.total_docs - freq + 0.5) / (freq + 0.5) + 1.0
            self.idf[token] = math.log(val) if val > 0 else 0.0

    def score_docs(self, query: str) -> Dict[int, float]:
        raw_tokens = tokenize(query)
        stemmed = [stem_token(t) for t in raw_tokens]
        if not raw_tokens:
            return {}

        doc_scores: Dict[int, float] = defaultdict(float)
        token_counts = Counter(stemmed)

        for q_token, q_count in token_counts.items():
            if q_token not in self.inverted_index:
                # Substring matching for typo resilience
                partials = [t for t in self.inverted_index if len(q_token) >= 4 and (t.startswith(q_token) or q_token.startswith(t))]
                for p in partials:
                    idf = self.idf.get(p, 0.0) * 0.7
                    for doc_idx, tf in self.inverted_index[p].items():
                        L = self.doc_len[doc_idx]
                        denom = tf + self.k1 * (1.0 - self.b + self.b * (L / self.avg_doc_len))
                        doc_scores[doc_idx] += idf * (tf * (self.k1 + 1.0)) / denom
                continue

            idf = self.idf.get(q_token, 0.0)
            for doc_idx, tf in self.inverted_index[q_token].items():
                L = self.doc_len[doc_idx]
                denom = tf + self.k1 * (1.0 - self.b + self.b * (L / self.avg_doc_len))
                doc_scores[doc_idx] += idf * (tf * (self.k1 + 1.0)) / denom

        # Exact phrase and 2-gram boosting
        query_str = " ".join(raw_tokens)
        for doc_idx in list(doc_scores.keys()):
            entry = self.entries[doc_idx]
            searchable = f"{entry.get('message', '')} {entry.get('description', '')} {entry.get('qna_description', '')}".lower()
            if query_str in searchable:
                doc_scores[doc_idx] += 8.0
            if len(raw_tokens) >= 2:
                for i in range(len(raw_tokens) - 1):
                    bigram = f"{raw_tokens[i]} {raw_tokens[i+1]}"
                    if bigram in searchable:
                        doc_scores[doc_idx] += 3.0

        return doc_scores

    def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        scores = self.score_docs(query)
        if not scores:
            return []
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        results = []
        for doc_idx, sc in ranked:
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
                "score": round(sc, 3),
                "entry": e
            })
        return results
