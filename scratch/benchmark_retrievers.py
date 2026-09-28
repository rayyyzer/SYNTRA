"""Benchmarking Retrieval Architectures on 164-Scenario Robustness Dataset.

Compares:
1. Baseline Jaccard Token Overlap (current Theme02_Engine implementation)
2. Pure Multi-Field BM25 (Okapi formula with weighted fields)
3. Multi-Field BM25 + Explicit Polarity Re-ranking
4. Dense Semantic Embedding Retrieval (all-MiniLM-L6-v2)
5. Hybrid Retrieval (BM25 + Dense Embeddings + Polarity Re-ranking)
"""

from __future__ import annotations
import json
import math
import os
import re
import sys
import time
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATASET_PATH = os.path.join(PROJECT_ROOT, "tests", "theme2", "robustness_dataset.jsonl")
CATALOG_PATH = os.path.join(PROJECT_ROOT, "scratch", "generated", "cleaned_deeplinks.json")
RESULTS_OUT = os.path.join(PROJECT_ROOT, "scratch", "generated", "retrieval_benchmark.json")

# Ensure Theme02_Engine is accessible for baseline Jaccard
THEME2_DIR = os.path.join(PROJECT_ROOT, "Theme02_Engine")
if THEME2_DIR not in sys.path:
    sys.path.insert(0, THEME2_DIR)

from deeplink_matcher import DeeplinkIndex


# -----------------------------------------------------------------------------
# Polarity & Intent Helper Functions
# -----------------------------------------------------------------------------
POLARITY_ENABLE_WORDS = {"enable", "turn on", "activate", "switch on", "start", "allow", "unmute"}
POLARITY_DISABLE_WORDS = {"disable", "turn off", "deactivate", "switch off", "stop", "mute", "block"}


def detect_query_polarity(query: str) -> str:
    """Classify query intent polarity as enable, disable, or neutral."""
    q_low = query.lower()
    for phrase in ("turn on", "switch on", "unmute", "turn off", "switch off"):
        if phrase in q_low:
            return "enable" if "on" in phrase or phrase == "unmute" else "disable"

    tokens = set(re.findall(r"\b[a-z]{2,}\b", q_low))
    if any(t in POLARITY_ENABLE_WORDS for t in tokens):
        return "enable"
    if any(t in POLARITY_DISABLE_WORDS for t in tokens):
        return "disable"
    return "neutral"


def get_entry_polarity(entry: Dict[str, Any]) -> str:
    """Determine the control polarity of a catalog entry."""
    ctrl = str(entry.get("control_type") or "").lower()
    if ctrl == "onurl":
        return "enable"
    if ctrl == "offurl":
        return "disable"

    text = f"{entry.get('message', '')} {entry.get('description', '')}".lower()
    if any(w in text for w in ("disable", "turn off", "deactivate", "switch off", "mute")):
        return "disable"
    if any(w in text for w in ("enable", "turn on", "activate", "switch on")):
        return "enable"
    return "neutral"


# -----------------------------------------------------------------------------
# 1. Baseline Jaccard Retriever Adapter
# -----------------------------------------------------------------------------
class BaselineJaccardAdapter:
    def __init__(self):
        self.matcher = DeeplinkIndex()

    def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        act_dl, _ = self.matcher.find_match(query, "")
        matched_entry = None
        for e in self.matcher.entries:
            if e["deeplink"] == act_dl["deeplink"]:
                matched_entry = e
                break
        return [{"deeplink": act_dl["deeplink"], "score": 1.0, "message": act_dl.get("message", ""), "entry": matched_entry}]


# -----------------------------------------------------------------------------
# 2. Pure Multi-Field BM25 Retriever
# -----------------------------------------------------------------------------
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
    def __init__(self, catalog: List[Dict[str, Any]], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.entries = catalog
        self.total_docs = len(catalog)
        self.doc_len: List[int] = []
        self.inverted_index: Dict[str, Dict[int, float]] = defaultdict(dict)
        self.df: Dict[str, int] = defaultdict(int)
        self.idf: Dict[str, float] = {}
        self._build_index()

    def _build_index(self):
        total_tokens = 0
        for idx, entry in enumerate(self.entries):
            msg_tokens = [stem_token(t) for t in tokenize(entry.get("message", ""))]
            desc_tokens = [stem_token(t) for t in tokenize(entry.get("description", ""))]
            qna_tokens = [stem_token(t) for t in tokenize(entry.get("qna_description", ""))]

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
                # Substring match for partial word matching
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
            norm_searchable = entry.get("normalized_searchable", "")
            if query_str in norm_searchable:
                doc_scores[doc_idx] += 8.0
            if len(raw_tokens) >= 2:
                for i in range(len(raw_tokens) - 1):
                    bigram = f"{raw_tokens[i]} {raw_tokens[i+1]}"
                    if bigram in norm_searchable:
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
                "id": e["id"],
                "message": e["message"],
                "score": round(sc, 3),
                "entry": e
            })
        return results


