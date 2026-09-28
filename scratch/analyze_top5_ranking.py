import sys, os
sys.path.insert(0, os.path.abspath('.'))
sys.path.insert(0, os.path.abspath('Theme02_Engine'))
import json
from collections import defaultdict
from retrieval.hybrid_retriever import HybridRetriever

retriever = HybridRetriever()
cases = [json.loads(line) for line in open('tests/theme2/robustness_dataset.jsonl', encoding='utf-8') if line.strip()]

top1_matches = 0
top5_matches = 0
recoverable_cases = []
rank_counts = defaultdict(int)

# To check if SIIS title changed ranking
title_effect_counts = {
    "promoted_target": 0,
    "demoted_target": 0,
    "no_change": 0
}

for c in cases:
    cid = c['id']
    q = c['query']
    siis = c.get('siis_response', {})
    title = siis.get('title', '')
    exp_uri = c.get('expected_uri')
    exp_act = c.get('expected_action')
    exp_pol = c.get('expected_polarity')
    
    # Retrieve top 5 for query alone
    cands_q = retriever.retrieve(q, top_k=5)
    
    # Retrieve top 5 for query + title
    cands_qt = retriever.retrieve(f"{q} {title}".strip() if title else q, top_k=5)
    
    uris_q = [cand['deeplink'] for cand in cands_q]
    uris_qt = [cand['deeplink'] for cand in cands_qt]
    
    # Handle hardware cases where exp_uri is None
    if exp_uri is None:
        # Hardware cases are handled by safety router
        top1_matches += 1
        top5_matches += 1
        rank_counts[1] += 1
        continue
    
    target_rank_q = None
    if exp_uri in uris_q:
        target_rank_q = uris_q.index(exp_uri) + 1
    
    target_rank_qt = None
    if exp_uri in uris_qt:
        target_rank_qt = uris_qt.index(exp_uri) + 1
        
    if target_rank_q == 1:
        top1_matches += 1
        top5_matches += 1
        rank_counts[1] += 1
    elif target_rank_q is not None:
        top5_matches += 1
        rank_counts[target_rank_q] += 1
        
        # Determine title effect
        if target_rank_qt is not None and (target_rank_q is None or target_rank_qt < target_rank_q):
            title_effect = "promoted"
            title_effect_counts["promoted_target"] += 1
        elif target_rank_qt is None or (target_rank_q is not None and target_rank_qt > target_rank_q):
            title_effect = "demoted"
            title_effect_counts["demoted_target"] += 1
        else:
            title_effect = "neutral"
            title_effect_counts["no_change"] += 1
            
        top1_cand = cands_q[0]
        target_cand = cands_q[target_rank_q - 1]
        
        recoverable_cases.append({
            "id": cid,
            "query": q,
            "title": title,
            "expected_uri": exp_uri,
            "expected_action": exp_act,
            "expected_polarity": exp_pol,
            "target_rank": target_rank_q,
            "target_rank_with_title": target_rank_qt,
            "top1_uri": top1_cand['deeplink'],
            "top1_action": top1_cand.get('message', ''),
            "top1_score": top1_cand.get('score', 0),
            "top1_bm25": top1_cand.get('bm25_score', 0),
            "top1_dense": top1_cand.get('dense_score', 0),
            "top1_pol_bonus": top1_cand.get('polarity_bonus', 0),
            "target_score": target_cand.get('score', 0),
            "target_bm25": target_cand.get('bm25_score', 0),
            "target_dense": target_cand.get('dense_score', 0),
            "target_pol_bonus": target_cand.get('polarity_bonus', 0),
            "title_effect": title_effect
        })
    else:
        rank_counts[">5 or None"] += 1

print("=" * 60)
print("PHASE 6C — STEP 2: TOP-5 RANKING ANALYSIS")
print("=" * 60)
print(f"Total Cases: {len(cases)}")
print(f"Top-1 Matches: {top1_matches} / {len(cases)} ({top1_matches/len(cases)*100:.2f}%)")
print(f"Top-5 Recall:  {top5_matches} / {len(cases)} ({top5_matches/len(cases)*100:.2f}%)")
recoverable = len(recoverable_cases)
print(f"Recoverable in Top-5 (Ranks 2-5): {recoverable} cases ({recoverable/len(cases)*100:.2f}%)")
print("\nBreakdown of Target Ranks:")
for r in [1, 2, 3, 4, 5, ">5 or None"]:
    cnt = rank_counts[r]
    pct = cnt / len(cases) * 100
    print(f"  Rank {r}: {cnt:3d} ({pct:5.2f}%)")

print("\nTitle Effect on Recoverable Candidates:")
print(f"  Promoted Target: {title_effect_counts['promoted_target']}")
print(f"  Demoted Target:  {title_effect_counts['demoted_target']}")
print(f"  No Change:       {title_effect_counts['no_change']}")

# Save detailed analysis to JSON
out_path = "scratch/generated/top5_ranking_analysis.json"
os.makedirs("scratch/generated", exist_ok=True)
with open(out_path, "w", encoding="utf-8") as f:
    json.dump({
        "total_cases": len(cases),
        "top1_matches": top1_matches,
        "top5_matches": top5_matches,
        "recoverable_count": recoverable,
        "rank_distribution": dict(rank_counts),
        "title_effects": title_effect_counts,
        "recoverable_cases": recoverable_cases
    }, f, indent=2)

print(f"\nWrote full recoverable analysis to {out_path}")
