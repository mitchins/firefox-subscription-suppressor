#!/usr/bin/env python3
"""Generate Project FIRE v1.3 staged synthetic records.

The model generates only a semantic candidate label. The caller owns all truth,
DOM structure, mechanical noise, action policy, flags, and provenance.
"""

from __future__ import annotations

import argparse
import http.client
import inspect
import json
import random
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from generate_synthetic import (
    EXPLICIT_OPTOUT,
    MARKETING_LANGUAGE,
    MAX_FIELD_LENGTH,
    OBLIGATIONS,
    POLARITIES,
    PURPOSES,
    QUALITY_FLAGS,
    STYLES,
    canonical_json,
    expected_action,
    no_sensitive_text,
    sha256_bytes,
)


SPEC_VERSION = "fire-synthetic-checkbox-v1.3"
COMBINATOR_VERSION = "fire-staged-combinator-v1.3"
MAX_TEMPERATURE = 0.2

PREAMBLES = {
    "none": None,
    "ted-flower-shop": "You are running Ted's flower shop.",
}

BACKENDS = {
    "llm1": {
        "endpoint": "http://192.168.4.3:8000/v1/chat/completions",
        "model": "coolthor/gemma-4-12B-it-NVFP4A16",
        "response_field": "content",
        "role": "clean semantic baseline",
    },
    "llm2": {
        "endpoint": "http://192.168.1.14:8000/v1/chat/completions",
        "model": "/data/model-conversion/final/Nemotron-3.5-Lightning-30B-A3B-W4A16-G64-cal512",
        "response_field": "content",
        "role": "bounded paraphraser/robustness challenger",
    },
    "llm3": {
        "endpoint": "http://localhost:1234/v1/chat/completions",
        "model": "qwen3.8-27b-uncensored-mlx-4-bit",
        "response_field": "reasoning_content",
        "role": "idiomatic/diversity specialist",
    },
}

ARCHETYPES = {"retailer", "SaaS", "publisher", "marketplace", "travel", "finance", "health", "community"}
FUNNEL_STAGES = {"newsletter_signup", "account_creation", "checkout", "booking", "lead_capture", "preferences"}
VOICES = {"formal", "cheerful", "urgent", "premium", "casual", "restrained"}
SURFACES = {"label_only", "label_plus_aria", "label_plus_name_id", "label_plus_legend", "mixed_dom_context"}
NOISE = {"none", "casing", "whitespace", "typo", "emoji", "fragment"}
METADATA_STYLES = {"descriptive", "neutral", "opaque", "conflicting"}
CHALLENGES = {
    "direct_positive",
    "implicit_positive",
    "explicit_negative",
    "conditional_negative",
    "double_negative",
    "misleading_dark_pattern",
    "euphemism",
    "mixed_legal_marketing",
    "no_polarity_signal",
}

SEMANTIC_FAMILIES = [
    {"purpose": "marketing", "polarity": "checked_enables_marketing", "obligation": "optional", "challenge": "direct_positive"},
    {"purpose": "marketing", "polarity": "checked_enables_marketing", "obligation": "optional", "challenge": "implicit_positive"},
    {"purpose": "marketing", "polarity": "unchecked_enables_marketing", "obligation": "optional", "challenge": "explicit_negative"},
    {"purpose": "marketing", "polarity": "unchecked_enables_marketing", "obligation": "optional", "challenge": "conditional_negative"},
    {"purpose": "marketing", "polarity": "checked_enables_marketing", "obligation": "optional", "challenge": "euphemism"},
    {"purpose": "marketing", "polarity": "checked_enables_marketing", "obligation": "ambiguous", "challenge": "misleading_dark_pattern"},
    {"purpose": "ambiguous", "polarity": "ambiguous", "obligation": "ambiguous", "challenge": "double_negative"},
    {"purpose": "functional", "polarity": "non_marketing", "obligation": "required", "challenge": "no_polarity_signal"},
    {"purpose": "functional", "polarity": "non_marketing", "obligation": "optional", "challenge": "no_polarity_signal"},
    {"purpose": "legal", "polarity": "non_marketing", "obligation": "required", "challenge": "explicit_negative"},
    {"purpose": "age", "polarity": "non_marketing", "obligation": "required", "challenge": "no_polarity_signal"},
    {"purpose": "security", "polarity": "non_marketing", "obligation": "required", "challenge": "no_polarity_signal"},
    {"purpose": "ambiguous", "polarity": "ambiguous", "obligation": "optional", "challenge": "no_polarity_signal"},
    {"purpose": "ambiguous", "polarity": "ambiguous", "obligation": "ambiguous", "challenge": "double_negative"},
    {"purpose": "ambiguous", "polarity": "ambiguous", "obligation": "ambiguous", "challenge": "mixed_legal_marketing"},
    {"purpose": "other", "polarity": "ambiguous", "obligation": "ambiguous", "challenge": "no_polarity_signal"},
]

PROFILE_GRAPH = [
    ("retailer", "newsletter_signup", "cheerful"),
    ("retailer", "checkout", "casual"),
    ("SaaS", "account_creation", "premium"),
    ("SaaS", "preferences", "restrained"),
    ("publisher", "lead_capture", "urgent"),
    ("publisher", "newsletter_signup", "formal"),
    ("marketplace", "checkout", "casual"),
    ("marketplace", "preferences", "cheerful"),
    ("travel", "booking", "restrained"),
    ("travel", "preferences", "premium"),
    ("finance", "preferences", "formal"),
    ("finance", "account_creation", "restrained"),
    ("health", "account_creation", "restrained"),
    ("health", "preferences", "formal"),
    ("community", "preferences", "casual"),
    ("community", "account_creation", "cheerful"),
]

PROFILE_COMPATIBILITY = {
    "marketing": {(p[0], p[1]) for p in PROFILE_GRAPH if p[1] in {"newsletter_signup", "checkout", "preferences", "lead_capture", "booking", "account_creation"}},
    "functional": {(p[0], p[1]) for p in PROFILE_GRAPH if p[1] in {"account_creation", "checkout", "booking", "preferences"}},
    "legal": {(p[0], p[1]) for p in PROFILE_GRAPH if p[1] in {"account_creation", "checkout", "booking"}},
    "age": {(p[0], p[1]) for p in PROFILE_GRAPH if p[1] in {"account_creation", "checkout", "booking"}},
    "security": {(p[0], p[1]) for p in PROFILE_GRAPH if p[1] in {"account_creation", "preferences"}},
    "ambiguous": {(p[0], p[1]) for p in PROFILE_GRAPH},
    "other": {(p[0], p[1]) for p in PROFILE_GRAPH},
}

