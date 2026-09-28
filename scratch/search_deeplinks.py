"""Phase 1: Lightweight, dependency-free semantic & lexical search prototype.

Uses Multi-Field BM25 + Suffix Normalization + Phrase Boosting over
the 578 Samsung deeplink entries.
Guarantees exact URI preservation: never constructs or alters URIs.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple


# Simple, transparent suffix stripper for morphological normalization
SUFFIXES = ("ing", "edly", "ed", "ly", "tion", "tions", "ness", "s", "er", "ers", "es")


def stem_token(token: str) -> str:
    """Lightweight suffix normalization without heavy external NLP packages."""
    t = token.lower()
    if len(t) <= 3:
        return t
    for s in SUFFIXES:
        if t.endswith(s) and len(t) - len(s) >= 3:
            return t[:-len(s)]
    return t


def normalize_query(text: str) -> List[str]:
    """Tokenize and normalize query text."""
    if not text:
        return []
    cleaned = re.sub(r"[^\w\s-]", " ", text.lower())
    tokens = [t for t in re.split(r"[\s-]+", cleaned) if len(t) > 1]
    return tokens


class DeeplinkBM25Retriever:
    """Inverted index BM25 search engine optimized for device setting catalogs."""

    def __init__(self, data_path: str, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.entries: List[Dict[str, Any]] = []
        self.doc_len: List[int] = []
        self.avg_doc_len: float = 0.0
        self.total_docs: int = 0
        
        # Inverted index: stemmed_token -> dict of {doc_idx: weighted_tf}
        self.inverted_index: Dict[str, Dict[int, float]] = defaultdict(dict)
        # Document frequency: stemmed_token -> count of docs containing it
        self.df: Dict[str, int] = defaultdict(int)
        # IDF table
        self.idf: Dict[str, float] = {}

        self._load_and_index(data_path)

    def _load_and_index(self, data_path: str):
        if not os.path.exists(data_path):
            raise FileNotFoundError(f"Cleaned dataset not found at {data_path}. Run prepare_deeplinks.py first.")

        with open(data_path, "r", encoding="utf-8") as f:
            self.entries = json.load(f)

        self.total_docs = len(self.entries)
        if self.total_docs == 0:
            return

        total_tokens = 0
        for idx, entry in enumerate(self.entries):
            # Extract fields with differential weighting:
            # - message (action/button label): weight 2.5
            # - description (settings path): weight 1.0
            # - qna_description (symptoms & purpose): weight 1.5
            msg_tokens = [stem_token(t) for t in normalize_query(entry.get("message", ""))]
            desc_tokens = [stem_token(t) for t in normalize_query(entry.get("description", ""))]
            qna_tokens = [stem_token(t) for t in normalize_query(entry.get("qna_description", ""))]

            weighted_counts: Dict[str, float] = defaultdict(float)
            for t in msg_tokens:
                weighted_counts[t] += 2.5
            for t in desc_tokens:
                weighted_counts[t] += 1.0
            for t in qna_tokens:
                weighted_counts[t] += 1.5

            d_len = len(msg_tokens) + len(desc_tokens) + len(qna_tokens)
            self.doc_len.append(d_len)
            total_tokens += d_len

            for token, w_tf in weighted_counts.items():
                self.inverted_index[token][idx] = w_tf
                self.df[token] += 1

        self.avg_doc_len = total_tokens / self.total_docs if self.total_docs > 0 else 1.0

        # Precompute standard Okapi BM25 IDF
        for token, freq in self.df.items():
            # Standard BM25 IDF with smoothing
            val = (self.total_docs - freq + 0.5) / (freq + 0.5) + 1.0
            self.idf[token] = math.log(val) if val > 0 else 0.0

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Search catalog with BM25 + phrase matching. Returns top_k candidates."""
        raw_tokens = normalize_query(query)
        stemmed_tokens = [stem_token(t) for t in raw_tokens]

        if not raw_tokens:
            return []

        doc_scores: Dict[int, float] = defaultdict(float)
        query_token_counts = Counter(stemmed_tokens)

        # 1. BM25 scoring across tokens
        for q_token, q_count in query_token_counts.items():
            if q_token not in self.inverted_index:
                # Check for prefix or substring match in dictionary for typo/stemming resilience
                partial_matches = [t for t in self.inverted_index if (len(q_token) >= 4 and (t.startswith(q_token) or q_token.startswith(t)))]
                for p_token in partial_matches:
                    idf = self.idf.get(p_token, 0.0) * 0.7
                    for doc_idx, tf in self.inverted_index[p_token].items():
                        L = self.doc_len[doc_idx]
                        denom = tf + self.k1 * (1.0 - self.b + self.b * (L / self.avg_doc_len))
                        term_score = idf * (tf * (self.k1 + 1.0)) / denom
                        doc_scores[doc_idx] += term_score
                continue

            idf = self.idf.get(q_token, 0.0)
            for doc_idx, tf in self.inverted_index[q_token].items():
                L = self.doc_len[doc_idx]
                denom = tf + self.k1 * (1.0 - self.b + self.b * (L / self.avg_doc_len))
                term_score = idf * (tf * (self.k1 + 1.0)) / denom
                doc_scores[doc_idx] += term_score

        # 2. Exact phrase & consecutive n-gram boosting
        query_str = " ".join(raw_tokens)
        for doc_idx, score in list(doc_scores.items()):
            entry = self.entries[doc_idx]
            norm_searchable = entry.get("normalized_searchable", "")
            
            # Full phrase match boost
            if query_str in norm_searchable:
                doc_scores[doc_idx] += 8.0
            
            # 2-gram phrase boost
            if len(raw_tokens) >= 2:
                for i in range(len(raw_tokens) - 1):
                    bigram = f"{raw_tokens[i]} {raw_tokens[i+1]}"
                    if bigram in norm_searchable:
                        doc_scores[doc_idx] += 3.0

        if not doc_scores:
            return []

        # Sort and take top_k
        ranked = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

        results = []
        for rank, (doc_idx, score) in enumerate(ranked, start=1):
            e = self.entries[doc_idx]
            results.append({
                "rank": rank,
                "score": round(score, 3),
                "id": e["id"],
                "message": e["message"],
                "description": e["description"],
                "qna_description": e.get("qna_description", ""),
                "deeplink": e["deeplink"],  # VERBATIM ORIGINAL URI
                "originalType": e.get("originalType"),
                "control_type": e.get("control_type"),
                "validation": e.get("validation"),
            })

        return results