# -----------------------------------------------------------------------------
# 3. Multi-Field BM25 + Polarity-Aware Re-ranking
# -----------------------------------------------------------------------------
class BM25PolarityRetriever:
    def __init__(self, bm25: BM25Retriever):
        self.bm25 = bm25

    def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        scores = self.bm25.score_docs(query)
        if not scores:
            return []

        q_polarity = detect_query_polarity(query)
        reranked: Dict[int, float] = {}

        for doc_idx, raw_score in scores.items():
            entry = self.bm25.entries[doc_idx]
            e_polarity = get_entry_polarity(entry)

            adjusted_score = raw_score
            if q_polarity in ("enable", "disable"):
                if e_polarity == q_polarity:
                    adjusted_score += 10.0  # Significant polarity match bonus
                elif e_polarity != "neutral" and e_polarity != q_polarity:
                    adjusted_score -= 15.0  # Severe penalty for opposite polarity

            reranked[doc_idx] = adjusted_score

        ranked = sorted(reranked.items(), key=lambda x: x[1], reverse=True)[:top_k]
        results = []
        for doc_idx, sc in ranked:
            e = self.bm25.entries[doc_idx]
            results.append({
                "deeplink": e["deeplink"],
                "id": e["id"],
                "message": e["message"],
                "score": round(sc, 3),
                "entry": e
            })
        return results


# -----------------------------------------------------------------------------
# 4. Dense Semantic Embedding Retriever
# -----------------------------------------------------------------------------
class DenseEmbeddingRetriever:
    def __init__(self, catalog: List[Dict[str, Any]], model_name: str = "all-MiniLM-L6-v2"):
        self.entries = catalog
        self.model_name = model_name
        self.model = None
        self.catalog_embeddings = None
        self._init_model()

    def _init_model(self):
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
            import numpy as np  # type: ignore
            print(f"[Dense] Loading SentenceTransformer: {self.model_name}...")
            t0 = time.perf_counter()
            self.model = SentenceTransformer(self.model_name)
            t1 = time.perf_counter()
            self.load_time_ms = (t1 - t0) * 1000.0
            print(f"[Dense] Model loaded in {self.load_time_ms:.1f} ms. Pre-computing catalog embeddings...")

            # Build searchable strings
            texts = [
                f"{e.get('message', '')}. {e.get('description', '')}. {e.get('qna_description', '')}"
                for e in self.entries
            ]
            t0 = time.perf_counter()
            self.catalog_embeddings = self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
            t1 = time.perf_counter()
            print(f"[Dense] Encoded {len(self.entries)} entries in {(t1 - t0)*1000.0:.1f} ms.")
        except Exception as e:
            print(f"[Dense Warning] Could not load {self.model_name}: {e}")
            self.model = None

    def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        if self.model is None or self.catalog_embeddings is None:
            return []
        import numpy as np  # type: ignore

        q_emb = self.model.encode([query], normalize_embeddings=True, show_progress_bar=False)[0]
        # Cosine similarity is dot product of normalized vectors
        scores = np.dot(self.catalog_embeddings, q_emb)

        top_indices = np.argsort(scores)[::-1][:top_k]
        results = []
        for idx in top_indices:
            e = self.entries[idx]
            results.append({
                "deeplink": e["deeplink"],
                "id": e["id"],
                "message": e["message"],
                "score": round(float(scores[idx]), 4),
                "entry": e
            })
        return results


