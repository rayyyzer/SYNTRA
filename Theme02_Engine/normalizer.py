"""Normalizer & Formatting Guardrails for Theme 2.

Enforces:
- Goal regex: Follow these steps to perform this <Name> Troubleshooting. / Configuration.
- Title: 2-3 words
- Action description: 5-7 words, must start with 'It will'
- URL Sanitizer: Zero URL leaks (Gate G5)
"""

from __future__ import annotations
import re
from typing import List

_URL_PATTERN = re.compile(r"(https?://\S+|www\.\S+|\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b|\.com\S*|\.html\S*|\[.*?\]\(.*?\))", re.I)


def sanitize_text(text: str) -> str:
    """Strip any URLs, markdown links, or .com mentions to guarantee Gate G5 pass."""
    cleaned = _URL_PATTERN.sub("", text)
    cleaned = re.sub(r"https?://[^\s]+", "", cleaned)
    cleaned = re.sub(r"www\.[^\s]+", "", cleaned)
    cleaned = re.sub(r"\.com\b", "", cleaned)
    cleaned = re.sub(r"\.html\b", "", cleaned)
    return " ".join(cleaned.split())


def format_goal(name: str, is_config: bool = False) -> str:
    """Format goal to strictly match regex: Follow these steps to perform this <Name> Troubleshooting."""
    clean_name = sanitize_text(name).strip().title()
    if not clean_name:
        clean_name = "Device Issue"
    suffix = "Configuration" if is_config else "Troubleshooting"
    return f"Follow these steps to perform this {clean_name} {suffix}."


def format_title(text: str) -> str:
    """Format title to strictly 2–3 words."""
    clean = sanitize_text(text)
    words = [w for w in re.findall(r"[A-Za-z0-9]+", clean) if len(w) > 1]
    if len(words) < 2:
        return "Device Screen Issue"
    elif len(words) == 2:
        return f"{words[0].title()} {words[1].title()}"
    else:
        return f"{words[0].title()} {words[1].title()} {words[2].title()}"


def format_action_description(action_name: str, context_hint: str = "") -> str:
    """Format action description to strictly 5–7 words starting with 'It will'."""
    clean_hint = sanitize_text(context_hint or action_name).lower()
    words = re.findall(r"[a-z0-9]+", clean_hint)
    
    # Base prefix is 2 words: 'It will'
    # Needs 3 to 5 following words
    filler_pool = ["help", "resolve", "your", "device", "settings", "issue", "smoothly"]
    
    chosen = []
    for w in words:
        if w not in ("it", "will") and len(w) > 2 and w not in chosen:
            chosen.append(w)
        if len(chosen) >= 4:
            break
            
    while len(chosen) < 3:
        for f in filler_pool:
            if f not in chosen:
                chosen.append(f)
            if len(chosen) >= 3:
                break
                
    chosen = chosen[:4] # 2 + 4 = 6 words total (strictly within 5-7 words)
    return f"It will {' '.join(chosen)}"
