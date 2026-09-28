import sys, os
sys.path.insert(0, os.path.abspath('.'))
sys.path.insert(0, os.path.abspath('Theme02_Engine'))
import json
import re
import time
from typing import Dict, List, Any
from retrieval.hybrid_retriever import HybridRetriever
from retrieval.polarity import detect_query_polarity, Polarity

retriever = HybridRetriever()
cases = [json.loads(line) for line in open('tests/theme2/robustness_dataset.jsonl', encoding='utf-8') if line.strip()]

DOMAIN_KEYWORDS = {
    "wifi", "wi-fi", "bluetooth", "battery", "screen", "display", "sound", "volume",
    "airplane", "flight", "dark", "brightness", "timeout", "charging", "touch", "call",
    "notification", "backup", "cloud", "keyboard", "vibration", "aod", "always on",
    "power", "saver", "saving", "avatar", "roaming", "clock", "date", "time", "sync"
}

def has_domain_keyword(q: str) -> bool:
    tokens = set(re.findall(r"\b[a-z]{3,}\b", q.lower()))
    return bool(tokens.intersection(DOMAIN_KEYWORDS))

def run_siis_strategy(name: str, get_retrieval_query_fn):
    uri_matches = 0
    action_matches = 0
    polarity_matches = 0
    polarity_eval_count = 0
    total = len(cases)
    
    t0 = time.perf_counter()
    for c in cases:
        exp_uri = c.get('expected_uri')
        exp_act = c.get('expected_action')
        exp_pol = c.get('expected_polarity')
        
        if exp_uri is None:
            uri_matches += 1
            action_matches += 1
            continue
            
        rq = get_retrieval_query_fn(c['query'], c.get('siis_response', {}))
        cands = retriever.retrieve(rq, top_k=1)
        if not cands:
            continue
            
        best = cands[0]
        gen_uri = best['deeplink']
        gen_act = best.get('message', '')
        
        if gen_uri == exp_uri:
            uri_matches += 1
        if exp_act and gen_act.strip().lower() == exp_act.strip().lower():
            action_matches += 1
        if exp_pol and exp_pol != "neutral":
            polarity_eval_count += 1
            if best.get('polarity') == exp_pol:
                polarity_matches += 1
                
    elapsed = (time.perf_counter() - t0) * 1000.0 / total
    uri_pct = uri_matches / total * 100.0
    act_pct = action_matches / total * 100.0
    pol_pct = polarity_matches / polarity_eval_count * 100.0 if polarity_eval_count else 0.0
    
    print(f"[{name}] Latency: {elapsed:.2f} ms/query")
    print(f"  URI Top-1:      {uri_matches:3d} / {total} ({uri_pct:5.2f}%)")
    print(f"  Action Top-1:   {action_matches:3d} / {total} ({act_pct:5.2f}%)")
    print(f"  Polarity:       {polarity_matches:3d} / {polarity_eval_count} ({pol_pct:5.2f}%)")
    print()
    return {
        "name": name,
        "uri_top1": uri_matches,
        "uri_pct": uri_pct,
        "act_top1": action_matches,
        "act_pct": act_pct,
        "pol_pct": pol_pct
    }

print("\n--- CONDITIONAL SIIS STRATEGIES EXPERIMENT ---\n")

# 1. Query only
run_siis_strategy("1. Query Only", lambda q, siis: q)

# 2. Unconditional Query + SIIS Title
run_siis_strategy("2. Unconditional Query + Title", lambda q, siis: f"{q} {siis.get('title', '')}".strip() if siis.get('title') else q)

# 3. Query + Title for short queries (<= 4 words)
run_siis_strategy("3. Query + Title for Short Queries (<= 4 words)", lambda q, siis: f"{q} {siis.get('title', '')}".strip() if len(q.split()) <= 4 and siis.get('title') else q)

# 4. Query + Title when query lacks domain keywords
run_siis_strategy("4. Query + Title when Lacking Domain Keywords", lambda q, siis: f"{q} {siis.get('title', '')}".strip() if not has_domain_keyword(q) and siis.get('title') else q)

# 5. Two-stage retrieval: Query only first; if top-1 score < 0.35, append title
def two_stage_confidence(q: str, siis: dict) -> str:
    # We test two-stage logic
    cands = retriever.retrieve(q, top_k=1)
    title = siis.get('title', '')
    if (not cands or cands[0]['score'] < 0.35) and title:
        return f"{q} {title}".strip()
    return q

run_siis_strategy("5. Low-Confidence Fallback (top-1 < 0.35)", two_stage_confidence)
