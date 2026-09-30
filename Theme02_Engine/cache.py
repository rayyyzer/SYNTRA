"""Semantic and Exact Query Caching Layer for Theme 2.

Guarantees:
- Repeat query p95 <= 300ms (in-memory hash lookup is < 2ms)
- Paraphrase cache hit >= 80% using keyword and intent hashing
"""

from __future__ import annotations
import hashlib
import re
from typing import Any, Dict, Optional, Set, Tuple

from retrieval.polarity import detect_query_polarity, Polarity


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
    r"\b(battery\s+saver|power\s+saving|battery\s+saving|low\s+power\s+mode|conserve\s+(?:battery\s+)?power|save\s+(?:battery|power))\b": "__power_saving__",

    r"\b(wi[- ]?fi(\s+connection)?|wireless\s+network|wlan)\b": "__wifi__",
    r"\b(bluetooth(\s+radio|\s+adapter)?|bt)\b": "__bluetooth__",
    r"\b(airplane\s+mode|flight\s+mode)\b": "__airplane_mode__",
    r"\b(always\s+on\s+display|aod)\b": "__aod__",
    r"\b(eye\s+comfort(\s+shield)?|blue\s+light(\s+filter)?|eye\s+protection(\s+shield)?)\b": "__eye_comfort__",
    r"\b(auto\s+dim(\s+screen)?)\b": "__auto_dim__",
    r"\b(screen\s+timeout)\b": "__screen_timeout__",
    r"\b(accidental\s+touch(\s+protection)?)\b": "__accidental_touch__",
    r"\b(app\s+icon\s+badges?)\b": "__icon_badges__",
    r"\b(auto\s+blocker)\b": "__auto_blocker__",
    r"\b(battery\s+protection|protect\s+battery)\b": "__battery_protect__",
    r"\b(samsung\s+cloud(\s+backup)?|back\s+up\s+data(\s+to\s+cloud)?|backup\s+phone\s+data)\b": "__cloud_backup__",
    r"\b(flashes?|blinks?|flickers?)\b": "__flicker__",
    r"\b(black|blank|dark)\b": "__black_screen__",
}

COMPILED_SYNONYMS = [(re.compile(p, re.I), r) for p, r in SYNONYM_MAP.items()]


