# FIRE Luna review contract

`gpt-5.6-luna` reviews composed synthetic records as a quality screen before
they can enter training. The review is blind to the generator's semantic labels
and expected action: the reviewer receives only the label, accessible metadata,
checked state, surface, and site context. It independently infers the meaning.

## Per-record output

Luna must emit exactly one JSON object per input record with these fields:

```json
{
  "record_id": "record-…",
  "review_id": "primary-record-…",
  "inferred_purpose": "marketing|functional|legal|age|security|other|ambiguous",
  "inferred_polarity": "checked_enables_marketing|unchecked_enables_marketing|non_marketing|ambiguous",
  "inferred_obligation": "optional|required|ambiguous",
  "inferred_action": "uncheck|leave|suggest",
  "semantic_fidelity": 0.0,
  "plausibility": 0.0,
  "noise_realism": 0.0,
  "surface_plausibility": 0.0,
  "conflicts": [],
  "verdict": "accept|reject|needs_adjudication",
  "confidence": 0.0,
  "reason": "short evidence-based reason"
}
```

Scores are in `[0,1]`. `inferred_action` follows the conservative FIRE policy:
only a checked, clearly optional, positive-polarity marketing opt-in may infer
`uncheck`; no record may infer `auto_check`. A contradiction, protected-purpose
conflict, placeholder, copied/identifiable text, or unsafe metadata is a reject.

## Review procedure

Review every record. Use a unique `primary-…` review_id in the first pass and a
unique `adjudication-…` review_id in the second pass. Route all `uncheck`, mixed legal/marketing, double-negative,
ambiguous, low-confidence, and initial reject/accept disagreements through an
independent second Luna pass using the same blind input and a fresh prompt. The
adjudicated verdict replaces the initial verdict only when the disagreement is
resolved; otherwise reject the record.

Persist the reviewer model, model revision, prompt hash, input/output hashes,
review pass, timestamp, verdict, scores, confidence, conflicts, and reason in a
sidecar JSONL file. Luna review does not replace independent real-form safety
certification or the 30,000-case negative corpus.
