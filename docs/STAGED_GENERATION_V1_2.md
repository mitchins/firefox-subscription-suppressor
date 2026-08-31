# FIRE staged generation v1.3

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

The authoritative v1.3 request is built by `tools/generate_staged.py`: the
validated seed and checklist are caller-owned data, and the model response is
only `{"candidate_text":"..."}`. The deterministic seed is derived from the
root seed and record index; the independent metadata slot is derived from
`SHA-256(root_seed + ":metadata-slot:" + index)`. The first 160 planned records
cover every semantic family/surface/checked-state combination when the pilot
count permits it. This uses deterministic index-modulo assignment only for that
coverage block; later records use weighted sampling. Each manifest reports planned,
accepted, and missing coverage;
the command exits nonzero when accepted coverage is incomplete.

## Semantic families and composition

The deterministic planner samples a weighted set of valid semantic families and
a weighted compatibility graph of site archetype, funnel stage, and voice. It
includes direct and implicit opt-ins, explicit and conditional opt-outs, euphemisms, dark
patterns, double negatives, mixed legal/marketing ambiguity, protected controls,
and unknown/ambiguous cases. Outside the initial coverage block, a seed does not
use index-modulo assignment.

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

Malformed JSON, malformed response envelopes, and recoverable realization
failures receive at most three deterministic retries. Every attempt is retained
with its sampling seed, payload/response hashes, status, and error; accepted
records retain the accepted-attempt index. Cross-backend exact, template, and
near-duplicate rates are checked by `tools/check_staged_corpus.py`.

The v1.3 generator retries only deterministic realization/format failures up to
three attempts. Every attempt records its sampling seed, payload hash, response
hash when available, status, and validator error; retries never change the
semantic seed or caller-owned action policy. Metadata pools are purpose-
independent and selected from an index-derived slot to reduce metadata leakage.

The generator supports a bounded diversity experiment through `--temperature`
(`0.0` through `0.2`) and an allowlisted `--preamble` (`none` or the single
fictional `ted-flower-shop` candidate). A preamble is delimited, non-authoritative
user-message context; it never changes the system contract or semantic seed.
Smoke runs must test temperature-only, preamble-only, and combined variants on
paired seeds. Any safety, leakage, or quality regression falls back to
backend-namespaced seeds at temperature 0 with no preamble. Manifests record
requested/sent temperature, base/effective root seeds, preamble ID/hash, system
prompt hash, and per-attempt effective-message hashes.

The v1.3 generator distinguishes hard safety conflicts from explicitly named
soft challenge conflicts. Soft conflicts are allowed only on misleading-dark-
pattern or mixed-legal/marketing records, and those records are always
`suggest`; `uncheck` requires zero conflicts. Challenge coverage is reported
separately for mechanically accepted and Luna-admitted records.

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

After review, `tools/admit_staged.py` performs a second global exact/near-
duplicate pass and keeps one reviewed representative per duplicate group. The
corpus checker reports raw single-purpose metadata vocabulary separately from
purpose-coded metadata leakage; only the purpose-coded metric is a gate because
generic field words become sparse after review filtering.

## Reproducibility

Each record contains the spec/combinator versions, backend, seed-derived family
and parent IDs, requested and applied transforms, observed features, and hashes.
The sidecar manifest records prompt hash, root seed, endpoint/model, response
channel, decoding parameters, per-record seed source, timestamps, and accepted
output hash. If a backend does not honor the requested seed, the manifest must
say so and the run is not treated as bit-for-bit reproducible.
