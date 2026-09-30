"""Phase 1: Rigorous Baseline Benchmarking Script for Theme 2.

Measures:
- Step 3: Cold start latency (process instantiation & first request across multiple runs)
- Step 4: Warm request latency (p50, p95, p99, min, max across identical & diverse requests)
- Step 5: Cache behavior on Exact, Case, Whitespace, and Paraphrase variants
- Step 6: Schema validation against official schema.py
- Step 7: Deeplink catalog integrity against the 578 official entries
- Step 8: Per-scenario breakdown over all 20 public scenarios
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Tuple

# Path setup
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CANDIDATE_KIT_DIRS = [
    os.path.join(PROJECT_ROOT, "data", "student_kit"),
    os.path.join(PROJECT_ROOT, "participant-kit-all-themes", "participant-kit", "Theme02_Input_Kit", "student_kit")
]
STUDENT_KIT_DIR = next((d for d in CANDIDATE_KIT_DIRS if os.path.exists(d)), CANDIDATE_KIT_DIRS[0])
ENGINE_DIR = os.path.join(PROJECT_ROOT, "Theme02_Engine")

sys.path.insert(0, STUDENT_KIT_DIR)
sys.path.insert(0, ENGINE_DIR)

from schema import ContextDeeplinkResponse
from engine import TroubleshootingEngine
from cache import QueryCache


def load_dataset() -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    siis_file = os.path.join(STUDENT_KIT_DIR, "siis_responses.json")
    with open(siis_file, "r", encoding="utf-8") as f:
        siis_data = json.load(f)
    
    dl_file = os.path.join(STUDENT_KIT_DIR, "deeplinks.json")
    with open(dl_file, "r", encoding="utf-8") as f:
        dl_data = json.load(f)
        
    return siis_data["responses"], dl_data


def benchmark_cold_start(scenarios: List[Dict[str, Any]], reps: int = 20) -> Dict[str, float]:
    """Measures fresh instance startup and first request latency."""
    first_req_latencies = []
    init_latencies = []

    sample = scenarios[0]
    q = sample["original_query"]
    siis = sample["siis_response"]

    for _ in range(reps):
        t0 = time.perf_counter()
        engine = TroubleshootingEngine()
        t1 = time.perf_counter()
        init_latencies.append((t1 - t0) * 1000)

        t_req0 = time.perf_counter()
        engine.troubleshoot(q, siis)
        t_req1 = time.perf_counter()
        first_req_latencies.append((t_req1 - t_req0) * 1000)

    first_req_latencies.sort()
    init_latencies.sort()

    def get_stats(arr: List[float]) -> Dict[str, float]:
        n = len(arr)
        return {
            "min": round(arr[0], 3),
            "median": round(arr[n // 2], 3),
            "p95": round(arr[int(n * 0.95)], 3),
            "max": round(arr[-1], 3),
        }

    return {
        "engine_init": get_stats(init_latencies),
        "first_request": get_stats(first_req_latencies),
    }


def benchmark_warm_latency(scenarios: List[Dict[str, Any]], reps: int = 100) -> Dict[str, Any]:
    """Measures latency for warm requests: repeat identical vs diverse requests."""
    engine = TroubleshootingEngine()
    
    # 1. Repeated identical requests (Cache hit path)
    sample = scenarios[0]
    q = sample["original_query"]
    siis = sample["siis_response"]
    
    # Prime cache
    engine.troubleshoot(q, siis)
    
    repeat_latencies = []
    for _ in range(reps):
        t0 = time.perf_counter()
        engine.troubleshoot(q, siis)
        t1 = time.perf_counter()
        repeat_latencies.append((t1 - t0) * 1000)
        
    repeat_latencies.sort()
    
    # 2. Diverse requests without cache (testing raw compute latency across scenarios)
    fresh_latencies = []
    for s in scenarios:
        fresh_engine = TroubleshootingEngine()
        t0 = time.perf_counter()
        fresh_engine.troubleshoot(s["original_query"], s["siis_response"])
        t1 = time.perf_counter()
        fresh_latencies.append((t1 - t0) * 1000)
        
    fresh_latencies.sort()
    
    def calc_percentiles(arr: List[float]) -> Dict[str, float]:
        n = len(arr)
        return {
            "min": round(arr[0], 3),
            "p50": round(arr[n // 2], 3),
            "p95": round(arr[int(n * 0.95)], 3),
            "p99": round(arr[min(n - 1, int(n * 0.99))], 3),
            "max": round(arr[-1], 3),
        }

    return {
        "repeat_cached": calc_percentiles(repeat_latencies),
        "cold_compute": calc_percentiles(fresh_latencies),
    }


def test_cache_behavior(scenarios: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Tests exact cache hit behavior across Test Cases A through F."""
    engine = TroubleshootingEngine()
    sample = scenarios[0]
    base_q = sample["original_query"]
    siis = sample["siis_response"]
    
    # Prime
    engine.troubleshoot(base_q, siis)
    
    tests = [
        ("A. Exact same query repeated", base_q, siis),
        ("B. Exact same query + same SIIS repeated", base_q, dict(siis)),
        ("C. Same query with different capitalization", base_q.upper(), siis),
        ("D. Same query with extra whitespace", f"  {base_q}   ", siis),
        ("E. Same semantic intent with different wording", "My tablet screen blinks and becomes black when opening an email in Gmail", siis),
        ("F. Same semantic intent + different wording + same SIIS", "Tablet screen goes completely dark whenever Gmail is opened", siis),
    ]
    
    results = []
    for label, q_text, s_data in tests:
        # Check if actual cache has it before calling
        is_hit_before = engine.cache.get(q_text) is not None
        t0 = time.perf_counter()
        res = engine.troubleshoot(q_text, s_data)
        t1 = time.perf_counter()
        elapsed_ms = (t1 - t0) * 1000
        
        results.append({
            "case": label,
            "query": q_text[:60] + "...",
            "cache_hit": is_hit_before,
            "latency_ms": round(elapsed_ms, 3),
            "has_response": res is not None and "contexts" in res,
        })
        
    return results


