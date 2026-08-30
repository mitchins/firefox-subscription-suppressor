# Project FIRE staged pilot report

Date: 2026-08-30

## Decision

The three LAN models are compatible with the approved v1.2 generation contract and produce useful candidates, but this pilot is **not training-admission ready**. Keep all generated records synthetic-only and fail closed; do not promote them into the gold set or use them to certify auto-uncheck safety.

## Generation

The pilot requested 200 records from each backend using the same approved prompt/combinator and root seed. The generator accepted 178 records and rejected 422 before review:

| Backend | Model role | Accepted | Rejected | Yield |
| --- | --- | ---: | ---: | ---: |
| LLM-1 | Gemma clean semantic baseline | 64 | 136 | 32.0% |
| LLM-2 | Nemotron robustness challenger | 49 | 151 | 24.5% |
| LLM-3 | Qwen idiomatic/diversity specialist | 65 | 135 | 32.5% |
| **Total** |  | **178** | **422** | **29.7%** |

The accepted source action distribution was 79 `leave`, 94 `suggest`, and 5 `uncheck`. LLM-3 supplied the largest accepted set and the broadest accepted semantic-family/surface coverage; LLM-2 was the most selective. All three covered every style and metadata-style category in their accepted output, and the combined corpus covered all five DOM surfaces and all 16 site-profile combinations.

## Diversity and blind-spot checks

- Combined family/surface/checked-state coverage: 106 of 160 required cells.
- Exact duplicate rate: 0.56% (one duplicate group).
- Near-duplicate rate: 0.56% (below the 5% limit).
- Template duplicate groups: 5 (below the 5% rate limit).
- Metadata single-purpose token rate: 0.40 (40%), above the 0.25 gate.
- Accepted requested challenge coverage was concentrated in `no_polarity_signal` (105); `double_negative` (21), `mixed_legal_marketing` (13), direct/implicit positive (24), and explicit/conditional negative (15) were present. Euphemism and misleading-dark-pattern records did not survive generation acceptance, so those are a material blind spot rather than a demonstrated coverage area.

The metadata failure is diagnostic rather than a reason to discard the models: tokens such as `consent`, `control`, `selection`, and `opt` remained too purpose-specific in this small accepted corpus. The generator should vary opaque metadata more independently from semantic purpose and track metadata leakage separately from label-text diversity.

## Luna review

Two independent blind `gpt-5.6-luna` passes reviewed all 178 accepted records. The primary review artifact initially stopped after the first 64 records; that was detected by `all_reviewed=false`, repaired with a second blind pass, and the final validator confirmed `all_reviewed=true`.

The final merge admitted 7 of 178 records (3.9%): LLM-1: 1, LLM-2: 2, LLM-3: 4. Every admitted record was `leave`; zero `uncheck` candidates passed the review gates. The 171 exclusions were driven mainly by semantic fidelity, plausibility, surface realism, axis disagreement, action disagreement, and conflicts. This is a useful safety result, but too little eligible material for training and evidence that the current synthetic contract is not yet producing reliably legible adversarial variants.

## Next changes before scaling

1. Keep the three backends in the pipeline; do not discard LLM-3’s diversity contribution.
2. Add a generation-side retry/repair budget for challenge families, but preserve caller-owned truth and never infer truth from a repaired label.
3. Redesign euphemism and dark-pattern seeds so their intended meaning is explicit enough for blind review while remaining linguistically realistic.
4. Decouple metadata tokens from semantic labels and add a per-purpose metadata leakage gate.
5. Add a review-yield target by challenge family and require nonzero accepted coverage for every safety-critical family before corpus admission.
6. Keep real-form/human-authored gold data separate; this pilot cannot satisfy the real-world safety gate.

Artifacts: `staged-pilot-llm*.jsonl`, their manifests, the corpus report, blind inputs, both Luna review passes, and the merged review summary under `data/generated/`.
