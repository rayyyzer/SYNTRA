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

from Theme02_Engine.engine import TroubleshootingEngine

cases = [json.loads(line) for line in open('tests/theme2/robustness_dataset.jsonl', encoding='utf-8') if line.strip()]

# Test 1: Standard persistent engine (current benchmark behavior)
eng1 = TroubleshootingEngine()
matches1 = 0
for c in cases:
    resp = eng1.troubleshoot(c['query'], c['siis_response'])
    sg = resp['contexts'][0]['actions'][0]['stepGroups'][0]
    gen_uri = sg.get('actionableDeeplink', {}).get('deeplink') if sg.get('actionableDeeplink') else None
    exp_uri = c.get('expected_uri')
    if (gen_uri == exp_uri) or (exp_uri is None and (gen_uri is None or gen_uri == 'bixby://dummy_positive')):
        matches1 += 1

# Test 2: Stateless / Fresh cache per query (measuring pure retrieval capability without cache cross-talk)
eng2 = TroubleshootingEngine()
matches2 = 0
for c in cases:
    eng2.cache.exact_cache.clear()
    eng2.cache.intent_cache.clear()
    eng2.cache.known_intents.clear()
    resp = eng2.troubleshoot(c['query'], c['siis_response'])
    sg = resp['contexts'][0]['actions'][0]['stepGroups'][0]
    gen_uri = sg.get('actionableDeeplink', {}).get('deeplink') if sg.get('actionableDeeplink') else None
    exp_uri = c.get('expected_uri')
    if (gen_uri == exp_uri) or (exp_uri is None and (gen_uri is None or gen_uri == 'bixby://dummy_positive')):
        matches2 += 1

print(f"Persistent Cache URI Matches: {matches1}/164 ({100*matches1/164:.2f}%)")
print(f"Fresh Cache Pure Retrieval URI Matches: {matches2}/164 ({100*matches2/164:.2f}%)")
print(f"Difference caused by cache cross-talk: {matches2 - matches1} cases ({100*(matches2 - matches1)/164:.2f} percentage points)")
