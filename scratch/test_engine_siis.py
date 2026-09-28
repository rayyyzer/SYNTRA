import sys, os
sys.path.insert(0, os.path.abspath('.'))
sys.path.insert(0, os.path.abspath('Theme02_Engine'))
import json
from Theme02_Engine.engine import TroubleshootingEngine

cases = [json.loads(line) for line in open('tests/theme2/robustness_dataset.jsonl', encoding='utf-8') if line.strip()]

# Test 1: Baseline engine (query only)
engine1 = TroubleshootingEngine()
matches1 = 0
for c in cases:
    exp = c.get('expected_uri')
    resp = engine1.troubleshoot(c['query'], c.get('siis_response', {}))
    sg0 = resp['contexts'][0]['actions'][0]['stepGroups'][0]
    gen_uri = sg0.get('actionableDeeplink', {}).get('deeplink') if sg0.get('actionableDeeplink') else None
    matched = (gen_uri == exp) if exp is not None else (gen_uri is None or gen_uri == "bixby://dummy_positive")
    if matched:
        matches1 += 1

# Test 2: Engine with retrieval_query = f"{query} {siis_title}".strip()
class SiiSEngine(TroubleshootingEngine):
    def troubleshoot(self, query, siis_response):
        # We temporarily patch self.retriever.retrieve to inject siis_title
        siis_title = (siis_response or {}).get('title', '')
        orig_retrieve = self.retriever.retrieve
        def patched_retrieve(q, top_k=5):
            rq = f"{q} {siis_title}".strip() if siis_title else q
            return orig_retrieve(rq, top_k=top_k)
        self.retriever.retrieve = patched_retrieve
        try:
            return super().troubleshoot(query, siis_response)
        finally:
            self.retriever.retrieve = orig_retrieve

engine2 = SiiSEngine()
matches2 = 0
for c in cases:
    exp = c.get('expected_uri')
    resp = engine2.troubleshoot(c['query'], c.get('siis_response', {}))
    sg0 = resp['contexts'][0]['actions'][0]['stepGroups'][0]
    gen_uri = sg0.get('actionableDeeplink', {}).get('deeplink') if sg0.get('actionableDeeplink') else None
    matched = (gen_uri == exp) if exp is not None else (gen_uri is None or gen_uri == "bixby://dummy_positive")
    if matched:
        matches2 += 1

print(f"Test 1 (Query Only):        {matches1}/164 ({matches1/164*100:.2f}%)")
print(f"Test 2 (Query + siis_title): {matches2}/164 ({matches2/164*100:.2f}%)")