# -----------------------------------------------------------------------------
# 5. Hybrid Retriever (Dense + BM25 + Polarity Re-ranking)
# -----------------------------------------------------------------------------
class HybridRetriever:
    def __init__(self, bm25: BM25Retriever, dense: DenseEmbeddingRetriever, alpha: float = 0.5):
        self.bm25 = bm25
        self.dense = dense
        self.alpha = alpha  # Weight for dense embeddings (1-alpha for BM25)

    def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        # 1. Get BM25 scores
        bm25_scores = self.bm25.score_docs(query)
        max_bm25 = max(bm25_scores.values()) if bm25_scores else 1.0

        # 2. Get Dense scores
        dense_scores: Dict[int, float] = {}
        if self.dense.model is not None and self.dense.catalog_embeddings is not None:
            import numpy as np  # type: ignore
            q_emb = self.dense.model.encode([query], normalize_embeddings=True, show_progress_bar=False)[0]
            d_sims = np.dot(self.dense.catalog_embeddings, q_emb)
            for idx, sim in enumerate(d_sims):
                dense_scores[idx] = float(sim)

        # 3. Fuse scores (Linear Combination of normalized scores)
        q_polarity = detect_query_polarity(query)
        fused: Dict[int, float] = {}

        candidate_indices = set(bm25_scores.keys()).union(set(dense_scores.keys()))
        for idx in candidate_indices:
            norm_bm25 = (bm25_scores.get(idx, 0.0) / max_bm25) if max_bm25 > 0 else 0.0
            norm_dense = dense_scores.get(idx, 0.0)

            score = (1.0 - self.alpha) * norm_bm25 + self.alpha * norm_dense

            # Polarity adjustment
            entry = self.bm25.entries[idx]
            e_polarity = get_entry_polarity(entry)
            if q_polarity in ("enable", "disable"):
                if e_polarity == q_polarity:
                    score += 0.25  # Substantial boost
                elif e_polarity != "neutral" and e_polarity != q_polarity:
                    score -= 0.50  # Severe penalty

            fused[idx] = score

        ranked = sorted(fused.items(), key=lambda x: x[1], reverse=True)[:top_k]
        results = []
        for idx, sc in ranked:
            e = self.bm25.entries[idx]
            results.append({
                "deeplink": e["deeplink"],
                "id": e["id"],
                "message": e["message"],
                "score": round(sc, 4),
                "entry": e
            })
        return results


