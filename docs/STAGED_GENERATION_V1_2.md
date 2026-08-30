# FIRE staged generation v1.2

This is the staged successor to `fire-synthetic-checkbox-v1.1`. It separates
semantic generation from record composition so a model cannot invent the action,
DOM metadata, quality flags, or provenance.

## Ownership boundary

The LAN model returns exactly one JSON object:

```json
{"candidate_text":"Keep me updated about new product drops"}
```

The caller owns:

- the validated semantic seed and checked state;
- the site-profile/funnel/surface combinator;
- `expected_action` and the no-auto-check policy;
- DOM-like metadata and field presence;
- deterministic mechanical noise;
- observed/requested flags, family IDs, deduplication, and provenance hashes.

The model is asked for plausible English wording only. It must preserve purpose,
polarity, obligation, style, profile, and the requested semantic challenge. It
must reject placeholders, prose, metadata, copied pages, URLs, and personal data.

## Semantic families and composition

The deterministic planner samples a weighted set of valid semantic families and
a weighted compatibility graph of site archetype, funnel stage, and voice. It
includes direct and implicit opt-ins, explicit and conditional opt-outs, euphemisms, dark
patterns, double negatives, mixed legal/marketing ambiguity, protected controls,
and unknown/ambiguous cases. A seed does not use index-modulo assignment.

Mechanical transforms are caller-owned and preserve the clean candidate parent:

- casing variation;
- repeated whitespace;
- a controlled typo;
- an emoji suffix;
- fragmentary phrasing.

Semantic challenges remain model-generated. The final record retains both the
clean candidate and the composed label, plus hashes for the raw candidate
response and clean candidate text.

## Validation and review

The generator rejects malformed JSON, unknown candidate keys, placeholders,
unsafe content, missing polarity/purpose/challenge evidence, action-envelope
violations, surface-invariant violations, and exact normalized duplicates.
The caller recomputes the action; the model never supplies it.

The 600-record pilot is reviewed by `gpt-5.6-luna` rather than a human review
queue. Luna scores every record for semantic fidelity, polarity, plausibility,
noise realism, surface plausibility, and duplication/template concerns. High-risk
records and Luna disagreements receive a second Luna adjudication pass. This is
an efficient synthetic-data quality screen, not a substitute for the independent
real-form negative corpus used for the extension's safety certification.

Pilot gates are: zero safety-critical polarity/purpose contradictions,
zero placeholders/prose/unsafe records, at least 98% semantic fidelity overall
with no reviewed cell below 95%, at least 95% plausibility overall with no
profile/challenge cell below 90%, at least 90% normalized uniqueness, at most
5% near-duplicates, and every pilot record reviewed. Records failing review are
excluded from training until repaired and re-reviewed.

## Reproducibility

Each record contains the spec/combinator versions, backend, seed-derived family
and parent IDs, requested and applied transforms, observed features, and hashes.
The sidecar manifest records prompt hash, root seed, endpoint/model, response
channel, decoding parameters, per-record seed source, timestamps, and accepted
output hash. If a backend does not honor the requested seed, the manifest must
say so and the run is not treated as bit-for-bit reproducible.