CANDIDATE_SYSTEM = """You generate one plausible human-facing checkbox label for Project FIRE.

The caller owns the semantic truth and will add all DOM metadata, action, flags,
and provenance. Return exactly one JSON object with only the candidate_text key.
Do not include metadata, explanations, markdown, or reasoning in that field.

The label must express the supplied purpose, polarity, obligation, style, site
profile, and semantic challenge. Noise, surface, and metadata_style are
caller-composed constraints; do not encode them in candidate_text. A checked_enables_marketing seed means checking
opts into marketing, so use positive opt-in language. An
unchecked_enables_marketing seed means leaving unchecked leaves marketing enabled,
so use explicit opt-out language. Never reverse polarity.

Semantic challenges are real wording requirements: implicit_positive means an
ordinary checkbox opt-in whose positive meaning is conveyed without an explicit
"yes" or "I want"; euphemism must imply the
marketing meaning without direct marketing keywords; a dark pattern must be
manipulative without becoming an opt-out. For euphemism, pair an opt-in cue such
as "Keep me in the loop" or "Let me in on" with a separate non-direct marketing
cue such as "member perks" or "inside scoop"; the opt-in cue alone is not the
euphemistic referent. Do not use newsletter, marketing, offers, deals, news,
updates, partner, or similar direct terms. For a dark pattern, use an explicit
positive opt-in plus genuine urgency or friction, such as "Get exclusive offers
before they disappear"; do not use "exclusive offers" alone, turn it into an
opt-out, or make it a required control. A double negative must contain exactly two separated negative
operators, such as "I don't want to miss not receiving member updates"; adjacent
"not not" is invalid. Euphemism, dark-pattern, and mixed legal/marketing cases
are always suggest-only. A mixed legal/marketing case must genuinely mix both
meanings.
For no_polarity_signal, express the supplied non-marketing or ambiguous purpose
without adding a marketing opt-in or opt-out polarity signal. This challenge is
not valid for a marketing purpose.
Do not use placeholders such as "...". If the requested combination cannot be
expressed, set candidate_text to the literal string GENERATION_FAILED.
"""

PURPOSE_MARKERS = {
    "functional": re.compile(r"\b(?:confirm|booking|reservation|order|seat|cart|notification|feature|account|profile|preference|enable|save)\b", re.I),
    "legal": re.compile(r"\b(?:terms?|conditions?|agreement|privacy|policy|consent|processing)\b", re.I),
    "age": re.compile(r"\b(?:age|18|adult|majority|birth|eligib)\b", re.I),
    "security": re.compile(r"\b(?:security|secure|two[- ]factor|2fa|multi[- ]factor|authentication|lock|protect)\b", re.I),
}
EUPHEMISM_MARKERS = re.compile(r"\b(?:extra sparkle|member perks|perks|inside scoop|little something|something for you)\b", re.I)
DARK_MARKERS = re.compile(r"\b(?:don't miss|do not miss|last chance|act now|urgent|limited time|while .* lasts|before .* disappear(?:s)?|regret)\b", re.I)
PROTECTED_MARKERS = re.compile(r"\b(?:terms?|conditions?|privacy|policy|age|18|adult|payment|billing|card|security|secure|two[- ]factor|2fa|authentication|password|required|mandatory|compulsory|essential|necessary|prerequisite|obligatory|must|need to|to continue|to proceed|so you can continue|to complete checkout|before checkout|checkout can be completed|access requires|consent to (?:data|information)|processing)\b", re.I)
POSITIVE_OPTIN = re.compile(r"\b(?:send|email|receive|get|subscribe|sign me up|opt me in|i would like|i'd like|join|keep me|let me in on|stay in the loop|be the first|discover|enjoy|learn about)\b", re.I)
EXPLICIT_POSITIVE = re.compile(r"\b(?:yes|i want|i would like|please|sign me up|subscribe)\b", re.I)
MARKETING_CORE = re.compile(r"\b(?:newsletter|marketing|promotional?|offers?|deals?|promos?|partner(?:s)?|specials?|product (?:news|updates?|drops?|launches?)|exclusive (?:offers?|access)|new arrivals?)\b", re.I)
NEGATIVE_OPERATOR = re.compile(r"\b(?:not|never|no|don't|do not|neither|without|won't|wouldn't)\b", re.I)
NEGATIVE_ACTION = re.compile(r"\b(?:reject|decline|skip|disable|refuse|avoid|stop|block|remove|exclude|cancel|turn off|turn down|pause|cease|end|halt|mute|silence|suspend|switch off|deactivate|suppress|prevent|discontinue|forbid|withdraw|deny|revoke|terminate)\b", re.I)
POLARITY_REVERSAL = re.compile(r"\b(?:freedom|relief|protection|immunity|shield|escape|avoidance|exemption|break|respite|reprieve|release|free|blocked|excluded|removed|barred|disconnected|removal|suppression|elimination|cessation|prevention|blocking|exclusion|disconnection|termination|ban|prohibition|denial|refusal|rejection|cancellation|embargo|moratorium|liberation|reduction|opt[ -]?out)\s+(?:from|against|of|to|regarding|about|around|on)\b|\b(?:get|rid)\s+(?:rid of|yourself of|away from|out of)\b|\b(?:marketing|newsletter|promotion|promotional|advertising)[ -]?free\b", re.I)
QUANTITY_NEGATION = re.compile(r"\b(?:zero|none|fewer|less|limited|reduced|minimum|only)\b", re.I)
UNSAFE_POSITIVE_CLAUSE = re.compile(r"\b(?:require|requires|required|obliged|obligatory|need to|must|essential|necessary|prerequisite|to continue|to proceed|proceed|so you can continue|so you may proceed|to complete checkout|before checkout|checkout can be completed|cannot continue|can't continue|or you|but|plus|except|only when|when this box|box is off|gain access|access)\b", re.I)
SAFE_POSITIVE_LABEL = re.compile(r"^\s*(?:yes,?\s+)?(?:(?:send|email|receive|get)\s+(?:me\s+)?|(?:subscribe|sign me up)\s+(?:for|to)\s+|(?:keep me (?:updated|informed)|stay in the loop)\s+(?:about|on|with)\s+|(?:opt me in|i would like|i'd like|join|be the first to|discover|enjoy|learn about)\s+)(?:(?:occasional|regular|weekly|monthly|personalized|curated|exclusive|special|product|member|wellness|new|latest|first)\s+){0,6}(?:newsletter|marketing(?:\s+emails?)?|promotional?\s+emails?|offers?|deals?|promos?|news|updates?|arrivals?|inspiration|wellness\s+tips|emails?|launch(?:es|ing)?|drops?|specials?)[.!?\s]*$", re.I)
STATE_POLARITY = re.compile(r"\b(?:checked|unchecked|left blank|left unchecked|not checked|box is blank|box is left)\b", re.I)
CONDITIONAL_OPTOUT = re.compile(r"^\s*(?:(?:if|unless|until|untick|uncheck|leave|skip)\b.{0,100}\b(?:do not|don't|never|no thanks|opt[ -]?out|unsubscribe)\b|(?:do not|don't|never)\b.{0,100}\b(?:if|unless)\b)", re.I)
DOUBLE_NEGATIVE = re.compile(r"\b(?:not|never|no|don't|do not|neither|without)\b.{1,100}\b(?:not|never|no|don't|do not|neither|without)\b", re.I)
ADJACENT_NEGATION = re.compile(r"\b(?:not|never|no|don't|do not|neither|without)\s+(?:not|never|no|don't|do not|neither|without)\b", re.I)