def run_benchmark(retriever: DeeplinkBM25Retriever) -> Dict[str, Any]:
    """Runs required test queries and produces detailed evaluation data."""
    test_queries = [
        # Dataset wording matches
        "power saving mode",
        "screen brightness",
        "bluetooth pairing",
        # Paraphrased queries
        "save battery",
        "my battery drains quickly",
        "turn on battery saver",
        "display is too dim",
    ]

    benchmark_results = {}
    print("\n" + "=" * 80)
    print("PHASE 1 RETRIEVAL BENCHMARK — TEST QUERIES")
    print("=" * 80)

    for query in test_queries:
        candidates = retriever.search(query, top_k=5)
        benchmark_results[query] = candidates
        print(f"\nQUERY: \"{query}\"")
        print("-" * 80)
        if not candidates:
            print("  [NO RESULTS RETURNED]")
            continue

        for c in candidates:
            print(f"  Rank {c['rank']} (Score: {c['score']:6.2f}) | ID: {c['id']}")
            print(f"    Message:     {c['message']}")
            print(f"    Description: {c['description']}")
            print(f"    QnA:         {c['qna_description']}")
            print(f"    URI:         {c['deeplink']}")
            print(f"    Type:        {c['originalType']}")
            print()

    return benchmark_results


def main():
    parser = argparse.ArgumentParser(description="Search Samsung Deeplinks Catalog")
    parser.add_argument("--query", type=str, help="Natural language query to search")
    parser.add_argument("--top_k", type=int, default=5, help="Number of results to return")
    parser.add_argument("--benchmark", action="store_true", help="Run full benchmark suite")
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    cleaned_data_path = os.path.join(script_dir, "generated", "cleaned_deeplinks.json")

    retriever = DeeplinkBM25Retriever(cleaned_data_path)

    if args.benchmark or not args.query:
        run_benchmark(retriever)
    else:
        results = retriever.search(args.query, top_k=args.top_k)
        print(f"\nQuery: \"{args.query}\"")
        print(f"Top {len(results)} matches:")
        for r in results:
            print(f"[{r['rank']}] Score: {r['score']} | {r['id']} | {r['message']}")
            print(f"    URI: {r['deeplink']}")
            print(f"    Desc: {r['description']}\n")


if __name__ == "__main__":
    main()
