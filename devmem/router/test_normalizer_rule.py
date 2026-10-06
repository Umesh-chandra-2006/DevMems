"""
Unit tests for the revised normalizer rule (synthetic strings plus the saved Step C replies):
the exact annotation is removed (with its observed variants V1 to V6) and NOTHING else is; text without the exact pattern comes back
byte for byte; the Unicode-space mapping applies only to the three originally covered prompts.
"""
import devmem.testing_env  # noqa: F401
import json
import os
import unittest
from pathlib import Path
from unittest import mock

from devmem.router import output_normalizer as on

ROOT = Path(__file__).resolve().parent.parent.parent
A = "(duration in minutes: 60, minutes left: 1380)"
PLAIN_PROMPT = "an ordinary prompt with no template fragments"
HOURLY_PROMPT = "Hourly schedule format:\n[...]"
DECOMP_PROMPT = "Describe subtasks in 5 min increments.\n---\n"


def norm(text, prompt=PLAIN_PROMPT):
    with mock.patch.dict(os.environ, {on.ENV_FLAG: "on"}):
        return on.maybe_normalize(prompt, text)[0]


class TestExactRuleVariants(unittest.TestCase):
    def test_variants_v1_to_v6_observed_in_saved_replies(self):
        cases = {
            "V1 end of line (followed by newline)": (f"eating breakfast {A}\nnext line", "eating breakfast\nnext line"),
            "V2 mid line (followed by a space)": (f"open the cafe {A} 3) serve", "open the cafe 3) serve"),
            "V3 followed by a comma": (f"open the cafe {A}, 3) serve", "open the cafe, 3) serve"),
            "V4 at the very end of the reply": (f"main room}} {A}", "main room}"),
            "V5 followed by a period": (f"at 8:00 am {A}. 3) next", "at 8:00 am. 3) next"),
            "V6 followed by a semicolon": (f"clean up {A}; then rest", "clean up; then rest"),
        }
        for name, (src, want) in cases.items():
            self.assertEqual(norm(src), want, name)

    def test_every_annotation_in_a_reply_is_removed_and_tabs_before_it_too(self):
        self.assertEqual(norm(f"a {A} b\t{A} c  {A}"), "a b c")

    def test_non_exact_lookalikes_are_left_byte_for_byte(self):
        lookalikes = [
            "x (duration in minutes: 30)",                                  # no 'minutes left'
            "x (Duration in minutes: 30, minutes left: 5)",                 # different case
            "x (duration in minutes: 30, minutes left: five)",              # non-numeric
            "x (duration in minutes:30, minutes left:5)",                   # different spacing
            "x (duration in minutes: 30,  minutes left: 5)",                # two spaces
            "x (duration  in minutes: 30, minutes left: 5)",
            "x (duration in minutes: 30, minutes left: 5",                  # no closing parenthesis
            "x (duration: 30 min)",
            "x [duration in minutes: 30, minutes left: 5]",
            "x (duration in minutes: 30,\nminutes left: 5)",                # newline inside
        ]
        for t in lookalikes:
            self.assertEqual(norm(t), t, repr(t))

    def test_unannotated_text_is_byte_identical_including_odd_characters(self):
        corpus = ["", " ", "\n", "plain", "  leading and trailing  ", "tabs\tand\r\nCRLF\r\n", "café ’quoted’ – dash",
                  "narrow no-break space and nbsp", "emoji \U0001f634\U0001f9c8", "{braces} and (parentheses) and [brackets]",
                  "a, b; c. d", "duration in minutes without parentheses", "(minutes left: 5)", "line1\n\n\nline4\n"]
        for t in corpus:
            self.assertEqual(norm(t), t, repr(t))

    def test_saved_live_replies_without_the_pattern_are_byte_identical_on_non_vetoed_prompts(self):
        # every one of the 31 Step C replies carries the annotation, so the unannotated corpus comes from the two saved probes too
        raws = [json.loads(l)["raw"] for l in
                (ROOT / "docs/phase6_stepc_artifacts/raw_replies.jsonl").read_text(encoding="utf-8").splitlines()]
        for name in ("model_probe.json", "model_probe_v2.json"):
            d = json.loads((ROOT / "docs/phase5_step4_artifacts" / name).read_text(encoding="utf-8"))
            raws += [c["raw"] for inv in d["invocations"] for c in inv["calls"] if c.get("raw")]
        unannotated = [r for r in raws if not on.STRICT_ANNOTATION.search(r)]
        annotated = [r for r in raws if on.STRICT_ANNOTATION.search(r)]
        self.assertGreater(len(unannotated), 20)
        self.assertGreater(len(annotated), 20)
        for r in unannotated:
            self.assertEqual(norm(r, PLAIN_PROMPT), r)
        for r in annotated:  # and the annotated ones lose only the annotation: removing it again changes nothing
            out = norm(r, PLAIN_PROMPT)
            self.assertFalse(on.STRICT_ANNOTATION.search(out))
            self.assertEqual(out, on.strip_annotation_exact(r))


class TestScopeOfSpaceMappingAndVeto(unittest.TestCase):
    def test_space_mapping_only_for_the_three_original_prompts(self):
        text = f"6:00 am go {A}"
        self.assertEqual(norm(text, HOURLY_PROMPT), "6:00 am go")             # mapped and stripped
        self.assertEqual(norm(text, PLAIN_PROMPT), "6:00 am go")    # stripped only; U+202F and NBSP preserved

    def test_vetoed_prompts_are_returned_untouched_even_with_unicode_spaces(self):
        text = f"wake up now {A}"
        for veto in on.VETO_MARKERS:
            self.assertEqual(norm(text, f"prefix {veto} suffix"), text)

    def test_flag_off_is_identity_for_everything(self):
        text = f"x y {A}"
        with mock.patch.dict(os.environ, {on.ENV_FLAG: "off"}):
            for prompt in (PLAIN_PROMPT, HOURLY_PROMPT, DECOMP_PROMPT):
                self.assertEqual(on.maybe_normalize(prompt, text), (text, None))

    def test_idempotent(self):
        once = norm(f"a b {A}", HOURLY_PROMPT)
        self.assertEqual(norm(once, HOURLY_PROMPT), once)


if __name__ == "__main__":
    unittest.main()
