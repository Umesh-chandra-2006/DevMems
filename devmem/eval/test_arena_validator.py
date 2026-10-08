"""Tests of the area-reply validator change (claims ledger H28, PM ruling 2026-10-08) on the REAL upstream functions run_gpt_prompt_action_arena and run_gpt_prompt_action_sector:
the model call is replaced by a capture of the validator and the clean-up that upstream passes to safe_generate_response; no model call, no key."""
import devmem.testing_env  # noqa: F401
import sys
import unittest
from pathlib import Path
from unittest import mock

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent / "reverie" / "reverie" / "backend_server"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from persona.prompt_template import run_gpt_prompt as R  # noqa: E402
from devmem.eval import arena_validator_replay as AR  # noqa: E402

RECORDED = ("cafe}\n1. Walk to the condiment station (duration in minutes: 2, minutes left: 58)\n2. Arrange sugar, stirrers, and napkins (duration in minutes: 5, minutes left: 53)\n"
            "3. Wipe down the counter surface (duration in minutes: 3, minutes left: 50)\n4. Restock empty condiment containers (duration in minutes: 5, minutes left: 45)")


class _Scratch:
    last_name = "Rodriguez"
    living_area = "the Ville:Isabella Rodriguez's apartment"
    curr_tile = (1, 1)

    def get_str_name(self):
        return "Isabella Rodriguez"

    def get_str_daily_plan_req(self):
        return ""


class _SMem:
    def __init__(self, arenas, sectors):
        self.arenas, self.sectors = arenas, sectors

    def get_str_accessible_sector_arenas(self, x):
        return self.arenas

    def get_str_accessible_sectors(self, world):
        return self.sectors


class _Maze:
    def access_tile(self, tile):
        return {"world": "the Ville", "sector": "Hobbs Cafe"}


def _capture(fn, *args):
    got = {}

    def fake_safe(prompt, gpt_param, repeat, fail_safe, validate, clean_up, *a, **k):
        got["validate"], got["clean_up"], got["fail_safe"] = validate, clean_up, fail_safe
        return "OUT"
    with mock.patch.object(R, "safe_generate_response", fake_safe), mock.patch.object(R, "generate_prompt", lambda pi, tpl: "PROMPT"), mock.patch.object(R, "print_run_prompts", lambda *a, **k: None):
        fn(*args)
    return got


class TestAreaValidator(unittest.TestCase):
    def setUp(self):
        persona = mock.Mock(scratch=_Scratch(), s_mem=_SMem("cafe", "Hobbs Cafe, Johnson Park"))
        self.arena = _capture(R.run_gpt_prompt_action_arena, "serving morning customers", persona, _Maze(), "the Ville", "Hobbs Cafe")
        self.sector = _capture(R.run_gpt_prompt_action_sector, "serving morning customers", persona, _Maze())

    def test_a_valid_reply_is_unchanged(self):
        for g in (self.arena, self.sector):
            self.assertTrue(g["validate"]("cafe}" if g is self.arena else "Hobbs Cafe}"))
        self.assertEqual(self.arena["clean_up"]("cafe} x"), "cafe")

    def test_the_recorded_run_on_reply_is_accepted_as_cafe(self):
        v = self.arena["validate"]
        self.assertTrue(v(RECORDED))
        self.assertEqual(self.arena["clean_up"](RECORDED), "cafe")                 # upstream's own clean-up: the text before the first brace
        self.assertTrue(self.sector["validate"]("Hobbs Cafe}\n1. Walk to the condiment station\n2. Arrange sugar, stirrers, and napkins"))

    def test_a_nonexistent_area_before_the_brace_still_fails_as_before(self):
        self.assertFalse(self.arena["validate"]("kitchen}\n1. Walk, then sit, and wait"))
        self.assertFalse(self.sector["validate"]("Moon Base}\n1. a, b"))
        self.assertEqual(self.arena["fail_safe"], "kitchen")                       # the fail-safe path is untouched

    def test_replies_without_a_brace_or_with_a_comma_before_it_behave_as_upstream(self):
        for g in (self.arena, self.sector):
            v = g["validate"]
            self.assertFalse(v("cafe, then more"))                                 # no brace and a comma: rejected as upstream does
            self.assertFalse(v("cafe"))                                            # no brace
            self.assertFalse(v(""))                                                # empty
            self.assertFalse(v("cafe, kitchen}"))                                  # comma BEFORE the brace: rejected as upstream does
        # a reply with a brace and no comma is judged as upstream judges it (it accepted any text before the brace)
        self.assertTrue(self.arena["validate"]("nonexistent}"))

    def test_the_helper_needs_an_exact_option(self):
        self.assertTrue(R._devmem_comma_after_brace_ok("cafe}, x", "cafe"))
        self.assertFalse(R._devmem_comma_after_brace_ok("caf}, x", "cafe"))
        self.assertFalse(R._devmem_comma_after_brace_ok("cafe, x", "cafe"))


class TestReplayScript(unittest.TestCase):
    def test_replay_counts_replies_and_calls_that_the_change_would_parse_differently(self):
        arena_prompt = "Isabella is going to Hobbs Cafe. (MUST pick one of {cafe}):\nAnswer: {"
        sector_prompt = "Area options: {Hobbs Cafe, Johnson Park}. \nshould go to the following area: {"
        rows = []
        for _ in range(5):                      # one call: five identical run-on replies, rejected by upstream (kitchen fail-safe), accepted by the change
            rows.append({"prompt": arena_prompt, "agent_id": "I", "delivered": RECORDED})
        rows.append({"prompt": sector_prompt, "agent_id": "I", "delivered": "Hobbs Cafe}"})                       # valid in both
        for _ in range(5):                      # a nonexistent area before the brace stays rejected
            rows.append({"prompt": arena_prompt.replace("cafe", "cafe2"), "agent_id": "I", "delivered": "kitchen}\n1. a, b"})
        res = AR.replay_rows(rows, R._devmem_comma_after_brace_ok)
        self.assertEqual((res["area_replies"], res["calls"], res["calls_with_a_different_outcome"]), (11, 3, 1))
        self.assertEqual(res["different_calls"][0]["upstream"], "fail-safe")
        self.assertEqual(res["different_calls"][0]["changed"], "accepted at attempt 1")
        self.assertEqual(AR.area_options(arena_prompt), ("arena", "cafe"))
        self.assertEqual(AR.area_options(sector_prompt), ("sector", "Hobbs Cafe, Johnson Park"))


if __name__ == "__main__":
    unittest.main()
