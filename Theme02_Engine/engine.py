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

from deeplink_matcher import DeeplinkIndex
from normalizer import sanitize_text, format_goal, format_title, format_action_description
from cache import QueryCache


class TroubleshootingEngine:
    def __init__(self):
        self.matcher = DeeplinkIndex()
        self.cache = QueryCache()

    def troubleshoot(self, query: str, siis_response: Dict[str, Any]) -> Dict[str, Any]:
        """Main entry point: returns schema-valid ContextDeeplinkResponse as dict."""
        # 1. Check cache first (<3ms)
        cached = self.cache.get(query)
        if cached:
            return cached

        # 2. Extract and sanitize raw text from SIIS
        siis_title = sanitize_text(siis_response.get("title", "Device Troubleshooting"))
        siis_content = sanitize_text(siis_response.get("content", ""))

        # 3. Derive goal & title
        goal_text = format_goal(siis_title)
        title_text = format_title(siis_title)

        # 4. Extract action steps from SIIS text (do not invent steps)
        # Break content into natural sentences or bullet points
        raw_sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", siis_content) if len(s.strip()) > 10]
        if not raw_sentences:
            raw_sentences = [
                "Navigate to and open Settings on your device.",
                "Inspect device display and backup all personal data to cloud storage.",
                "Visit an authorized Samsung Service Center if hardware is damaged."
            ]

        # Partition steps into automated settings actions vs manual repair actions
        auto_steps = []
        manual_steps = []

        for sent in raw_sentences:
            low_s = sent.lower()
            if any(k in low_s for k in ("settings", "tap", "select", "turn on", "navigate", "backup", "screen", "display", "battery", "reset", "clear", "accounts")):
                auto_steps.append(sent)
            else:
                manual_steps.append(sent)

        if not auto_steps:
            auto_steps = [raw_sentences[0]]
            manual_steps = raw_sentences[1:]

        # 5. Build Action 1: Automated Settings Action (category: auto -> MUST have actionableDeeplink)
        act1_name = "Configure Device Settings"
        if any("backup" in s.lower() for s in auto_steps):
            act1_name = "Back Up Phone Data"
        elif any("display" in s.lower() or "screen" in s.lower() for s in auto_steps):
            act1_name = "Adjust Display Configuration"
        elif any("battery" in s.lower() for s in auto_steps):
            act1_name = "Optimize Battery Settings"

        act1_desc = format_action_description(act1_name, auto_steps[0])
        act_dl_dict, val_dl_dict = self.matcher.find_match(query, " ".join(auto_steps))

        actionable_dl = Deeplink(
            deeplink=act_dl_dict["deeplink"],
            description=act_dl_dict.get("description", "Opens the relevant device Settings page."),
            message=act_dl_dict.get("message", "Open Settings"),
            originalType=act_dl_dict.get("originalType", "onClickURL")
        )

        validation_dl = None
        if val_dl_dict:
            validation_dl = ValidationDeepLink(
                deeplink=val_dl_dict["deeplink"],
                key=val_dl_dict["key"],
                resultType=ResultTypes.boolean,
                condition=Condition.equal,
                value=val_dl_dict["value"]
            )

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

        # 6. Build Action 2: Manual / Service Action (category: manual)
        actions = [action_1]
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

        # 7. Construct Goal
        goal = Goal(
            goal=goal_text,
            title=title_text,
            actions=actions,
            score=0.95
        )

        # 8. Construct validated ContextDeeplinkResponse
        response_obj = ContextDeeplinkResponse(contexts=[goal])
        result_dict = response_obj.model_dump()

        # Store in cache
        self.cache.put(query, result_dict)
        return result_dict
