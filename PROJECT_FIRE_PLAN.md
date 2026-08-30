# Project FIRE

## Working title

**FIRE — Firefox Intelligent Registration-Form Exemptor**

A privacy-preserving Firefox extension that detects optional marketing/newsletter consent checkboxes and automatically leaves them unchecked, while preserving required, legal, age, privacy, and functional choices.

## Product decision

v1 will ship with the full auto-uncheck machinery implemented, but **auto-action disabled by default** until the safety gates pass. Highlight/suggest-only is the first usable mode, followed by shadow auto-action that logs what would have changed without mutating the page. Promotion to active auto-uncheck is a release-policy change in the same decision engine, not a separate product direction.

The initial auto-action envelope is deliberately narrow:

- Native `<input type="checkbox">` only.
- Currently checked controls only.
- Clearly positive-polarity marketing opt-ins only: checked means the user opts into marketing.
- Deliberately high calibrated classifier confidence.
- No ambiguity involving terms, privacy, age, payment, account functionality, or other required behavior.
- Mutation handling proven idempotent and resistant to framework reversion.
- Dynamically rewritten labels are reclassified before any action; no action occurs while their meaning is stale or unresolved.

The promotion gate requires zero false auto-actions across a large real-world negative corpus, plus explicit polarity torture tests. A target of 0 false positives across approximately 30,000 independent negative cases corresponds to an approximate 95% rule-of-three upper bound of 0.01%. Synthetic data may support training and fuzzing, but cannot satisfy this certification gate.

## Problem

Checkboxes rarely declare their intent using a reliable HTML standard. A useful classifier must combine visible label text with accessible names and DOM metadata, handle negation and awkward dark-pattern wording, and fail conservatively when intent is unclear.

## Goals

- Detect optional marketing, newsletter, promotional, partner, and product-update opt-ins.
- Leave required, legal, age, privacy, security, payment, and functional checkboxes untouched.
- Handle dynamically inserted native checkbox inputs; defer custom controls to a later scope decision.
- Run classification locally in the browser with no page-content network requests.
- Make every automatic change explainable and reversible.
- Establish a reproducible data, training, evaluation, and release pipeline.

## Non-goals for v1

- Automatically changing radio buttons, toggles, select controls, or unsubscribe links.
- Solving every language or jurisdiction; start with English.
- Unchecking a box solely because it is checked. Semantics and polarity matter.
- Sending page text to a LAN or public model at runtime.
- Guaranteeing protection against deceptive behavior outside form controls.

## Product behavior

For each supported checkbox, assemble a bounded text record from:

1. Associated `<label>` text.
2. `aria-label` and resolved `aria-labelledby` text.
3. `name` and `id` attributes. Do not collect raw values by default because they may contain user data.
4. Nearby fieldset/legend and conservative container text.
5. Structural signals such as `required`, disabled state, form context, and current checked state.

Apply the decision pipeline:

```text
DOM extraction → normalization → hard safety rules → polarity checks
→ compact classifier → confidence policy → uncheck / leave / explain
```

The semantic result must keep separate axes rather than collapsing everything into one class:

```text
purpose: marketing | functional | legal | age | security | other | ambiguous
polarity: checked_enables_marketing | unchecked_enables_marketing | ambiguous
obligation: optional | required | ambiguous
language: english | unsupported | ambiguous
model_confidence: calibrated score
conflicts: rule/model/context conflicts
action: uncheck | leave | suggest
```

For v1, `uncheck` is permitted only when all of these hold:

- It is a native, enabled `<input type="checkbox">` in the main document.
- It is currently checked and has not been interacted with by the user.
- The purpose is marketing and the checked state unambiguously enables marketing.
- Optionality is established; neither `required` nor `aria-required` is present.
- The language is supported, the text is not mixed with legal/required language, and no evidence conflicts.
- The calibrated action threshold is met.

Negative-polarity controls remain unchanged in v1; the extension never auto-checks a box. `UNKNOWN` is a policy abstention, not merely a third learned class.

## Classification design

Use a hybrid system rather than a single large regex:

- Hard exclusions for terms/conditions, privacy policy, consent to data processing, age confirmation, payment/security, required controls, and explicit functional preferences.
- Strong positive and negative lexical features for newsletter, marketing, promotional, offers, deals, updates, partner communications, and similar wording.
- Metadata features for names and IDs such as `newsletter_opt_in`, `marketingConsent`, and `promoEmail`.
- Explicit polarity handling for patterns such as “do not send me marketing email,” “untick if you do not want…,” and double negatives.
- A compact fastText model as one learned baseline, with character n-grams enabled to cover snake_case, camelCase, typos, and brand-specific phrasing.
- A field-aware sparse logistic-regression baseline using word/character TF-IDF or hashed n-grams plus explicit polarity features; this may be easier to calibrate, inspect, and ship in pure JavaScript.

Keep the model input and output inspectable. Use rule traces plus model confidence for explanations; do not promise native fastText feature explanations. Avoid exposing page text in telemetry by default.

## Data strategy

### Sources

- Human-curated seed examples representing purpose, polarity, obligation, and abstention cases.
- Publicly observable real forms collected without submitting forms, entering personal data, bypassing access controls, or collecting unnecessary page content.
- Synthetic variants generated by local LAN LLMs from controlled prompts and seed records.
- Adversarial examples written specifically for negation, double negation, misleading labels, custom controls, and mixed marketing/legal text.

The LAN LLMs are an offline development dependency for dataset creation and augmentation only. The shipped extension must not depend on them. The current backend registry covers all three supplied models; each backend may have an explicit response-channel adapter, but all share the same approved prompt and validation gates.

The approved generation protocol is [GENERATION_PROMPT_SPEC.md](docs/GENERATION_PROMPT_SPEC.md), currently v1.3 with bounded deterministic retries and purpose-independent metadata pools. LAN backend 1 of 3 is the OpenAI-compatible Gemma service at `http://192.168.4.3:8000/v1/chat/completions`, model `coolthor/gemma-4-12B-it-NVFP4A16`. This endpoint belongs only to the offline generation pipeline and must not appear in extension runtime code, permissions, configuration, or packaged artifacts.

### Record format

Store one normalized training example per line in a versioned model-specific format, retaining provenance and structured annotations in a separate manifest. If fastText is used, export a compatible view. Every field must be explicitly namespaced. Example:

```text
__label__marketing label_keep=Keep me updated with news and special offers name_newsletter=newsletter_opt_in
__label__functional label_terms=I agree to the Terms and Conditions required=true
__label__unknown label_remember=Remember my choice on this device id_remember=rememberChoice
```

The production corpus should include both label-only and label-plus-metadata examples, because the extension will encounter both. It must also annotate purpose, polarity, obligation, language, provenance, annotators, and adjudication status.

### Target composition for the first experiment

- 1,000–2,000 human-curated or real-form-derived examples per class.
- 2,000–3,000 synthetic variants per class.
- At least 20% real-form-derived or human-reviewed records overall.
- At least 15% adversarial/polarity-focused records.
- Gold data must be real/human-authored, independently double-annotated, adjudicated when needed, and excluded from augmentation prompts.
- Deduplicate before splitting, then hold out entire domains and form-vendor/component fingerprints so scores do not measure template memorization.

This gives an initial corpus of roughly 10,000–15,000 examples while preserving room to grow based on error analysis.

Synthetic data must be treated as augmentation, not ground truth. Deduplicate near-identical generations, validate labels with rules and human sampling, report inter-annotator agreement on the gold set, and retain the original seed plus generator metadata.

## Evaluation

Build a fixed, human-reviewed gold set separated by source domain and never used for prompt generation. Track:

- Precision and recall for `MARKETING`.
- Protected-control alteration rate across legal, age, security, functional, and ambiguous examples.
- Coverage: percentage of eligible checkboxes receiving a confident decision.
- Calibration of confidence thresholds.
- Accuracy on polarity and adversarial subsets.
- Incorrect state-transition rate, protected-control alteration rate, post-change reversion rate, and user-override violations.
- Runtime cost and bundle size in Firefox desktop and Android where supported.