# -----------------------------------------------------------------------------
# Evaluation Runner
# -----------------------------------------------------------------------------
def evaluate_retriever(name: str, retriever, cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    print(f"\nEvaluating: {name} on {len(cases)} cases...")
    latencies = []
    top1_matches = 0
    top3_matches = 0
    polarity_eval_count = 0
    polarity_matches = 0
    action_matches = 0

    class_matches: Dict[str, int] = defaultdict(int)
    class_totals: Dict[str, int] = defaultdict(int)

    for case in cases:
        q = case["query"]
        c_class = case["class"]
        exp_uri = case.get("expected_uri")
        exp_act = case.get("expected_action")
        exp_pol = case.get("expected_polarity", "neutral")

        class_totals[c_class] += 1

        t0 = time.perf_counter()
        candidates = retriever.retrieve(q, top_k=5)
        t1 = time.perf_counter()
        latencies.append((t1 - t0) * 1000.0)

        top1_uri = candidates[0]["deeplink"] if candidates else None
        top3_uris = [c["deeplink"] for c in candidates[:3]]
        top1_msg = candidates[0].get("message", "") if candidates else ""

        # Top-1 URI Match
        is_top1 = False
        if exp_uri:
            is_top1 = (top1_uri == exp_uri)
        else:
            is_top1 = (top1_uri in ("bixby://dummy_positive", None))

        if is_top1:
            top1_matches += 1
            class_matches[c_class] += 1

        # Top-3 URI Match
        if exp_uri and exp_uri in top3_uris:
            top3_matches += 1
        elif not exp_uri and any(u in ("bixby://dummy_positive", None) for u in top3_uris):
            top3_matches += 1

        # Action match
        if exp_act and top1_msg and (exp_act.lower() in top1_msg.lower() or top1_msg.lower() in exp_act.lower()):
            action_matches += 1

        # Polarity match on Class D
        if exp_pol in ("enable", "disable"):
            polarity_eval_count += 1
            top1_entry = candidates[0].get("entry") if candidates else None
            gen_pol = get_entry_polarity(top1_entry) if top1_entry else "unknown"
            if gen_pol == exp_pol:
                polarity_matches += 1

    total = len(cases)
    lat_sorted = sorted(latencies)
    top1_rate = (top1_matches / total) * 100.0
    top3_rate = (top3_matches / total) * 100.0
    action_rate = (action_matches / total) * 100.0
    pol_rate = (polarity_matches / polarity_eval_count) * 100.0 if polarity_eval_count else 0.0

    class_rates = {
        cls_name: round((class_matches[cls_name] / class_totals[cls_name]) * 100.0, 1)
        for cls_name in sorted(class_totals.keys())
    }

    results = {
        "name": name,
        "total_cases": total,
        "top1_uri_match_rate_pct": round(top1_rate, 2),
        "top3_uri_recall_rate_pct": round(top3_rate, 2),
        "action_match_rate_pct": round(action_rate, 2),
        "polarity_accuracy_pct": round(pol_rate, 2),
        "class_breakdown": class_rates,
        "cold_start_lat_ms": round(latencies[0], 3),
        "p50_lat_ms": round(lat_sorted[int(total * 0.50)], 3),
        "p95_lat_ms": round(lat_sorted[int(total * 0.95)], 3),
        "mean_lat_ms": round(sum(latencies) / len(latencies), 3),
    }

    print(f"  Top-1 URI Match:   {top1_rate:.2f}% ({top1_matches}/{total})")
    print(f"  Top-3 URI Recall:  {top3_rate:.2f}% ({top3_matches}/{total})")
    print(f"  Polarity Accuracy: {pol_rate:.2f}% ({polarity_matches}/{polarity_eval_count})")
    print(f"  Severe Paraphrase (Class C): {class_rates.get('C_severe_paraphrase', 0)}%")
    print(f"  Public Regression (Class A): {class_rates.get('A_public_regression', 0)}%")
    print(f"  P50 Latency:       {results['p50_lat_ms']} ms | P95: {results['p95_lat_ms']} ms")
    return results


def run_benchmark():
    print("=" * 80)
    print("PHASE 4: RETRIEVAL & EMBEDDING BENCHMARK")
    print("=" * 80)

    # 1. Load Dataset
    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        cases = [json.loads(line) for line in f if line.strip()]

    # 2. Load Catalog
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    all_results = {}

    # Approach 1: Baseline Jaccard
    jaccard_retriever = BaselineJaccardAdapter()
    all_results["1_baseline_jaccard"] = evaluate_retriever("1. Baseline Jaccard", jaccard_retriever, cases)

    # Approach 2: Pure Multi-Field BM25
    bm25 = BM25Retriever(catalog)
    all_results["2_pure_bm25"] = evaluate_retriever("2. Pure Multi-Field BM25", bm25, cases)

    # Approach 3: BM25 + Polarity-Aware Re-ranking
    bm25_polarity = BM25PolarityRetriever(bm25)
    all_results["3_bm25_with_polarity"] = evaluate_retriever("3. BM25 + Polarity Re-ranking", bm25_polarity, cases)

    # Approach 4: Dense Semantic Embedding (all-MiniLM-L6-v2)
    dense = DenseEmbeddingRetriever(catalog, model_name="all-MiniLM-L6-v2")
    if dense.model is not None:
        all_results["4_dense_minilm"] = evaluate_retriever("4. Dense all-MiniLM-L6-v2", dense, cases)

        # Approach 5: Hybrid (Dense + BM25 + Polarity)
        hybrid = HybridRetriever(bm25, dense, alpha=0.55)
        all_results["5_hybrid_retrieval"] = evaluate_retriever("5. Hybrid BM25+Dense+Polarity", hybrid, cases)
    else:
        print("\n[Dense Embedding Note] sentence-transformers is not active in this run; skipping dense/hybrid benchmark.")
        all_results["4_dense_minilm"] = {"status": "unavailable_in_current_env"}
        all_results["5_hybrid_retrieval"] = {"status": "unavailable_in_current_env"}

    # Save Results
    os.makedirs(os.path.dirname(RESULTS_OUT), exist_ok=True)
    with open(RESULTS_OUT, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\n[Saved] Detailed benchmark results written to {RESULTS_OUT}")


if __name__ == "__main__":
    run_benchmark()
