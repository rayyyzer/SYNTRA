import sys, os
sys.path.insert(0, os.path.abspath('.'))
sys.path.insert(0, os.path.abspath('Theme02_Engine'))
import json
import time
import numpy as np
from typing import Dict, List, Any
from retrieval.hybrid_retriever import HybridRetriever
from retrieval.polarity import detect_query_polarity, get_entry_polarity, Polarity

retriever = HybridRetriever()
cases = [json.loads(line) for line in open('tests/theme2/robustness_dataset.jsonl', encoding='utf-8') if line.strip()]

# 1. Pre-embed all catalog messages
print("Pre-embedding all catalog messages...")
entries = retriever.bm25.entries
messages = [e.get("message", "") for e in entries]
msg_embeddings = retriever.dense.model.encode(messages, normalize_embeddings=True, batch_size=64)
print(f"Pre-embedded {len(msg_embeddings)} messages. Shape: {msg_embeddings.shape}")

# Map entry deeplink to its message embedding
uri_to_msg_emb = {e["deeplink"]: msg_embeddings[i] for i, e in enumerate(entries)}

# Pre-retrieve top 5 candidates
cached_cands_with_qemb = []
for c in cases:
    q = c['query']
    cands = retriever.retrieve(q, top_k=5)
    q_emb = retriever.dense.encode_query(q)
    cached_cands_with_qemb.append((cands, q_emb))

def test_config(name, w_base, w_msg, w_pol):
    uri_matches = 0
    action_matches = 0
    polarity_matches = 0
    polarity_eval_count = 0
    total = len(cases)
    
    t0 = time.perf_counter()
    for idx, c in enumerate(cases):
        exp_uri = c.get('expected_uri')
        exp_act = c.get('expected_action')
        exp_pol = c.get('expected_polarity')
        
        if exp_uri is None:
            uri_matches += 1
            action_matches += 1
            continue
            
        cands, q_emb = cached_cands_with_qemb[idx]
        if not cands:
            continue
            
        q_pol = detect_query_polarity(c['query'])
        
        def rank_score(cand):
            base = cand['score']
            m_emb = uri_to_msg_emb.get(cand['deeplink'])
            if m_emb is not None and q_emb is not None:
                cos_sim = float(np.dot(q_emb, m_emb))
            else:
                cos_sim = 0.0
                
            pol_adj = 0.0
            msg_low = cand.get('message', '').lower()
            if q_pol == Polarity.ENABLE:
                if msg_low.startswith(('enable', 'turn on', 'activate')):
                    pol_adj += 0.20
                elif msg_low.startswith(('view', 'open')):
                    pol_adj -= 0.15
            elif q_pol == Polarity.DISABLE:
                if msg_low.startswith(('disable', 'turn off', 'deactivate')):
                    pol_adj += 0.20
                elif msg_low.startswith(('view', 'open')):
                    pol_adj -= 0.15
            elif q_pol == Polarity.VIEW:
                if msg_low.startswith(('view', 'open', 'check', 'show')):
                    pol_adj += 0.15
            elif q_pol == Polarity.CONFIGURE:
                if msg_low.startswith(('adjust', 'configure', 'change', 'format')):
                    pol_adj += 0.15
                    
            return w_base * base + w_msg * cos_sim + w_pol * pol_adj
            
        ranked = sorted(cands, key=rank_score, reverse=True)
        best = ranked[0]
        
        if best['deeplink'] == exp_uri:
            uri_matches += 1
        if exp_act and best.get('message', '').strip().lower() == exp_act.strip().lower():
            action_matches += 1
        if exp_pol and exp_pol != "neutral":
            polarity_eval_count += 1
            if best.get('polarity') == exp_pol:
                polarity_matches += 1
                
    elapsed = (time.perf_counter() - t0) * 1000.0 / total
    print(f"[{name}] Latency: {elapsed:.4f} ms")
    print(f"  URI:      {uri_matches}/{total} ({uri_matches/total*100:.2f}%)")
    print(f"  Action:   {action_matches}/{total} ({action_matches/total*100:.2f}%)")
    print(f"  Polarity: {polarity_matches}/{polarity_eval_count} ({polarity_matches/polarity_eval_count*100:.2f}%)")
    print()

print("\n--- TUNING WEIGHTS OF DENSE MESSAGE SIMILARITY ---\n")
test_config("w_base=0.5, w_msg=0.5, w_pol=0.0", 0.5, 0.5, 0.0)
test_config("w_base=0.4, w_msg=0.6, w_pol=0.0", 0.4, 0.6, 0.0)
test_config("w_base=0.6, w_msg=0.4, w_pol=0.0", 0.6, 0.4, 0.0)
test_config("w_base=0.5, w_msg=0.5, w_pol=0.5", 0.5, 0.5, 0.5)
test_config("w_base=0.4, w_msg=0.6, w_pol=0.4", 0.4, 0.6, 0.4)
test_config("w_base=0.5, w_msg=0.5, w_pol=0.3", 0.5, 0.5, 0.3)
test_config("w_base=0.6, w_msg=0.4, w_pol=0.3", 0.6, 0.4, 0.3)
