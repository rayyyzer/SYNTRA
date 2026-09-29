"""Explicit Polarity and Action Intent Handling.

Distinguishes:
- enable: turn on, activate, switch on, start, allow, unmute, resource conservation goals, negation reversals
- disable: turn off, deactivate, switch off, stop, mute, block, prevent, mode reversals, complaints
- view: open, view, check, inspect, show, display
- configure: adjust, customize, set up, format, change
- query: how do I, why does, what is
- unknown: ambiguous, symptom diagnosis, or no clear directional signal
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
    "connect to", "reconnect"
)

POLARITY_DISABLE_PHRASES = (
    "turn off", "switch off", "deactivate", "disable", "stop", "mute",
    "block", "shut off", "turn down", "silence", "disconnect",
    "stop buzzing", "no more", "prevent", "cancel"
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

DRAIN_SYMPTOM_RE = re.compile(
    r"\b(battery\s+(?:dies|dying|draining|drains|drops\s+fast)|drain\s+issu|battery\s+drain|check\s+why\s+battery|battery\s+isn'?t\s+making\s+it|eating\s+(?:up\s+)?charge)\b",
    re.I
)

CONSERVATION_INTENT_PATTERN = re.compile(
    r"\b("
    r"(?:use\s+less|consume\s+less|save|conserve|preserve|extend|reduce|cut\s+down)\b.*?\b(?:battery|power|charge|energy|consumption|usage)"
    r"|stretch\b.*?\b(?:time\s+between\s+charges|charges)"
    r"|(?:better|longer|improve|increase|more)\s+(?:battery\s+life|battery\s+runtime|hours\s+out\s+of)"
    r"|(?:battery|power|charge)\b.*?\b(?:last|stretch|longer|more\s+hours|all\s+day)"
    r"|power\s+saving|battery\s+saver"
    r"|energy\s+conservation"
    r"|eating\s+(?:up\s+)?battery"
    r"|stop\s+using\s+so\s+much\s+(?:battery|power)"
    r")\b",
    re.I
)

DISABLE_REVERSAL_PATTERN = re.compile(
    r"\b("
    r"stop\s+(?:conserving|saving|battery\s+saver)|return\s+to\s+normal|restore\s+normal|resume\s+normal|normal\s+(?:battery|power)\s+usage"
    r"|turn\s+(?:battery\s+saver|power\s+saving)\s+off"
    r"|(?:turn\s+off|disable|deactivate|stop)\s+(?:power\s+saving|battery\s+saver)"
    r"|don'?t\s+want\s+(?:power\s+saving|battery\s+saver)\s+enabled"
    r"|don'?t\s+use\s+power\s+saving"
    r")\b",
    re.I
)


def detect_query_polarity(query: str, dense_retriever: Any = None, siis_text: Optional[str] = None) -> Polarity:
    """Classifies query intent into a discrete semantic Polarity state using compositional reasoning."""
    q_low = query.lower()

    # 0. Diagnostic Symptoms and Ongoing Issues are NOT direct toggle actions
    if DRAIN_SYMPTOM_RE.search(q_low):
        return Polarity.UNKNOWN

    # 1. Complex Polarity Traps & Double Negations
    # "I don't want power saving turned off" -> Double negative = ENABLE
    # "stop disabling battery saving" -> Double negative = ENABLE
    # "don't stop conserving power" -> Double negative = ENABLE
    if re.search(r"\b(?:don'?t\s+want|do\s+not\s+want|never\s+want)\b.*?\b(?:off|disabled?|deactivated)\b", q_low):
        return Polarity.ENABLE
    if re.search(r"\b(?:stop|prevent|avoid)\s+(?:disabling|turning\s+off|deactivating)\b", q_low):
        return Polarity.ENABLE
    if re.search(r"\b(?:don'?t|do\s+not)\s+stop\s+(?:conserving|saving)\b", q_low):
        return Polarity.ENABLE
    if re.search(r"\b(?:don'?t\s+want|do\s+not\s+want|never\s+want)\b.*?\b(?:on|enabled?|activated)\b", q_low):
        return Polarity.DISABLE

    # 1b. Inactive / Not active state goals ("make sure power saving is not active")
    if re.search(r"\b(?:not|isn'?t|aren'?t|never|no longer)\s+(?:active|on|enabled|running)\b", q_low):
        return Polarity.DISABLE

    # 2. Single Negations on Enablers / Disablers
    # "don't enable Bluetooth" -> DISABLE
    # "keep airplane mode disabled" -> DISABLE
    # "keep Wi-Fi enabled" -> ENABLE
    if re.search(r"\b(?:don'?t|do\s+not|never)\s+(?:enable|activate|turn\s+on)\b", q_low):
        return Polarity.DISABLE
    if re.search(r"\bkeep\b.*?\b(?:off|disabled?|deactivated)\b", q_low) and not re.search(r"\bkeep\b.*?\bfrom\b", q_low):
        return Polarity.DISABLE
    if re.search(r"\bkeep\b.*?\b(?:on|enabled?|activated)\b", q_low) or re.search(r"\bkeep\b.*?\bfrom\s+(?:turning\s+off|shutting\s+off)\b", q_low):
        return Polarity.ENABLE

    # 3. Explicit Mode Reversals (e.g. "stop conserving power", "return to normal battery usage")
    if DISABLE_REVERSAL_PATTERN.search(q_low):
        return Polarity.DISABLE

    # 3b. Joint SIIS Grounded Interpretation for symptom / nuisance / protection goals
    # Applies when the query is NOT already an explicit toggle directive (e.g. "turn off X", "disable X")
    has_explicit_directive = bool(re.search(r"\b(?:turn\s+off|disable|deactivate|switch\s+off|turn\s+on|enable|activate|switch\s+on)\b", q_low))
    if siis_text and not has_explicit_directive:
        siis_low = siis_text.lower()
        if any(w in q_low for w in ("stop", "prevent", "block", "avoid", "protect", "drain", "wont", "won't", "keep from")):
            if re.search(r"\b(?:turn on|enable|activate|switch on|tap\s+.*?\s+to\s+on|switch to on)\b", siis_low):
                return Polarity.ENABLE
            if re.search(r"\b(?:turn off|disable|deactivate|switch off|tap\s+.*?\s+to\s+off|switch to off)\b", siis_low):
                return Polarity.DISABLE

    # 4. Resource Reduction / Conservation Goals (wants restriction mode active)
    if CONSERVATION_INTENT_PATTERN.search(q_low) and not re.search(r"\b(?:turn\s+off|disable|deactivate|switch\s+off)\b", q_low):
        return Polarity.ENABLE

    # 4b. Vibration / Noise Complaints (wants to disable nuisance feedback)
    if any(k in q_low for k in ("buzzes", "buzzing", "vibrates every time", "vibrating every time", "stop buzzing", "stop vibrating")):
        return Polarity.DISABLE

    # 5. Device Mode Enablers (Flight, Zen/Do Not Disturb)
    if any(k in q_low for k in ("take off", "takeoff", "flight mode", "on a plane", "on a flight")):
        if not any(k in q_low for k in ("turn off", "disable", "stop", "end", "deactivate", "leave", "landed", "signal back")):
            return Polarity.ENABLE
        else:
            return Polarity.DISABLE

    if any(k in q_low for k in ("silence all", "mute all", "total silence", "stop making noise", "do not disturb")):
        if not any(k in q_low for k in ("turn off", "disable", "stop", "end", "deactivate")):
            return Polarity.ENABLE
        else:
            return Polarity.DISABLE

    # 6. Multi-word phrase check (higher specificity)
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

    # 7. Token-level fallback
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
            return 0.20  # Boost for matching polarity
        if entry_polarity in (Polarity.ENABLE, Polarity.DISABLE) and entry_polarity != query_polarity:
            return -0.20  # Soft penalty for opposite polarity toggle
    return 0.0


def get_entry_specificity_penalty(query: str, entry: Optional[Dict[str, Any]]) -> float:
    """Calculates a soft penalty if the candidate's validation key or description specifies
    a specialized sub-feature that the user's query did NOT request.

    100% domain-general. Differentiates primary device settings (e.g. Wi-Fi, Bluetooth) from
    auxiliary services (e.g. Wi-Fi Scanning, Bluetooth Scanning, Hotspot, Tethering, Magnification).
    """
    if not entry or not query:
        return 0.0

    entry_data = entry.get("entry") if ("entry" in entry and isinstance(entry["entry"], dict)) else entry
    val = entry_data.get("validation") or {}
    val_key = (val.get("key") or "").lower()
    desc = (entry_data.get("description") or "").lower()
    q_low = query.lower()

    SUB_FEATURE_QUALIFIERS = (
        "scanning",
        "hotspot",
        "tethering",
        "magnification",
        "strobing",
    )

    penalty = 0.0
    for qual in SUB_FEATURE_QUALIFIERS:
        has_qual = (qual in val_key) or (f" {qual} " in f" {desc} ")
        if has_qual and qual not in q_low:
            penalty -= 0.15

    return penalty
