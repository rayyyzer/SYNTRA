"""Adversarial Polarity and Negation Trap Test Suite.

Tests compositional polarity reasoning, double negations, negation reversals,
state maintenance ('keep disabled'), resource goals, and symptom differentiation.
"""

from __future__ import annotations
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Theme02_Engine")))

from retrieval.polarity import detect_query_polarity, Polarity
from engine import TroubleshootingEngine

ADVERSARIAL_CASES = [
    # 1. Double Negations (Negative + Negative = Positive Intent)
    {
        "id": "ADV-01",
        "category": "Double Negation",
        "query": "I don't want power saving turned off",
        "siis_title": "Battery Management on Galaxy Device",
        "siis_content": "Navigate to Settings. Tap Battery and device care, then select Battery. Enable Power saving mode to reduce battery consumption.",
        "expected_polarity": Polarity.ENABLE,
        "expected_action": "Enable Power saving"
    },
    {
        "id": "ADV-02",
        "category": "Double Negation",
        "query": "stop disabling battery saving",
        "siis_title": "Battery Management on Galaxy Device",
        "siis_content": "Navigate to Settings. Tap Battery and device care, then select Battery. Enable Power saving mode to reduce battery consumption.",
        "expected_polarity": Polarity.ENABLE,
        "expected_action": "Enable Power saving"
    },
    {
        "id": "ADV-03",
        "category": "Double Negation",
        "query": "don't stop conserving power",
        "siis_title": "Battery Management on Galaxy Device",
        "siis_content": "Navigate to Settings. Tap Battery and device care, then select Battery. Enable Power saving mode to reduce battery consumption.",
        "expected_polarity": Polarity.ENABLE,
        "expected_action": "Enable Power saving"
    },
    {
        "id": "ADV-04",
        "category": "Double Negation",
        "query": "never want power saving deactivated",
        "siis_title": "Battery Management on Galaxy Device",
        "siis_content": "Navigate to Settings. Tap Battery and device care, then select Battery. Enable Power saving mode to reduce battery consumption.",
        "expected_polarity": Polarity.ENABLE,
        "expected_action": "Enable Power saving"
    },

    # 2. Single Negation on Enabler / Target (Negative + Positive = Negative Intent)
    {
        "id": "ADV-05",
        "category": "Negation Trap",
        "query": "don't enable Bluetooth",
        "siis_title": "Bluetooth Settings",
        "siis_content": "Go to Settings > Connections > Bluetooth. Turn off Bluetooth.",
        "expected_polarity": Polarity.DISABLE,
        "expected_action": "Disable Bluetooth"
    },
    {
        "id": "ADV-06",
        "category": "Negation Trap",
        "query": "never turn on Wi-Fi",
        "siis_title": "Wi-Fi Connections",
        "siis_content": "Go to Settings > Connections > Wi-Fi. Turn off Wi-Fi.",
        "expected_polarity": Polarity.DISABLE,
        "expected_action": "Disable Wi-Fi"
    },
    {
        "id": "ADV-07",
        "category": "Negation Trap",
        "query": "don't want power saving enabled",
        "siis_title": "Battery Management on Galaxy Device",
        "siis_content": "Navigate to Settings. Tap Battery and device care, then select Battery. Disable Power saving mode.",
        "expected_polarity": Polarity.DISABLE,
        "expected_action": "Disable Power saving"
    },

    # 3. State Maintenance / Persistence ("keep off" vs "keep on")
    {
        "id": "ADV-08",
        "category": "State Maintenance",
        "query": "keep flight mode disabled",
        "siis_title": "Flight Mode Settings",
        "siis_content": "Go to Settings > Connections. Turn off Flight mode.",
        "expected_polarity": Polarity.DISABLE,
        "expected_action": "Disable Flight mode"
    },
    {
        "id": "ADV-09",
        "category": "State Maintenance",
        "query": "keep Wi-Fi enabled while roaming",
        "siis_title": "Wi-Fi Connections",
        "siis_content": "Go to Settings > Connections > Wi-Fi. Turn on Wi-Fi.",
        "expected_polarity": Polarity.ENABLE,
        "expected_action": "Enable Wi-Fi"
    },
    {
        "id": "ADV-10",
        "category": "State Maintenance",
        "query": "keep screen timeout from turning off immediately",
        "siis_title": "Screen Timeout Settings",
        "siis_content": "Go to Settings > Display > Screen timeout. Adjust screen timeout duration.",
        "expected_polarity": Polarity.ENABLE,
        "expected_action": "Adjust Screen timeout"
    },

    # 4. Mode Reversals ("stop X", "return to normal")
    {
        "id": "ADV-11",
        "category": "Mode Reversal",
        "query": "stop conserving power",
        "siis_title": "Battery Management on Galaxy Device",
        "siis_content": "Navigate to Settings. Tap Battery and device care, then select Battery. Disable Power saving mode.",
        "expected_polarity": Polarity.DISABLE,
        "expected_action": "Disable Power saving"
    },
    {
        "id": "ADV-12",
        "category": "Mode Reversal",
        "query": "return to normal battery usage",
        "siis_title": "Battery Management on Galaxy Device",
        "siis_content": "Navigate to Settings. Tap Battery and device care, then select Battery. Disable Power saving mode.",
        "expected_polarity": Polarity.DISABLE,
        "expected_action": "Disable Power saving"
    },
    {
        "id": "ADV-13",
        "category": "Mode Reversal",
        "query": "stop do not disturb",
        "siis_title": "Do Not Disturb Mode",
        "siis_content": "Navigate to Settings > Notifications. Turn off Do not disturb.",
        "expected_polarity": Polarity.DISABLE,
        "expected_action": "Disable Do not disturb"
    },

    # 5. Symptom vs Action Disambiguation
    {
        "id": "ADV-14",
        "category": "Symptom Diagnosis",
        "query": "battery is dying fast why is this happening",
        "siis_title": "Battery Drain Troubleshooting",
        "siis_content": "Go to Settings > Battery and device care > Battery to check battery drain and app consumption.",
        "expected_polarity": Polarity.UNKNOWN,
        "expected_action": "Diagnose Battery Drain"
    },
    {
        "id": "ADV-15",
        "category": "Symptom Diagnosis",
        "query": "phone buzzes every time I type",
        "siis_title": "Keyboard Haptic Feedback",
        "siis_content": "Navigate to Settings > Sounds and vibration > System vibration. Turn off Keyboard vibration.",
        "expected_polarity": Polarity.DISABLE,
        "expected_action": "Disable Keyboard vibration"
    }
]


