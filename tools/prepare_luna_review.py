#!/usr/bin/env python3
"""Create a blind view of staged records for gpt-5.6-luna review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


VISIBLE_FIELDS = (
    "record_id", "label_text", "aria_label", "name", "id", "legend_or_context",
    "checked_state", "site_profile", "surface", "applied_transforms",
)

LUNA_SYSTEM_PROMPT = """You are the blind quality reviewer for Project FIRE synthetic checkbox records.
Infer meaning from the supplied visible checkbox evidence only. Do not assume a
generator label, seed, expected action, family, or quality flag exists. Return
exactly one JSON object per input line and no prose.

Infer purpose, polarity, obligation, and the conservative action independently.
For the primary pass, review_id must be unique and start with primary-. For the
adjudication pass, review_id must be unique and start with adjudication-.
Only a checked, clearly optional, positive-polarity marketing opt-in may infer
uncheck. Never infer auto-check. A contradiction, protected-purpose conflict,
placeholder, copied/identifiable text, or unsafe metadata is reject.

Scores must be numbers from 0 to 1. Verdict is accept only when the meaning is
clear, plausible, and the requested mechanical transform is visibly realistic.
Use needs_adjudication for uncertainty or disagreement with the evidence.

Output keys exactly: record_id, review_id, inferred_purpose, inferred_polarity,
inferred_obligation, inferred_action, semantic_fidelity, plausibility,
noise_realism, surface_plausibility, conflicts, verdict, confidence, reason.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prompt-output", type=Path)
    parser.add_argument("--adjudication-prompt-output", type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as out:
        for source in args.inputs:
            for line in source.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                blind = {field: record.get(field) for field in VISIBLE_FIELDS}
                out.write(json.dumps(blind, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    if args.prompt_output:
        args.prompt_output.parent.mkdir(parents=True, exist_ok=True)
        args.prompt_output.write_text(LUNA_SYSTEM_PROMPT, encoding="utf-8")
    if args.adjudication_prompt_output:
        args.adjudication_prompt_output.parent.mkdir(parents=True, exist_ok=True)
        args.adjudication_prompt_output.write_text(LUNA_SYSTEM_PROMPT + "\nThis is an independent adjudication pass. Re-infer every field from the blind evidence; do not copy any prior review.\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
