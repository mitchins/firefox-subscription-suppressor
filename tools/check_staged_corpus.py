#!/usr/bin/env python3
"""Check global exact and near-duplicate rates for staged JSONL records."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def normalize(text: str) -> str:
    text = text.casefold()
    text = re.sub(r"\s+", " ", text)
    return re.sub(r"[^a-z0-9 ]", "", text).strip()


def delex(text: str) -> str:
    text = normalize(text)
    text = re.sub(r"\b(?:[a-f0-9]{8,}|\d+)\b", "<id>", text)
    text = re.sub(r"\b(?:send|email|receive|get|subscribe|join|keep|discover|enjoy|learn)\b", "<verb>", text)
    text = re.sub(r"\b(?:newsletter|marketing|promotional?|offers?|deals?|promos?|partner(?:s)?|specials?|updates?|news|product|drops?|arrivals?)\b", "<purpose>", text)
    return text


def shingles(text: str, size: int = 3) -> set[str]:
    normalized = normalize(text)
    return {normalized[index:index + size] for index in range(max(0, len(normalized) - size + 1))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--max-metadata-leakage", type=float, default=0.25)
    args = parser.parse_args()
    records = []
    for source in args.inputs:
        for line in source.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                record["_source"] = source.name
                records.append(record)
    exact = {}
    templates = {}
    near = []
    metadata_token_purposes = {}
    for index, record in enumerate(records):
        text = record.get("label_text", "")
        exact.setdefault(normalize(text), []).append(index)
        templates.setdefault(delex(text), []).append(index)
        metadata = " ".join(str(record.get(field) or "") for field in ("name", "id"))
        for token in re.findall(r"[a-z0-9]+", metadata.casefold()):
            if len(token) >= 8 and re.fullmatch(r"[a-f0-9]+", token):
                continue
            metadata_token_purposes.setdefault(token, set()).add(record.get("purpose", "unknown"))
    for left in range(len(records)):
        left_shingles = shingles(records[left].get("label_text", ""))
        if not left_shingles:
            continue
        for right in range(left + 1, len(records)):
            right_shingles = shingles(records[right].get("label_text", ""))
            union = left_shingles | right_shingles
            similarity = len(left_shingles & right_shingles) / len(union) if union else 1.0
            if similarity >= 0.92:
                near.append({"left": left, "right": right, "jaccard": round(similarity, 4)})
    duplicate_groups = [group for group in exact.values() if len(group) > 1]
    template_groups = [group for group in templates.values() if len(group) > 1]
    metadata_tokens = [token for token in metadata_token_purposes if token not in {"", "id"}]
    single_purpose_tokens = [token for token in metadata_tokens if len(metadata_token_purposes[token]) == 1]
    report = {
        "records": len(records),
        "exact_duplicate_groups": duplicate_groups,
        "template_duplicate_groups": template_groups,
        "near_duplicate_pairs": near,
        "exact_duplicate_rate": sum(len(group) - 1 for group in duplicate_groups) / len(records) if records else 0,
        "near_duplicate_rate": len(near) / len(records) if records else 0,
        "metadata_token_single_purpose_rate": len(single_purpose_tokens) / len(metadata_tokens) if metadata_tokens else 0,
        "metadata_token_purposes": {token: sorted(purposes) for token, purposes in sorted(metadata_token_purposes.items())},
        "inputs": [str(path) for path in args.inputs],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("records", "exact_duplicate_rate", "near_duplicate_rate", "metadata_token_single_purpose_rate")}, indent=2))
    return 1 if duplicate_groups or len(near) / len(records) > 0.05 or sum(len(group) - 1 for group in template_groups) / len(records) > 0.05 or report["metadata_token_single_purpose_rate"] > args.max_metadata_leakage else 0


if __name__ == "__main__":
    raise SystemExit(main())
