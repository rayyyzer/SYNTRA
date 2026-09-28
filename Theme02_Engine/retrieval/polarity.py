"""Explicit Polarity and Action Intent Handling.

Distinguishes:
- enable: turn on, activate, switch on, start, allow, unmute
- disable: turn off, deactivate, switch off, stop, mute, block, prevent
- view: open, view, check, inspect, show, display
- configure: adjust, customize, set up, format, change
- query: how do I, why does, what is
- unknown: ambiguous or no clear directional signal
"""

from __future__ import annotations
import re
from enum import Enum
from typing import Any, Dict, Optional, Set


class Polarity(str, Enum):
    ENABLE = "enable"
    DISABLE = "disable"
    VIEW = "view"
    CONFIGURE = "configure"
    QUERY = "query"
    UNKNOWN = "unknown"


POLARITY_ENABLE_PHRASES = (
    "turn on", "switch on", "activate", "enable", "start", "allow",
    "unmute", "bring back", "turn back on", "switch back on", "turn up",
    "increase brightness", "connect to", "reconnect"
)

POLARITY_DISABLE_PHRASES = (
    "turn off", "switch off", "deactivate", "disable", "stop", "mute",
    "block", "shut off", "turn down", "silence", "disconnect",
    "stop buzzing", "no more", "prevent", "cancel", "disabel"
)

POLARITY_VIEW_PHRASES = (
    "view", "open", "check", "inspect", "show", "display", "navigate to",
    "look at", "find", "access"
)

POLARITY_CONFIG_PHRASES = (
    "adjust", "configure", "set up", "setup", "customize", "change",
    "modify", "format", "switch time format", "personalize"
)

POLARITY_QUERY_PHRASES = (
    "how do i", "how to", "why does", "what is", "can i", "is there a way"
)


def detect_query_polarity(query: str) -> Polarity:
    """Classifies query intent into a discrete semantic Polarity state."""
    q_low = query.lower()

    # 1. Multi-word phrase check (higher specificity)
    for phrase in POLARITY_ENABLE_PHRASES:
        if phrase in q_low:
            return Polarity.ENABLE

    for phrase in POLARITY_DISABLE_PHRASES:
        if phrase in q_low:
            return Polarity.DISABLE

    for phrase in POLARITY_CONFIG_PHRASES:
        if phrase in q_low:
            return Polarity.CONFIGURE

    for phrase in POLARITY_VIEW_PHRASES:
        if phrase in q_low:
            return Polarity.VIEW

    for phrase in POLARITY_QUERY_PHRASES:
        if phrase in q_low:
            return Polarity.QUERY

    # 2. Token-level fallback
    tokens = set(re.findall(r"\b[a-z]{2,}\b", q_low))
    if any(t in ("enable", "activate", "on") for t in tokens):
        return Polarity.ENABLE
    if any(t in ("disable", "deactivate", "off", "mute") for t in tokens):
        return Polarity.DISABLE

    return Polarity.UNKNOWN


def get_entry_polarity(entry: Optional[Dict[str, Any]]) -> Polarity:
    """Extracts official control polarity from catalog entry metadata."""
    if not entry:
        return Polarity.UNKNOWN

    ctrl = str(entry.get("control_type") or "").strip().lower()
    if ctrl == "onurl":
        return Polarity.ENABLE
    if ctrl == "offurl":
        return Polarity.DISABLE

    text = f"{entry.get('message', '')} {entry.get('description', '')}".lower()
    if any(w in text for w in ("disable", "turn off", "deactivate", "switch off", "mute")):
        return Polarity.DISABLE
    if any(w in text for w in ("enable", "turn on", "activate", "switch on", "unmute")):
        return Polarity.ENABLE
    if any(w in text for w in ("view", "open", "check", "inspect", "show")):
        return Polarity.VIEW
    if any(w in text for w in ("adjust", "configure", "settings", "format")):
        return Polarity.CONFIGURE

    return Polarity.UNKNOWN


def compute_polarity_adjustment(query_polarity: Polarity, entry_polarity: Polarity) -> float:
    """Calculates additive re-ranking score adjustment based on polarity alignment."""
    if query_polarity in (Polarity.ENABLE, Polarity.DISABLE):
        if entry_polarity == query_polarity:
            return 0.30  # Substantial boost for matching polarity
        if entry_polarity in (Polarity.ENABLE, Polarity.DISABLE) and entry_polarity != query_polarity:
            return -0.60  # Severe penalty for opposite polarity toggle
    return 0.0
