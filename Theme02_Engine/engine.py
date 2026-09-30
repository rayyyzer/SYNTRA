"""Troubleshooting Engine: Core logic transforming query + SIIS knowledge into schema-valid ContextDeeplinkResponse."""

from __future__ import annotations
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional

# Add student_kit to sys.path to import official Pydantic models
CANDIDATE_KIT_DIRS = [
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "student_kit")),
    os.path.abspath(os.path.join(os.path.dirname(__file__), "data", "student_kit")),
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "participant-kit-all-themes", "participant-kit", "Theme02_Input_Kit", "student_kit")),
]
STUDENT_KIT_DIR = next((d for d in CANDIDATE_KIT_DIRS if os.path.exists(d)), CANDIDATE_KIT_DIRS[0])
if STUDENT_KIT_DIR not in sys.path:
    sys.path.insert(0, STUDENT_KIT_DIR)

from schema import (
    ContextDeeplinkResponse,
    Goal,
    Action,
    StepGroup,
    Deeplink,
    ValidationDeepLink,
    actionCategory,
    ResultTypes,
    Condition
)

from normalizer import sanitize_text, format_goal, format_title, format_action_description
from cache import QueryCache
from safety_router import is_unsupported_hardware, get_hardware_repair_action
from retrieval.hybrid_retriever import HybridRetriever
from retrieval.polarity import detect_query_polarity
from adjudicator import CandidateAdjudicator
from gemini_verifier import GeminiSemanticVerifier, GeminiVerificationResult
from gemini_reasoner import GeminiSemanticReasoner, GeminiReasonerResult