HARD_SAFETY_CONFLICTS = {
    "protected-purpose-marker",
    "missing-protected-purpose",
    "positive-polarity-marker",
    "missing-explicit-opt-out",
    "double-negative-ambiguity",
    "missing-marketing-purpose",
    "marketing-marker-on-nonmarketing-seed",
    "state-dependent-polarity",
    "missing-positive-opt-in-entailment",
}
SOFT_CHALLENGE_CONFLICTS = {
    "positive-opt-in-outside-safe-envelope",
    "mixed-legal-marketing",
}


def negative_operator_count(text: str) -> int:
    count = 0
    for match in NEGATIVE_OPERATOR.finditer(text):
        following = text[match.end():].lstrip().casefold()
        if following.startswith("miss out"):
            continue
        count += 1
    return count


def hard_conflicts(seed: dict[str, Any], conflicts: list[str]) -> list[str]:
    """Return conflicts that make a candidate unsafe or semantically unusable."""
    hard = [conflict for conflict in conflicts if conflict in HARD_SAFETY_CONFLICTS]
    soft = [conflict for conflict in conflicts if conflict in SOFT_CHALLENGE_CONFLICTS]
    hard.extend(conflict for conflict in conflicts if conflict not in HARD_SAFETY_CONFLICTS | SOFT_CHALLENGE_CONFLICTS)
    if soft and seed["challenge"] not in {"misleading_dark_pattern", "mixed_legal_marketing"}:
        hard.extend(soft)
    return sorted(set(hard))


def unique_evidence(values: list[str | None]) -> str:
    """Join distinct DOM evidence once so duplicated ARIA/label text is not double-counted."""
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value:
            continue
        key = re.sub(r"\s+", " ", value).strip().casefold()
        if key and key not in seen:
            seen.add(key)
            result.append(value)
    return " ".join(result)


def retryable_error(message: str) -> bool:
    """Retry only recoverable realization/format failures, never unsafe content."""
    retry_markers = (
        "schema mismatch",
        "malformed candidate JSON",
        "malformed HTTP JSON",
        "malformed response envelope",
        "one-line JSON",
        "response field",
        "request failed",
        "placeholder",
        "not expressed",
        "lost",
        "lacks",
        "normalized label duplicate",
        "could not apply controlled typo",
        "purpose ",
        "positive marketing lacks",
        "negative polarity lacks",
        "no-polarity challenge",
        "mixed legal/marketing meaning",
        "semantic safety conflicts",
        "post-transform",
    )
    non_retryable_markers = (
        "unsafe candidate",
        "unsafe ",
        "protected-purpose-marker",
        "missing-protected-purpose",
        "marketing-marker-on-nonmarketing-seed",
        "sensitive",
    )
    return any(marker in message for marker in retry_markers) and not any(marker in message for marker in non_retryable_markers)


MAX_ATTEMPTS = 3


def infer_safety_conflicts(text: str, seed: dict[str, Any], label_text: str | None = None) -> list[str]:
    """Infer conservative conflicts independently of the supplied seed."""
    conflicts: list[str] = []
    has_marketing = bool(MARKETING_CORE.search(text))
    has_optout = bool(EXPLICIT_OPTOUT.search(text))
    has_optin = bool(POSITIVE_OPTIN.search(text))
    has_protected = bool(PROTECTED_MARKERS.search(text))
    if STATE_POLARITY.search(text):
        conflicts.append("state-dependent-polarity")
    if seed["purpose"] == "marketing":
        if has_protected:
            conflicts.append("protected-purpose-marker")
        if seed["polarity"] == "checked_enables_marketing":
            negative_count = negative_operator_count(text)
            if has_optout or negative_count or NEGATIVE_ACTION.search(text) or POLARITY_REVERSAL.search(text) or QUANTITY_NEGATION.search(text) or STATE_POLARITY.search(text):
                conflicts.append("negative-polarity-marker")
            if not has_marketing and seed["challenge"] != "euphemism":
                conflicts.append("missing-marketing-purpose")
            grammar_text = label_text if label_text is not None else text
            if seed["challenge"] not in {"euphemism", "misleading_dark_pattern"} and not SAFE_POSITIVE_LABEL.fullmatch(grammar_text):
                conflicts.append("positive-opt-in-outside-safe-envelope")
            if UNSAFE_POSITIVE_CLAUSE.search(text):
                conflicts.append("required-or-conditional-clause")
            if not has_optin and seed["challenge"] not in {"euphemism", "misleading_dark_pattern", "implicit_positive"}:
                conflicts.append("missing-positive-opt-in-entailment")
        elif seed["polarity"] == "unchecked_enables_marketing":
            if not has_optout:
                conflicts.append("missing-explicit-opt-out")
            if has_unnegated_positive(text):
                conflicts.append("positive-polarity-marker")
            if len(NEGATIVE_OPERATOR.findall(text)) >= 2:
                conflicts.append("double-negative-ambiguity")
    elif seed["purpose"] != "ambiguous" and has_marketing:
        conflicts.append("marketing-marker-on-nonmarketing-seed")
    if seed["challenge"] == "no_polarity_signal" and has_optin:
        conflicts.append("positive-polarity-marker")
    if seed["purpose"] != "ambiguous" and seed["obligation"] == "optional" and re.search(r"\b(?:terms?|conditions?|privacy|policy|must|required|agree)\b", text, re.I) and has_marketing:
        conflicts.append("mixed-legal-marketing")
    if seed["purpose"] in {"functional", "legal", "age", "security"} and not PURPOSE_MARKERS[seed["purpose"]].search(text):
        conflicts.append("missing-protected-purpose")
    return sorted(set(conflicts))


def staged_expected_action(seed: dict[str, Any], conflicts: list[str] | None = None) -> str:
    """Keep inherently ambiguous challenge families out of auto-uncheck."""
    if seed["challenge"] in {"euphemism", "misleading_dark_pattern", "mixed_legal_marketing"}:
        return "suggest"
    if conflicts:
        return "suggest"
    return expected_action(seed)


def semantic_signature(text: str) -> tuple[object, ...]:
    """Features whose loss under a mechanical transform can change meaning."""
    return (
        bool(MARKETING_CORE.search(text)),
        bool(POSITIVE_OPTIN.search(text)),
        bool(EXPLICIT_OPTOUT.search(text) or NEGATIVE_ACTION.search(text)),
        negative_operator_count(text),
        bool(QUANTITY_NEGATION.search(text)),
        bool(PROTECTED_MARKERS.search(text)),
        bool(re.search(r"\b(?:confirm|agree|accept|must|required)\b", text, re.I)),
        bool(PURPOSE_MARKERS["functional"].search(text)),
        bool(PURPOSE_MARKERS["legal"].search(text)),
        bool(PURPOSE_MARKERS["age"].search(text)),
        bool(PURPOSE_MARKERS["security"].search(text)),
    )