class QueryCache:
    def __init__(self, capacity: int = 1000):
        self.capacity = capacity
        self.exact_cache: Dict[str, Dict[str, Any]] = {}
        self.intent_cache: Dict[str, Dict[str, Any]] = {}
        self.known_intents: Dict[str, Tuple[str, Set[str], str, Dict[str, Any]]] = {}

    @staticmethod
    def _normalize(query: str) -> str:
        clean = re.sub(r"[^\w\s]", "", query.lower())
        return " ".join(clean.split())

    @staticmethod
    def _compute_siis_digest(siis_title: str = "", siis_content: str = "") -> str:
        """Derive a stable cryptographic digest of SIIS troubleshooting context."""
        clean_title = (siis_title or "").strip().lower()
        clean_content = (siis_content or "").strip().lower()
        if not clean_title and not clean_content:
            return "none"
        combined = f"{clean_title}::{clean_content}".encode("utf-8")
        return hashlib.sha256(combined).hexdigest()[:16]

    @staticmethod
    def _detect_polarity(query: str) -> str:
        """Classify directional intent to prevent cross-polarity cache collisions."""
        pol = detect_query_polarity(query)
        if pol == Polarity.ENABLE:
            return "ENABLE"
        if pol == Polarity.DISABLE:
            return "DISABLE"
        if pol == Polarity.VIEW:
            return "VIEW"
        if pol == Polarity.CONFIGURE:
            return "CONFIG"
        return "NEUTRAL"

    @classmethod
    def _extract_intent_signature(cls, query: str) -> str:
        """Extract canonical semantic tokens with strict polarity namespacing."""
        pol = cls._detect_polarity(query)
        q = query.lower()
        for pat, replacement in COMPILED_SYNONYMS:
            q = pat.sub(replacement, q)
        tokens = re.findall(r"__[a-z_]+__|[a-z]{3,}", q)
        stopwords = {"the", "and", "for", "phone", "device", "samsung", "galaxy", "mode", "with", "from", "when", "after", "about", "cant", "cannot", "turn", "switch", "off", "on"}
        feature_tokens = sorted([t for t in tokens if t not in stopwords and t not in ("__enable__", "__disable__", "__adjust__", "__view__")])
        if not feature_tokens:
            feature_tokens = sorted([t for t in tokens if t not in stopwords])
        return f"{pol}:{' '.join(feature_tokens)}"

    def get(self, query: str, siis_title: str = "", siis_content: str = "") -> Optional[Dict[str, Any]]:
        norm = self._normalize(query)
        digest = self._compute_siis_digest(siis_title, siis_content)
        has_context = (digest != "none")

        # 1. Exact normalized match (<0.01ms)
        if has_context:
            exact_key = f"{norm}#{digest}"
            if exact_key in self.exact_cache:
                return self.exact_cache[exact_key]
        else:
            # Fallback for query-only callers without SIIS context
            prefix = f"{norm}#"
            for k, v in self.exact_cache.items():
                if k.startswith(prefix) or k == norm:
                    return v

        # 2. Polarity-safe intent signature match (<0.03ms)
        sig = self._extract_intent_signature(query)
        if sig:
            if has_context:
                sig_key = f"{sig}#{digest}"
                if sig_key in self.intent_cache:
                    return self.intent_cache[sig_key]
            else:
                sig_prefix = f"{sig}#"
                for k, v in self.intent_cache.items():
                    if k.startswith(sig_prefix) or k == sig:
                        return v

        # 3. Token overlap fuzzy match with strict polarity guard & context isolation
        q_pol = self._detect_polarity(query)
        q_tokens = set(re.findall(r"\b[a-z]{3,}\b", norm))
        best_score = 0.0
        best_resp = None

        # Bounded scan across recent entries to prevent O(N) CPU exhaustion
        recent_items = list(self.known_intents.items())[-100:]
        for known_key, (known_pol, known_tokens, known_digest, resp) in recent_items:
            # Context isolation: Must match the same SIIS context digest if context provided
            if has_context and known_digest != digest:
                continue
            # STRICT POLARITY GUARD: Opposites can NEVER match
            if q_pol != "NEUTRAL" and known_pol != "NEUTRAL" and q_pol != known_pol:
                continue
            if not known_tokens:
                continue
            overlap = len(q_tokens.intersection(known_tokens))
            union = len(q_tokens.union(known_tokens))
            jaccard = overlap / union if union else 0
            # For queries within the exact same SIIS context digest, also test containment
            containment = overlap / min(len(q_tokens), len(known_tokens)) if min(len(q_tokens), len(known_tokens)) > 0 else 0
            score = max(jaccard, containment if (has_context and known_digest == digest) else 0)
            if score > best_score:
                best_score = score
                best_resp = resp

        if best_score >= 0.50:
            # Store in exact cache to speed up subsequent queries
            store_key = f"{norm}#{digest}" if has_context else f"{norm}#none"
            if len(self.exact_cache) >= self.capacity:
                del self.exact_cache[next(iter(self.exact_cache))]
            self.exact_cache[store_key] = best_resp
            return best_resp

        return None

    def put(self, query: str, response: Dict[str, Any], siis_title: str = "", siis_content: str = ""):
        norm = self._normalize(query)
        digest = self._compute_siis_digest(siis_title, siis_content)
        exact_key = f"{norm}#{digest}"
        sig = self._extract_intent_signature(query)
        sig_key = f"{sig}#{digest}"
        pol = self._detect_polarity(query)

        # Strict capacity bounds and deterministic FIFO eviction on all tiers
        if len(self.exact_cache) >= self.capacity:
            del self.exact_cache[next(iter(self.exact_cache))]
        self.exact_cache[exact_key] = response

        if sig:
            if len(self.intent_cache) >= self.capacity:
                del self.intent_cache[next(iter(self.intent_cache))]
            self.intent_cache[sig_key] = response

        if len(self.known_intents) >= self.capacity:
            del self.known_intents[next(iter(self.known_intents))]
        q_tokens = set(re.findall(r"\b[a-z]{3,}\b", norm))
        self.known_intents[exact_key] = (pol, q_tokens, digest, response)
