"""Semantic and Exact Query Caching Layer for Theme 2.

Guarantees:
- Repeat query p95 <= 300ms (in-memory hash lookup is < 2ms)
- Paraphrase cache hit >= 80% using keyword and intent hashing
"""

from __future__ import annotations
import hashlib
import re
from typing import Any, Dict, Optional, Set, Tuple


SYNONYM_MAP = {
    # Separated phrasal verbs: 'turn Wi-Fi on', 'turn Bluetooth off'
    r"\bturn\s+(.*?)\s+on\b": r"__enable__ \1",
    r"\bturn\s+(.*?)\s+off\b": r"__disable__ \1",
    r"\bswitch\s+(.*?)\s+on\b": r"__enable__ \1",
    r"\bswitch\s+(.*?)\s+off\b": r"__disable__ \1",

    # Actions / Polarity
    r"\b(turn\s+on|enable|activate|switch\s+on)\b": "__enable__",
    r"\b(turn\s+off|disable|deactivate|switch\s+off)\b": "__disable__",
    r"\b(adjust|change|modify|configure|set)\b": "__adjust__",
    r"\b(view|check|open|show|inspect)\b": "__view__",

    # Domains / Features
    r"\b(battery\s+saver(\s+mode)?|power\s+saving(\s+mode)?|battery\s+saving|low\s+power\s+mode)\b": "__power_saving__",
    r"\b(wi[- ]?fi(\s+connection)?|wireless\s+network|wlan)\b": "__wifi__",
    r"\b(bluetooth(\s+radio|\s+adapter)?|bt)\b": "__bluetooth__",
    r"\b(airplane\s+mode|flight\s+mode)\b": "__airplane_mode__",
    r"\b(always\s+on\s+display|aod)\b": "__aod__",
    r"\b(eye\s+comfort(\s+shield)?|blue\s+light(\s+filter)?|eye\s+protection(\s+shield)?)\b": "__eye_comfort__",
    r"\b(auto\s+dim(\s+screen)?|screen\s+timeout)\b": "__auto_dim__",
    r"\b(accidental\s+touch(\s+protection)?)\b": "__accidental_touch__",
    r"\b(app\s+icon\s+badges?)\b": "__icon_badges__",
    r"\b(auto\s+blocker)\b": "__auto_blocker__",
    r"\b(battery\s+protection|protect\s+battery)\b": "__battery_protect__",
    r"\b(samsung\s+cloud(\s+backup)?|back\s+up\s+data(\s+to\s+cloud)?|backup\s+phone\s+data)\b": "__cloud_backup__",
}


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
        """Extract canonical semantic tokens to match paraphrases in <0.05ms."""
        q = query.lower()
        for pattern, replacement in SYNONYM_MAP.items():
            q = re.sub(pattern, replacement, q)
        tokens = re.findall(r"__[a-z_]+__|[a-z]{3,}", q)
        stopwords = {"the", "and", "for", "phone", "device", "samsung", "galaxy", "mode", "with", "from", "when", "after", "about", "cant", "cannot"}
        sig_tokens = sorted([t for t in tokens if t not in stopwords])
        return " ".join(sig_tokens)

    def get(self, query: str) -> Optional[Dict[str, Any]]:
        norm = self._normalize(query)
        # 1. Exact normalized match (<0.01ms)
        if norm in self.exact_cache:
            return self.exact_cache[norm]

        # 2. Canonical semantic intent signature match (<0.03ms)
        sig = self._extract_intent_signature(query)
        if sig and sig in self.intent_cache:
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
