import sys, os
sys.path.insert(0, os.path.abspath('Theme02_Engine'))
import json
from retrieval.hybrid_retriever import HybridRetriever

retriever = HybridRetriever()
cases = [json.loads(line) for line in open('tests/theme2/robustness_dataset.jsonl', encoding='utf-8') if line.strip()]

helped = []
hurt = []

for c in cases:
    exp = c.get('expected_uri')
    if not exp:
        continue
    q = c['query']
    siis = c.get('siis_response', {})
    title = siis.get('title', '')
    
    cand_before = retriever.retrieve(q, top_k=1)
    cand_after = retriever.retrieve(f"{q} {title}".strip(), top_k=1)
    
    ub = cand_before[0]['deeplink'] if cand_before else None
    ua = cand_after[0]['deeplink'] if cand_after else None
    
    if ub != exp and ua == exp:
        helped.append((c['id'], q, title, exp, ub, ua))
    elif ub == exp and ua != exp:
        hurt.append((c['id'], q, title, exp, ub, ua))

print(f"Cases Helped ({len(helped)}):")
for h in helped:
    print(f"  [+] {h[0]}: Q='{h[1][:40]}' Title='{h[2]}'")
print(f"\nCases Hurt ({len(hurt)}):")
for h in hurt:
    print(f"  [-] {h[0]}: Q='{h[1][:40]}' Title='{h[2]}'")
