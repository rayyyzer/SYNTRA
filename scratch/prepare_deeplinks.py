"""Phase 1: Samsung Deeplinks Dataset Preparation & Validation.

Inspects, validates, cleans, and indexes deeplinks.json without modifying
the original file. Preserves original URIs and IDs exactly.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple


def normalize_text(text: Optional[str]) -> str:
    """Normalize text for lexical matching while preserving semantic words."""
    if not text:
        return ""
    # Lowercase and replace non-alphanumeric (except hyphens) with spaces
    text = text.lower()
    text = re.sub(r"[^\w\s-]", " ", text)
    # Collapse multiple whitespaces
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokenize(text: str) -> List[str]:
    """Tokenize normalized text into words."""
    norm = normalize_text(text)
    return [t for t in re.split(r"[\s-]+", norm) if len(t) > 1]


def load_and_inspect_dataset(filepath: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]], Dict[str, Any]]:
    """Loads deeplinks.json and computes deep statistical validation metrics."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"deeplinks.json not found at {filepath}")

    with open(filepath, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    readme = raw_data.get("_readme", "")
    declared_count = raw_data.get("count", 0)
    raw_items = raw_data.get("deeplinks", [])

    stats: Dict[str, Any] = {
        "readme": readme,
        "declared_count": declared_count,
        "actual_count": len(raw_items),
        "unique_ids": 0,
        "duplicate_ids": [],
        "unique_uris": 0,
        "duplicate_uris": [],
        "missing_ids": 0,
        "missing_uris": 0,
        "missing_descriptions": 0,
        "missing_messages": 0,
        "missing_qna_descriptions": 0,
        "original_type_counts": {},
        "control_type_counts": {},
        "with_validation": 0,
        "without_validation": 0,
        "dummy_entries": [],
    }

    ids = [x.get("id") for x in raw_items]
    uris = [x.get("deeplink") for x in raw_items]

    stats["unique_ids"] = len(set(ids))
    id_counts = Counter(ids)
    stats["duplicate_ids"] = [k for k, v in id_counts.items() if v > 1]

    stats["unique_uris"] = len(set(uris))
    uri_counts = Counter(uris)
    stats["duplicate_uris"] = [k for k, v in uri_counts.items() if v > 1]

    stats["missing_ids"] = sum(1 for x in ids if not x)
    stats["missing_uris"] = sum(1 for x in uris if not x)
    stats["missing_descriptions"] = sum(1 for x in raw_items if not x.get("description", "").strip())
    stats["missing_messages"] = sum(1 for x in raw_items if not x.get("message", "").strip())
    stats["missing_qna_descriptions"] = sum(1 for x in raw_items if not (x.get("qna_description") or "").strip())

    stats["original_type_counts"] = dict(Counter(str(x.get("originalType")) for x in raw_items))
    stats["control_type_counts"] = dict(Counter(str(x.get("control_type")) for x in raw_items))

    stats["with_validation"] = sum(1 for x in raw_items if x.get("validation") is not None)
    stats["without_validation"] = sum(1 for x in raw_items if x.get("validation") is None)

    for x in raw_items:
        if "dummy" in (x.get("deeplink") or "").lower() or "dummy" in (x.get("id") or "").lower():
            stats["dummy_entries"].append({
                "id": x.get("id"),
                "deeplink": x.get("deeplink"),
                "description": x.get("description"),
                "message": x.get("message"),
                "originalType": x.get("originalType"),
            })

    # Prepare cleaned dataset
    cleaned_items: List[Dict[str, Any]] = []
    for item in raw_items:
        item_id = item.get("id", "").strip()
        deeplink = item.get("deeplink", "").strip()
        description = item.get("description", "").strip()
        message = item.get("message", "").strip()
        qna_description = (item.get("qna_description") or "").strip()
        orig_type = item.get("originalType")
        ctrl_type = item.get("control_type")
        validation = item.get("validation")

        # Compose unified searchable text representations
        searchable_parts = []
        if message:
            searchable_parts.append(message)
        if description:
            searchable_parts.append(description)
        if qna_description:
            searchable_parts.append(qna_description)

        searchable_text = " ".join(searchable_parts)
        normalized_searchable = normalize_text(searchable_text)
        tokens = tokenize(searchable_text)

        cleaned_items.append({
            "id": item_id,
            "deeplink": deeplink,  # PRESERVED VERBATIM
            "description": description,
            "message": message,
            "originalType": orig_type,
            "control_type": ctrl_type,
            "qna_description": qna_description,
            "validation": validation,
            "searchable_text": searchable_text,
            "normalized_searchable": normalized_searchable,
            "tokens": tokens,
            "token_count": len(tokens),
        })

    return raw_data, cleaned_items, stats


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    workspace_root = os.path.abspath(os.path.join(script_dir, ".."))
    
    candidate_paths = [
        os.path.join(workspace_root, "data", "student_kit", "deeplinks.json"),
        os.path.join(workspace_root, "participant-kit-all-themes", "participant-kit", "Theme02_Input_Kit", "student_kit", "deeplinks.json")
    ]
    input_path = next((p for p in candidate_paths if os.path.exists(p)), candidate_paths[0])
    
    out_dir = os.path.join(script_dir, "generated")
    os.makedirs(out_dir, exist_ok=True)
    out_cleaned_path = os.path.join(out_dir, "cleaned_deeplinks.json")
    out_stats_path = os.path.join(out_dir, "stats.json")

    print(f"[Phase 1] Inspecting: {input_path}")
    raw_data, cleaned_items, stats = load_and_inspect_dataset(input_path)

    print("\n--- DATASET INSPECTION RESULTS ---")
    print(f"Declared count: {stats['declared_count']}")
    print(f"Actual items: {stats['actual_count']}")
    print(f"Unique IDs: {stats['unique_ids']} (Duplicates: {len(stats['duplicate_ids'])})")
    print(f"Unique URIs: {stats['unique_uris']} (Duplicates: {len(stats['duplicate_uris'])})")
    print(f"Missing IDs: {stats['missing_ids']}, Missing URIs: {stats['missing_uris']}")
    print(f"Missing Descriptions: {stats['missing_descriptions']}, Missing Messages: {stats['missing_messages']}")
    print(f"Missing QnA Descriptions: {stats['missing_qna_descriptions']}")
    print(f"originalType distribution: {stats['original_type_counts']}")
    print(f"control_type distribution: {stats['control_type_counts']}")
    print(f"Entries with validation: {stats['with_validation']}, without: {stats['without_validation']}")
    print(f"Special/Fallback entries: {len(stats['dummy_entries'])}")
    for d in stats['dummy_entries']:
        print(f"  -> {d['id']}: {d['deeplink']} | {d['description']}")

    # Save cleaned dataset
    with open(out_cleaned_path, "w", encoding="utf-8") as f:
        json.dump(cleaned_items, f, indent=2, ensure_ascii=False)
    print(f"\n[Phase 1] Cleaned dataset saved to: {out_cleaned_path}")

    # Save stats
    with open(out_stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    print(f"[Phase 1] Stats summary saved to: {out_stats_path}")


if __name__ == "__main__":
    main()