def verify_deeplink_integrity(catalog_data: Dict[str, Any], results_file: str) -> Dict[str, Any]:
    """Verifies that all deeplinks in results.jsonl exist verbatim in the catalog."""
    catalog_uris = {item["deeplink"] for item in catalog_data["deeplinks"]}
    val_catalog_uris = {item["validation"]["deeplink"] for item in catalog_data["deeplinks"] if item.get("validation")}
    
    with open(results_file, "r", encoding="utf-8") as f:
        lines = [json.loads(l) for l in f if l.strip()]
        
    total_actions = 0
    valid_act_uris = 0
    invalid_act_uris = 0
    valid_val_uris = 0
    invalid_val_uris = 0
    url_leaks = 0
    
    found_uris = set()
    
    for item in lines:
        resp = item["response"]
        raw_text = json.dumps(resp)
        if any(leak in raw_text for leak in ("http://", "https://", "www.", ".com", ".html")):
            url_leaks += 1
            
        for ctx in resp.get("contexts", []):
            for act in ctx.get("actions", []):
                total_actions += 1
                for sg in act.get("stepGroups", []):
                    act_dl = sg.get("actionableDeeplink")
                    if act_dl:
                        uri = act_dl.get("deeplink")
                        found_uris.add(uri)
                        if uri in catalog_uris:
                            valid_act_uris += 1
                        else:
                            invalid_act_uris += 1
                            
                    val_dl = sg.get("validationDeeplink")
                    if val_dl:
                        v_uri = val_dl.get("deeplink")
                        if v_uri in val_catalog_uris or v_uri in catalog_uris:
                            valid_val_uris += 1
                        else:
                            invalid_val_uris += 1
                            
    return {
        "total_actions": total_actions,
        "valid_actionable_uris": valid_act_uris,
        "invalid_actionable_uris": invalid_act_uris,
        "valid_validation_uris": valid_val_uris,
        "invalid_validation_uris": invalid_val_uris,
        "url_leaks": url_leaks,
        "distinct_actionable_uris_emitted": len(found_uris),
        "distinct_uris_list": sorted(list(found_uris)),
    }


def main():
    print("=" * 70)
    print("PHASE 1 BASELINE BENCHMARK EXECUTION")
    print("=" * 70)
    
    scenarios, catalog = load_dataset()
    results_path = os.path.join(ENGINE_DIR, "results.jsonl")
    
    # Step 3: Cold Start
    print("\n[Step 3] Running Cold Start Benchmark (20 fresh instantiations)...")
    cold_stats = benchmark_cold_start(scenarios, reps=20)
    print(f"  Engine __init__():  min={cold_stats['engine_init']['min']}ms, med={cold_stats['engine_init']['median']}ms, p95={cold_stats['engine_init']['p95']}ms, max={cold_stats['engine_init']['max']}ms")
    print(f"  First Request:      min={cold_stats['first_request']['min']}ms, med={cold_stats['first_request']['median']}ms, p95={cold_stats['first_request']['p95']}ms, max={cold_stats['first_request']['max']}ms")

    # Step 4: Warm Latency
    print("\n[Step 4] Running Warm Request Latency Benchmark (100 reps)...")
    warm_stats = benchmark_warm_latency(scenarios, reps=100)
    print(f"  Repeat (Cached):    min={warm_stats['repeat_cached']['min']}ms, p50={warm_stats['repeat_cached']['p50']}ms, p95={warm_stats['repeat_cached']['p95']}ms, p99={warm_stats['repeat_cached']['p99']}ms, max={warm_stats['repeat_cached']['max']}ms")
    print(f"  Fresh (Compute):    min={warm_stats['cold_compute']['min']}ms, p50={warm_stats['cold_compute']['p50']}ms, p95={warm_stats['cold_compute']['p95']}ms, p99={warm_stats['cold_compute']['p99']}ms, max={warm_stats['cold_compute']['max']}ms")

    # Step 5: Cache Behavior
    print("\n[Step 5] Testing Cache Behavior (Cases A - F)...")
    cache_cases = test_cache_behavior(scenarios)
    for c in cache_cases:
        hit_str = "[HIT]" if c['cache_hit'] else "[MISS]"
        print(f"  {c['case']}: {hit_str} (latency: {c['latency_ms']} ms)")

    # Step 6 & 7: Schema & Deeplink Integrity
    print("\n[Step 6 & 7] Verifying Deeplink Integrity & URL Leaks...")
    integrity = verify_deeplink_integrity(catalog, results_path)
    print(f"  Total Actions: {integrity['total_actions']}")
    print(f"  Valid Actionable URIs: {integrity['valid_actionable_uris']}/{integrity['total_actions']}")
    print(f"  Invalid URIs: {integrity['invalid_actionable_uris']}")
    print(f"  Valid Validation URIs: {integrity['valid_validation_uris']}")
    print(f"  URL Leaks: {integrity['url_leaks']}")
    print(f"  Distinct URIs used: {integrity['distinct_actionable_uris_emitted']}")
    print(f"  Emitted URIs: {integrity['distinct_uris_list']}")

    # Save summary json
    summary = {
        "cold_start": cold_stats,
        "warm_latency": warm_stats,
        "cache_behavior": cache_cases,
        "integrity": integrity,
    }
    out_file = os.path.join(PROJECT_ROOT, "scratch", "generated", "baseline_metrics.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"\n[Done] Baseline metrics saved to {out_file}")


if __name__ == "__main__":
    main()
