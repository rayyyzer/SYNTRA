import json

data = json.load(open("scratch/generated/top5_ranking_analysis.json", encoding="utf-8"))
recs = data["recoverable_cases"]
print(f"Total recoverable cases: {len(recs)}\n")

for i, r in enumerate(recs):
    print(f"[{i+1}/{len(recs)}] [{r['id']}] Q: '{r['query']}'")
    print(f"  Exp: '{r['expected_action']}' (Rank {r['target_rank']}) URI: {r['expected_uri']}")
    print(f"  Top-1: '{r['top1_action']}' URI: {r['top1_uri']}")
    print(f"    Top-1 Scores: final={r['top1_score']:.4f} bm25={r['top1_bm25']:.4f} dense={r['top1_dense']:.4f} pol={r['top1_pol_bonus']:.4f}")
    print(f"    Target Scores: final={r['target_score']:.4f} bm25={r['target_bm25']:.4f} dense={r['target_dense']:.4f} pol={r['target_pol_bonus']:.4f}")
    score_gap = r['top1_score'] - r['target_score']
    print(f"    Score gap: {score_gap:.4f} | Title effect: {r['title_effect']}")
    print()
