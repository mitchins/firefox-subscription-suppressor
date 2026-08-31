# Project FIRE namespaced pilot and diversity experiment

Date: 2026-08-31

## Decision

Use backend-namespaced root seeds for future multi-backend generation. Do not
use the fictional preamble `You are running Ted's flower shop.` in production
generation. Blind Luna adjudication found merchant-role and copied-text
leakage in generated labels. The approved fallback is:

```text
backend-namespaced root seed
temperature=0.0
preamble=none
top_p=1, n=1
```

No additional preambles are being introduced.

## Clean fallback pilot

The fallback used base root
`fire-staged-v13-namespaced-fallback-2026-08-31` and effective roots formed by
appending `:llm1`, `:llm2`, or `:llm3`. Each backend received 200 requests.

| Backend | Requests | Mechanically accepted | Luna-admitted | Final deduplicated |
| --- | ---: | ---: | ---: | ---: |
| LLM-1 Gemma | 200 | 57 | 17 | 17 |
| LLM-2 Nemotron | 200 | 45 | 15 | 14 |
| LLM-3 Qwen | 200 | 60 | 17 | 14 |
| **Total** | **600** | **162** | **49** | **45** |

The final set contains 43 `leave` records and 2 narrow, independently reviewed
`uncheck` records: `Sign me up for MARKETING emails` and `Yes, send me marketing
emails`. The extension remains highlight/suggest-only by default; these are
synthetic augmentation candidates, not evidence for enabling live action.

## Diversity experiment

The four paired smoke variants used identical backend-namespaced seeds:
control, temperature 0.2 only, the Ted preamble only, and both together. Luna
found no safety-critical regression in the small accepted sample, but no useful
Nemotron variation and only limited Qwen variation. Gemma showed the clearest
wording variation.

The larger combined run demonstrated why the preamble gate matters: labels such
as `Ted's Flowers`, `flower preferences`, and `flower shop updates` were
rejected as merchant-role/copy leakage. That run is retained as a failed
experiment and is not admitted to training. No additional preambles are being
added.

## Corpus gates

The raw fallback corpus had 10 exact duplicate groups and 18 near-duplicate
pairs across 162 records. `tools/admit_staged.py` kept one reviewed
representative for each duplicate group. The final 45-record corpus has zero
exact duplicates and zero near-duplicate pairs.

The raw metadata diagnostic was high in the small reviewed subset because
generic pool words such as `account`, `choice`, and `preference` appeared in
only one surviving purpose. The checker now reports that raw diagnostic
separately and gates on purpose-coded metadata tokens. Purpose-coded metadata
leakage was zero for both raw fallback and final admitted corpora.

## Review and provenance

All 162 mechanically accepted fallback records received independent primary and
adjudication passes by `gpt-5.6-luna`. The merge gate admitted 49 records: 21
from primary review and 28 after adjudication. Every generation manifest
records the base/effective root, requested/sent temperature, allowlisted
preamble ID/hash, system prompt hash, per-attempt effective-message hash, and
canonical payload/response hashes.

The fallback is suitable for the next data-pipeline step, subject to real/human
gold-set separation and domain-held-out evaluation. It does not replace the
30,000-case real-world negative safety certification gate.
