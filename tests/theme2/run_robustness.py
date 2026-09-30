"""Robustness Benchmark Harness for Samsung PRISM GenAI Hackathon 3.0 — Theme 2.

Evaluates:
- Schema validity (Gate G2, Block A1: goal regex, title word count, description rules)
- Catalog grounding & deeplink validity (Block A2)
- URI & Action exact/semantic matching
- Polarity accuracy (Enable vs Disable vs Neutral)
- Category generalization & cross-topic performance (Wi-Fi, Battery, Sound, Bluetooth, etc.)
- Hardware safety & boundary fallback handling
- Paraphrase & Repeat cache performance (Block A3)
- Suspicious convergence / hardcoding diagnostic (distinct URIs & actions)
"""

from __future__ import annotations
import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Set, Tuple

# Path setup
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
THEME2_DIR = os.path.join(PROJECT_ROOT, "Theme02_Engine")
CANDIDATE_KIT_DIRS = [
    os.path.join(PROJECT_ROOT, "data", "student_kit"),
    os.path.join(PROJECT_ROOT, "participant-kit-all-themes", "participant-kit", "Theme02_Input_Kit", "student_kit")
]
STUDENT_KIT_DIR = next((d for d in CANDIDATE_KIT_DIRS if os.path.exists(d)), CANDIDATE_KIT_DIRS[0])
DATASET_PATH = os.path.join(os.path.dirname(__file__), "robustness_dataset.jsonl")
CATALOG_PATH = os.path.join(STUDENT_KIT_DIR, "deeplinks.json")
RESULTS_OUT_PATH = os.path.join(PROJECT_ROOT, "scratch", "generated", "robustness_baseline_results.json")
STATS_OUT_PATH = os.path.join(PROJECT_ROOT, "scratch", "generated", "robustness_dataset_stats.json")

# Ensure imports resolve
if STUDENT_KIT_DIR not in sys.path:
    sys.path.insert(0, STUDENT_KIT_DIR)
if THEME2_DIR not in sys.path:
    sys.path.insert(0, THEME2_DIR)

from schema import ContextDeeplinkResponse  # type: ignore
from engine import TroubleshootingEngine    # type: ignore

GOAL_REGEX = re.compile(r"^Follow these steps to perform this .* (Troubleshooting|Configuration)\.$")
URL_LEAK_REGEX = re.compile(r"https?://", re.IGNORECASE)


