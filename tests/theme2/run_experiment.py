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
            elif mode == "gemini-targeted":
                if reasoner.should_trigger_targeted_gemini(q, candidates, det_best):
                    should_rerank = True

            if should_rerank:
                gemini_calls += 1
                if mode == "gemini-targeted":
                    res = reasoner.select_targeted_candidate(
                        query=q,
                        siis_title=siis_title,
                        siis_content=siis_content,
                        candidate_pool=candidates,
                        deterministic_draft=det_best
                    )
                else:
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


def run_targeted_experiment(
    targeted_dataset_path: str,
    engine: TroubleshootingEngine,
    reasoner: GeminiSemanticReasoner,
    top_k: int = 10,
) -> Dict[str, Any]:
    with open(targeted_dataset_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    total_cases = len(cases)
    available_in_k = 0
    deterministic_matches = 0
    gemini_matches = 0

    true_corrections = 0
    false_corrections = 0
    no_change = 0
    ambiguous_count = 0
    invalid_fallback = 0

    latencies = []
    case_evaluations = []

    for c in cases:
        cid = c["id"]
        q = c["query"]
        s_resp = c.get("siis") or {}
        siis_title = str(s_resp.get("title", "")) if s_resp.get("title") else ""
        siis_content = str(s_resp.get("content", "")) if s_resp.get("content") else ""
        exp_act = (c.get("expected_action") or "").strip().lower()
        exp_uri = c.get("expected_uri")

        t0 = time.perf_counter()

        # Retrieve candidates sliced to top_k
        candidates = engine.retriever.retrieve(
            query=q,
            top_k=top_k,
            siis_title=siis_title,
            siis_content=siis_content
        )

        is_available = any((cand.get("message") or "").strip().lower() == exp_act for cand in candidates)
        if is_available:
            available_in_k += 1

        det_adj = engine.adjudicator.adjudicate(
            query=q,
            siis_title=siis_title,
            siis_content=siis_content,
            candidates=candidates
        )
        det_best = det_adj.get("selected_candidate") or (candidates[0] if candidates else None)
        det_act = (det_best.get("message") or "").strip().lower() if det_best else ""
        det_is_match = (det_act == exp_act)
        if det_is_match:
            deterministic_matches += 1

        res = reasoner.select_targeted_candidate(
            query=q,
            siis_title=siis_title,
            siis_content=siis_content,
            candidate_pool=candidates,
            deterministic_draft=det_best
        )

        # Pace live requests to respect 15 req/min quota
        if res.source not in ("gemini_targeted_cache", "deterministic_fallback"):
            time.sleep(4.1)

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        latencies.append(elapsed_ms)

        cand_map = {c.get("id"): c for c in candidates if c.get("id")}
        chosen = None
        if res.decision == "SELECT" and res.selected_candidate_id in cand_map:
            chosen = cand_map[res.selected_candidate_id]

        final_best = chosen or det_best
        final_act = (final_best.get("message") or "").strip().lower() if final_best else ""
        final_is_match = (final_act == exp_act)

        if final_is_match:
            gemini_matches += 1

        if res.decision == "AMBIGUOUS":
            ambiguous_count += 1
            transition = "AMBIGUOUS"
        elif res.decision != "SELECT" or not chosen:
            invalid_fallback += 1
            transition = "INVALID"
        elif chosen.get("id") == (det_best.get("id") if det_best else None):
            no_change += 1
            transition = "NO_CHANGE"
        elif final_is_match and not det_is_match:
            true_corrections += 1
            transition = "TRUE_CORRECTION"
        elif det_is_match and not final_is_match:
            false_corrections += 1
            transition = "FALSE_CORRECTION"
        else:
            transition = "NO_CHANGE"

        case_evaluations.append({
            "id": cid,
            "query": q,
            "expected_action": exp_act,
            "expected_candidate_in_top_k": is_available,
            "deterministic_action": det_act,
            "deterministic_match": det_is_match,
            "gemini_action": final_act,
            "gemini_decision": res.decision,
            "gemini_match": final_is_match,
            "transition": transition,
            "reason_code": res.reason_code,
            "explanation": res.explanation,
            "latency_ms": round(res.latency_ms, 2)
        })

    avg_lat = sum(latencies) / len(latencies) if latencies else 0.0
    p95_lat = sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0.0

    return {
        "dataset": "targeted_gemini_dataset.json",
        "top_k": top_k,
        "total_target_cases": total_cases,
        "expected_candidate_available": available_in_k,
        "availability_pct": round(available_in_k / total_cases * 100.0, 2),
        "deterministic_action_matches": deterministic_matches,
        "deterministic_accuracy": round(deterministic_matches / total_cases * 100.0, 2),
        "gemini_action_matches": gemini_matches,
        "gemini_accuracy": round(gemini_matches / total_cases * 100.0, 2),
        "true_corrections": true_corrections,
        "false_corrections": false_corrections,
        "no_change": no_change,
        "ambiguous": ambiguous_count,
        "invalid_fallback": invalid_fallback,
        "avg_latency_ms": round(avg_lat, 2),
        "p95_latency_ms": round(p95_lat, 2),
        "case_evaluations": case_evaluations
    }


def main():
    parser = argparse.ArgumentParser(description="Phase 20 Gemini Semantic Experiment Runner")
    parser.add_argument(
        "--mode",
        choices=["deterministic", "gemini-rerank", "gemini-intent", "gemini-intent-rerank", "gemini-selective", "gemini-targeted"],
        default="deterministic",
        help="Evaluation decision mode"
    )
    parser.add_argument("--top-k", type=int, default=10, help="Candidate pool size (5, 8, 10, 15)")
    parser.add_argument("--dataset", choices=["robustness", "heldout", "targeted", "all"], default="all", help="Dataset to evaluate")
    parser.add_argument("--output", type=str, default="", help="Optional JSON output file path")
    args = parser.parse_args()

    engine = TroubleshootingEngine()
    reasoner = GeminiSemanticReasoner(mode=args.mode)

    print("=" * 80)
    print(f"PHASE 20.1 EXPERIMENT RUNNER — MODE: {args.mode.upper()} (Top-K = {args.top_k})")
    print(f"Gemini Reasoner Enabled: {reasoner.is_enabled()} (Model: {reasoner.model_name})")
    print("=" * 80)

    results = {}

    if args.dataset in ("targeted", "all"):
        targeted_path = os.path.join(PROJECT_ROOT, "scratch", "targeted_gemini_dataset.json")
        if os.path.exists(targeted_path):
            print(f"\nEvaluating Targeted Candidate Population (Top-K = {args.top_k})...")
            tgt_res = run_targeted_experiment(targeted_path, engine, reasoner, top_k=args.top_k)
            results["targeted"] = tgt_res
            print(f"  Target Cases:             {tgt_res['total_target_cases']}")
            print(f"  Expected Available @ K:   {tgt_res['expected_candidate_available']}/{tgt_res['total_target_cases']} ({tgt_res['availability_pct']}%)")
            print(f"  Deterministic Matches:    {tgt_res['deterministic_action_matches']}/{tgt_res['total_target_cases']} ({tgt_res['deterministic_accuracy']}%)")
            print(f"  Gemini Matches:           {tgt_res['gemini_action_matches']}/{tgt_res['total_target_cases']} ({tgt_res['gemini_accuracy']}%)")
            print(f"  True Corrections:         {tgt_res['true_corrections']}")
            print(f"  False Corrections:        {tgt_res['false_corrections']}")
            print(f"  No Change:                {tgt_res['no_change']}")
            print(f"  Ambiguous / Fallbacks:    {tgt_res['ambiguous'] + tgt_res['invalid_fallback']}")
            print(f"  Latency (Avg/P95):        {tgt_res['avg_latency_ms']} ms / {tgt_res['p95_latency_ms']} ms")

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
