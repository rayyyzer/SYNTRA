"""Deeplink Matcher: Fast semantic and keyword matcher over 578 masked Galaxy Settings deeplinks."""

from __future__ import annotations
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

CANDIDATE_KIT_DIRS = [
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "student_kit")),
    os.path.abspath(os.path.join(os.path.dirname(__file__), "data", "student_kit")),
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "participant-kit-all-themes", "participant-kit", "Theme02_Input_Kit", "student_kit")),
]
KIT_DIR = next((d for d in CANDIDATE_KIT_DIRS if os.path.exists(d)), CANDIDATE_KIT_DIRS[0])
DEEPLINKS_PATH = os.path.join(KIT_DIR, "deeplinks.json")


class DeeplinkIndex:
    def __init__(self, catalog_path: str = DEEPLINKS_PATH):
        self.catalog_path = catalog_path
        self.entries: List[Dict[str, Any]] = []
        self._load_catalog()

    def _load_catalog(self):
        with open(self.catalog_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.entries = data.get("deeplinks", [])

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        return [w.lower() for w in re.findall(r"\b[A-Za-z0-9_]{3,}\b", text)]

    def find_match(self, query: str, step_text: str = "") -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        """Find the best matching deeplink from the 578 masked entries."""
        combined_text = f"{query} {step_text}".lower()
        query_tokens = set(self._tokenize(combined_text))

        best_score = -1.0
        best_entry = None

        for entry in self.entries:
            desc = entry.get("description", "")
            msg = entry.get("message", "")
            qna = entry.get("qna_description", "") or ""
            target_tokens = set(self._tokenize(f"{desc} {msg} {qna}"))

            if not target_tokens:
                continue

            # Jaccard / token overlap score
            intersection = query_tokens.intersection(target_tokens)
            score = len(intersection) / len(query_tokens.union(target_tokens))

            # Bonus for exact key phrase matches
            if any(token in combined_text for token in ("backup", "display", "screen", "battery", "reset", "network", "wifi", "sound")):
                for token in ("backup", "display", "screen", "battery", "reset", "network", "wifi", "sound"):
                    if token in combined_text and token in desc.lower():
                        score += 0.2

            if score > best_score:
                best_score = score
                best_entry = entry

        # Threshold check: If match is solid, return it
        if best_entry and best_score >= 0.05:
            act_dl = {
                "deeplink": best_entry["deeplink"],
                "description": best_entry.get("description", "Opens the relevant device Settings page."),
                "message": best_entry.get("message", "Open Settings"),
                "originalType": best_entry.get("originalType", "onClickURL")
            }
            val_dl = None
            if "validation" in best_entry and best_entry["validation"]:
                v = best_entry["validation"]
                val_dl = {
                    "deeplink": v.get("deeplink", best_entry["deeplink"].replace("/act/", "/val/")),
                    "key": v.get("key", "Setting Status"),
                    "resultType": v.get("resultType", "boolean"),
                    "condition": v.get("condition", "equal"),
                    "value": str(v.get("value", "True"))
                }
            return act_dl, val_dl

        # Fallback to official generic placeholder
        fallback_act = {
            "deeplink": "bixby://dummy_positive",
            "description": "It will open device settings screen",
            "message": "Open Settings Screen",
            "originalType": "onClickURL"
        }
        return fallback_act, None