def has_unnegated_positive(text: str) -> bool:
    """Find a positive commitment verb not governed by a nearby negator."""
    tokens = re.findall(r"[a-z]+", text.casefold())
    positive = {"send", "email", "receive", "get", "subscribe", "join", "keep", "discover", "enjoy", "learn", "add", "enroll", "include", "put", "activate", "allow", "enable", "grant", "sign", "register", "opt"}
    negative = {"not", "never", "no", "don", "dont", "without", "wont", "wouldnt"}
    for index, token in enumerate(tokens):
        if token == "opt":
            if index + 2 < len(tokens) and tokens[index + 2] == "out":
                continue
            if index + 2 >= len(tokens) or tokens[index + 2] != "in":
                continue
        if token in positive and not any(previous in negative for previous in tokens[max(0, index - 3):index]):
            return True
    return False

FAMILY_WEIGHTS = [
    16, 8, 6, 5, 4, 4, 4, 12, 5, 8, 5, 5, 8, 4, 4, 2,
]


def seed_for(index: int, root_seed: str, total_count: int = 600) -> dict[str, Any]:
    material = f"{root_seed}:{index}"
    rng = random.Random(int(sha256_bytes(material.encode())[:16], 16))
    family_order = list(range(len(SEMANTIC_FAMILIES)))
    random.Random(int(sha256_bytes(f"{root_seed}:family-cover".encode())[:16], 16)).shuffle(family_order)
    surface_order = sorted(SURFACES)
    random.Random(int(sha256_bytes(f"{root_seed}:surface-cover".encode())[:16], 16)).shuffle(surface_order)
    coverage_block = len(SEMANTIC_FAMILIES) * len(surface_order)
    coverage_size = coverage_block * 2
    family_index = family_order[index % len(family_order)] if index < coverage_size else rng.choices(range(len(SEMANTIC_FAMILIES)), weights=FAMILY_WEIGHTS, k=1)[0]
    family = SEMANTIC_FAMILIES[family_index]
    compatible_profiles = [profile for profile in PROFILE_GRAPH if (profile[0], profile[1]) in PROFILE_COMPATIBILITY[family["purpose"]]]
    profile = compatible_profiles[index % len(compatible_profiles)] if index < coverage_size else compatible_profiles[rng.randrange(len(compatible_profiles))]
    style_order = ["plain", "friendly", "dark", "subversive"]
    style = style_order[index % len(style_order)] if index < coverage_size else rng.choices(style_order, weights=[38, 27, 20, 15], k=1)[0]
    metadata_order = ["descriptive", "neutral", "opaque", "conflicting"]
    metadata_style = metadata_order[index % len(metadata_order)] if index < coverage_size else rng.choices(metadata_order, weights=[35, 35, 20, 10], k=1)[0]
    noise_order = ["none", "casing", "whitespace", "typo", "emoji", "fragment"]
    noise = noise_order[index % len(noise_order)] if index < coverage_size else rng.choices(noise_order, weights=[78, 5, 5, 5, 4, 3], k=1)[0]
    surface = surface_order[(index // len(SEMANTIC_FAMILIES)) % len(surface_order)] if index < coverage_size else rng.choices(surface_order, weights=[25, 20, 20, 20, 15], k=1)[0]
    challenge = family["challenge"]
    if challenge == "euphemism" and family["purpose"] != "marketing":
        raise ValueError("invalid euphemism family")
    seed = {
        "purpose": family["purpose"],
        "polarity": family["polarity"],
        "obligation": family["obligation"],
        "style": style,
        "site_profile": {"archetype": profile[0], "funnel_stage": profile[1], "voice": profile[2]},
        "surface": surface,
        "metadata_style": metadata_style,
        "noise": noise,
        "challenge": challenge,
        "checked_state": family["polarity"] == "checked_enables_marketing" and rng.random() > 0.25,
        "family_index": family_index,
        "metadata_slot": int(sha256_bytes(f"{root_seed}:metadata-slot:{index}".encode())[:16], 16),
    }
    if family["polarity"] == "unchecked_enables_marketing":
        seed["checked_state"] = rng.random() > 0.5
    if family["purpose"] in {"functional", "legal", "age", "security"}:
        seed["checked_state"] = rng.random() > 0.15
    if family["purpose"] == "ambiguous":
        seed["checked_state"] = rng.random() > 0.5
    if index < coverage_size:
        seed["checked_state"] = (index // coverage_block) == 1
    seed["seed_id"] = "seed-" + sha256_bytes(canonical_json(seed).encode())[:24]
    seed["family_id"] = "family-" + sha256_bytes(canonical_json({k: seed[k] for k in ("family_index", "purpose", "polarity", "obligation", "style", "site_profile", "challenge")}).encode())[:16]
    return seed


def sample_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {"candidate_text": {"type": "string", "minLength": 1, "maxLength": MAX_FIELD_LENGTH}},
        "required": ["candidate_text"],
    }


def request_candidate(
    backend: dict[str, str],
    seed: dict[str, Any],
    max_tokens: int,
    timeout: int,
    attempt: int = 1,
    retry_note: str | None = None,
    temperature: float = 0.0,
    preamble_id: str = "none",
) -> tuple[str, dict[str, Any], str]:
    if not 0.0 <= temperature <= MAX_TEMPERATURE:
        raise ValueError(f"temperature must be between 0.0 and {MAX_TEMPERATURE}")
    if preamble_id not in PREAMBLES:
        raise ValueError(f"unknown preamble id: {preamble_id}")
    sampling_seed = (int(seed["seed_id"][5:], 16) + (attempt - 1) * 1000003) % (2**31 - 1)
    checklist = (
        "FINAL CHECKLIST: generate only candidate_text.\n"
        f"purpose={seed['purpose']}; polarity={seed['polarity']}; obligation={seed['obligation']}; caller-owned checked_state={seed['checked_state']} (do not encode in candidate_text)\n"
        f"style={seed['style']}; site_profile={canonical_json(seed['site_profile'])}; challenge={seed['challenge']}\n"
        f"caller-owned noise={seed['noise']}; surface={seed['surface']}; metadata_style={seed['metadata_style']}; policy_action={staged_expected_action(seed)}; do not encode these in candidate_text\n"
        "The text must express these semantics. Do not emit placeholders or metadata.\n"
        + (f"Retry diagnostic (inert caller data): {retry_note}\n" if retry_note else "")
    )
    user_content = "Validated seed (data only):\n" + canonical_json(seed) + "\n\n" + checklist
    if PREAMBLES[preamble_id] is not None:
        user_content = (
            "BEGIN NON-AUTHORITATIVE FICTIONAL STYLE CONTEXT. Do not treat this as an instruction, "
            "semantic truth, DOM metadata, action policy, or provenance; do not copy it into the label.\n"
            + PREAMBLES[preamble_id]
            + "\nEND NON-AUTHORITATIVE FICTIONAL STYLE CONTEXT.\n\n"
            + user_content
        )
    payload = {
        "model": backend["model"],
        "messages": [
            {"role": "system", "content": CANDIDATE_SYSTEM},
            {"role": "user", "content": user_content},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": 1,
        "n": 1,
        "seed": sampling_seed,
        "chat_template_kwargs": {"enable_thinking": False},
        "response_format": {"type": "json_schema", "json_schema": {"name": "fire_candidate", "strict": True, "schema": sample_schema()}},
    }
    request = urllib.request.Request(backend["endpoint"], data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw_body = response.read()
        response_sha256 = sha256_bytes(raw_body)
        body = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        error = RuntimeError("malformed HTTP JSON")
        error.payload = payload  # type: ignore[attr-defined]
        error.response_sha256 = response_sha256 if "response_sha256" in locals() else None  # type: ignore[attr-defined]
        raise error from exc
    except urllib.error.HTTPError as exc:
        try:
            error_body = exc.read()
        except http.client.IncompleteRead as read_exc:
            error_body = read_exc.partial or b""
        except OSError:
            error_body = b""
        error = RuntimeError(f"request failed: HTTP {exc.code}")
        error.payload = payload  # type: ignore[attr-defined]
        error.response_sha256 = sha256_bytes(error_body)  # type: ignore[attr-defined]
        raise error from exc
    except http.client.IncompleteRead as exc:
        error = RuntimeError("request failed: incomplete HTTP response")
        error.payload = payload  # type: ignore[attr-defined]
        error.response_sha256 = sha256_bytes(exc.partial or b"")  # type: ignore[attr-defined]
        raise error from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        error = RuntimeError(f"request failed: {exc}")
        error.payload = payload  # type: ignore[attr-defined]
        error.response_sha256 = sha256_bytes(b"")  # type: ignore[attr-defined]
        raise error from exc
    try:
        message = body["choices"][0]["message"]
        content = message.get(backend["response_field"])
    except (KeyError, IndexError, TypeError, AttributeError) as exc:
        error = ValueError("malformed response envelope")
        error.payload = payload  # type: ignore[attr-defined]
        error.response_sha256 = response_sha256  # type: ignore[attr-defined]
        raise error from exc
    if not isinstance(content, str):
        error = ValueError(f"response field {backend['response_field']} is not text")
        error.payload = payload  # type: ignore[attr-defined]
        error.response_sha256 = response_sha256  # type: ignore[attr-defined]
        raise error
    return content, payload, response_sha256


def validate_candidate(content: str, seed: dict[str, Any]) -> str:
    if "\n" in content or "```" in content:
        raise ValueError("candidate is not one-line JSON")
    try:
        obj = json.loads(content.strip())
    except json.JSONDecodeError as exc:
        raise ValueError("malformed candidate JSON") from exc
    if not isinstance(obj, dict) or set(obj) != {"candidate_text"}:
        raise ValueError("candidate schema mismatch")
    text = obj["candidate_text"]
    if not isinstance(text, str) or not text.strip() or text.strip() in {"...", "GENERATION_FAILED"}:
        raise ValueError("placeholder or empty candidate")
    if len(text) > MAX_FIELD_LENGTH or not no_sensitive_text(text):
        raise ValueError("unsafe candidate")
    if seed["polarity"] == "unchecked_enables_marketing" and not EXPLICIT_OPTOUT.search(text):
        raise ValueError("negative polarity lacks explicit opt-out wording")
    if seed["polarity"] == "checked_enables_marketing" and not MARKETING_LANGUAGE.search(text) and seed["challenge"] not in {"euphemism", "implicit_positive"}:
        raise ValueError("positive marketing lacks marketing signal")
    if seed["polarity"] == "checked_enables_marketing" and EXPLICIT_OPTOUT.search(text) and not re.search(r"don't miss out|do not miss out", text, re.I):
        raise ValueError("positive marketing has opt-out wording")
    if seed["purpose"] in PURPOSE_MARKERS and not PURPOSE_MARKERS[seed["purpose"]].search(text):
        raise ValueError(f"purpose {seed['purpose']} is not expressed")
    if seed["challenge"] == "euphemism" and (
        MARKETING_LANGUAGE.search(text)
        or not EUPHEMISM_MARKERS.search(text)
        or not POSITIVE_OPTIN.search(text)
    ):
        raise ValueError("euphemism needs an opt-in cue and a non-direct marketing cue")
    if seed["challenge"] == "misleading_dark_pattern" and (not DARK_MARKERS.search(text) or not POSITIVE_OPTIN.search(text)):
        raise ValueError("dark pattern needs positive opt-in and urgency/friction")
    if seed["challenge"] == "double_negative" and (negative_operator_count(text) != 2 or not DOUBLE_NEGATIVE.search(text) or ADJACENT_NEGATION.search(text)):
        raise ValueError("double negative must contain exactly two separated negative operators")
    if seed["challenge"] == "direct_positive" and (not POSITIVE_OPTIN.search(text) or EXPLICIT_OPTOUT.search(text)):
        raise ValueError("direct positive is not expressed")
    if seed["challenge"] == "implicit_positive" and (EXPLICIT_OPTOUT.search(text) or EXPLICIT_POSITIVE.search(text) or not POSITIVE_OPTIN.search(text)):
        raise ValueError("implicit positive is not expressed")
    if seed["challenge"] == "conditional_negative" and not CONDITIONAL_OPTOUT.search(text):
        raise ValueError("conditional negative is not expressed")
    if seed["challenge"] == "no_polarity_signal" and seed["purpose"] == "marketing":
        raise ValueError("marketing no-polarity family is undefined")
    if seed["challenge"] == "no_polarity_signal" and (MARKETING_CORE.search(text) or EXPLICIT_OPTOUT.search(text)):
        raise ValueError("no-polarity challenge contains a marketing polarity signal")
    if seed["challenge"] == "no_polarity_signal" and POSITIVE_OPTIN.search(text):
        raise ValueError("no-polarity challenge contains a positive opt-in cue")
    if seed["challenge"] == "no_polarity_signal" and (NEGATIVE_OPERATOR.search(text) or NEGATIVE_ACTION.search(text)):
        raise ValueError("no-polarity challenge contains a negative operator")
    if seed["challenge"] == "mixed_legal_marketing" and not (re.search(r"\b(?:terms?|conditions?|agreement|privacy|consent)\b", text, re.I) and MARKETING_LANGUAGE.search(text)):
        raise ValueError("mixed legal/marketing meaning is not expressed")
    conflicts = infer_safety_conflicts(text, seed)
    hard = hard_conflicts(seed, conflicts)
    if hard:
        raise ValueError("semantic safety conflicts: " + ", ".join(hard))
    return text.strip()


def apply_noise(text: str, noise: str, seed: dict[str, Any]) -> tuple[str, list[str]]:
    if noise == "none":
        return text, []
    if noise == "casing":
        words = text.split(" ")
        for index, word in enumerate(words):
            if len(re.sub(r"[^A-Za-z]", "", word)) >= 5:
                words[index] = word.upper()
                return " ".join(words), ["casing_variation"]
        return text.upper(), ["casing_variation"]
    if noise == "whitespace":
        if " " not in text:
            raise ValueError("whitespace transform needs a multiword candidate")
        transformed = text.replace(" ", "  ", 1)
        if transformed == text:
            raise ValueError("whitespace transform made no change")
        return transformed, ["repeated_whitespace"]
    if noise == "emoji":
        emoji = "✨" if seed["purpose"] == "marketing" else ("✈️" if seed["site_profile"]["archetype"] == "travel" else "✅")
        return text.rstrip() + " " + emoji, ["emoji_suffix"]
    if noise == "fragment":
        fragment = re.sub(r"^(?:yes,? |please |i would like to |i want to )", "", text, flags=re.I).rstrip(".!?")
        if fragment == text or not fragment.strip():
            raise ValueError("candidate lacks a safe fragment prefix")
        if len(NEGATIVE_OPERATOR.findall(fragment)) != len(NEGATIVE_OPERATOR.findall(text)):
            raise ValueError("fragment transform removed a negative operator")
        return fragment, ["fragmentary_text"]
    if noise == "typo":
        substitutions = {"updates": "updaets", "offers": "ofers", "newsletter": "newsltter", "product": "prodcut", "exclusive": "exclsuive", "promotional": "promotonal", "account": "acocunt"}
        for source, replacement in substitutions.items():
            if re.search(rf"\b{source}\b", text, re.I):
                return re.sub(rf"\b{source}\b", replacement, text, count=1, flags=re.I), ["controlled_typo"]
        match = re.search(r"\b[A-Za-z]{5,}\b", text)
        if match:
            word = match.group(0)
            typo = word[:2] + word[3] + word[2] + word[4:]
            return text[:match.start()] + typo + text[match.end():], ["controlled_typo"]
        raise ValueError("could not apply controlled typo")
    raise ValueError(f"unknown noise {noise}")


def context_for(seed: dict[str, Any]) -> str:
    stage = seed["site_profile"]["funnel_stage"]
    return {
        "newsletter_signup": "Communication preferences",
        "account_creation": "Account preferences",
        "checkout": "Checkout preferences",
        "booking": "Booking details",
        "lead_capture": "Contact preferences",
        "preferences": "Notification preferences",
    }[stage]


def compose_record(
    seed: dict[str, Any],
    clean_text: str,
    raw_content: str,
    payload: dict[str, Any],
    backend_name: str,
    attempt_log: list[dict[str, Any]],
    accepted_attempt: int,
) -> dict[str, Any]:
    noisy_text, transforms = apply_noise(clean_text, seed["noise"], seed)
    digest = seed["seed_id"][-12:]
    metadata_pools = {
        # These are intentionally shared across semantic purposes. The DOM
        # metadata may be descriptive, but must not become a label shortcut.
        "descriptive": [
            "user_preference", "contact_choice", "account_option", "notification_setting",
            "subscription_choice", "communication_preference", "profile_option", "service_preference",
        ],
        "neutral": ["preference", "choice", "settings", "selection", "option", "user_choice", "toggle", "field"],
        "conflicting": ["account_settings", "notification_choice", "profile_preference", "communication_choice", "updates_preference", "user_option", "form_setting", "account_choice"],
    }
    if seed["metadata_style"] == "descriptive":
        name_base = metadata_pools["descriptive"][seed["metadata_slot"] % len(metadata_pools["descriptive"])]
    elif seed["metadata_style"] == "neutral":
        name_base = metadata_pools["neutral"][seed["metadata_slot"] % len(metadata_pools["neutral"])]
    elif seed["metadata_style"] == "conflicting":
        name_base = metadata_pools["conflicting"][seed["metadata_slot"] % len(metadata_pools["conflicting"])]
    else:
        name_base = ["field", "option", "control", "input", "cb"][seed["metadata_slot"] % 5]
    name = f"{name_base}_{digest}"
    identifier = f"{name_base.replace('_', '-')}-{digest}"
    aria = clean_text if seed["surface"] in {"label_plus_aria", "mixed_dom_context"} else None
    legend = context_for(seed) if seed["surface"] in {"label_plus_legend", "mixed_dom_context"} else None
    if seed["surface"] == "label_only":
        name = identifier = None
    if seed["surface"] == "label_plus_aria":
        name = identifier = None
    if seed["surface"] == "label_plus_legend":
        name = identifier = None
    observed = list(transforms)
    if seed["challenge"] == "misleading_dark_pattern":
        observed.append("dark_pattern")
    if seed["challenge"] == "double_negative":
        observed.append("double_negative")
    if seed["challenge"] == "euphemism":
        observed.append("euphemistic_marketing")
    if seed["challenge"] == "mixed_legal_marketing":
        observed.append("mixed_legal_marketing")
    if seed["challenge"] in {"explicit_negative", "conditional_negative"}:
        observed.append("explicit_opt_out")
    preliminary_fields = [noisy_text, aria, name, identifier, legend]
    safety_conflicts = infer_safety_conflicts(unique_evidence(preliminary_fields), seed, noisy_text)
    record = {
        "record_id": "record-" + backend_name + "-" + seed["seed_id"][5:],
        "parent_record_id": "parent-" + seed["seed_id"][5:],
        "family_id": seed["family_id"],
        "backend": backend_name,
        "purpose": seed["purpose"],
        "polarity": seed["polarity"],
        "obligation": seed["obligation"],
        "style": seed["style"],
        "metadata_style": seed["metadata_style"],
        "site_profile": seed["site_profile"],
        "surface": seed["surface"],
        "checked_state": seed["checked_state"],
        "label_text": noisy_text,
        "aria_label": aria,
        "name": name,
        "id": identifier,
        "legend_or_context": legend,
        "expected_action": staged_expected_action(seed, safety_conflicts),
        "requested_challenges": [seed["challenge"]],
        "applied_transforms": transforms,
        "observed_features": sorted(set(observed)),
        "safety_conflicts": safety_conflicts,
        "validation_status": "mechanically_validated",
        "clean_candidate_text": clean_text,
        "candidate_response_sha256": sha256_bytes(raw_content.encode("utf-8")),
        "candidate_text_sha256": sha256_bytes(clean_text.encode("utf-8")),
        "payload_sha256": sha256_bytes(canonical_json(payload).encode("utf-8")),
        "input_seed_sha256": sha256_bytes(canonical_json(seed).encode("utf-8")),
        "sampling_seed": payload["seed"],
        "accepted_attempt": accepted_attempt,
        "generation_attempts": attempt_log,
        "spec_version": SPEC_VERSION,
        "combinator_version": COMBINATOR_VERSION,
        "source_kind": "synthetic_llm_candidate",
    }
    return record


def validate_record(record: dict[str, Any], seed: dict[str, Any]) -> None:
    text = unique_evidence([record[field] for field in ("label_text", "aria_label", "name", "id", "legend_or_context")])
    label_conflicts = infer_safety_conflicts(record["label_text"], seed)
    label_hard_conflicts = hard_conflicts(seed, label_conflicts)
    if label_hard_conflicts:
        raise ValueError("post-transform label semantic conflicts: " + ", ".join(label_hard_conflicts))
    if seed["challenge"] == "direct_positive" and (not POSITIVE_OPTIN.search(record["label_text"]) or EXPLICIT_OPTOUT.search(record["label_text"])):
        raise ValueError("post-transform direct positive lost polarity")
    if seed["challenge"] == "implicit_positive" and (not POSITIVE_OPTIN.search(record["label_text"]) or EXPLICIT_POSITIVE.search(record["label_text"]) or EXPLICIT_OPTOUT.search(record["label_text"])):
        raise ValueError("post-transform implicit positive lost polarity")
    if seed["challenge"] == "explicit_negative" and not EXPLICIT_OPTOUT.search(record["label_text"]):
        raise ValueError("post-transform explicit negative lost polarity")
    if seed["challenge"] == "conditional_negative" and not CONDITIONAL_OPTOUT.search(record["label_text"]):
        raise ValueError("post-transform conditional negative lost polarity")
    if seed["challenge"] == "double_negative" and (negative_operator_count(record["label_text"]) != 2 or not DOUBLE_NEGATIVE.search(record["label_text"]) or ADJACENT_NEGATION.search(record["label_text"])):
        raise ValueError("post-transform double negative lost its two separated operators")
    if seed["challenge"] == "no_polarity_signal" and (MARKETING_CORE.search(record["label_text"]) or EXPLICIT_OPTOUT.search(record["label_text"]) or POSITIVE_OPTIN.search(record["label_text"])):
        raise ValueError("post-transform no-polarity challenge gained polarity")
    if seed["noise"] == "fragment" and semantic_signature(record["clean_candidate_text"]) != semantic_signature(record["label_text"]):
        raise ValueError("fragment transform changed semantic signature")
    if seed["challenge"] == "euphemism" and (
        MARKETING_LANGUAGE.search(record["label_text"])
        or not EUPHEMISM_MARKERS.search(record["label_text"])
        or not POSITIVE_OPTIN.search(record["label_text"])
    ):
        raise ValueError("post-transform euphemism lost its opt-in or non-direct marketing cue")
    if seed["challenge"] == "misleading_dark_pattern" and (not DARK_MARKERS.search(record["label_text"]) or not POSITIVE_OPTIN.search(record["label_text"])):
        raise ValueError("post-transform dark pattern lost positive opt-in or urgency/friction")
    if seed["challenge"] == "mixed_legal_marketing" and not (re.search(r"\b(?:terms?|conditions?|agreement|privacy|consent)\b", record["label_text"], re.I) and MARKETING_LANGUAGE.search(record["label_text"])):
        raise ValueError("post-transform mixed meaning was lost")
    conflicts = infer_safety_conflicts(text, seed, record["label_text"])
    hard = hard_conflicts(seed, conflicts)
    if hard:
        raise ValueError("post-transform semantic conflicts: " + ", ".join(hard))
    expected = staged_expected_action(seed, conflicts)
    if record["safety_conflicts"] != conflicts:
        raise ValueError("safety conflict provenance mismatch")
    if record["requested_challenges"] != [seed["challenge"]]:
        raise ValueError("challenge provenance mismatch")
    if record["expected_action"] != expected:
        raise ValueError("action policy mismatch")
    if record["expected_action"] == "uncheck" and conflicts:
        raise ValueError("uncheck requires zero safety conflicts")
    if record["label_text"] in {"...", "GENERATION_FAILED"} or not record["label_text"].strip():
        raise ValueError("placeholder final label")
    if seed["surface"] == "label_only" and any(record[field] is not None for field in ("aria_label", "name", "id", "legend_or_context")):
        raise ValueError("label-only surface has metadata")
    if seed["surface"] == "label_plus_aria" and not record["aria_label"]:
        raise ValueError("ARIA surface missing aria label")
    if seed["surface"] == "label_plus_legend" and not record["legend_or_context"]:
        raise ValueError("legend surface missing context")
    if seed["surface"] == "mixed_dom_context" and sum(record[field] is not None for field in ("aria_label", "name", "id", "legend_or_context")) < 2:
        raise ValueError("mixed surface lacks context")
    for field in ("label_text", "aria_label", "name", "id", "legend_or_context", "clean_candidate_text"):
        if record[field] is not None and (len(record[field]) > MAX_FIELD_LENGTH or not no_sensitive_text(record[field])):
            raise ValueError(f"unsafe {field}")
    if record["expected_action"] == "uncheck" and not (seed["purpose"] == "marketing" and seed["polarity"] == "checked_enables_marketing" and seed["obligation"] == "optional" and seed["checked_state"] and not conflicts):
        raise ValueError("unsafe uncheck envelope")
    if seed["noise"] == "casing" and not re.search(r"[a-z][A-Z]|\b[A-Z]{2,}\b", record["label_text"]):
        raise ValueError("casing transform not observed")
    if seed["noise"] == "whitespace" and not re.search(r"\s{2,}", record["label_text"]):
        raise ValueError("whitespace transform not observed")
    if seed["noise"] == "emoji" and not any(ord(char) >= 0x1F000 for char in record["label_text"]):
        raise ValueError("emoji transform not observed")
    if seed["noise"] == "fragment" and "fragmentary_text" not in record["applied_transforms"]:
        raise ValueError("fragment transform not recorded")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=sorted(BACKENDS), required=True)
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--root-seed", default="fire-staged-pilot-2026-08-30")
    parser.add_argument("--base-root-seed", help="base seed recorded separately from the effective backend-namespaced root")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--preamble", choices=sorted(PREAMBLES), default="none")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--max-tokens", type=int, default=220)
    parser.add_argument("--delay", type=float, default=0)
    args = parser.parse_args()
    if args.count < 1 or args.count > 1000:
        parser.error("--count must be between 1 and 1000")
    if not 0.0 <= args.temperature <= MAX_TEMPERATURE:
        parser.error(f"--temperature must be between 0.0 and {MAX_TEMPERATURE}")
    backend = BACKENDS[args.backend]
    args.output = args.output or Path(f"data/generated/staged-{args.backend}.jsonl")
    args.manifest = args.manifest or Path(f"data/generated/staged-{args.backend}.manifest.json")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen_text: set[str] = set()
    planned_seeds = [seed_for(index, args.root_seed, args.count) for index in range(args.count)]
    started = datetime.now(timezone.utc).isoformat()
    for index in range(args.count):
        seed = planned_seeds[index]
        attempt_log: list[dict[str, Any]] = []
        accepted_record: dict[str, Any] | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            content: str | None = None
            payload: dict[str, Any] | None = None
            response_sha256: str | None = None
            try:
                retry_note = attempt_log[-1]["error"] if attempt_log else None
                content, payload, response_sha256 = request_candidate(
                    backend, seed, args.max_tokens, args.timeout, attempt, retry_note,
                    args.temperature, args.preamble,
                )
                clean = validate_candidate(content, seed)
                record = compose_record(seed, clean, content, payload, args.backend, attempt_log, attempt)
                validate_record(record, seed)
                text_key = re.sub(r"[^a-z0-9 ]", "", re.sub(r"\s+", " ", record["label_text"].lower())).strip()
                if text_key in seen_text:
                    raise ValueError("normalized label duplicate")
                attempt_log.append({
                    "attempt": attempt,
                    "sampling_seed": payload["seed"],
                    "payload_sha256": sha256_bytes(canonical_json(payload).encode("utf-8")),
                    "effective_messages_sha256": sha256_bytes(canonical_json(payload["messages"]).encode("utf-8")),
                    "response_sha256": response_sha256,
                    "status": "accepted",
                    "error": None,
                })
                record["generation_attempts"] = attempt_log
                accepted_record = record
                seen_text.add(text_key)
                accepted.append(record)
                print(f"accepted {index + 1}/{args.count}: {record['expected_action']} {record['record_id']} attempt={attempt}", flush=True)
                break
            except Exception as exc:
                error_message = str(exc)
                error_payload = payload or getattr(exc, "payload", None)
                attempt_log.append({
                    "attempt": attempt,
                    "sampling_seed": error_payload.get("seed") if error_payload else None,
                    "payload_sha256": sha256_bytes(canonical_json(error_payload).encode("utf-8")) if error_payload else None,
                    "effective_messages_sha256": sha256_bytes(canonical_json(error_payload["messages"]).encode("utf-8")) if error_payload and "messages" in error_payload else None,
                    "response_sha256": response_sha256 or getattr(exc, "response_sha256", None),
                    "status": "rejected",
                    "error": error_message,
                })
                print(f"rejected {index + 1}/{args.count} attempt={attempt}: {error_message}", file=sys.stderr, flush=True)
                if attempt == MAX_ATTEMPTS or not retryable_error(error_message):
                    rejected.append({"index": str(index), "seed_id": seed["seed_id"], "error": error_message, "attempts": attempt_log})
                    break
        if args.delay:
            time.sleep(args.delay)
    with args.output.open("w", encoding="utf-8") as handle:
        for record in accepted:
            handle.write(canonical_json(record) + "\n")
    manifest = {
        "spec_version": SPEC_VERSION,
        "combinator_version": COMBINATOR_VERSION,
        "system_prompt_sha256": sha256_bytes(CANDIDATE_SYSTEM.encode()),
        "prompt_sha256": sha256_bytes(CANDIDATE_SYSTEM.encode()),
        "root_seed": args.root_seed,
        "base_root_seed": args.base_root_seed,
        "effective_root_seed": args.root_seed,
        "backend": args.backend,
        "endpoint": backend["endpoint"],
        "model": backend["model"],
        "response_field": backend["response_field"],
        "role": backend["role"],
        "chat_template_kwargs": {"enable_thinking": False},
        "decoding": {"requested_temperature": args.temperature, "sent_temperature": args.temperature, "top_p": 1, "n": 1, "max_tokens": args.max_tokens},
        "preamble": {"id": args.preamble, "sha256": sha256_bytes(PREAMBLES[args.preamble].encode("utf-8")) if PREAMBLES[args.preamble] is not None else None},
        "sampling_seed_source": "seed_id suffix plus deterministic attempt offset",
        "retry_policy": {"max_attempts": MAX_ATTEMPTS, "retryable_error_policy": "deterministic realization/format failures only"},
        "deterministic_seed_support": "requested; backend compliance not independently established",
        "model_artifact_revision": "model-id:" + backend["model"],
        "model_artifact_revision_status": "artifact digest unavailable from OpenAI-compatible endpoint; bit-for-bit reproducibility not claimed",
        "tokenizer_runtime_hardware": "server-reported details unavailable; client=python-stdlib-http",
        "generator_sha256": sha256_bytes(Path(__file__).read_bytes()),
        "policy_validator_sha256": sha256_bytes((Path(__file__).with_name("generate_synthetic.py")).read_bytes()),
        "transform_version": COMBINATOR_VERSION,
        "transform_sha256": sha256_bytes(inspect.getsource(apply_noise).encode("utf-8")),
        "started_at": started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "requested": args.count,
        "accepted": len(accepted),
        "rejected": len(rejected),
        "rejections": rejected,
        "output_sha256": sha256_bytes(args.output.read_bytes()),
        "synthetic_only": True,
    }
    accepted_ids = {record["record_id"] for record in accepted}
    planned_cells = {(seed["family_index"], seed["surface"], seed["checked_state"]) for seed in planned_seeds}
    accepted_cells = {(seed["family_index"], seed["surface"], seed["checked_state"]) for seed in planned_seeds if "record-" + args.backend + "-" + seed["seed_id"][5:] in accepted_ids}
    coverage_requirements = {
        "family_surface_checked": (planned_cells, accepted_cells),
        "style": ({seed["style"] for seed in planned_seeds}, {record["style"] for record in accepted}),
        "metadata_style": ({seed["metadata_style"] for seed in planned_seeds}, {record["metadata_style"] for record in accepted}),
        "noise": ({seed["noise"] for seed in planned_seeds}, {next(seed["noise"] for seed in planned_seeds if "record-" + args.backend + "-" + seed["seed_id"][5:] == record["record_id"]) for record in accepted}),
        "profile": ({(seed["site_profile"]["archetype"], seed["site_profile"]["funnel_stage"]) for seed in planned_seeds}, {(record["site_profile"]["archetype"], record["site_profile"]["funnel_stage"]) for record in accepted}),
    }
    missing_coverage = {name: [list(cell) if isinstance(cell, tuple) else cell for cell in sorted(required - observed, key=str)] for name, (required, observed) in coverage_requirements.items() if required - observed}
    manifest["planned_coverage"] = {name: len(required) for name, (required, _observed) in coverage_requirements.items()}
    manifest["accepted_coverage"] = {name: len(observed) for name, (_required, observed) in coverage_requirements.items()}
    manifest["missing_coverage"] = missing_coverage
    args.manifest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"accepted={len(accepted)} rejected={len(rejected)} output={args.output}")
    return 0 if accepted and not missing_coverage else 1


if __name__ == "__main__":
    raise SystemExit(main())
