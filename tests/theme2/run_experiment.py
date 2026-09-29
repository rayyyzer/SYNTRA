"""Phase 20 Experiment Runner & Gemini Semantic Lab.

Usage:
  python -m tests.theme2.run_experiment --mode deterministic --top-k 10
  python -m tests.theme2.run_experiment --mode gemini-rerank --top-k 10
  python -m tests.theme2.run_experiment --mode gemini-intent --top-k 10
  python -m tests.theme2.run_experiment --mode gemini-intent-rerank --top-k 10
  python -m tests.theme2.run_experiment --mode gemini-selective --top-k 10
"""

from __future__ import annotations
import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
THEME2_DIR = os.path.join(PROJECT_ROOT, "Theme02_Engine")
STUDENT_KIT_DIR = os.path.join(PROJECT_ROOT, "participant-kit-all-themes", "participant-kit", "Theme02_Input_Kit", "student_kit")
ROBUSTNESS_DATASET = os.path.join(os.path.dirname(__file__), "robustness_dataset.jsonl")
HELDOUT_DATASET = os.path.join(os.path.dirname(__file__), "held_out_generalization_dataset.jsonl")

if THEME2_DIR not in sys.path:
    sys.path.insert(0, THEME2_DIR)
if STUDENT_KIT_DIR not in sys.path:
    sys.path.insert(0, STUDENT_KIT_DIR)

from engine import TroubleshootingEngine
from gemini_reasoner import GeminiSemanticReasoner, GeminiIntentOutput, GeminiReasonerResult
from retrieval.polarity import detect_query_polarity, get_entry_polarity, Polarity


