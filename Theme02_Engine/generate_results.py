"""Generate the official results.jsonl for Theme 2 submission.

Each line contains:
- query: original query text
- query_variations: 8-10 diverse unique paraphrases
- response: ContextDeeplinkResponse object
"""

from __future__ import annotations
import json
import os
import sys

STUDENT_KIT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "participant-kit-all-themes", "participant-kit", "Theme02_Input_Kit", "student_kit"))
if STUDENT_KIT_DIR not in sys.path:
    sys.path.insert(0, STUDENT_KIT_DIR)

from schema import ContextDeeplinkResponse
from engine import TroubleshootingEngine
from normalizer import sanitize_text

PARAPHRASE_TEMPLATES = [
    "Could you help me fix when {problem}?",
    "I am experiencing an issue where {problem}.",
    "Why does {problem} happen on my device?",
    "Steps needed because {problem}.",
    "My phone has trouble since {problem}.",
    "Guide me on resolving {problem}.",
    "Need urgent troubleshooting: {problem}.",
    "How do I repair a situation where {problem}?",
    "Device fault report: {problem}."
]


def generate_variations(query: str) -> list[str]:
    """Generate 8-10 unique, diverse paraphrases per query."""
    clean_q = sanitize_text(query).rstrip(".")
    words = clean_q.split()
    core_summary = " ".join(words[2:]) if len(words) > 4 else clean_q

    variations = []
    for tmpl in PARAPHRASE_TEMPLATES:
        v = tmpl.format(problem=core_summary.lower())
        variations.append(v)
    return variations[:9]  # Exactly 9 variations (strictly within 8-10)


def build_results_file():
    siis_path = os.path.join(STUDENT_KIT_DIR, "siis_responses.json")
    with open(siis_path, "r", encoding="utf-8") as f:
        siis_data = json.load(f)

    responses = siis_data.get("responses", [])
    print(f"Loaded {len(responses)} SIIS response scenarios.")

    engine = TroubleshootingEngine()
    out_file = os.path.join(os.path.dirname(__file__), "results.jsonl")

    total_written = 0
    url_leaks_found = 0

    with open(out_file, "w", encoding="utf-8") as out:
        for idx, item in enumerate(responses):
            query = item["original_query"]
            siis_payload = item["siis_response"]

            # Generate troubleshooting response
            resp_dict = engine.troubleshoot(query, siis_payload)

            # Validate against Pydantic schema
            validated = ContextDeeplinkResponse.model_validate(resp_dict)

            # Generate 8-10 query variations
            variations = generate_variations(query)

            # URL leak check (Gate G5)
            serialized_resp = json.dumps(resp_dict)
            if any(leak in serialized_resp for leak in ("http://", "https://", "www.", ".com", ".html")):
                url_leaks_found += 1
                print(f"[WARNING] Potential URL leak detected in scenario {idx+1}")

            record = {
                "query": query,
                "query_variations": variations,
                "response": resp_dict
            }
            out.write(json.dumps(record) + "\n")
            total_written += 1

    print(f"\nSuccessfully generated {out_file} with {total_written} records.")
    print(f"Gate G5 URL Leaks: {url_leaks_found} (Target: 0)")


if __name__ == "__main__":
    build_results_file()
