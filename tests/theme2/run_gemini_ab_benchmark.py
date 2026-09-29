"""Phase 17: Gemini A/B Benchmark Runner across Modes A, B, and C.

Modes:
- Mode A: Deterministic baseline (GEMINI_MODE=off)
- Mode B: Gemini always-on (GEMINI_MODE=always)
- Mode C: Gemini conditional on ambiguity (GEMINI_MODE=confidence)
"""

import sys
import os
import json
import time
from typing import Any, Dict, List, Optional

# Path setup
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
THEME2_DIR = os.path.join(PROJECT_ROOT, "Theme02_Engine")
STUDENT_KIT_DIR = os.path.join(PROJECT_ROOT, "participant-kit-all-themes", "participant-kit", "Theme02_Input_Kit", "student_kit")
DATASET_PATH = os.path.join(os.path.dirname(__file__), "robustness_dataset.jsonl")
CATALOG_PATH = os.path.join(STUDENT_KIT_DIR, "deeplinks.json")

if STUDENT_KIT_DIR not in sys.path:
    sys.path.insert(0, STUDENT_KIT_DIR)
if THEME2_DIR not in sys.path:
    sys.path.insert(0, THEME2_DIR)

from engine import TroubleshootingEngine
from schema import ContextDeeplinkResponse