The primary metric is incorrect state-transition rate, not standalone classifier accuracy. A provisional release gate is zero failures on a mandatory protected-control suite, plus zero protected alterations on at least 3,000 independently reviewed protected examples and a one-sided 95% upper confidence bound of no more than 0.1%. Report all metrics by subtype rather than only in aggregate. If uncertain, the extension leaves the checkbox unchanged.

Required evaluation fixtures should include static HTML, dynamically inserted forms, framework-controlled inputs, labels detached through ARIA, missing labels, multilingual-looking noise, typos, conflicting metadata, and every must-pass negation/polarity case. v1 explicitly excludes `role="checkbox"`, closed Shadow DOM, cross-origin iframes, and custom controls unless a later phase adds them.

## Extension architecture

- Content script observes native checkbox additions and relevant attribute mutations with debounced processing; cap work per page and mutation queue size.
- DOM adapter resolves labels and accessible names without broad page scraping.
- Classifier module exposes a small pure function for deterministic tests.
- Policy module applies safety rules, thresholding, and idempotence.
- Intervention state machine: `discovered → evaluated → changed → user-overridden/site-overridden`. User interaction permanently wins for that page lifecycle; framework reversion must not trigger repeated changes.
- v1 must not call `click()` or dispatch `input`/`change` automatically. Phase 0 benchmarks property-only mutation versus native-setter plus events, measuring framework reversion, validation, network activity, and price/state changes before any event-emitting policy is considered.
- Optional popup/options UI shows counts, lets users disable auto-action per site, and supports best-effort undo while the original node remains connected and unchanged by the user/site.
- No remote telemetry in v1; if diagnostics are later added, use opt-in, aggregate-only events.
- Enforce resource limits: bounded text per field, bounded controls per page, bounded mutation work, and memory-only debug traces. Render page-derived strings with `textContent`, never `innerHTML`.

## Milestones

### Phase 0 — Feasibility spike

- Define record schema, label policy, safety taxonomy, and initial hard rules.
- Create a small fixture suite of representative real-form patterns and the structured polarity/action schema.
- Train a fastText baseline and compare it with rules-only classification.
- Train a sparse logistic-regression baseline and compare all models using the final action policy.
- Benchmark Firefox CSP/WASM requirements, bundle size, startup time, per-frame memory, and the actual checkbox mutation protocol.
- Restrict all automatic action testing to fixtures or highlight-only mode.

**Exit:** repeatable benchmark, documented error taxonomy, measurable safety gates, and a go/no-go decision for desktop/native-checkbox auto-action.

### Phase 1 — Data pipeline

- Implement seed ingestion, normalization, provenance manifests, deduplication, prompt-based LAN generation, and `gpt-5.6-luna` review queues for synthetic records.
- Integrate the approved prompt/seed combinator and backend registry; reject malformed, unsafe, contradictory, or duplicate model output before it enters the corpus.
- Add domain/template-aware train/dev/test splitting.
- Generate adversarial polarity sets.

The first three-backend staged pilot is documented in [STAGED_PILOT_REPORT.md](docs/STAGED_PILOT_REPORT.md). All three backends satisfy the response contract and produce useful candidates, but the pilot is not admitted to training: blind Luna review accepted 7/178 records, and the corpus still has metadata leakage plus euphemism/dark-pattern coverage gaps.

The v1.3 remediation and three-backend smoke are documented in [STAGED_V1_3_SMOKE_REPORT.md](docs/STAGED_V1_3_SMOKE_REPORT.md). The revised generator is SOL-approved, the safety regression suite passes, and all smoke records were independently reviewed by Luna. Before scaling, namespace the root seed per backend to reduce correlated cross-model duplicates; synthetic output remains separate from the gold/certification corpus.

**Exit:** versioned 10k–15k corpus, gold set, and one-command training/evaluation run.

### Phase 2 — Firefox prototype

