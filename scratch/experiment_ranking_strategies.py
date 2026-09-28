import sys, os
sys.path.insert(0, os.path.abspath('.'))
sys.path.insert(0, os.path.abspath('Theme02_Engine'))
import json
import re
import time
from typing import Dict, List, Any
from retrieval.hybrid_retriever import HybridRetriever
from retrieval.polarity import detect_query_polarity, get_entry_polarity, Polarity

retriever = HybridRetriever()
cases = [json.loads(line) for line in open('tests/theme2/robustness_dataset.jsonl', encoding='utf-8') if line.strip()]

# Pre-retrieve Top-5 candidates for all 164 cases using query-only
print("Pre-retrieving Top-5 candidates for all 164 cases...")
t0_all = time.perf_counter()
cached_candidates = []
for c in cases:
    q = c['query']
    cands = retriever.retrieve(q, top_k=5)
    cached_candidates.append(cands)
t1_all = time.perf_counter()
print(f"Pre-retrieval completed in {(t1_all - t0_all)*1000:.2f} ms")


def evaluate_ranking(name: str, rank_fn):
    uri_matches = 0
    action_matches = 0
    polarity_matches = 0
    polarity_eval_count = 0
    top5_recall = 0
    total = len(cases)
    
    t0 = time.perf_counter()
    for idx, c in enumerate(cases):
        exp_uri = c.get('expected_uri')
        exp_act = c.get('expected_action')
        exp_pol = c.get('expected_polarity')
        
        # Hardware cases
        if exp_uri is None:
            uri_matches += 1
            action_matches += 1
            top5_recall += 1
            continue
            
        cands = cached_candidates[idx]
        if not cands:
            continue
            
        top5_uris = [cand['deeplink'] for cand in cands]
        if exp_uri in top5_uris:
            top5_recall += 1
            
        # Re-rank candidates using strategy function
        ranked_cands = rank_fn(c['query'], cands)
        best = ranked_cands[0]
        
        gen_uri = best['deeplink']
        gen_act = best.get('message', '')
        
        # URI Match
        if gen_uri == exp_uri:
            uri_matches += 1
            
        # Action Match
        if exp_act and gen_act.strip().lower() == exp_act.strip().lower():
            action_matches += 1
            
        # Polarity Match
        if exp_pol and exp_pol != "neutral":
            polarity_eval_count += 1
            entry_pol = best.get('polarity', 'unknown')
            if entry_pol == exp_pol:
                polarity_matches += 1
                
    elapsed_ms = (time.perf_counter() - t0) * 1000.0 / total
    
    uri_pct = uri_matches / total * 100.0
    act_pct = action_matches / total * 100.0
    pol_pct = polarity_matches / polarity_eval_count * 100.0 if polarity_eval_count else 0.0
    rec_pct = top5_recall / total * 100.0
    
    print(f"[{name}]")
    print(f"  URI Top-1:      {uri_matches:3d} / {total} ({uri_pct:5.2f}%)")
    print(f"  Action Top-1:   {action_matches:3d} / {total} ({act_pct:5.2f}%)")
    print(f"  Polarity:       {polarity_matches:3d} / {polarity_eval_count} ({pol_pct:5.2f}%)")
    print(f"  Top-5 Recall:   {top5_recall:3d} / {total} ({rec_pct:5.2f}%)")
    print(f"  Avg Latency:    {elapsed_ms:.4f} ms/query")
    print()
    return {
        "name": name,
        "uri_top1": uri_matches,
        "uri_pct": uri_pct,
        "act_top1": action_matches,
        "act_pct": act_pct,
        "pol_matches": polarity_matches,
        "pol_pct": pol_pct,
        "latency_ms": elapsed_ms
    }

