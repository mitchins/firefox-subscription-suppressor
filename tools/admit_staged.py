#!/usr/bin/env python3
"""Admit Luna-reviewed staged records after global duplicate filtering."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def normalize(text: str) -> str:
    text = text.casefold()
    text = re.sub(r"\s+", " ", text)
    return re.sub(r"[^a-z0-9 ]", "", text).strip()


def shingles(text: str, size: int = 3) -> set[str]:
    text = normalize(text)
    return {text[index:index + size] for index in range(max(0, len(text) - size + 1))}


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", nargs="+", type=Path, required=True)
    parser.add_argument("--reviewed", type=Path, required=True, help="Luna merge output")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    records = [record for source in args.records for record in read_jsonl(source)]
    record_by_id = {record["record_id"]: record for record in records}
    reviewed = read_jsonl(args.reviewed)
    reviewed_ids = [item["record_id"] for item in reviewed]
    if len(set(reviewed_ids)) != len(reviewed_ids):
        parser.error("reviewed record IDs must be unique")
    missing = [record_id for record_id in reviewed_ids if record_id not in record_by_id]
    if missing:
        parser.error("review references missing record: " + missing[0])

    selected: list[dict] = []
    dropped: list[dict] = []
    seen_normalized: dict[str, str] = {}
    for record_id in reviewed_ids:
        record = record_by_id[record_id]
        key = normalize(record["label_text"])
        if key in seen_normalized:
            dropped.append({"record_id": record_id, "reason": "exact_normalized_duplicate", "kept_record_id": seen_normalized[key]})
            continue
        current_shingles = shingles(record["label_text"])
        near_duplicate = None
        for kept in selected:
            kept_shingles = shingles(kept["label_text"])
            union = current_shingles | kept_shingles
            similarity = len(current_shingles & kept_shingles) / len(union) if union else 1.0
            if similarity >= 0.92:
                near_duplicate = (kept, round(similarity, 4))
                break
        if near_duplicate:
            kept, similarity = near_duplicate
            dropped.append({"record_id": record_id, "reason": "near_duplicate", "similarity": similarity, "kept_record_id": kept["record_id"]})
            continue
        selected.append(record)
        seen_normalized[key] = record_id

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for record in selected), encoding="utf-8")
    report = {
        "reviewed": len(reviewed_ids),
        "admitted": len(selected),
        "dropped": len(dropped),
        "dropped_records": dropped,
        "policy": {"requires_luna_merge": True, "exact_normalized_duplicates": "keep_first", "near_duplicate_jaccard_threshold": 0.92},
        "output_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
        "inputs": [str(path) for path in args.records],
        "reviewed_input": str(args.reviewed),
    }
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("reviewed", "admitted", "dropped")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
