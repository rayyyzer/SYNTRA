import json
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CANDIDATE_KIT_DIRS = [
    os.path.join(PROJECT_ROOT, "data", "student_kit"),
    os.path.join(PROJECT_ROOT, "participant-kit-all-themes", "participant-kit", "Theme02_Input_Kit", "student_kit")
]
STUDENT_KIT_DIR = next((d for d in CANDIDATE_KIT_DIRS if os.path.exists(d)), CANDIDATE_KIT_DIRS[0])

sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "Theme02_Engine"))
sys.path.insert(0, STUDENT_KIT_DIR)

from Theme02_Engine.cache import QueryCache
from Theme02_Engine.engine import TroubleshootingEngine

cases = [json.loads(line) for line in open('tests/theme2/robustness_dataset.jsonl', encoding='utf-8') if line.strip()]

engine = TroubleshootingEngine()
false_cache_hits = []

for idx, c in enumerate(cases):
    q = c['query']
    siis = c['siis_response']
    
    # Check if cache hits BEFORE engine runs
    cached = engine.cache.get(q)
    if cached is not None:
        gen_act = cached['contexts'][0]['actions'][0]['actionName']
        exp_act = c.get('expected_action', '')
        exp_uri = c.get('expected_uri')
        sg_0 = cached['contexts'][0]['actions'][0]['stepGroups'][0]
        gen_uri = sg_0.get('actionableDeeplink', {}).get('deeplink') if sg_0.get('actionableDeeplink') else None
        
        if exp_uri and gen_uri != exp_uri:
            false_cache_hits.append({
                "id": c['id'],
                "query": q,
                "expected_action": exp_act,
                "cached_action": gen_act,
                "expected_uri": exp_uri,
                "cached_uri": gen_uri
            })
            
    # Now run troubleshoot
    engine.troubleshoot(q, siis)

print(f"Total False Cache Hits in sequential benchmark: {len(false_cache_hits)}")
for f in false_cache_hits:
    print(f"[{f['id']}] Q: '{f['query']}'")
    print(f"   Exp: '{f['expected_action']}' ({f['expected_uri']})")
    print(f"   Cache returned: '{f['cached_action']}' ({f['cached_uri']})")
    print()