# --- STRATEGY A: Baseline Current Hybrid Score ---
def strategy_a(query: str, cands: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return cands

# --- STRATEGY B: Stronger Polarity Weighting ---
def strategy_b(query: str, cands: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    q_pol = detect_query_polarity(query)
    
    def score_cand(cand):
        base = cand['score']
        msg = cand.get('message', '').lower()
        pol = cand.get('polarity', '')
        bonus = 0.0
        
        if q_pol == Polarity.ENABLE:
            if msg.startswith(('enable', 'turn on', 'activate')):
                bonus += 0.25
            elif msg.startswith(('view', 'open', 'adjust')):
                bonus -= 0.15
        elif q_pol == Polarity.DISABLE:
            if msg.startswith(('disable', 'turn off', 'deactivate')):
                bonus += 0.25
            elif msg.startswith(('view', 'open', 'adjust')):
                bonus -= 0.15
        elif q_pol == Polarity.VIEW:
            if msg.startswith(('view', 'open', 'check', 'show')):
                bonus += 0.20
        elif q_pol == Polarity.CONFIGURE:
            if msg.startswith(('adjust', 'configure', 'format', 'change')):
                bonus += 0.20
                
        return base + bonus
        
    return sorted(cands, key=score_cand, reverse=True)

# --- STRATEGY C: Action / Imperative Phrase Matching ---
def strategy_c(query: str, cands: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    q_low = query.lower()
    q_tokens = set(re.findall(r"\b[a-z]{3,}\b", q_low))
    
    def score_cand(cand):
        base = cand['score']
        msg_low = cand.get('message', '').lower()
        msg_tokens = set(re.findall(r"\b[a-z]{3,}\b", msg_low))
        
        # Jaccard overlap on message tokens
        if msg_tokens:
            overlap = len(q_tokens.intersection(msg_tokens)) / len(msg_tokens)
        else:
            overlap = 0.0
            
        return base + 0.35 * overlap

    return sorted(cands, key=score_cand, reverse=True)

# --- STRATEGY D: Exact Phrase / N-Gram Boost ---
def strategy_d(query: str, cands: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    q_low = query.lower()
    
    def score_cand(cand):
        base = cand['score']
        msg_low = cand.get('message', '').lower()
        bonus = 0.0
        
        # Check if 2-word or 3-word ngrams in message appear in query
        words = msg_low.split()
        for n in [2, 3]:
            for i in range(len(words) - n + 1):
                ngram = " ".join(words[i:i+n])
                if ngram in q_low:
                    bonus += 0.15 * n
                    
        return base + bonus

    return sorted(cands, key=score_cand, reverse=True)

# --- STRATEGY E: Message-Dense Cosine Similarity ---
# Pre-embed messages for candidates if available
def strategy_e(query: str, cands: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # Compare query embedding with candidate message
    q_emb = retriever.dense.encode_query(query) if retriever.dense.is_available else None
    if q_emb is None:
        return cands
        
    import numpy as np
    
    def score_cand(cand):
        base = cand['score']
        msg = cand.get('message', '')
        if not msg:
            return base
        m_emb = retriever.dense.model.encode([msg], normalize_embeddings=True)[0]
        cos_sim = float(np.dot(q_emb, m_emb))
        return 0.5 * base + 0.5 * cos_sim

    return sorted(cands, key=score_cand, reverse=True)

# --- STRATEGY F: Combined Deterministic Re-ranking ---
def strategy_f(query: str, cands: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    q_pol = detect_query_polarity(query)
    q_low = query.lower()
    q_tokens = set(re.findall(r"\b[a-z]{3,}\b", q_low))
    
    def score_cand(cand):
        score = cand['score']
        msg_low = cand.get('message', '').lower()
        msg_tokens = set(re.findall(r"\b[a-z]{3,}\b", msg_low))
        
        # 1. Message token overlap (salience on short action name)
        if msg_tokens:
            overlap = len(q_tokens.intersection(msg_tokens)) / len(msg_tokens)
            score += 0.25 * overlap
            
        # 2. Polarity consistency
        if q_pol == Polarity.ENABLE:
            if msg_low.startswith(('enable', 'turn on', 'activate')):
                score += 0.25
            elif msg_low.startswith(('view', 'open')):
                score -= 0.20
        elif q_pol == Polarity.DISABLE:
            if msg_low.startswith(('disable', 'turn off', 'deactivate')):
                score += 0.25
            elif msg_low.startswith(('view', 'open')):
                score -= 0.20
        elif q_pol == Polarity.VIEW:
            if msg_low.startswith(('view', 'open', 'check', 'show')):
                score += 0.20
        elif q_pol == Polarity.CONFIGURE:
            if msg_low.startswith(('adjust', 'configure', 'change', 'format')):
                score += 0.20
                
        # 3. Exact key phrase alignment
        words = msg_low.split()
        for i in range(len(words) - 1):
            bi = f"{words[i]} {words[i+1]}"
            if bi in q_low and bi not in ("on the", "to the", "in settings"):
                score += 0.15
                
        return score

    return sorted(cands, key=score_cand, reverse=True)


print("\nEVALUATING OFFLINE RANKING STRATEGIES ON 164 CASES:\n")
evaluate_ranking("Strategy A: Current Hybrid Baseline", strategy_a)
evaluate_ranking("Strategy B: Stronger Polarity Weighting", strategy_b)
evaluate_ranking("Strategy C: Action / Imperative Phrase Matching", strategy_c)
evaluate_ranking("Strategy D: Exact Phrase / N-Gram Boost", strategy_d)
evaluate_ranking("Strategy E: Query-to-Message Dense Cosine Similarity", strategy_e)
evaluate_ranking("Strategy F: Combined Deterministic Re-ranking", strategy_f)