- Implement Manifest V3-compatible extension structure and content-script checkbox discovery.
- Add label/ARIA/metadata extraction, safety rules, classifier inference, and conservative action policy.
- Add debug explanation mode and per-site disable/undo controls.
- Ship highlight/suggest-only as the default safety mode.

**Exit:** extension works on fixture pages and never changes protected controls in automated tests.

### Phase 3 — Real-form validation

- Run against a consented or carefully selected public-form corpus without submissions.
- Compare predicted actions to human judgments.
- Run shadow auto-action against at least 30,000 independent real-world negative cases and record would-have-acted decisions without mutating pages.
- Run explicit polarity torture tests and verify that synthetic examples are excluded from certification metrics.
- Tune thresholds and expand only the error classes observed in the wild.

**Exit:** release candidate meets safety and performance gates on unseen domains; only then may the default policy be promoted from highlight/suggest-only to the narrow auto-action envelope.

### Phase 4 — Packaging and release

- Privacy review, permissions minimization, accessibility review, Firefox desktop smoke tests, explicit Firefox Android scope decision, and add-on submission assets.
- Publish model/data provenance and a clear user-facing explanation of limitations.

**Exit:** signed release candidate with rollback path and reproducible build.

## Safety and ethics

- Never submit forms or interact with consent flows beyond the requested checkbox change.
- Do not collect names, email addresses, cookies, authentication material, or full page snapshots unless explicitly necessary and legally reviewed.
- Respect site terms, robots guidance where applicable, rate limits, and applicable privacy/copyright requirements during corpus creation.
- Default to no action on ambiguity, missing context, or conflicting signals.
- Provide an allowlist/disable mechanism and make changes reversible.
- Treat required marketing consent or region-specific legal controls as `UNKNOWN` unless policy is unambiguous.
- Treat page text as attacker-controlled input. Cap extraction and mutation work, avoid storing raw page-derived text, and keep per-site settings out of synced storage unless explicitly designed for it.

## Initial acceptance criteria

- The shipped default mode is highlight/suggest-only; no page mutation occurs until the certification gate passes.
- The implemented auto-action policy unchecks only high-confidence optional marketing/newsletter boxes whose checked state unambiguously enables marketing on the fixture corpus when explicitly enabled for testing.
- It does not auto-uncheck protected/required examples in the gold set.
- It handles dynamically added checkboxes without repeated toggling or excessive CPU use.
- It performs inference entirely locally at runtime and ships without a LAN service dependency.
- The model, training data version, evaluation metrics, and threshold policy are reproducible from the repository.
- Users can disable automation per site and undo changes on the current page.
- It never uses synthetic clicks, never auto-checks a box, and user interaction wins over automation.
- Shadow mode records would-have-acted decisions without mutating the page.

## Open decisions

- Whether the first shipped model is fastText WASM/native-compatible inference or a converted lightweight linear model.
- Exact browser permissions and whether all-sites automation or per-site activation is the default.
- Whether Firefox Android is included in the first release; current planning scope is desktop-first.
- Whether to support only English initially or add language detection and an explicit non-English `UNKNOWN` path.
- Whether real-form collection is a separate private corpus repository because of provenance and retention constraints.
- Which mutation semantics, if any, are compatible with common controlled-input frameworks without causing side effects.

## Suggested repository layout

```text
extension/       Firefox extension source
classifier/      feature extraction, rules, model adapter
data/             schemas, seeds, manifests, evaluation fixtures
tools/            LAN generation, dedupe, training, benchmarking
docs/             privacy, collection protocol, model card
tests/            unit, fixture, mutation-observer, and browser tests
```

## Peer review disposition

The draft was reviewed by the Codex router using `gpt-5.6-sol`. The review gave a **conditional GO for Phase 0** and a **no-go for live auto-action until the safety amendments are in place**. The critical findings were polarity-aware action modeling, mutation/event side effects, measurable protected-control error bounds, gold-set and template-leakage controls, explicit DOM scope, attacker-controlled input/resource limits, and Firefox MV3/WASM/Android packaging constraints. Those findings are incorporated above.
