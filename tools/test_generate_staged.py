#!/usr/bin/env python3
"""Pure unit tests for the staged generator's safety and retry policy."""

from __future__ import annotations

import json
import unittest

from generate_staged import (
    MAX_TEMPERATURE,
    PREAMBLES,
    compose_record,
    hard_conflicts,
    infer_safety_conflicts,
    retryable_error,
    seed_for,
    staged_expected_action,
    validate_candidate,
    validate_record,
)


def seed_matching(**wanted):
    for index in range(600):
        seed = seed_for(index, "fire-v1.3-unit-tests", 600)
        if all(seed[key] == value for key, value in wanted.items()):
            return seed
    raise AssertionError(f"no seed matched {wanted}")


class StagedGeneratorTests(unittest.TestCase):
    def test_diversity_knobs_are_bounded_and_allowlisted(self):
        self.assertEqual(PREAMBLES["none"], None)
        self.assertEqual(PREAMBLES["ted-flower-shop"], "You are running Ted's flower shop.")
        self.assertEqual(MAX_TEMPERATURE, 0.2)

    def test_safe_positive_is_the_only_auto_action_shape(self):
        seed = seed_matching(purpose="marketing", challenge="direct_positive")
        seed["checked_state"] = True
        validate_candidate(json.dumps({"candidate_text": "Send me occasional product updates"}), seed)
        conflicts = infer_safety_conflicts("Send me occasional product updates", seed)
        self.assertEqual(conflicts, [])
        self.assertEqual(staged_expected_action(seed, conflicts), "uncheck")

    def test_safe_positive_survives_all_dom_surfaces(self):
        for surface in ("label_only", "label_plus_aria", "label_plus_name_id", "label_plus_legend", "mixed_dom_context"):
            with self.subTest(surface=surface):
                seed = seed_matching(purpose="marketing", challenge="direct_positive")
                seed["checked_state"] = True
                seed["surface"] = surface
                payload = {"seed": 1}
                record = compose_record(
                    seed,
                    "Send me occasional product updates",
                    '{"candidate_text":"Send me occasional product updates"}',
                    payload,
                    "test",
                    [],
                    1,
                )
                validate_record(record, seed)
                self.assertEqual(record["expected_action"], "uncheck")

    def test_freedom_from_is_not_positive_opt_in(self):
        seed = seed_matching(purpose="marketing", challenge="direct_positive")
        for text in (
            "Get freedom from promotional emails",
            "Get protection against promotional emails",
            "Get immunity against promotional emails",
            "Get immunity to promotional emails",
            "Get rid of promotional emails",
            "Get away from promotional emails",
            "Get out of promotional emails",
            "I would like an exemption from product updates",
            "I would like a break from product updates",
            "Get respite from promotional emails",
            "Get a reprieve from promotional emails",
            "Get release from promotional emails",
            "Get marketing-free product updates",
            "Get blocked from promotional emails",
            "Get excluded from promotional emails",
            "Get removed from promotional emails",
            "Get barred from promotional emails",
            "Get disconnected from promotional emails",
            "Get removal of promotional emails",
            "Get suppression of promotional emails",
            "Enjoy relief regarding promotional emails",
            "Get a ban on promotional emails",
            "Get an embargo on promotional emails",
            "Get a moratorium on promotional emails",
            "Get liberation from promotional emails",
            "Get a reduction of promotional emails",
        ):
            with self.subTest(text=text), self.assertRaises(ValueError):
                validate_candidate(json.dumps({"candidate_text": text}), seed)

    def test_challenge_examples_are_suggest_only(self):
        examples = {
            "euphemism": "Keep me in the loop about member perks",
            "misleading_dark_pattern": "Get exclusive offers before they disappear",
            "double_negative": "I don't want to miss not receiving member updates",
            "mixed_legal_marketing": "I accept the Terms and receive occasional updates",
        }
        for challenge, text in examples.items():
            seed = seed_matching(challenge=challenge)
            validate_candidate(json.dumps({"candidate_text": text}), seed)
            self.assertEqual(staged_expected_action(seed, infer_safety_conflicts(text, seed)), "suggest")

    def test_no_polarity_rejects_positive_opt_in(self):
        seed = seed_matching(purpose="functional", challenge="no_polarity_signal")
        with self.assertRaises(ValueError):
            validate_candidate(json.dumps({"candidate_text": "Subscribe to receive account emails"}), seed)

    def test_soft_conflicts_never_apply_to_uncheck(self):
        dark = seed_matching(challenge="misleading_dark_pattern")
        functional = seed_matching(purpose="functional", challenge="no_polarity_signal")
        self.assertEqual(hard_conflicts(dark, ["positive-opt-in-outside-safe-envelope"]), [])
        self.assertEqual(hard_conflicts(functional, ["positive-opt-in-outside-safe-envelope"]), ["positive-opt-in-outside-safe-envelope"])
        self.assertEqual(hard_conflicts(dark, ["future-unknown-conflict"]), ["future-unknown-conflict"])

    def test_retry_policy_covers_format_failures_but_not_unsafe_content(self):
        for message in ("malformed candidate JSON", "malformed response envelope", "candidate is not one-line JSON"):
            self.assertTrue(retryable_error(message))
        self.assertFalse(retryable_error("unsafe candidate"))


if __name__ == "__main__":
    unittest.main()
