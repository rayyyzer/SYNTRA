"""Safety & Hardware Router for Theme 2.

Intercepts requests involving:
1. Physical liquid/hardware damage (ocean immersion, shattered glass, bent motherboard, smoke)
2. Unsafe/unsupported operations (unofficial APKs, physical heat gun disassembly)
3. Direct hardware repair requirements where software toggles are dangerous or ineffective.

Guarantees:
- Zero hallucinated auto-fix settings for broken hardware (Gate G4 & safety conformance)
- Returns official Samsung repair guidance with category: manual and actionableDeeplink: None
"""

from __future__ import annotations
import re
from typing import Any, Dict, List, Optional, Tuple

# Patterns identifying physical damage, hardware failure, or dangerous operations
UNSUPPORTED_PATTERNS = [
    re.compile(r"\b(ocean|salt\s+water|submerged|water\s+got\s+inside|charging\s+port\s+.*water|dropped\s+(?:my\s+)?phone\s+in\s+water)\b", re.I),
    re.compile(r"\b(shattered\s+(into\s+)?sharp\s+pieces|shattered\s+on\s+concrete)\b", re.I),
    re.compile(r"\b(motherboard\s+is\s+bent|smoke\s+came\s+out|battery\s+swollen|swelling\s+battery)\b", re.I),
    re.compile(r"\b(unofficial\s+third[- ]party\s+apk|unverified\s+website)\b", re.I),
    re.compile(r"\b(replace\s+(the\s+)?physical\s+oled|heat\s+gun|panel\s+myself)\b", re.I),
]


def is_unsupported_hardware(query: str, context: str = "") -> bool:
    """Checks whether the query describes unfixable physical damage or unsafe instructions."""
    combined = f"{query} {context}".strip()
    for pat in UNSUPPORTED_PATTERNS:
        if pat.search(combined):
            return True
    return False


def get_hardware_repair_action() -> Dict[str, Any]:
    """Generates the official Samsung repair action with category: manual and null deeplink."""
    return {
        "actionName": "Schedule Device Repair Service",
        "description": "It will schedule authorized device repair",
        "category": "manual",
        "stepGroups": [
            {
                "steps": [
                    "Back up critical device data immediately if the device is still responsive.",
                    "Power down the device and do not connect it to any electrical charger.",
                    "Visit an authorized Samsung Service Center or contact customer support for hardware repair."
                ],
                "actionableDeeplink": None,
                "validationDeeplink": None
            }
        ]
    }