def run_benchmark_on_dataset(
    dataset_path: str,
    engine: TroubleshootingEngine,
    reasoner: GeminiSemanticReasoner,
    mode: str = "deterministic",
    top_k: int = 10,
    is_heldout: bool = False,
) -> Dict[str, Any]:
    with open(dataset_path, "r", encoding="utf-8") as f:
        cases = [json.loads(line) for line in f if line.strip()]

    uri_matches = 0
    act_matches = 0
    pol_matches = 0
    pol_total = 0
    hw_matches = 0
    hw_total = 0

    gemini_calls = 0
    gemini_corrections = 0
    gemini_true_corrections = 0
    gemini_false_corrections = 0
    gemini_no_change = 0
    gemini_fallbacks = 0

    latencies = []
    t_cold_start_0 = time.perf_counter()
    cold_start_ms = 0.0

    for idx, c in enumerate(cases):
        q = c["query"]
        s_resp = c.get("siis_response") or {}
        siis_title = str(s_resp.get("title", "")) if s_resp.get("title") else ""
        siis_content = str(s_resp.get("content", "")) if s_resp.get("content") else ""

        exp_uri = c.get("expected_uri")
        exp_act = (c.get("expected_action") or "").strip().lower()
        exp_pol = c.get("expected_polarity")
        c_class = c.get("class", "")
        c_cat = c.get("category", "")

        if is_heldout:
            is_hw = (c_cat == "Hardware")
        else:
            is_hw = (c_class == "M_unsupported_hardware")
        if is_hw:
            hw_total += 1

        t0 = time.perf_counter()

        # Check safety router first
        from safety_router import is_unsupported_hardware, get_hardware_repair_action
        if is_unsupported_hardware(q, siis_content):
            if is_hw:
                hw_matches += 1
            gen_uri = None
            gen_act = "Schedule Device Repair Service"
            uri_match = (gen_uri == exp_uri) if exp_uri is not None else (gen_uri in (None, "bixby://dummy_positive"))
            act_match = (gen_act.strip().lower() == exp_act) if exp_act else False
            if uri_match:
                uri_matches += 1
            if act_match:
                act_matches += 1
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            latencies.append(elapsed_ms)
            if idx == 0:
                cold_start_ms = (time.perf_counter() - t_cold_start_0) * 1000.0
            continue

        # 1. Retrieve candidates
        candidates = engine.retriever.retrieve(
            query=q,
            top_k=top_k,
            siis_title=siis_title,
            siis_content=siis_content
        )

        if not candidates or candidates[0]["score"] < 0.20:
            gen_uri = "bixby://dummy_positive"
            gen_act = "Open Relevant Settings Screen"
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            latencies.append(elapsed_ms)
            if idx == 0:
                cold_start_ms = (time.perf_counter() - t_cold_start_0) * 1000.0
            continue

        # 2. Deterministic Adjudication
        adj = engine.adjudicator.adjudicate(
            query=q,
            siis_title=siis_title,
            siis_content=siis_content,
            candidates=candidates
        )
        det_best = adj.get("selected_candidate") or candidates[0]
        final_best = det_best

        # 3. Gemini Experiment Modes
        if mode != "deterministic" and reasoner.is_enabled():
            intent_out: Optional[GeminiIntentOutput] = None
            if "intent" in mode:
                intent_out = reasoner.extract_intent(q, siis_title=siis_title, siis_content=siis_content)

            should_rerank = False
            if mode in ("gemini-rerank", "gemini-intent-rerank"):
                should_rerank = True
            elif mode == "gemini-selective":
                # Selective ambiguity condition
                margin = adj.get("margin", 1.0)
                conf = adj.get("confidence", 1.0)
                if margin < 0.06 or conf < 0.35:
                    should_rerank = True
                elif len(candidates) >= 2:
                    p1 = (candidates[0].get("polarity") or "neutral").lower()
                    p2 = (candidates[1].get("polarity") or "neutral").lower()
                    if (p1 == "enable" and p2 == "disable") or (p1 == "disable" and p2 == "enable"):
                        should_rerank = True

            if should_rerank:
                gemini_calls += 1
                res = reasoner.rerank_candidates(
                    query=q,
                    siis_title=siis_title,
                    siis_content=siis_content,
                    candidate_pool=candidates,
                    deterministic_draft=det_best,
                    extracted_intent=intent_out
                )
                cand_map = {c.get("id"): c for c in candidates if c.get("id")}
                if res.decision == "SELECT" and res.selected_candidate_id in cand_map:
                    chosen = cand_map[res.selected_candidate_id]
                    if chosen.get("id") != det_best.get("id"):
                        gemini_corrections += 1
                        # Evaluate whether correction was true or false
                        det_act_match = (det_best.get("message", "").strip().lower() == exp_act) if exp_act else False
                        gem_act_match = (chosen.get("message", "").strip().lower() == exp_act) if exp_act else False
                        if gem_act_match and not det_act_match:
                            gemini_true_corrections += 1
                        elif det_act_match and not gem_act_match:
                            gemini_false_corrections += 1

                        final_best = chosen
                    else:
                        gemini_no_change += 1
                else:
                    gemini_fallbacks += 1

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        latencies.append(elapsed_ms)
        if idx == 0:
            cold_start_ms = (time.perf_counter() - t_cold_start_0) * 1000.0

        gen_uri = final_best.get("deeplink")
        gen_act = final_best.get("message", "")

        # Check URI Match
        uri_match = (gen_uri == exp_uri) if exp_uri else (gen_uri in (None, "bixby://dummy_positive"))
        if uri_match:
            uri_matches += 1

        # Check Action Match
        act_match = (gen_act.strip().lower() == exp_act) if exp_act else False
        if act_match:
            act_matches += 1

        # Check Polarity Match
        if exp_pol in ("enable", "disable"):
            pol_total += 1
            inferred_pol = "unknown"
            for e in engine.retriever.bm25.entries:
                if e.get("deeplink") == gen_uri:
                    desc = (e.get("description", "") + " " + e.get("message", "")).lower()
                    if any(w in desc for w in ("disable", "turn off", "deactivate", "switch off", "mute")):
                        inferred_pol = "disable"
                    elif any(w in desc for w in ("enable", "turn on", "activate", "switch on")):
                        inferred_pol = "enable"
                    else:
                        inferred_pol = "neutral"
                    break
            if inferred_pol == exp_pol:
                pol_matches += 1

    lats_sorted = sorted(latencies)
    avg_lat = sum(latencies) / len(latencies) if latencies else 0.0
    p50_lat = lats_sorted[int(len(lats_sorted) * 0.50)] if lats_sorted else 0.0
    p95_lat = lats_sorted[int(len(lats_sorted) * 0.95)] if lats_sorted else 0.0

    return {
        "dataset": os.path.basename(dataset_path),
        "total_cases": len(cases),
        "uri_matches": uri_matches,
        "uri_accuracy": round(uri_matches / len(cases) * 100.0, 2),
        "action_matches": act_matches,
        "action_accuracy": round(act_matches / len(cases) * 100.0, 2),
        "polarity_matches": pol_matches,
        "polarity_total": pol_total,
        "polarity_accuracy": round(pol_matches / pol_total * 100.0, 2) if pol_total else 100.0,
        "hardware_matches": hw_matches,
        "hardware_total": hw_total,
        "hardware_safety": round(hw_matches / hw_total * 100.0, 2) if hw_total else 100.0,
        "gemini_calls": gemini_calls,
        "gemini_corrections": gemini_corrections,
        "gemini_true_corrections": gemini_true_corrections,
        "gemini_false_corrections": gemini_false_corrections,
        "gemini_no_change": gemini_no_change,
        "gemini_fallbacks": gemini_fallbacks,
        "cold_start_ms": round(cold_start_ms, 2),
        "avg_latency_ms": round(avg_lat, 2),
        "p50_latency_ms": round(p50_lat, 2),
        "p95_latency_ms": round(p95_lat, 2),
    }


