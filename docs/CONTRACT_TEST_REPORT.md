# Shared-contract backend test

**Date:** 2026-08-30
**Seed set:** `contract-v1-2026-08-30`
**Cases:** 12 identical seed tuples per backend
**Certification status:** not certification data; synthetic compatibility testing only

## Results

| Backend | Accepted | Rejected | Response adapter | Result |
| --- | ---: | ---: | --- | --- |
| Gemma 4 12B | 11/12 | 1 | `content`, thinking disabled | Best current fit; one emoji-noise miss |
| Nemotron 3.5 Lightning 30B | 4/12 | 8 | `content`, thinking disabled | Not ready for broad noise/challenge generation |
| Qwen 3.8 27B MLX | 6/12 | 6 | explicit `reasoning_content`, thinking disabled | Contract-compatible adapter; slow and inconsistent on adversarial/noise cases |

## Findings

The shared semantic contract is valid across all three backends. No model-specific semantic relaxation is approved. The validator correctly rejected every observed failure; no invalid `uncheck` action entered an accepted result.

Backend-specific settings are transport/runtime details only:

- LLM-1 and LLM-2 use the final response from `content`.
- LLM-3 requires the explicit `reasoning_content` response adapter because its server exposes the structured result there even when thinking is disabled.
- All three use `chat_template_kwargs.enable_thinking=false`.

Observed model-quality differences:

- LLM-1 missed one emoji requirement.
- LLM-2 frequently missed casing, emoji, whitespace, typo, dark-pattern, and double-negative requirements, and once violated a label-only surface invariant.
- LLM-3 missed one negative-polarity realization, several noise/challenge requirements, and timed out on one case at the current 90-second request limit.

## Decision

Do not scale any backend directly from this test. Keep strict rejection and resampling. Gemma is the current primary candidate for the next larger pilot. Nemotron and Qwen remain compatible for controlled experiments, but their acceptance rates must improve—or their generation roles must be narrowed—before they contribute substantial training data.

The certification corpus remains real/human-reviewed and must not include synthetic compatibility outputs as evidence.