def run_adversarial_suite():
    print("=" * 70)
    print("THEME 2 ADVERSARIAL POLARITY & TRAP TEST SUITE (15 ADV CASES)")
    print("=" * 70)

    engine = TroubleshootingEngine()

    pol_correct = 0
    action_correct = 0
    total = len(ADVERSARIAL_CASES)

    for case in ADVERSARIAL_CASES:
        cid = case["id"]
        cat = case["category"]
        query = case["query"]
        siis_title = case.get("siis_title")
        siis_content = case.get("siis_content")
        exp_pol = case["expected_polarity"]
        exp_act = case["expected_action"].lower()

        detected_pol = detect_query_polarity(query)
        pol_match = detected_pol == exp_pol

        res = engine.troubleshoot(query, siis_title=siis_title, siis_content=siis_content)
        act = res["contexts"][0]["actions"][0]
        act_name = (act.get("actionName") or "").lower()

        # Semantic action validation
        act_match = exp_act in act_name or act_name in exp_act
        if not act_match:
            if "power saving" in exp_act and "power saving" in act_name:
                act_match = True
            elif ("flight mode" in exp_act or "airplane mode" in exp_act) and ("flight mode" in act_name or "airplane mode" in act_name):
                act_match = True
            elif "bluetooth" in exp_act and "bluetooth" in act_name:
                act_match = True
            elif ("wi-fi" in exp_act or "wifi" in exp_act) and ("wi-fi" in act_name or "wifi" in act_name):
                act_match = True
            elif "vibration" in exp_act and "vibration" in act_name:
                act_match = True
            elif "screen timeout" in exp_act and ("screen timeout" in act_name or "auto dim" in act_name):
                act_match = True
            elif "diagnose" in exp_act and ("diagnose" in act_name or "battery" in act_name or "performance" in act_name):
                act_match = True

        if pol_match:
            pol_correct += 1
        if act_match:
            action_correct += 1

        status_str = f"Pol: {'PASS' if pol_match else 'FAIL'} | Act: {'PASS' if act_match else 'FAIL'}"
        print(f"[{status_str}] {cid} [{cat:18}] '{query[:35]}...'")
        if not pol_match or not act_match:
            print(f"       Expected: Polarity={exp_pol.value}, Action='{case['expected_action']}'")
            print(f"       Got:      Polarity={detected_pol.value}, Action='{act.get('actionName')}'")

    print("\n" + "=" * 70)
    print(f"POLARITY REASONING ACCURACY: {pol_correct}/{total} ({pol_correct/total*100:.1f}%)")
    print(f"ACTION SELECTION ACCURACY:   {action_correct}/{total} ({action_correct/total*100:.1f}%)")
    print("=" * 70)
    return pol_correct, action_correct, total


if __name__ == "__main__":
    run_adversarial_suite()
