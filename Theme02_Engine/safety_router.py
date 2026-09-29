"""Safety & Hardware Router for Theme 2.

Intercepts requests involving:
1. Physical structural damage (crushed, shattered, broken, bent, snapped, or split hardware)
2. Serious liquid ingress (submerged, soaked, or spilled inside ports, chassis, or device)
3. Thermal or electrical hazards (smoke, sparks, fire, burning smells, or battery swelling/leaking)
4. Physical DIY repair or disassembly (prying tools, opening handset to replace internal components)
5. Clearly unsafe or unverified software modifications outside official platform bounds.

Guarantees:
- Zero hallucinated auto-fix settings for broken hardware (Gate G4 & safety conformance)
- Returns official Samsung repair guidance with category: manual and actionableDeeplink: None
"""

from __future__ import annotations
import re
from typing import Any, Dict, List, Optional, Tuple

# Category A: Physical Structural Damage (severe destruction of hardware parts)
STRUCTURAL_DAMAGE = re.compile(
    r"\b(?:shatter(?:ed|ing)?|crush(?:ed|ing)?|crack(?:ed|ing)?|bent|warped|snapp(?:ed|ing)(?:\s+off)?|split(?:\s+in\s+half)?|smashed|punctured)\b.*?\b(?:screen|display|glass|panel|frame|chassis|body|housing|motherboard|board|port|usb|connector|phone|smartphone|device|handset)\b"
    r"|\b(?:screen|display|glass|panel|frame|chassis|body|housing|motherboard|board|port|usb|connector|phone|smartphone|device|handset)\b.*?\b(?:shatter(?:ed|ing)?|crush(?:ed|ing)?|crack(?:ed|ing)?|bent|warped|snapp(?:ed|ing)(?:\s+off)?|split(?:\s+in\s+half)?|smashed|punctured)\b",
    re.I
)

# Category B: Liquid Ingress / Serious Liquid Exposure
LIQUID_INGRESS = re.compile(
    r"\b(?:submerged|immersed|soaked)\b"
    r"|\b(?:dropped|fell|spilled)\b.*?\b(?:in|into|inside)\b.*?\b(?:water|ocean|sea|pool|toilet|sink|liquid|coffee|tea|soda|beverage)\b"
    r"|\b(?:water|liquid|coffee|tea|soda|ocean|salt\s+water)\b.*?\b(?:got\s+inside|spilled\s+inside|seeped\s+inside|inside\s+(?:the\s+)?(?:phone|smartphone|device|handset|port|charging\s+port|speaker))\b"
    r"|\bliquid\s+damage(?:\s+detected)?\b",
    re.I
)

# Category C: Thermal / Electrical Hazards
THERMAL_ELECTRICAL = re.compile(
    r"\b(?:smoke|smoking|smolder(?:ing)?|sparks?|sparking|fire|exploded?|exploding)\b"
    r"|\b(?:burning|smell\s+(?:of\s+)?burning)\b.*?\b(?:electronics?|phone|smartphone|device|battery|charger|plastic)\b"
    r"|\b(?:battery|cell|back\s+panel)\b.*?\b(?:swollen|swelling|bulg(?:ed|ing)|expand(?:ed|ing)|leak(?:ed|ing))\b"
    r"|\b(?:swollen|swelling|bulg(?:ed|ing)|expand(?:ed|ing)|leak(?:ed|ing))\b.*?\b(?:battery|cell)\b",
    re.I
)

# Category D: Physical Repair / DIY Disassembly Procedures
PHYSICAL_REPAIR = re.compile(
    r"\b(?:heat\s+gun|soldering\s+iron|pry\s+tool)\b"
    r"|\b(?:open|opening|disassemble|disassembling|take\s+apart|taking\s+apart)\b.*?\b(?:phone|smartphone|device|handset|casing|chassis)\b.*?\b(?:replace|repair|fix)\b"
    r"|\b(?:replace|replacing|repair|repairing)\b.*?\bphysical\s+(?:oled|screen|display|battery|camera|motherboard|component)\b"
    r"|\b(?:open|opening)\b.*?\b(?:phone|smartphone|device|handset)\b.*?\b(?:replace|repair|install)\b.*?\b(?:internal\s+component|part|hardware)\b",
    re.I
)

# Category E: Clearly Unsafe / Malicious Software Modifications
UNSAFE_SOFTWARE = re.compile(
    r"\b(?:unofficial|unverified|malicious|pirated|cracked)\b.*?\b(?:third[- ]party\s+)?(?:apk|package|firmware|rom)\b"
    r"|\b(?:download|install|sideload)\b.*?\b(?:unofficial|unverified|untrusted|sketchy|shady)\b.*?\b(?:apk|app|source|website)\b",
    re.I
)

UNSUPPORTED_CATEGORIES = [
    STRUCTURAL_DAMAGE,
    LIQUID_INGRESS,
    THERMAL_ELECTRICAL,
    PHYSICAL_REPAIR,
    UNSAFE_SOFTWARE,
]


def is_unsupported_hardware(query: str, context: str = "") -> bool:
    """Checks whether the query or context describes physical hardware failure, liquid damage, thermal danger, or unsafe repair."""
    # 1. Primary check: User query indicates physical damage, liquid ingress, thermal hazard, or disassembly
    if any(p.search(query) for p in UNSUPPORTED_CATEGORIES):
        return True
    # 2. Secondary check: SIIS context explicitly diagnoses unfixable hardware / liquid damage
    if context and re.search(r"\b(?:liquid\s+damage\s+detected|severe\s+hardware\s+failure|physical\s+display\s+damage:\s+software\s+settings\s+cannot\s+repair)\b", context, re.I):
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