def load_catalog_uris(catalog_path: str) -> Set[str]:
    """Load valid URIs from official deeplinks catalog."""
    with open(catalog_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    uris = {e["deeplink"] for e in data.get("deeplinks", [])}
    uris.add("bixby://dummy_positive")
    uris.add("bixby://dummy_negative")
    return uris


def evaluate_response_schema(resp: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate Pydantic schema and official formatting constraints per test_suite.py."""
    errors = []
    # 1. Pydantic validation
    try:
        obj = ContextDeeplinkResponse(**resp)
    except Exception as e:
        return False, [f"Pydantic validation failed: {str(e)[:150]}"]

    raw_json = json.dumps(resp)
    # 2. URL leak check (Gate G5)
    if URL_LEAK_REGEX.search(raw_json):
        errors.append("Leaked web URL (http:// or https://) in response")

    # 3. Goal format regex
    goal = resp.get("contexts", [{}])[0].get("goal", "")
    if not GOAL_REGEX.match(goal):
        errors.append(f"Goal regex failed: '{goal[:80]}'")

    # 4. Title word count (2-3 words per test_suite.py line 82)
    title = resp.get("contexts", [{}])[0].get("title", "")
    words = [w for w in title.split() if w.strip()]
    if not (2 <= len(words) <= 3):
        errors.append(f"Title word count {len(words)} not in [2, 3]: '{title}'")

    # 5. Action description checks (5-7 words, starts with 'It will' per test_suite.py line 87)
    actions = resp.get("contexts", [{}])[0].get("actions", [])
    for act in actions:
        desc = act.get("description", "")
        desc_words = [w for w in desc.split() if w.strip()]
        if not desc.startswith("It will"):
            errors.append(f"Action description does not start with 'It will': '{desc[:60]}'")
        if not (5 <= len(desc_words) <= 7):
            errors.append(f"Action description word count {len(desc_words)} not in [5, 7]: '{desc}'")

    return (len(errors) == 0), errors


def determine_uri_polarity(uri: str, catalog_entries: List[Dict[str, Any]]) -> str:
    """Infer whether a deeplink action is enable, disable, or neutral."""
    uri_clean = uri.strip()
    for e in catalog_entries:
        if e.get("deeplink") == uri_clean:
            desc = (e.get("description", "") + " " + e.get("message", "")).lower()
            if any(w in desc for w in ("disable", "turn off", "deactivate", "switch off", "mute")):
                return "disable"
            if any(w in desc for w in ("enable", "turn on", "activate", "switch on")):
                return "enable"
            return "neutral"
    return "unknown"


def run_benchmark():
    print("=" * 70)
    print("SAMSUNG PRISM THEME 2 — OFFLINE ROBUSTNESS BENCHMARK")
    print("=" * 70)

    # 1. Load dataset
    if not os.path.isfile(DATASET_PATH):
        raise FileNotFoundError(f"Robustness dataset not found at {DATASET_PATH}. Run scratch/build_robustness_dataset.py first.")

    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        cases = [json.loads(line) for line in f if line.strip()]

    print(f"Loaded {len(cases)} test cases from {DATASET_PATH}")

    # 2. Load catalog
    valid_uris = load_catalog_uris(CATALOG_PATH)
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        catalog_raw = json.load(f)
    catalog_entries = catalog_raw.get("deeplinks", [])
    print(f"Loaded {len(valid_uris)} valid catalog URIs (including dummy placeholders)")

    # 3. Instantiate Engine
    engine = TroubleshootingEngine()

    results = []
    latencies = []
    distinct_uris = set()
    distinct_actions = set()

    class_stats: Dict[str, Dict[str, Any]] = {}
    category_stats: Dict[str, Dict[str, Any]] = {}
    difficulty_stats: Dict[str, Dict[str, Any]] = {}

    # Metrics accumulators
    schema_passes = 0
    uri_exact_matches = 0
    action_matches = 0
    polarity_matches = 0
    polarity_eval_count = 0
    catalog_valid_count = 0
    hardware_safety_passes = 0
    hardware_cases_count = 0

    print(f"\nExecuting {len(cases)} test cases against baseline TroubleshootingEngine...\n")

    for idx, case in enumerate(cases):
        c_id = case["id"]
        c_class = case["class"]
        c_cat = case["category"]
        c_diff = case.get("difficulty", "medium")
        query = case["query"]
        siis = case["siis_response"]
        exp_uri = case.get("expected_uri")
        exp_act = case.get("expected_action")
        exp_pol = case.get("expected_polarity", "neutral")

        # Init breakdown buckets
        for bucket, key in [(class_stats, c_class), (category_stats, c_cat), (difficulty_stats, c_diff)]:
            if key not in bucket:
                bucket[key] = {
                    "total": 0,
                    "schema_pass": 0,
                    "uri_match": 0,
                    "action_match": 0,
                    "polarity_match": 0,
                    "polarity_total": 0,
                    "uris_emitted": set(),
                    "actions_emitted": set(),
                }
            bucket[key]["total"] += 1

        # Execute engine call & measure latency
        t0 = time.perf_counter()
        resp = engine.troubleshoot(query, siis)
        t1 = time.perf_counter()
        lat_ms = (t1 - t0) * 1000.0
        latencies.append(lat_ms)

        # Schema & Formatting
        is_schema_valid, schema_errors = evaluate_response_schema(resp)
        if is_schema_valid:
            schema_passes += 1
            class_stats[c_class]["schema_pass"] += 1
            category_stats[c_cat]["schema_pass"] += 1
            difficulty_stats[c_diff]["schema_pass"] += 1

        # Extract generated actionable deeplink & action
        contexts = resp.get("contexts", [])
        act_0 = contexts[0].get("actions", [{}])[0] if contexts and contexts[0].get("actions") else {}
        step_groups = act_0.get("stepGroups", [])
        sg_0 = step_groups[0] if step_groups else {}
        actionable_dl = sg_0.get("actionableDeeplink") or {}
        gen_uri = actionable_dl.get("deeplink")
        gen_act_name = act_0.get("actionName", "")

        if gen_uri:
            distinct_uris.add(gen_uri)
            class_stats[c_class]["uris_emitted"].add(gen_uri)
            category_stats[c_cat]["uris_emitted"].add(gen_uri)
            difficulty_stats[c_diff]["uris_emitted"].add(gen_uri)

        if gen_act_name:
            distinct_actions.add(gen_act_name)
            class_stats[c_class]["actions_emitted"].add(gen_act_name)
            category_stats[c_cat]["actions_emitted"].add(gen_act_name)
            difficulty_stats[c_diff]["actions_emitted"].add(gen_act_name)

        # Catalog validity
        is_catalog_valid = (gen_uri in valid_uris) if gen_uri else False
        if is_catalog_valid:
            catalog_valid_count += 1

        # URI match
        uri_matched = False
        if exp_uri is not None:
            uri_matched = (gen_uri == exp_uri)
        else:
            # If expected_uri is None (e.g. pure hardware repair), URI match requires either None or dummy
            uri_matched = (gen_uri is None or gen_uri == "bixby://dummy_positive")

        if uri_matched:
            uri_exact_matches += 1
            class_stats[c_class]["uri_match"] += 1
            category_stats[c_cat]["uri_match"] += 1
            difficulty_stats[c_diff]["uri_match"] += 1

        # Action match (substring or equality)
        action_matched = False
        if exp_act:
            action_matched = (gen_act_name.strip().lower() == exp_act.strip().lower())
        if action_matched:
            action_matches += 1
            class_stats[c_class]["action_match"] += 1
            category_stats[c_cat]["action_match"] += 1
            difficulty_stats[c_diff]["action_match"] += 1

        # Polarity match
        pol_matched = False
        if exp_pol in ("enable", "disable"):
            polarity_eval_count += 1
            class_stats[c_class]["polarity_total"] += 1
            category_stats[c_cat]["polarity_total"] += 1
            difficulty_stats[c_diff]["polarity_total"] += 1
            inferred_pol = determine_uri_polarity(gen_uri, catalog_entries) if gen_uri else "unknown"
            if inferred_pol == exp_pol:
                polarity_matches += 1
                pol_matched = True
                class_stats[c_class]["polarity_match"] += 1
                category_stats[c_cat]["polarity_match"] += 1
                difficulty_stats[c_diff]["polarity_match"] += 1

        # Hardware safety check for Class M
        hw_safe = None
        if c_class == "M_unsupported_hardware":
            hardware_cases_count += 1
            # An engine is safe if it does NOT offer an auto setting purporting to fix physical/liquid damage
            # If it generates category: auto with a display/sound toggle, that is a severe hallucination/safety violation
            is_auto = (act_0.get("category") == "auto")
            # If it offered an automated setting to "fix" smashed screen or water damage, fail safety
            if not is_auto or gen_uri in ("bixby://dummy_positive", None):
                hardware_safety_passes += 1
                hw_safe = True
            else:
                # Flag failure: it tried to fix physical damage via auto deeplink
                hw_safe = False

        results.append({
            "id": c_id,
            "class": c_class,
            "category": c_cat,
            "difficulty": c_diff,
            "query": query,
            "latency_ms": round(lat_ms, 3),
            "schema_valid": is_schema_valid,
            "schema_errors": schema_errors,
            "catalog_valid": is_catalog_valid,
            "gen_uri": gen_uri,
            "exp_uri": exp_uri,
            "uri_match": uri_matched,
            "gen_action": gen_act_name,
            "exp_action": exp_act,
            "action_match": action_matched,
            "exp_polarity": exp_pol,
            "polarity_match": pol_matched,
            "hardware_safety": hw_safe
        })

    # Cache Repeat & Paraphrase Check
    print("Testing repeat and paraphrase cache behavior...")
    # Repeat test on first 20 cases using existing engine
    repeat_latencies = []
    repeat_hits = 0
    for case in cases[:20]:
        t0 = time.perf_counter()
        r = engine.troubleshoot(case["query"], case["siis_response"])
        t1 = time.perf_counter()
        lat = (t1 - t0) * 1000.0
        repeat_latencies.append(lat)
        if lat < 2.0:
            repeat_hits += 1

    # Honest Paraphrase test using Class P (cache equivalence groups):
    # Spin up a fresh engine with an empty cache.
    # Warm the cache with the canonical query of each equivalence group,
    # then check whether subsequent paraphrases in the same group hit cache.
    fresh_engine = TroubleshootingEngine()
    cache_equiv_cases = [c for c in cases if c["class"] == "P_cache_equivalence"]
    
    # Group by notes / source / category
    equiv_groups: Dict[str, List[Dict[str, Any]]] = {}
    for c in cache_equiv_cases:
        grp_key = f"{c['category']}_{c.get('expected_action', '')}"
        equiv_groups.setdefault(grp_key, []).append(c)

    paraphrase_hits = 0
    paraphrase_total = 0

    for grp_key, grp_cases in equiv_groups.items():
        if len(grp_cases) < 2:
            continue
        # 1. Warm cache with first query in equivalence group
        canonical_case = grp_cases[0]
        fresh_engine.troubleshoot(canonical_case["query"], canonical_case["siis_response"])

        # 2. Test if subsequent semantic paraphrases in the same group hit cache
        for variant_case in grp_cases[1:]:
            paraphrase_total += 1
            t0 = time.perf_counter()
            cached_resp = fresh_engine.cache.get(variant_case["query"])
            t1 = time.perf_counter()
            lookup_lat = (t1 - t0) * 1000.0
            if cached_resp is not None and lookup_lat < 2.0:
                paraphrase_hits += 1

    repeat_hit_rate = (repeat_hits / len(repeat_latencies)) * 100.0 if repeat_latencies else 0.0
    paraphrase_hit_rate = (paraphrase_hits / paraphrase_total) * 100.0 if paraphrase_total else 0.0

    # Summary statistics
    total_cases = len(cases)
    schema_rate = (schema_passes / total_cases) * 100.0
    uri_match_rate = (uri_exact_matches / total_cases) * 100.0
    action_match_rate = (action_matches / total_cases) * 100.0
    polarity_rate = (polarity_matches / polarity_eval_count) * 100.0 if polarity_eval_count else 0.0
    catalog_rate = (catalog_valid_count / total_cases) * 100.0
    hw_safety_rate = (hardware_safety_passes / hardware_cases_count) * 100.0 if hardware_cases_count else 0.0

    latencies_sorted = sorted(latencies)
    cold_start_lat = latencies[0]
    p50_lat = latencies_sorted[int(len(latencies_sorted) * 0.50)]
    p95_lat = latencies_sorted[int(len(latencies_sorted) * 0.95)]
    max_lat = latencies_sorted[-1]

    # Convert sets to lists for JSON serialization
    for b in (class_stats, category_stats, difficulty_stats):
        for k in b:
            b[k]["uris_emitted"] = list(b[k]["uris_emitted"])
            b[k]["actions_emitted"] = list(b[k]["actions_emitted"])
            b[k]["uri_match_rate"] = round((b[k]["uri_match"] / b[k]["total"]) * 100.0, 1)
            b[k]["schema_pass_rate"] = round((b[k]["schema_pass"] / b[k]["total"]) * 100.0, 1)
            b[k]["action_match_rate"] = round((b[k]["action_match"] / b[k]["total"]) * 100.0, 1)
            if b[k]["polarity_total"] > 0:
                b[k]["polarity_rate"] = round((b[k]["polarity_match"] / b[k]["polarity_total"]) * 100.0, 1)
            else:
                b[k]["polarity_rate"] = None

    summary_stats = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_test_cases": total_cases,
        "gates_and_formatting": {
            "schema_pass_count": schema_passes,
            "schema_validity_rate_pct": round(schema_rate, 2),
            "catalog_validity_rate_pct": round(catalog_rate, 2),
        },
        "retrieval_and_accuracy": {
            "uri_exact_matches": uri_exact_matches,
            "uri_match_rate_pct": round(uri_match_rate, 2),
            "action_matches": action_matches,
            "action_match_rate_pct": round(action_match_rate, 2),
            "polarity_eval_count": polarity_eval_count,
            "polarity_matches": polarity_matches,
            "polarity_accuracy_rate_pct": round(polarity_rate, 2),
            "hardware_cases_count": hardware_cases_count,
            "hardware_safety_passes": hardware_safety_passes,
            "hardware_safety_rate_pct": round(hw_safety_rate, 2),
        },
        "diversity_diagnostics": {
            "distinct_actionable_uris": len(distinct_uris),
            "distinct_action_names": len(distinct_actions),
            "uris_list": sorted(list(distinct_uris)),
            "actions_list": sorted(list(distinct_actions)),
            "collapse_warning": len(distinct_uris) <= 5,
        },
        "latency_and_caching": {
            "cold_start_ms": round(cold_start_lat, 3),
            "p50_latency_ms": round(p50_lat, 3),
            "p95_latency_ms": round(p95_lat, 3),
            "max_latency_ms": round(max_lat, 3),
            "repeat_cache_hit_rate_pct": round(repeat_hit_rate, 2),
            "paraphrase_cache_hit_rate_pct": round(paraphrase_hit_rate, 2),
        },
        "breakdown_by_class": class_stats,
        "breakdown_by_category": category_stats,
        "breakdown_by_difficulty": difficulty_stats,
    }

    # Write output files
    os.makedirs(os.path.dirname(RESULTS_OUT_PATH), exist_ok=True)
    with open(RESULTS_OUT_PATH, "w", encoding="utf-8") as f:
        json.dump({"summary": summary_stats, "results": results}, f, indent=2, ensure_ascii=False)
    print(f"\n[Saved] Detailed results saved to {RESULTS_OUT_PATH}")

    with open(STATS_OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(summary_stats, f, indent=2, ensure_ascii=False)
    print(f"[Saved] Summary statistics saved to {STATS_OUT_PATH}")

    # Print Formatted Console Report
    print("\n" + "=" * 70)
    print("ROBUSTNESS BENCHMARK RESULTS SUMMARY (BASELINE ENGINE)")
    print("=" * 70)
    print(f"Total Test Cases:               {total_cases}")
    print(f"Schema Validity Rate:           {schema_rate:.2f}% ({schema_passes}/{total_cases})")
    print(f"Catalog Deeplink Validity:      {catalog_rate:.2f}% ({catalog_valid_count}/{total_cases})")
    print(f"URI Exact Match Rate:           {uri_match_rate:.2f}% ({uri_exact_matches}/{total_cases})")
    print(f"Action Name Match Rate:         {action_match_rate:.2f}% ({action_matches}/{total_cases})")
    print(f"Polarity Accuracy Rate:         {polarity_rate:.2f}% ({polarity_matches}/{polarity_eval_count})")
    print(f"Hardware Safety Pass Rate:      {hw_safety_rate:.2f}% ({hardware_safety_passes}/{hardware_cases_count})")
    print("-" * 70)
    print(f"Distinct Actionable URIs:       {len(distinct_uris)} (Collapse Warning: {'YES' if len(distinct_uris) <= 5 else 'NO'})")
    print(f"Distinct Action Names:          {len(distinct_actions)}")
    print(f"Actions Generated:              {list(distinct_actions)}")
    print(f"URIs Generated:                 {list(distinct_uris)}")
    print("-" * 70)
    print(f"Cold Start Latency:             {cold_start_lat:.3f} ms")
    print(f"P50 Latency:                    {p50_lat:.3f} ms")
    print(f"P95 Latency:                    {p95_lat:.3f} ms")
    print(f"Repeat Cache Hit Rate:          {repeat_hit_rate:.2f}%")
    print(f"Paraphrase Cache Hit Rate:      {paraphrase_hit_rate:.2f}%")
    print("=" * 70)

    # Class performance summary
    print("\nPERFORMANCE BY TEST CLASS:")
    print(f"{'Class':<32} {'Total':<6} {'Schema %':<10} {'URI Match %':<12} {'Distinct URIs':<14}")
    print("-" * 75)
    for c_name, c_data in sorted(class_stats.items()):
        print(f"{c_name:<32} {c_data['total']:<6} {c_data['schema_pass_rate']:<10.1f} {c_data['uri_match_rate']:<12.1f} {len(c_data['uris_emitted']):<14}")

    # Category performance summary
    print("\nPERFORMANCE BY DEVICE CATEGORY:")
    print(f"{'Category':<22} {'Total':<6} {'URI Match %':<12} {'Distinct URIs':<14} {'Actions Emitted'}")
    print("-" * 80)
    for cat_name, cat_data in sorted(category_stats.items()):
        acts = ", ".join(cat_data['actions_emitted'][:2])
        print(f"{cat_name:<22} {cat_data['total']:<6} {cat_data['uri_match_rate']:<12.1f} {len(cat_data['uris_emitted']):<14} {acts}")

    print("=" * 70)
    return summary_stats


if __name__ == "__main__":
    run_benchmark()
