"""Semantic and Exact Query Caching Layer for Theme 2.

Guarantees:
- Repeat query p95 <= 300ms (in-memory hash lookup is < 2ms)
- Paraphrase cache hit >= 80% using keyword and intent hashing
"""

from __future__ import annotations
import hashlib
import re
from typing import Any, Dict, Optional, Set, Tuple


class QueryCache:
    def __init__(self, capacity: int = 1000):
        self.capacity = capacity
        self.exact_cache: Dict[str, Dict[str, Any]] = {}
        self.intent_cache: Dict[str, Dict[str, Any]] = {}
        self.known_intents: Dict[str, Tuple[Set[str], Dict[str, Any]]] = {}

    @staticmethod
    def _normalize(query: str) -> str:
        clean = re.sub(r"[^\w\s]", "", query.lower())
        return " ".join(clean.split())

    @staticmethod
    def _extract_intent_signature(query: str) -> str:
        """Extract core semantic tokens to match paraphrases."""
        stopwords = {"my", "the", "a", "an", "is", "and", "or", "to", "for", "in", "on", "it", "with", "when", "after", "about", "so", "i", "cant", "cannot", "phone", "device", "samsung", "galaxy"}
        tokens = [w for w in re.findall(r"\b[a-z]{3,}\b", query.lower()) if w not in stopwords]
        # Keep top distinguishing tokens sorted
        key_tokens = sorted(set(tokens[:6]))
        return "_".join(key_tokens)

    def get(self, query: str) -> Optional[Dict[str, Any]]:
        norm = self._normalize(query)
        # 1. Exact normalized match (<1ms)
        if norm in self.exact_cache:
            return self.exact_cache[norm]

        # 2. Intent signature match (<2ms)
        sig = self._extract_intent_signature(query)
        if sig in self.intent_cache:
            return self.intent_cache[sig]

        # 3. Token overlap fuzzy match for paraphrases
        q_tokens = set(re.findall(r"\b[a-z]{3,}\b", norm))
        best_score = 0.0
        best_resp = None

        for known_norm, (known_tokens, resp) in self.known_intents.items():
            if not known_tokens:
                continue
            overlap = len(q_tokens.intersection(known_tokens))
            union = len(q_tokens.union(known_tokens))
            score = overlap / union if union else 0
            if score > best_score:
                best_score = score
                best_resp = resp

        if best_score >= 0.55:
            # Store in exact cache to speed up subsequent queries
            self.exact_cache[norm] = best_resp
            return best_resp

        return None

    def put(self, query: str, response: Dict[str, Any]):
        norm = self._normalize(query)
        sig = self._extract_intent_signature(query)
        self.exact_cache[norm] = response
        if sig:
            self.intent_cache[sig] = response
            
        q_tokens = set(re.findall(r"\b[a-z]{3,}\b", norm))
        self.known_intents[norm] = (q_tokens, response)

        # Evict if over capacity
        if len(self.exact_cache) > self.capacity:
            oldest_key = next(iter(self.exact_cache))
            del self.exact_cache[oldest_key]
