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

_SCRIPT_BLOCK_PATTERN = re.compile(r"<(script|style|iframe)\b[^>]*>.*?</\1>", re.I | re.DOTALL)
_HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
_JS_SCHEME_PATTERN = re.compile(r"\bjavascript:\S*", re.I)
_EVENT_HANDLER_PATTERN = re.compile(r"\bon\w+\s*=\s*(?:\"[^\"]*\"|'[^']*'|\S+)", re.I)
_URL_PATTERN = re.compile(r"(https?://\S+|www\.\S+|\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b|\.com\S*|\.html\S*|\[.*?\]\(.*?\))", re.I)
_BARE_DOMAIN_PATTERN = re.compile(r"\b(?:[a-zA-Z0-9-]+\.)+(?:com|org|net|io|edu|gov|xyz|app|ru|cn|co)(?:/[^\s]*)?\b", re.I)


def sanitize_text(text: str) -> str:
    """Strip URLs, bare domains, markdown links, HTML tags, script blocks, and javascript URIs."""
    if not isinstance(text, str):
        text = str(text) if text is not None else ""
    # 1. Strip script, style, and iframe blocks with contents
    cleaned = _SCRIPT_BLOCK_PATTERN.sub(" ", text)
    # 2. Strip remaining HTML tags
    cleaned = _HTML_TAG_PATTERN.sub(" ", cleaned)
    # 3. Strip javascript: URIs
    cleaned = _JS_SCHEME_PATTERN.sub("", cleaned)
    # 4. Strip inline event handlers
    cleaned = _EVENT_HANDLER_PATTERN.sub("", cleaned)
    # 5. Strip URLs, bare domains, and markdown links
    cleaned = _URL_PATTERN.sub("", cleaned)
    cleaned = _BARE_DOMAIN_PATTERN.sub("", cleaned)
    # 6. Clean protocol and domain residues
    cleaned = re.sub(r"https?://[^\s]*", "", cleaned)
    cleaned = re.sub(r"www\.[^\s]*", "", cleaned)
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
