# FIRE staged v1.2 smoke report

## Disposition

The three-backend preflight was **not promoted to the 600-record pilot**.
The generator's acceptance/coverage gate failed, and the blind Luna review
accepted only 5 of the 22 records that reached composition.

This is a quality-control result, not an extension safety-certification result.
No live form was submitted or mutated, and no synthetic record contributes to
the 30,000-case real-form safety gate.

## Run

```text
root seed: fire-staged-smoke-2026-08-30
requested: 20 records per backend
backends: Gemma (LLM-1), Nemotron (LLM-2), Qwen (LLM-3)
```

| Backend | Accepted by generator | Rejected by generator |
|---|---:|---:|
| LLM-1 / Gemma | 7 | 13 |
| LLM-2 / Nemotron | 7 | 13 |
| LLM-3 / Qwen | 8 | 12 |
| Total | 22 | 38 |

The generator returned a failed coverage status for each backend because the
planned cells were not all accepted. Failures were predominantly challenge
realization, safe fragment/noise realization, protected-purpose realization,
and semantic safety conflicts. This is the intended fail-closed behavior.

## Luna review

Two independent `gpt-5.6-luna` passes reviewed all 22 records from a blind view:

```text
primary:       16 accept, 2 needs adjudication, 4 reject
adjudication:  16 accept, 0 needs adjudication, 6 reject
merged gate:    5 accepted, 17 excluded
```

The merged gate required exact agreement with hidden purpose/polarity/
obligation/action, no reviewer conflicts, semantic fidelity ≥0.98,
plausibility ≥0.95, noise and surface plausibility ≥0.95, and confidence ≥0.85.
Most exclusions were intentionally ambiguous updates, mixed legal/marketing
wording, low-plausibility double-negative text, button-like security wording,
or reviewer scores below the release thresholds.

The cross-backend duplicate report found no exact, template, or near-duplicate
pairs in the 22 composed records. The metadata leakage metric is not
interpretable at this smoke size because only two records exposed name/id
metadata; it is retained for the larger pilot gate.

## Next decision

Do not generate the 600-record pilot yet. First use the excluded-record reasons
to improve the semantic candidate prompts and/or the allocation of challenge
families, then repeat a bounded smoke run. The 600-record pilot remains gated
on full generator coverage and complete Luna review/adjudication, followed by
the documented diversity/plausibility thresholds.