class TroubleshootingEngine:
    def __init__(self):
        self.retriever = HybridRetriever()
        self.adjudicator = CandidateAdjudicator(dense=self.retriever.dense)
        self.verifier = GeminiSemanticVerifier()
        self.reasoner = GeminiSemanticReasoner()
        self.cache = QueryCache()

    def troubleshoot(
        self,
        query: str,
        siis_response: Optional[Dict[str, Any]] = None,
        siis_title: Optional[str] = None,
        siis_content: Optional[str] = None,
        _debug_trace: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        # 1. Extract and sanitize raw text from SIIS (with strict type safety)
        if siis_response is None:
            siis_response = {}
        elif hasattr(siis_response, "model_dump"):
            siis_response = siis_response.model_dump()
        elif not isinstance(siis_response, dict):
            siis_response = {}

        raw_title = siis_title if siis_title is not None else siis_response.get("title", "Device Issue")
        raw_content = siis_content if siis_content is not None else siis_response.get("content", "")

        if not isinstance(raw_title, str):
            raw_title = str(raw_title) if raw_title is not None else "Device Issue"
        if not isinstance(raw_content, str):
            raw_content = str(raw_content) if raw_content is not None else ""

        siis_title = sanitize_text(raw_title)
        siis_content = sanitize_text(raw_content)

        # 2. Check context-isolated cache (<0.05ms)
        cached = self.cache.get(query, siis_title=siis_title, siis_content=siis_content)
        if cached:
            if _debug_trace is not None:
                _debug_trace["cached"] = True
                _debug_trace["cached_response"] = cached
            return cached

        # 3. Check Safety & Hardware Router for physical damage or hazardous operations
        if is_unsupported_hardware(query, siis_content):
            if _debug_trace is not None:
                _debug_trace["hardware_triggered"] = True
            hw_data = get_hardware_repair_action()
            action_hw = Action(
                actionName=hw_data["actionName"],
                description=format_action_description(hw_data["actionName"], "authorized customer repair center"),
                stepGroups=[
                    StepGroup(
                        steps=hw_data["stepGroups"][0]["steps"],
                        actionableDeeplink=None,
                        validationDeeplink=None
                    )
                ],
                category=actionCategory.manual
            )
            goal = Goal(
                goal=format_goal(siis_title or "Hardware Damage", is_config=False),
                title=format_title(siis_title or "Device Hardware Repair"),
                actions=[action_hw],
                score=0.95
            )
            resp_obj = ContextDeeplinkResponse(contexts=[goal])
            result_dict = resp_obj.model_dump()
            self.cache.put(query, result_dict, siis_title=siis_title, siis_content=siis_content)
            return result_dict

        # 4. Extract action steps from SIIS text (grounded, do not hallucinate)
        raw_sentences = [
            sanitize_text(s.strip())
            for s in re.split(r"(?<=[.!?])\s+|\n+", siis_content)
            if len(s.strip()) > 10
        ]
        if not raw_sentences:
            raw_sentences = [
                "Navigate to and open Settings on your Galaxy device.",
                "Locate the setting and configure your preferences.",
                "Restart your device if changes do not take effect immediately."
            ]

        # Partition steps into automated settings actions vs manual service actions
        auto_steps: List[str] = []
        manual_steps: List[str] = []

        for sent in raw_sentences:
            low_s = sent.lower()
            if any(k in low_s for k in ("service center", "contact support", "repair", "technician", "warranty", "replacement")):
                manual_steps.append(sent)
            else:
                auto_steps.append(sent)

        if not auto_steps:
            auto_steps = [raw_sentences[0]]
            manual_steps = raw_sentences[1:]

        # 5. SIIS-Grounded Hybrid Retrieval (<25ms) + Candidate Adjudication + Gemini Verification
        t_ret_0 = time.perf_counter()
        candidates = self.retriever.retrieve(
            query=query,
            top_k=10,
            siis_title=siis_title,
            siis_content=siis_content
        )
        retrieval_ms = (time.perf_counter() - t_ret_0) * 1000.0

        verifier_res: Optional[GeminiVerificationResult] = None
        adj: Optional[Dict[str, Any]] = None
        selection_ms: float = 0.0

        if candidates and candidates[0]["score"] >= 0.20:
            t_sel_0 = time.perf_counter()
            adj = self.adjudicator.adjudicate(
                query=query,
                siis_title=siis_title,
                siis_content=siis_content,
                candidates=candidates
            )
            selection_ms = (time.perf_counter() - t_sel_0) * 1000.0
            best = adj.get("selected_candidate") or candidates[0]
            det_best = best

            # Phase 20.1: Targeted Gemini Semantic Candidate Selection & Clone Disambiguation
            # Operates strictly over verified candidate pool when ambiguity signals are detected
            targeted_res: Optional[GeminiReasonerResult] = None
            if self.reasoner.is_enabled() and self.reasoner.should_trigger_targeted_gemini(query, candidates[:5], adj):
                targeted_res = self.reasoner.select_targeted_candidate(
                    query=query,
                    siis_title=siis_title,
                    siis_content=siis_content,
                    candidate_pool=candidates[:5],
                    deterministic_draft=det_best
                )
                if targeted_res and targeted_res.decision == "SELECT" and targeted_res.selected_candidate_id:
                    cand_map = {c["id"]: c for c in candidates if "id" in c}
                    if targeted_res.selected_candidate_id in cand_map:
                        best = cand_map[targeted_res.selected_candidate_id]

            # Phase 17: Native Gemini Final Semantic Verification Layer
            # Runs as secondary verification if targeted reasoner did not run
            if targeted_res is None and self.verifier.should_verify(adj, candidates):
                verifier_res = self.verifier.verify(
                    query=query,
                    siis_title=siis_title,
                    siis_content=siis_content,
                    candidate_pool=candidates,
                    deterministic_draft=best
                )
                if verifier_res and verifier_res.decision == "CORRECT" and verifier_res.selected_candidate_id:
                    cand_map = {c["id"]: c for c in candidates if "id" in c}
                    if verifier_res.selected_candidate_id in cand_map:
                        best = cand_map[verifier_res.selected_candidate_id]

            act_dl = best["deeplink"]
            act1_name = best.get("message") or "Configure Device Settings"
            act_desc_hint = best.get("description") or act1_name
            val_dict = best.get("validation")
        else:
            # DL-DUMMY Fallback as mandated by Samsung FAQ lines 255, 275-277
            best = None
            act_dl = "bixby://dummy_positive"
            act1_name = "Open Relevant Settings Screen"
            act_desc_hint = "Opens the relevant device Settings screen"
            val_dict = None

        # Construct Actionable Deeplink (Verbatim catalog URI only - never LLM generated)
        actionable_dl = Deeplink(
            deeplink=act_dl,
            description=sanitize_text(act_desc_hint),
            message=sanitize_text(act1_name),
            originalType=best.get("originalType", "onClickURL") if best else "onClickURL"
        )

        # Construct Validation Deeplink if catalog entry defines one
        validation_dl = None
        if val_dict and isinstance(val_dict, dict) and "deeplink" in val_dict:
            rt_val = val_dict.get("resultType", "boolean")
            try:
                res_type = ResultTypes(rt_val)
            except (ValueError, KeyError):
                res_type = ResultTypes.boolean

            cond_val = val_dict.get("condition", "equal")
            try:
                cond = Condition(cond_val)
            except (ValueError, KeyError):
                cond = Condition.equal

            validation_dl = ValidationDeepLink(
                deeplink=val_dict["deeplink"],
                key=val_dict.get("key", "Setting Status"),
                resultType=res_type,
                condition=cond,
                value=str(val_dict.get("value", "True"))
            )

        # 6. Build Action 1 (Auto action with Deeplink)
        act1_desc = format_action_description(act1_name, act_desc_hint)
        step_group_1 = StepGroup(
            steps=auto_steps[:4],
            actionableDeeplink=actionable_dl,
            validationDeeplink=validation_dl
        )
        action_1 = Action(
            actionName=act1_name,
            description=act1_desc,
            stepGroups=[step_group_1],
            category=actionCategory.auto
        )

        actions = [action_1]

        # 7. Build Action 2 (Manual / Service action if applicable)
        if manual_steps:
            act2_name = "Schedule Device Repair Service"
            act2_desc = format_action_description(act2_name, manual_steps[0])
            step_group_2 = StepGroup(
                steps=manual_steps[:3],
                actionableDeeplink=None,
                validationDeeplink=None
            )
            action_2 = Action(
                actionName=act2_name,
                description=act2_desc,
                stepGroups=[step_group_2],
                category=actionCategory.manual
            )
            actions.append(action_2)

        # 8. Construct Goal and ContextDeeplinkResponse
        goal_text = format_goal(siis_title or act1_name)
        title_text = format_title(siis_title or act1_name)

        goal = Goal(
            goal=goal_text,
            title=title_text,
            actions=actions,
            score=0.95
        )

        response_obj = ContextDeeplinkResponse(contexts=[goal])
        result_dict = response_obj.model_dump()

        # Store in context-isolated cache
        self.cache.put(query, result_dict, siis_title=siis_title, siis_content=siis_content)

        if _debug_trace is not None:
            _debug_trace["candidates"] = candidates
            _debug_trace["adjudication"] = adj
            _debug_trace["det_best"] = det_best
            _debug_trace["targeted_res"] = targeted_res
            _debug_trace["verifier_res"] = verifier_res
            _debug_trace["best"] = best
            _debug_trace["retrieval_ms"] = retrieval_ms
            _debug_trace["selection_ms"] = selection_ms

        return result_dict

    def troubleshoot_debug(self, query: str, siis_response: Dict[str, Any]) -> Dict[str, Any]:
        """Development-only debug execution returning full diagnostic trace + official response."""
        t_total_0 = time.perf_counter()

        # 1. SIIS Extraction & Sanitization
        raw_t = (siis_response or {}).get("title", "Device Issue")
        raw_c = (siis_response or {}).get("content", "")
        if not isinstance(raw_t, str):
            raw_t = str(raw_t) if raw_t is not None else "Device Issue"
        if not isinstance(raw_c, str):
            raw_c = str(raw_c) if raw_c is not None else ""
        siis_title = sanitize_text(raw_t)
        siis_content = sanitize_text(raw_c)
        siis_digest = self.cache._compute_siis_digest(siis_title, siis_content)

        # 2. Polarity Analysis
        q_pol = detect_query_polarity(query)
        intent_sig = self.cache._extract_intent_signature(query)
        polarity_info = {
            "detected": q_pol.value.upper(),
            "detected_polarity": q_pol.value.upper(),
            "signature": intent_sig,
            "details": f"Query classified under '{q_pol.value.upper()}' polarity with intent signature '{intent_sig}'."
        }

        # 3. Cache Inspection
        t_cache_0 = time.perf_counter()
        norm_q = self.cache._normalize(query)
        exact_key = f"{norm_q}#{siis_digest}"
        sig_key = f"{intent_sig}#{siis_digest}"
        cache_status = "MISS"
        cache_tier = "- (Cache Miss)"

        if exact_key in self.cache.exact_cache:
            cache_status = "HIT"
            cache_tier = "Tier 1: Exact Normalized Query Hash (<0.01ms)"
        elif intent_sig and sig_key in self.cache.intent_cache:
            cache_status = "HIT"
            cache_tier = "Tier 2: Polarity-Safe Intent Signature (<0.03ms)"
        else:
            cached_check = self.cache.get(query, siis_title=siis_title, siis_content=siis_content)
            if cached_check is not None:
                cache_status = "HIT"
                cache_tier = "Tier 3: Token Overlap Fuzzy Match with Polarity Guard (<0.05ms)"

        t_cache_1 = time.perf_counter()
        cache_latency_ms = (t_cache_1 - t_cache_0) * 1000.0

        cache_info = {
            "status": cache_status,
            "tier": cache_tier,
            "latency_ms": round(cache_latency_ms, 3),
            "details": f"Cache lookup evaluated with status {cache_status}."
        }

        # 4. Hardware Safety Check
        hw_triggered = is_unsupported_hardware(query, siis_content)
        safety_info = {
            "hardware_triggered": hw_triggered,
            "safety_action": "Schedule Device Repair Service" if hw_triggered else None,
            "triage_reason": "Physical crack, liquid exposure, or component failure detected" if hw_triggered else "Standard settings troubleshooting"
        }

        # 5. Run Execution via troubleshoot with debug trace
        trace: Dict[str, Any] = {}
        official_response = self.troubleshoot(
            query,
            siis_response,
            siis_title=siis_title,
            siis_content=siis_content,
            _debug_trace=trace
        )

        candidates = trace.get("candidates")
        if candidates is None and not hw_triggered:
            candidates = self.retriever.retrieve(
                query=query,
                top_k=5,
                siis_title=siis_title,
                siis_content=siis_content
            )
        elif candidates is None:
            candidates = []

        retrieval_latency_ms = trace.get("retrieval_ms", 0.0)

        det_best = trace.get("det_best")
        targeted_res: Optional[GeminiReasonerResult] = trace.get("targeted_res")
        verifier_res: Optional[GeminiVerificationResult] = trace.get("verifier_res")
        best = trace.get("best")

        formatted_cands = []
        for idx, c in enumerate(candidates, start=1):
            c_int_id = f"candidate_{idx}"
            is_det = bool(det_best and c.get("id") == det_best.get("id"))
            is_gem = bool(targeted_res and c.get("id") == targeted_res.selected_candidate_id)
            is_fin = bool(best and c.get("id") == best.get("id"))
            formatted_cands.append({
                "rank": c.get("rank", idx),
                "internal_id": c_int_id,
                "catalog_id": c.get("id"),
                "action": c.get("message"),
                "description": c.get("description"),
                "uri": c.get("deeplink"),
                "score": c.get("score"),
                "bm25_score": c.get("bm25_score", 0.0),
                "dense_score": c.get("dense_score", 0.0),
                "polarity": c.get("polarity"),
                "polarity_alignment": c.get("polarity_adjustment", 0.0),
                "is_deterministic_winner": is_det,
                "is_gemini_winner": is_gem,
                "is_final_winner": is_fin,
            })

        retrieval_info = {
            "method": "Hybrid BM25 + Dense (all-MiniLM-L6-v2) + Polarity Filter",
            "latency_ms": round(retrieval_latency_ms, 3),
            "candidate_count": len(candidates),
            "candidates": formatted_cands
        }

        # 6. Selection & Gemini Verification Info
        adj = trace.get("adjudication")
        if adj is None and candidates and not hw_triggered:
            adj = self.adjudicator.adjudicate(
                query=query,
                siis_title=siis_title,
                siis_content=siis_content,
                candidates=candidates
            )

        if det_best is None and adj:
            det_best = adj.get("selected_candidate") or (candidates[0] if candidates else None)

        if best is None:
            best = det_best

        if hw_triggered:
            selection_info = {
                "method": "Hardware Safety Router",
                "selected_rank": None,
                "selected_catalog_id": None,
                "confidence": 1.0,
                "latency_ms": 0.01
            }
            det_choice = {
                "catalog_id": None,
                "action": "Schedule Device Repair Service",
                "uri": None,
                "score": 1.0,
                "confidence": 1.0
            }
            targeted_info = {
                "enabled": self.reasoner.is_enabled(),
                "mode": "gemini-targeted",
                "model": self.reasoner.model_name,
                "triggered": False,
                "trigger_reasons": ["Hardware Safety Intercept Triggered"],
                "decision": "SKIPPED",
                "selected_internal_id": None,
                "selected_catalog_id": None,
                "selected_action": None,
                "confidence": 1.0,
                "reason_code": "SAFETY_INTERCEPT",
                "explanation": "Hardware safety router intercepted query prior to candidate adjudication and LLM verification.",
                "correction_status": "SKIPPED",
                "is_override": False,
                "latency_ms": 0.0,
                "source": "hardware_safety"
            }
            gemini_info = {
                "enabled": self.verifier.is_enabled(),
                "mode": self.verifier.mode,
                "model": self.verifier.model_name,
                "decision": "SKIPPED",
                "selected_catalog_id": None,
                "confidence": 1.0,
                "reason_code": "SAFETY_INTERCEPT",
                "explanation": "Hardware safety router intercepted query prior to candidate adjudication and LLM verification.",
                "latency_ms": 0.0,
                "is_override": False
            }
            catalog_info = {
                "catalog_id": None,
                "action": "Schedule Device Repair Service",
                "uri": None,
                "valid": True,
                "original_type": "manual_action"
            }
        else:
            selected_catalog_id = best.get("id") if best else "DL-DUMMY"
            selected_rank = None
            for idx, c in enumerate(candidates, start=1):
                if best and c.get("id") == best.get("id"):
                    selected_rank = idx
                    break

            selection_info = {
                "method": "Gemini Targeted Selection (Phase 20.1)" if (targeted_res and targeted_res.decision == "SELECT") else (adj or {}).get("source", "deterministic_dense_adjudicator"),
                "selected_rank": selected_rank or 1,
                "selected_catalog_id": selected_catalog_id,
                "confidence": (targeted_res.confidence if (targeted_res and targeted_res.decision == "SELECT") else (adj or {}).get("confidence", 0.92)),
                "latency_ms": round(trace.get("selection_ms", 0.0), 3)
            }

            det_choice = {
                "catalog_id": det_best.get("id") if det_best else "DL-DUMMY",
                "action": det_best.get("message") if det_best else "Open Relevant Settings Screen",
                "uri": det_best.get("deeplink") if det_best else "bixby://dummy_positive",
                "score": round(det_best.get("score", 0.0), 4) if det_best else 0.0,
                "confidence": round((adj or {}).get("confidence", 0.90), 4) if adj else 0.90
            }

            # Phase 20.1 Targeted Gemini Diagnostics
            trigger_reasons = []
            conf = (adj or {}).get("confidence", 1.0)
            if conf < 0.40:
                trigger_reasons.append(f"Low deterministic confidence ({conf:.2f} < 0.40)")
            margin = (adj or {}).get("margin", 1.0)
            if margin < 0.08:
                trigger_reasons.append(f"Small score margin between Top-1 and Top-2 ({margin:.3f} < 0.08)")
            seen_acts = set()
            for c in candidates[:8]:
                act_msg = (c.get("message") or "").strip().lower()
                if act_msg in seen_acts:
                    trigger_reasons.append(f"Clone candidates detected in Top-8 (e.g. '{act_msg}')")
                    break
                seen_acts.add(act_msg)
            if len(candidates) >= 2:
                p1 = (candidates[0].get("polarity") or "neutral").lower()
                p2 = (candidates[1].get("polarity") or "neutral").lower()
                if (p1 == "enable" and p2 == "disable") or (p1 == "disable" and p2 == "enable"):
                    trigger_reasons.append(f"Opposing polarities in Top-2 candidates ({p1} vs {p2})")

            is_triggered = (targeted_res is not None)
            is_override = False
            corr_status = "UNTRIGGERED"
            sel_internal_id = None
            sel_cat_id = None
            sel_act = None

            if targeted_res:
                sel_cat_id = targeted_res.selected_candidate_id
                for idx, c in enumerate(candidates, start=1):
                    if c.get("id") == sel_cat_id:
                        sel_internal_id = f"candidate_{idx}"
                        sel_act = c.get("message")
                        break
                if targeted_res.decision == "SELECT" and sel_cat_id:
                    if det_best and sel_cat_id != det_best.get("id"):
                        is_override = True
                        corr_status = "TRUE_CORRECTION"
                    else:
                        corr_status = "NO_CHANGE"
                elif targeted_res.decision == "AMBIGUOUS":
                    corr_status = "AMBIGUOUS"
                else:
                    corr_status = "FALLBACK"
            elif not self.reasoner.is_enabled():
                corr_status = "DISABLED"

            targeted_info = {
                "enabled": self.reasoner.is_enabled(),
                "mode": "gemini-targeted",
                "model": self.reasoner.model_name,
                "triggered": is_triggered,
                "trigger_reasons": trigger_reasons if is_triggered else (trigger_reasons or ["Deterministic confidence was sufficient; no ambiguity detected"]),
                "decision": targeted_res.decision if targeted_res else ("DISABLED" if not self.reasoner.is_enabled() else "UNTRIGGERED"),
                "selected_internal_id": sel_internal_id or ("candidate_1" if det_best else None),
                "selected_catalog_id": sel_cat_id or (det_best.get("id") if det_best else None),
                "selected_action": sel_act or (det_best.get("message") if det_best else None),
                "confidence": targeted_res.confidence if targeted_res else round((adj or {}).get("confidence", 0.90), 4),
                "reason_code": targeted_res.reason_code if targeted_res else "DETERMINISTIC_PASS",
                "explanation": targeted_res.explanation if targeted_res else "Deterministic selection accepted without targeted Gemini override.",
                "correction_status": corr_status,
                "is_override": is_override,
                "latency_ms": round(targeted_res.latency_ms, 3) if targeted_res else 0.0,
                "source": targeted_res.source if targeted_res else "deterministic"
            }

            gemini_info = {
                "enabled": self.verifier.is_enabled(),
                "mode": self.verifier.mode,
                "model": self.verifier.model_name,
                "decision": verifier_res.decision if verifier_res else ("SKIPPED" if not self.verifier.is_enabled() else "UNTRIGGERED"),
                "selected_catalog_id": verifier_res.selected_candidate_id if (verifier_res and verifier_res.selected_candidate_id) else selected_catalog_id,
                "confidence": verifier_res.confidence if verifier_res else ((adj or {}).get("confidence", 0.90)),
                "reason_code": verifier_res.reason_code if verifier_res else "DETERMINISTIC_PASS",
                "explanation": verifier_res.raw_output if verifier_res else "Deterministic selection accepted without LLM override.",
                "latency_ms": round(verifier_res.latency_ms, 3) if verifier_res else 0.0,
                "is_override": (verifier_res.decision == "CORRECT") if verifier_res else False
            }

            act_dl = best.get("deeplink") if best else "bixby://dummy_positive"
            valid_uris = {e["deeplink"] for e in self.retriever.bm25.entries}
            valid_uris.add("bixby://dummy_positive")
            is_valid = (act_dl in valid_uris) if act_dl else False

            catalog_info = {
                "catalog_id": selected_catalog_id,
                "action": best.get("message") if best else "Open Relevant Settings Screen",
                "uri": act_dl,
                "valid": is_valid,
                "original_type": best.get("originalType", "onClickURL") if best else "onClickURL"
            }

        # 7. Performance Summary
        total_latency_ms = (time.perf_counter() - t_total_0) * 1000.0
        perf_info = {
            "total_latency_ms": round(total_latency_ms, 3),
            "cache_lookup_latency_ms": round(cache_latency_ms, 3),
            "retrieval_latency_ms": round(retrieval_latency_ms, 3) if not hw_triggered else 0.0,
            "selection_latency_ms": selection_info.get("latency_ms", 0.0),
            "gemini_targeted_latency_ms": round(targeted_res.latency_ms, 3) if targeted_res else 0.0,
            "gemini_latency_ms": round(verifier_res.latency_ms, 3) if verifier_res else 0.0
        }

        return {
            "debug": {
                "query": query,
                "siis": {
                    "title": siis_title,
                    "content": siis_content
                },
                "polarity": polarity_info,
                "cache": cache_info,
                "safety": safety_info,
                "retrieval": retrieval_info,
                "selection": selection_info,
                "deterministic_choice": det_choice,
                "gemini_targeted": targeted_info,
                "gemini_verification": gemini_info,
                "catalog_resolution": catalog_info,
                "performance": perf_info
            },
            "response": official_response
        }