def load_catalog_uris(catalog_path: str):
    with open(catalog_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    uris = {e["deeplink"] for e in data.get("deeplinks", [])}
    uris.add("bixby://dummy_positive")
    uris.add("bixby://dummy_negative")
    return uris


def evaluate_mode(mode_name: str, gemini_mode: str, cases: List[Dict[str, Any]], valid_uris: set) -> Dict[str, Any]:
    print(f"\n=======================================================")
    print(f"EVALUATING: {mode_name} (GEMINI_MODE={gemini_mode})")
    print(f"=======================================================")

    os.environ["GEMINI_MODE"] = gemini_mode
    engine = TroubleshootingEngine()
    engine.adjudicator.mode = gemini_mode

    total_cases = len(cases)
    schema_passes = 0
    catalog_passes = 0
    uri_matches = 0
    action_matches = 0
    polarity_matches = 0
    polarity_count = 0
    hardware_passes = 0
    hardware_count = 0
    latencies = []

    for c in cases:
        c_class = c["class"]
        q = c["query"]
        siis = c["siis_response"]
        exp_uri = c.get("expected_uri")
        exp_act = (c.get("expected_action") or "").strip().lower()
        exp_pol = c.get("expected_polarity", "neutral")

        t0 = time.perf_counter()
        resp = engine.troubleshoot(q, siis)
        lat = (time.perf_counter() - t0) * 1000.0
        latencies.append(lat)

        # 1. Schema check
        try:
            ContextDeeplinkResponse(**resp)
            schema_passes += 1
        except Exception:
            pass

        # 2. Extract action and uri
        try:
            action_obj = resp["contexts"][0]["actions"][0]
            gen_act = action_obj.get("actionName", "").strip().lower()
            sg = action_obj.get("stepGroups", [{}])[0]
            act_dl = sg.get("actionableDeeplink") or {}
            gen_uri = act_dl.get("deeplink")
        except Exception:
            gen_act = ""
            gen_uri = None

        # 3. Catalog validity
        if gen_uri in valid_uris:
            catalog_passes += 1

        # 4. URI Match
        uri_matched = (gen_uri == exp_uri) if exp_uri is not None else (gen_uri is None or gen_uri == "bixby://dummy_positive")
        if uri_matched:
            uri_matches += 1

        # 5. Action Match
        if exp_act and (gen_act == exp_act):
            action_matches += 1

        # 6. Polarity Match
        if exp_pol in ("enable", "disable"):
            polarity_count += 1
            gen_desc = (action_obj.get("description") or "").lower()
            gen_name_low = gen_act.lower()
            if exp_pol == "enable" and (gen_name_low.startswith("enable") or "enable" in gen_desc):
                polarity_matches += 1
            elif exp_pol == "disable" and (gen_name_low.startswith("disable") or "disable" in gen_desc):
                polarity_matches += 1

        # 7. Hardware Safety
        if c_class == "M_unsupported_hardware":
            hardware_count += 1
            if gen_uri is None and gen_act == "schedule device repair service":
                hardware_passes += 1

    sorted_lats = sorted(latencies)
    cold_lat = sorted_lats[-1] if sorted_lats else 0.0
    p50_lat = sorted_lats[len(sorted_lats) // 2] if sorted_lats else 0.0
    p95_lat = sorted_lats[int(len(sorted_lats) * 0.95)] if sorted_lats else 0.0

    stats = engine.adjudicator.stats

    return {
        "mode": mode_name,
        "gemini_mode": gemini_mode,
        "total_cases": total_cases,
        "schema_validity_pct": round((schema_passes / total_cases) * 100.0, 2),
        "catalog_validity_pct": round((catalog_passes / total_cases) * 100.0, 2),
        "uri_match_pct": round((uri_matches / total_cases) * 100.0, 2),
        "action_match_pct": round((action_matches / total_cases) * 100.0, 2),
        "polarity_accuracy_pct": round((polarity_matches / polarity_count) * 100.0 if polarity_count else 0.0, 2),
        "hardware_safety_pct": round((hardware_passes / hardware_count) * 100.0 if hardware_count else 100.0, 2),
        "cold_lat_ms": round(cold_lat, 2),
        "p50_lat_ms": round(p50_lat, 2),
        "p95_lat_ms": round(p95_lat, 2),
        "gemini_calls": stats.get("calls", 0),
        "gemini_success": stats.get("success", 0),
        "gemini_fallbacks": stats.get("fallbacks", 0),
        "gemini_http_429": stats.get("http_429", 0),
    }


def main():
    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        cases = [json.loads(line) for line in f if line.strip()]

    valid_uris = load_catalog_uris(CATALOG_PATH)

    results = []
    # Mode A: Deterministic
    res_a = evaluate_mode("Mode A: Deterministic Baseline", "off", cases, valid_uris)
    results.append(res_a)

    # Mode B: Gemini Always
    res_b = evaluate_mode("Mode B: Gemini Always", "always", cases, valid_uris)
    results.append(res_b)

    # Mode C: Gemini Conditional
    res_c = evaluate_mode("Mode C: Gemini Conditional", "confidence", cases, valid_uris)
    results.append(res_c)

    print("\n" + "=" * 90)
    print("PHASE 17: GEMINI A/B BENCHMARK COMPARISON TABLE")
    print("=" * 90)
    header = f"{'Metric':<25} | {'Mode A (Deterministic)':<22} | {'Mode B (Gemini Always)':<22} | {'Mode C (Conditional)':<22}"
    print(header)
    print("-" * len(header))

    metrics = [
        ("URI Exact Match %", "uri_match_pct"),
        ("Action Match %", "action_match_pct"),
        ("Polarity Accuracy %", "polarity_accuracy_pct"),
        ("Hardware Safety %", "hardware_safety_pct"),
        ("Schema Validity %", "schema_validity_pct"),
        ("Catalog Validity %", "catalog_validity_pct"),
        ("P50 Latency (ms)", "p50_lat_ms"),
        ("P95 Latency (ms)", "p95_lat_ms"),
        ("Gemini Calls", "gemini_calls"),
        ("Gemini Fallbacks", "gemini_fallbacks"),
        ("HTTP 429 Errors", "gemini_http_429"),
    ]

    for label, key in metrics:
        row = f"{label:<25} | {str(res_a[key]):<22} | {str(res_b[key]):<22} | {str(res_c[key]):<22}"
        print(row)


if __name__ == "__main__":
    main()