def main():
    parser = argparse.ArgumentParser(description="Phase 20 Gemini Semantic Experiment Runner")
    parser.add_argument(
        "--mode",
        choices=["deterministic", "gemini-rerank", "gemini-intent", "gemini-intent-rerank", "gemini-selective"],
        default="deterministic",
        help="Evaluation decision mode"
    )
    parser.add_argument("--top-k", type=int, default=10, help="Candidate pool size (5, 8, 10, 15)")
    parser.add_argument("--dataset", choices=["robustness", "heldout", "all"], default="all", help="Dataset to evaluate")
    parser.add_argument("--output", type=str, default="", help="Optional JSON output file path")
    args = parser.parse_args()

    engine = TroubleshootingEngine()
    reasoner = GeminiSemanticReasoner(mode=args.mode)

    print("=" * 80)
    print(f"PHASE 20 EXPERIMENT RUNNER — MODE: {args.mode.upper()} (Top-K = {args.top_k})")
    print(f"Gemini Reasoner Enabled: {reasoner.is_enabled()} (Model: {reasoner.model_name})")
    print("=" * 80)

    results = {}

    if args.dataset in ("robustness", "all"):
        print("\nEvaluating Robustness Dataset (164 cases)...")
        rob_res = run_benchmark_on_dataset(ROBUSTNESS_DATASET, engine, reasoner, mode=args.mode, top_k=args.top_k, is_heldout=False)
        results["robustness"] = rob_res
        print(f"  URI Accuracy:       {rob_res['uri_matches']}/{rob_res['total_cases']} ({rob_res['uri_accuracy']}%) [Baseline: 53.05%]")
        print(f"  Action Accuracy:    {rob_res['action_matches']}/{rob_res['total_cases']} ({rob_res['action_accuracy']}%) [Baseline: 53.66%]")
        print(f"  Polarity Accuracy:  {rob_res['polarity_matches']}/{rob_res['polarity_total']} ({rob_res['polarity_accuracy']}%) [Baseline: 86.90%]")
        print(f"  Hardware Safety:    {rob_res['hardware_matches']}/{rob_res['hardware_total']} ({rob_res['hardware_safety']}%)")
        print(f"  Latency (P50/P95):  {rob_res['p50_latency_ms']} ms / {rob_res['p95_latency_ms']} ms")
        if args.mode != "deterministic":
            print(f"  Gemini Invocations: {rob_res['gemini_calls']} (Corrections: {rob_res['gemini_corrections']} | True: {rob_res['gemini_true_corrections']} | False: {rob_res['gemini_false_corrections']})")

    if args.dataset in ("heldout", "all"):
        print("\nEvaluating Held-Out Generalization Dataset (30 cases)...")
        held_res = run_benchmark_on_dataset(HELDOUT_DATASET, engine, reasoner, mode=args.mode, top_k=args.top_k, is_heldout=True)
        results["heldout"] = held_res
        print(f"  Action Accuracy:    {held_res['action_matches']}/{held_res['total_cases']} ({held_res['action_accuracy']}%) [Baseline: 83.33%]")
        print(f"  Hardware Safety:    {held_res['hardware_matches']}/{held_res['hardware_total']} ({held_res['hardware_safety']}%)")
        print(f"  Latency (Avg/P95):  {held_res['avg_latency_ms']} ms / {held_res['p95_latency_ms']} ms")

    print("\n" + "=" * 80)
    print("EXPERIMENT EXECUTION COMPLETE")
    print("=" * 80)

    out_file = args.output or os.path.join(PROJECT_ROOT, "scratch", f"experiment_{args.mode}_top{args.top_k}.json")
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"[Saved] Full experiment results saved to: {out_file}")


if __name__ == "__main__":
    main()
