#!/usr/bin/env python3
"""Validate and merge blind gpt-5.6-luna reviews for staged records."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


PURPOSES = {"marketing", "functional", "legal", "age", "security", "other", "ambiguous"}
POLARITIES = {"checked_enables_marketing", "unchecked_enables_marketing", "non_marketing", "ambiguous"}
OBLIGATIONS = {"optional", "required", "ambiguous"}
ACTIONS = {"uncheck", "leave", "suggest"}
VERDICTS = {"accept", "reject", "needs_adjudication"}
REVIEW_KEYS = {"record_id", "review_id", "inferred_purpose", "inferred_polarity", "inferred_obligation", "inferred_action", "semantic_fidelity", "plausibility", "noise_realism", "surface_plausibility", "conflicts", "verdict", "confidence", "reason"}
VISIBLE_FIELDS = ("record_id", "label_text", "aria_label", "name", "id", "legend_or_context", "checked_state", "site_profile", "surface", "applied_transforms")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def blind_view(record: dict) -> dict:
    return {field: record.get(field) for field in VISIBLE_FIELDS}


def blind_hash(record: dict) -> str:
    return hashlib.sha256(json.dumps(blind_view(record), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def valid_review(review: dict, review_prefix: str) -> bool:
    if set(review) != REVIEW_KEYS:
        return False
    if not isinstance(review["review_id"], str) or not review["review_id"].startswith(review_prefix):
        return False
    if review["inferred_purpose"] not in PURPOSES or review["inferred_polarity"] not in POLARITIES or review["inferred_obligation"] not in OBLIGATIONS or review["inferred_action"] not in ACTIONS or review["verdict"] not in VERDICTS:
        return False
    if not isinstance(review["conflicts"], list) or not isinstance(review["reason"], str) or not review["reason"].strip():
        return False
    return all(isinstance(review[field], (int, float)) and 0 <= review[field] <= 1 for field in ("semantic_fidelity", "plausibility", "noise_realism", "surface_plausibility", "confidence"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", nargs="+", type=Path, required=True)
    parser.add_argument("--reviews", type=Path, required=True)
    parser.add_argument("--adjudications", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="gpt-5.6-luna")
    parser.add_argument("--model-revision", default="unreported-by-subagent")
    parser.add_argument("--adjudication-model", default="gpt-5.6-luna-adjudication")
    parser.add_argument("--adjudication-model-revision", default="unreported-by-subagent")
    parser.add_argument("--prompt", type=Path, required=True)
    parser.add_argument("--adjudication-prompt", type=Path)
    args = parser.parse_args()
    record_list = [record for source in args.records for record in read_jsonl(source)]
    review_list = read_jsonl(args.reviews)
    adjudication_list = read_jsonl(args.adjudications) if args.adjudications else []
    if len({record["record_id"] for record in record_list}) != len(record_list):
        parser.error("record IDs must be globally unique")
    if len({review.get("record_id") for review in review_list}) != len(review_list) or len({review.get("review_id") for review in review_list}) != len(review_list):
        parser.error("primary record_id and review_id values must be unique")
    if len({review.get("record_id") for review in adjudication_list}) != len(adjudication_list) or len({review.get("review_id") for review in adjudication_list}) != len(adjudication_list):
        parser.error("adjudication record_id and review_id values must be unique")
    records = {record["record_id"]: record for record in record_list}
    reviews = {review["record_id"]: review for review in review_list}
    adjudications = {review["record_id"]: review for review in adjudication_list}
    if args.adjudications and not args.adjudication_prompt:
        parser.error("--adjudication-prompt is required with --adjudications")
    if args.adjudications and args.reviews.resolve() == args.adjudications.resolve():
        parser.error("primary and adjudication reviews must be distinct files")
    if args.adjudications and args.adjudications.read_bytes() == args.reviews.read_bytes():
        parser.error("adjudication output must not be a byte-identical copy of primary output")
    prompt_hash = hashlib.sha256(args.prompt.read_bytes()).hexdigest()
    adjudication_prompt_hash = hashlib.sha256(args.adjudication_prompt.read_bytes()).hexdigest() if args.adjudication_prompt else None
    if adjudication_prompt_hash and adjudication_prompt_hash == prompt_hash:
        parser.error("primary and adjudication prompts must be distinct")
    errors = []
    merged = []
    for record_id, record in records.items():
        review = reviews.get(record_id)
        if not review or not valid_review(review, "primary-"):
            errors.append({"record_id": record_id, "error": "missing or malformed primary review"})
            continue
        axis_map = {"inferred_purpose": "purpose", "inferred_polarity": "polarity", "inferred_obligation": "obligation"}
        axis_disagreement = any(review[review_field] != record[record_field] for review_field, record_field in axis_map.items())
        action_disagreement = review["inferred_action"] != record["expected_action"]
        high_risk = record["expected_action"] == "uncheck" or bool(record["safety_conflicts"]) or record["purpose"] == "ambiguous" or record["polarity"] == "ambiguous" or record["obligation"] == "ambiguous" or "double_negative" in record["requested_challenges"] or "mixed_legal_marketing" in record["requested_challenges"] or review["verdict"] != "accept" or review["confidence"] < 0.85 or axis_disagreement or action_disagreement
        chosen = review
        pass_name = "primary"
        if high_risk:
            adjudication = adjudications.get(record_id)
            if not adjudication or not valid_review(adjudication, "adjudication-"):
                errors.append({"record_id": record_id, "error": "high-risk record lacks adjudication"})
                continue
            chosen = adjudication
            pass_name = "adjudication"
        if chosen["verdict"] != "accept" or chosen["conflicts"] or any(chosen[review_field] != record[record_field] for review_field, record_field in axis_map.items()) or chosen["inferred_action"] != record["expected_action"] or chosen["semantic_fidelity"] < 0.98 or chosen["plausibility"] < 0.95 or chosen["noise_realism"] < 0.95 or chosen["surface_plausibility"] < 0.95 or chosen["confidence"] < 0.85:
            errors.append({"record_id": record_id, "error": "review gate failed", "pass": pass_name, "review": chosen})
            continue
        merged.append({
            "record_id": record_id,
            "review_pass": pass_name,
            "reviewer_model": args.adjudication_model if pass_name == "adjudication" else args.model,
            "review_prompt_sha256": adjudication_prompt_hash if pass_name == "adjudication" else prompt_hash,
            "primary_review_prompt_sha256": prompt_hash,
            "adjudication_prompt_sha256": adjudication_prompt_hash if pass_name == "adjudication" else None,
            "reviewer_model_revision": args.adjudication_model_revision if pass_name == "adjudication" else args.model_revision,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "review_input_sha256": blind_hash(record),
            "review_output_sha256": hashlib.sha256(json.dumps(chosen, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            "primary_review_output_sha256": hashlib.sha256(json.dumps(review, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            "adjudication_review_output_sha256": hashlib.sha256(json.dumps(chosen, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest() if pass_name == "adjudication" else None,
            "review": chosen,
        })
    result = {"records": len(records), "accepted": len(merged), "errors": errors, "all_reviewed": len(reviews) == len(records), "reviewer_model": args.model, "review_prompt_sha256": prompt_hash}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in merged), encoding="utf-8")
    args.output.with_suffix(".summary.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("records", "accepted", "all_reviewed")}, indent=2))
    return 0 if not errors and len(merged) == len(records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
