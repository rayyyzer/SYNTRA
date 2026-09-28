"""Troubleshooting Engine: Core logic transforming query + SIIS knowledge into schema-valid ContextDeeplinkResponse."""

from __future__ import annotations
import os
import re
import sys
from typing import Any, Dict, List, Optional

# Add student_kit to sys.path to import official Pydantic models
STUDENT_KIT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "participant-kit-all-themes", "participant-kit", "Theme02_Input_Kit", "student_kit"))
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
from adjudicator import CandidateAdjudicator


class TroubleshootingEngine:
    def __init__(self):
        self.retriever = HybridRetriever()
        self.adjudicator = CandidateAdjudicator(dense=self.retriever.dense)
        self.cache = QueryCache()

    def troubleshoot(self, query: str, siis_response: Dict[str, Any]) -> Dict[str, Any]:
        """Main entry point: returns schema-valid ContextDeeplinkResponse as dict."""
        # 1. Check two-tier cache first (<0.05ms)
        cached = self.cache.get(query)
        if cached:
            return cached

        # 2. Extract and sanitize raw text from SIIS
        siis_title = sanitize_text(siis_response.get("title", "Device Issue"))
        siis_content = sanitize_text(siis_response.get("content", ""))

        # 3. Check Safety & Hardware Router for physical damage or hazardous operations
        if is_unsupported_hardware(query, siis_content):
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
            self.cache.put(query, result_dict)
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

        # 5. Hybrid Retrieval (<25ms) + Candidate Adjudication
        candidates = self.retriever.retrieve(query, top_k=5)

        if candidates and candidates[0]["score"] >= 0.20:
            adj = self.adjudicator.adjudicate(
                query=query,
                siis_title=siis_title,
                siis_content=siis_content,
                candidates=candidates
            )
            best = adj.get("selected_candidate") or candidates[0]
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

        # Store in cache
        self.cache.put(query, result_dict)
        return result_dict
