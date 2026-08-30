# Project FIRE staged v1.3 remediation smoke

Date: 2026-08-31

## Result

The SOL-approved v1.3 remediation is ready for a larger generation run. The
smoke produced candidates from all three LAN models, exercised retries and the
new challenge validators, and completed independent Luna review. No candidate
was admitted to auto-uncheck training from this smoke.

| Backend | Requests | Accepted | Generator yield | Retried accepted records |
| --- | ---: | ---: | ---: | ---: |
| LLM-1 | 20 | 7 | 35.0% | 0 |
| LLM-2 | 20 | 6 | 30.0% | 1 |
| LLM-3 | 20 | 10 | 50.0% | 1 |
| **Total** | **60** | **23** | **38.3%** | **2** |

All 23 accepted candidates received primary and adjudication Luna review. The
merge validator admitted 2/23, both protected/non-marketing `leave` records;
0 `uncheck` records passed. The first 20 coverage seeds deliberately use
`checked_state=false`, so this smoke does not measure positive checked-state
auto-uncheck yield.

## Fixed issues observed in the v1.2 pilot

- Euphemism candidates now require separate opt-in and non-direct referent cues.
- Dark patterns now require positive opt-in plus urgency/friction and remain
  `suggest`-only.
- Double negatives require exactly two separated negative operators.
- Positive no-polarity candidates and active/passive/nominal reversal phrases
  are rejected by hard safety checks.
- Strict auto-uncheck grammar is applied to label text only; caller-owned ARIA,
  metadata, and legend context no longer invalidate safe labels.
- Metadata leakage was 0 on this smoke corpus.
- Retry attempts now preserve deterministic seed, payload hash, raw response
  hash, status, and error, including malformed/partial HTTP responses.

## Remaining operational finding

The combined same-seed smoke had two exact duplicate groups (8.7% duplicate
rate), both common phrases emitted by different backends. Before a larger
cross-backend corpus run, use backend-namespaced root seeds such as
`<root>:llm1`, `<root>:llm2`, and `<root>:llm3`, then retain the global duplicate
gate. This preserves the shared contract while reducing avoidable correlated
phrasing.

This smoke is still synthetic-only. It does not replace the real-form or
human-authored gold set, nor the 30,000-case real-world negative safety gate.
