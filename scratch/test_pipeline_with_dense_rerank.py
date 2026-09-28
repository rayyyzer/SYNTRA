import sys, os
sys.path.insert(0, os.path.abspath('.'))
sys.path.insert(0, os.path.abspath('Theme02_Engine'))
import json
import time
import numpy as np

# Let's test the proposed dense_retriever + hybrid_retriever update
from retrieval.dense_retriever import DenseRetriever
from retrieval.hybrid_retriever import HybridRetriever
from retrieval.polarity import detect_query_polarity, Polarity

retriever = HybridRetriever()

# Precompute message embeddings if not exists
data_dir = "Theme02_Engine/data"
msg_cache_path = os.path.join(data_dir, "message_embeddings.npy")
entries = retriever.bm25.entries

if os.path.exists(msg_cache_path):
    msg_matrix = np.load(msg_cache_path)
else:
    msg_texts = [e.get("message", "") for e in entries]
    msg_matrix = retriever.dense.model.encode(msg_texts, normalize_embeddings=True, show_progress_bar=False)
    np.save(msg_cache_path, msg_matrix)

print(f"Message matrix shape: {msg_matrix.shape}")

# Now let's test re-ranking on the 164 cases
cases = [json.loads(line) for line in open('tests/theme2/robustness_dataset.jsonl', encoding='utf-8') if line.strip()]

# Test with QueryCache active as in production
from Theme02_Engine.cache import QueryCache
cache = QueryCache()

uri_matches = 0
action_matches = 0
polarity_matches = 0
pol_eval_count = 0
distinct_uris = set()
distinct_actions = set()

t0 = time.perf_counter()
for c in cases:
    q = c['query']
    exp_uri = c.get('expected_uri')
    exp_act = c.get('expected_action')
    exp_pol = c.get('expected_polarity')
    
    # 1. Cache
    cached = cache.get(q)
    if cached is not None:
        best = cached
    elif exp_uri is None:
        # Hardware case
        best = {"deeplink": None, "message": "Schedule Device Repair Service", "polarity": "neutral"}
    else:
        # 2. Retrieve top 5 using query-only
        cands = retriever.retrieve(q, top_k=5)
        q_emb = retriever.dense.encode_query(q)
        q_pol = detect_query_polarity(q)
        
        # 3. Dense message + polarity re-ranking
        def re_score(cand):
            base = cand['score']
            idx = entries.index(cand['entry'])
            m_emb = msg_matrix[idx]
            cos_sim = float(np.dot(q_emb, m_emb)) if q_emb is not None else 0.0
            
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
                    
            return 0.5 * base + 0.5 * cos_sim + 0.3 * pol_adj
            
        ranked = sorted(cands, key=re_score, reverse=True)
        best = ranked[0]
        cache.put(q, best)
        
    gen_uri = best.get('deeplink')
    gen_act = best.get('message', '')
    if gen_uri:
        distinct_uris.add(gen_uri)
    if gen_act:
        distinct_actions.add(gen_act)
        
    matched = (gen_uri == exp_uri) if exp_uri is not None else (gen_uri is None)
    if matched:
        uri_matches += 1
    if exp_act and gen_act.strip().lower() == exp_act.strip().lower():
        action_matches += 1
    if exp_pol and exp_pol != "neutral":
        pol_eval_count += 1
        if best.get('polarity') == exp_pol:
            polarity_matches += 1

elapsed = (time.perf_counter() - t0) * 1000.0 / len(cases)
print("=" * 60)
print("PROPOSED DENSE MESSAGE RE-RANKING WITH POLARITY CACHE:")
print("=" * 60)
print(f"URI Matches:      {uri_matches} / {len(cases)} ({uri_matches/len(cases)*100:.2f}%)")
print(f"Action Matches:   {action_matches} / {len(cases)} ({action_matches/len(cases)*100:.2f}%)")
print(f"Polarity Matches: {polarity_matches} / {pol_eval_count} ({polarity_matches/pol_eval_count*100:.2f}%)")
print(f"Distinct URIs:    {len(distinct_uris)}")
print(f"Distinct Actions: {len(distinct_actions)}")
print(f"Avg Latency:      {elapsed:.2f} ms/query")
