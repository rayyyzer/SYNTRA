"""Audit script for Phase 20.1: Detailed classification of action failures and targeted dataset creation."""

import os
import sys
import json
import time

PROJECT_ROOT = r"D:\Samsung_Hackathon"
THEME2_DIR = os.path.join(PROJECT_ROOT, "Theme02_Engine")
STUDENT_KIT_DIR = os.path.join(PROJECT_ROOT, "participant-kit-all-themes", "participant-kit", "Theme02_Input_Kit", "student_kit")
ROBUSTNESS_DATASET = os.path.join(PROJECT_ROOT, "tests", "theme2", "robustness_dataset.jsonl")

if THEME2_DIR not in sys.path:
    sys.path.insert(0, THEME2_DIR)
if STUDENT_KIT_DIR not in sys.path:
    sys.path.insert(0, STUDENT_KIT_DIR)

from engine import TroubleshootingEngine
from safety_router import is_unsupported_hardware

def main():
    engine = TroubleshootingEngine()

    with open(os.path.join(STUDENT_KIT_DIR, "deeplinks.json"), "r", encoding="utf-8") as f:
        catalog_data = json.load(f)
    catalog_entries = catalog_data.get("deeplinks", [])
    catalog_actions = {e.get("message", "").strip().lower() for e in catalog_entries if e.get("message")}
    catalog_uris = {e.get("deeplink") for e in catalog_entries if e.get("deeplink")}

    with open(ROBUSTNESS_DATASET, "r", encoding="utf-8") as f:
        cases = [json.loads(line) for line in f if line.strip()]

    print(f"Total test cases: {len(cases)}")
    print(f"Total catalog unique actions: {len(catalog_actions)}")

    failures = []
    targeted_cases = []

    classification_counts = {
        "SYNTHETIC_EXPECTATION": 0,
        "RETRIEVAL_MISS": 0,
        "CORRECT_CANDIDATE_AVAILABLE": 0,
        "CATALOG_CLONE": 0,
        "POLARITY_CONFLICT": 0,
        "SIIS_CONFLICT": 0,
        "OTHER": 0,
    }

    top_availability_counts = {
        "in_top5": 0,
        "in_top8": 0,
        "in_top10": 0,
        "in_top15": 0,
        "not_in_top15": 0,
    }

    action_matches_count = 0
    uri_matches_count = 0

    for idx, c in enumerate(cases):
        cid = c["id"]
        c_class = c.get("class", "")
        q = c["query"]
        s_resp = c.get("siis_response") or {}
        siis_title = str(s_resp.get("title", "")) if s_resp.get("title") else ""
        siis_content = str(s_resp.get("content", "")) if s_resp.get("content") else ""
        exp_uri = c.get("expected_uri")
        exp_act = (c.get("expected_action") or "").strip().lower()
        exp_pol = c.get("expected_polarity", "neutral")

        # Live engine troubleshoot call
        resp = engine.troubleshoot(q, s_resp)
        act_0 = resp["contexts"][0]["actions"][0]
        gen_act = act_0.get("actionName", "").strip().lower()
        sg_0 = act_0.get("stepGroups", [{}])[0]
        gen_uri = (sg_0.get("actionableDeeplink") or {}).get("deeplink")

        is_act_match = (gen_act == exp_act) if exp_act else False
        is_uri_match = (gen_uri == exp_uri) if exp_uri is not None else (gen_uri in (None, "bixby://dummy_positive"))

        if is_act_match:
            action_matches_count += 1
        if is_uri_match:
            uri_matches_count += 1

        if is_act_match:
            continue

        # This is an action failure
        # 1. Retrieve candidates up to Top-25 to inspect ranks
        top_candidates = engine.retriever.retrieve(
            query=q,
            top_k=25,
            siis_title=siis_title,
            siis_content=siis_content
        )

        in_catalog = (exp_act in catalog_actions)

        # Check ranks of expected action
        exp_rank = None
        exp_cand = None
        for r_idx, cand in enumerate(top_candidates, start=1):
            cand_act = (cand.get("message") or "").strip().lower()
            if cand_act == exp_act:
                exp_rank = r_idx
                exp_cand = cand
                break

        in_top5 = (exp_rank is not None and exp_rank <= 5)
        in_top8 = (exp_rank is not None and exp_rank <= 8)
        in_top10 = (exp_rank is not None and exp_rank <= 10)
        in_top15 = (exp_rank is not None and exp_rank <= 15)

        if in_top5:
            top_availability_counts["in_top5"] += 1
        elif in_top8:
            top_availability_counts["in_top8"] += 1
        elif in_top10:
            top_availability_counts["in_top10"] += 1
        elif in_top15:
            top_availability_counts["in_top15"] += 1
        else:
            top_availability_counts["not_in_top15"] += 1

        # Check deterministic choice from top_10
        det_adj = engine.adjudicator.adjudicate(
            query=q,
            siis_title=siis_title,
            siis_content=siis_content,
            candidates=top_candidates[:10]
        )
        det_chosen = det_adj.get("selected_candidate") or (top_candidates[0] if top_candidates else None)
        det_act = (det_chosen.get("message") or "").strip().lower() if det_chosen else ""
        det_uri = det_chosen.get("deeplink") if det_chosen else None

        # Determine Classification
        if not in_catalog:
            cat = "SYNTHETIC_EXPECTATION"
            reason = f"Expected action '{exp_act}' is synthetic / does not exist in 578-entry catalog."
        elif exp_rank is None:
            cat = "RETRIEVAL_MISS"
            reason = f"Expected action '{exp_act}' not retrieved in Top-25."
        elif exp_rank > 15:
            cat = "RETRIEVAL_MISS"
            reason = f"Expected action '{exp_act}' retrieved at rank #{exp_rank} (beyond Top-15)."
        else:
            # Expected action is in Top-15
            clone_entries = [e for e in catalog_entries if e.get("message", "").strip().lower() == exp_act]
            exp_pol_lower = exp_pol.lower()
            det_pol = (det_chosen.get("polarity") or "neutral").lower() if det_chosen else "neutral"

            if exp_pol_lower in ("enable", "disable") and det_pol != exp_pol_lower and ("enable" in det_act or "disable" in det_act):
                cat = "POLARITY_CONFLICT"
                reason = f"Polarity conflict: expected '{exp_pol}', deterministic selected '{det_act}' with polarity '{det_pol}'."
            elif is_uri_match and not is_act_match:
                cat = "CATALOG_CLONE"
                reason = f"URI match achieved ({gen_uri}) but action name differs ({gen_act} vs {exp_act})."
            elif len(clone_entries) > 1 and exp_uri in [e.get("deeplink") for e in clone_entries]:
                cat = "CATALOG_CLONE"
                reason = f"Catalog has {len(clone_entries)} clones for action '{exp_act}' with differing descriptions/URIs."
            elif siis_content and (siis_title.lower() in gen_act or any(word in gen_act for word in siis_title.lower().split() if len(word) > 4)):
                cat = "SIIS_CONFLICT"
                reason = f"Deterministic adjudication favored SIIS guide guidance ('{siis_title}') over standalone query intent."
            elif in_top10:
                cat = "CORRECT_CANDIDATE_AVAILABLE"
                reason = f"Correct action is present in candidate pool at rank #{exp_rank}, but deterministic selection chose '{det_act}'."
            else:
                cat = "OTHER"
                reason = f"Correct action in Top-15 at rank #{exp_rank}, but outside Top-10."

        classification_counts[cat] += 1

        failure_record = {
            "id": cid,
            "class": c_class,
            "query": q,
            "siis_title": siis_title,
            "siis_content": siis_content[:300],
            "expected_action": exp_act,
            "expected_uri": exp_uri,
            "expected_polarity": exp_pol,
            "generated_action": gen_act,
            "generated_uri": gen_uri,
            "in_catalog": in_catalog,
            "expected_rank": exp_rank,
            "in_top5": in_top5,
            "in_top8": in_top8,
            "in_top10": in_top10,
            "in_top15": in_top15,
            "deterministic_selected_action": det_act,
            "deterministic_selected_uri": det_uri,
            "classification": cat,
            "reason": reason,
            "top10_candidates": [
                {
                    "rank": r,
                    "id": c.get("id"),
                    "action": c.get("message"),
                    "uri": c.get("deeplink"),
                    "score": round(c.get("score", 0.0), 4),
                    "description": c.get("description", "")
                }
                for r, c in enumerate(top_candidates[:10], start=1)
            ]
        }
        failures.append(failure_record)

        # Build Targeted Gemini Population:
        # Criteria:
        # 1. Expected action is catalog-grounded (in_catalog == True)
        # 2. Expected candidate exists in the candidate pool (in_top15 == True)
        # 3. Deterministic ranking selected a different candidate (det_act != exp_act)
        if in_catalog and in_top15 and det_act != exp_act:
            targeted_cases.append({
                "id": cid,
                "class": c_class,
                "query": q,
                "siis": s_resp,
                "expected_action": exp_act,
                "expected_uri": exp_uri,
                "expected_polarity": exp_pol,
                "expected_rank": exp_rank,
                "expected_candidate_in_top5": in_top5,
                "expected_candidate_in_top8": in_top8,
                "expected_candidate_in_top10": in_top10,
                "expected_candidate_in_top15": in_top15,
                "deterministic_selected_action": det_act,
                "deterministic_selected_uri": det_uri,
                "deterministic_confidence": round(det_adj.get("confidence", 0.0), 4),
                "deterministic_margin": round(det_adj.get("margin", 0.0), 4),
                "candidates_top15": [
                    {
                        "candidate_id": f"candidate_{r}",
                        "catalog_id": c.get("id"),
                        "rank": r,
                        "action": c.get("message"),
                        "description": c.get("description", ""),
                        "score": round(c.get("score", 0.0), 4),
                        "polarity": c.get("polarity", "neutral"),
                        "is_expected": (c.get("message", "").strip().lower() == exp_act)
                    }
                    for r, c in enumerate(top_candidates[:15], start=1)
                ]
            })

    print(f"\nLive Execution Results:")
    print(f"Action Matches: {action_matches_count}/{len(cases)} ({action_matches_count/len(cases)*100:.2f}%)")
    print(f"URI Matches:    {uri_matches_count}/{len(cases)} ({uri_matches_count/len(cases)*100:.2f}%)")
    print(f"Action Failures: {len(failures)}")
    print(f"\nClassification Breakdown:")
    for k, v in classification_counts.items():
        print(f"  {k:30s}: {v}")
    print(f"\nTop Availability Breakdown (among 42 catalog failures):")
    for k, v in top_availability_counts.items():
        print(f"  {k:30s}: {v}")
    print(f"\nTargeted Dataset Size: {len(targeted_cases)} cases")

    # Save outputs
    out_class = os.path.join(PROJECT_ROOT, "scratch", "phase20_1_action_failure_classification.json")
    with open(out_class, "w", encoding="utf-8") as f:
        json.dump({
            "total_cases": len(cases),
            "action_matches": action_matches_count,
            "action_failures": len(failures),
            "classification_counts": classification_counts,
            "top_availability_counts": top_availability_counts,
            "targeted_population_count": len(targeted_cases),
            "failures": failures
        }, f, indent=2)
    print(f"[Saved] Classification report saved to: {out_class}")

    out_targeted = os.path.join(PROJECT_ROOT, "scratch", "targeted_gemini_dataset.json")
    with open(out_targeted, "w", encoding="utf-8") as f:
        json.dump(targeted_cases, f, indent=2)
    print(f"[Saved] Targeted dataset saved to: {out_targeted}")

if __name__ == "__main__":
    main()
