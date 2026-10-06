"""
Offline tests for the router wiring of the output normalizer (DEVMEM_OUTPUT_NORMALIZER, default off).

Prompts are rendered by upstream's own code from the real templates; the provider layer is stubbed (synthetic replies); `call_llm`
is the real router function. Checks: default off changes nothing; on, it touches only the three allow-listed prompts and never the
task-decomposition prompts; it applies identically to baseline and staged; the optional raw-reply log records raw and delivered.
"""
import devmem.testing_env  # noqa: F401
import datetime
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND = ROOT / "reverie" / "reverie" / "backend_server"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
from devmem.run_headless import load_runner_config  # noqa: E402,F401  (chdir to the backend dir; upstream paths are cwd-relative)

import persona.prompt_template.gpt_structure as gs  # noqa: E402
import persona.prompt_template.run_gpt_prompt as rgp  # noqa: E402
from persona.persona import Persona  # noqa: E402
from devmem.memory import episodic  # noqa: E402
from devmem.memory.consolidation import SUMMARIZATION_PROMPT_TEMPLATE  # noqa: E402
from devmem.memory.p5_model_probe import HOURS, REF_PLAN  # noqa: E402
from devmem.router import llm_router, output_normalizer as on  # noqa: E402
from devmem.router.cooldown import CooldownManager  # noqa: E402
from devmem.router.providers import ProviderResponse  # noqa: E402

DIRTY = "eating breakfast at 7:00 am (duration in minutes: 60, minutes left: 0)"
CLEAN = "eating breakfast at 7:00 am"


class TestNormalizerWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        persona_dir = ROOT / "reverie/environment/frontend_server/storage/base_the_ville_isabella_maria_klaus/personas/Isabella Rodriguez"
        cls.persona = Persona("Isabella Rodriguez", str(persona_dir))
        cls.persona.scratch.curr_time = datetime.datetime(2023, 2, 13, 0, 0, 0)
        cls.persona.scratch.daily_req = list(REF_PLAN)
        cls.prompts = cls._render_prompts()

    @classmethod
    def _render_prompts(cls):
        seen = {}
        captured = []

        def spy(prompt, **kw):
            captured.append(prompt)
            return "6"
        with mock.patch.object(gs, "call_llm", spy), mock.patch.object(gs, "temp_sleep"):
            rgp.run_gpt_prompt_wake_up_hour(cls.persona)
            seen["wake_up_hour"] = captured[-1]
            rgp.run_gpt_prompt_daily_plan(cls.persona, 6)
            seen["daily_plan"] = captured[-1]
            rgp.run_gpt_prompt_generate_hourly_schedule(cls.persona, "07:00 AM", ["sleeping"] * 7, HOURS)
            seen["hourly_schedule"] = captured[-1]
            # prompts that must never be touched, rendered from the real templates or built by the real functions
            seen["task_decomp"] = gs.generate_prompt(["x"] * 8, "persona/prompt_template/v2/task_decomp_v3.txt")
            seen["new_decomp_schedule"] = gs.generate_prompt(["x"] * 12, "persona/prompt_template/v2/new_decomp_schedule_v1.txt")
            rgp.run_gpt_prompt_pronunciatio("eating breakfast", cls.persona)
            seen["pronunciatio"] = captured[-1]
            rgp.run_gpt_prompt_event_triple("eating breakfast", cls.persona)
            seen["event_triple"] = captured[-1]
            rgp.run_gpt_prompt_event_poignancy(cls.persona, "Isabella is eating breakfast")
            seen["event_poignancy_upstream"] = captured[-1]
            rgp.run_gpt_prompt_focal_pt(cls.persona, "a statement", 3)
            seen["focal_pt"] = captured[-1]
        seen["staged_scoring"] = episodic.build_staged_prompt("Isabella Rodriguez", "Isabella argued with a neighbor", kind="event")
        seen["consolidation_summary"] = SUMMARIZATION_PROMPT_TEMPLATE.format(
            persona_context="priors", agent_name="Isabella Rodriguez", cluster_entries="- a")
        return seen

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="p5_wiring_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.cfg = os.path.join(self.tmp, "providers.yaml")
        self.db = os.path.join(self.tmp, "ledger.db")
        with open(self.cfg, "w", encoding="utf-8") as f:
            yaml.dump({"providers": [{"name": "groq", "priority": 1, "models": {"fast": "openai/gpt-oss-20b"},
                                      "keys": [{"env": "WIRING_TEST_KEY"}], "rpm": 1000, "rpd": 100000, "tpd": 10 ** 9}]}, f)
        env = mock.patch.dict(os.environ, {"WIRING_TEST_KEY": "not-a-real-key"})
        env.start()
        self.addCleanup(env.stop)
        mgr = CooldownManager(state_file=Path(self.tmp) / "cd.json")
        for p in (mock.patch.object(llm_router, "cooldown_manager", mgr),
                  mock.patch.object(llm_router, "send_request", return_value=ProviderResponse(DIRTY, 11, 7))):
            p.start()
            self.addCleanup(p.stop)
        os.environ.pop(on.ENV_FLAG, None)
        os.environ.pop("DEVMEM_RAW_REPLY_LOG", None)
        self.addCleanup(lambda: (os.environ.pop(on.ENV_FLAG, None), os.environ.pop("DEVMEM_RAW_REPLY_LOG", None)))
        on.STATS.clear()

    def call(self, prompt, **kw):
        return llm_router.call_llm(prompt, tier="fast", config_path=self.cfg, db_path=self.db, **kw)

    # ---- classification on real prompts ------------------------------------------------------------------------------
    def test_prompt_kind_allow_list_on_real_upstream_prompts(self):
        for kind in ("wake_up_hour", "daily_plan", "hourly_schedule"):
            self.assertEqual(on.prompt_kind(self.prompts[kind]), kind, kind)
        for name, prompt in self.prompts.items():
            if name not in ("wake_up_hour", "daily_plan", "hourly_schedule"):
                self.assertIsNone(on.prompt_kind(prompt), f"{name} must never be normalized")

    def test_decomposition_prompts_are_vetoed_even_if_they_mention_an_allow_listed_phrase(self):
        poisoned = self.prompts["task_decomp"] + "\nplan today in broad-strokes\nHourly schedule format:"
        self.assertIsNone(on.prompt_kind(poisoned))
        self.assertIsNone(on.prompt_kind(self.prompts["new_decomp_schedule"] + " wake up hour:"))

    # ---- router behavior ---------------------------------------------------------------------------------------------
    def test_default_off_returns_the_provider_text_untouched_for_every_prompt(self):
        for name, prompt in self.prompts.items():
            self.assertEqual(self.call(prompt, purpose="planning"), DIRTY, name)
        self.assertEqual(on.STATS, {})

    def test_on_normalizes_only_allow_listed_prompts(self):
        os.environ[on.ENV_FLAG] = "on"
        for kind in ("wake_up_hour", "daily_plan", "hourly_schedule"):
            self.assertEqual(self.call(self.prompts[kind], purpose="planning"), CLEAN, kind)
        for name in ("task_decomp", "new_decomp_schedule", "pronunciatio", "event_triple", "event_poignancy_upstream",
                     "focal_pt", "staged_scoring", "consolidation_summary"):
            self.assertEqual(self.call(self.prompts[name], purpose="planning"), DIRTY, f"{name} must keep its annotation")
        self.assertEqual({k: v["applied"] for k, v in on.STATS.items()}, {"wake_up_hour": 1, "daily_plan": 1, "hourly_schedule": 1})

    def test_flag_value_other_than_on_is_off(self):
        for value in ("off", "", "0", "true", "ON "):
            os.environ[on.ENV_FLAG] = value
            expected = CLEAN if value.strip().lower() == "on" else DIRTY
            self.assertEqual(self.call(self.prompts["hourly_schedule"], purpose="planning"), expected, repr(value))

    def test_identical_for_baseline_and_staged_conditions(self):
        os.environ[on.ENV_FLAG] = "on"
        out = {c: self.call(self.prompts["daily_plan"], purpose="planning", condition=c) for c in ("baseline", "staged")}
        self.assertEqual(out["baseline"], out["staged"])
        self.assertEqual(out["baseline"], CLEAN)

    def test_return_obj_keeps_tokens_and_only_replaces_text(self):
        os.environ[on.ENV_FLAG] = "on"
        r = self.call(self.prompts["hourly_schedule"], purpose="planning", return_obj=True)
        self.assertEqual((r.text, r.tokens_in, r.tokens_out), (CLEAN, 11, 7))

    def test_raw_reply_log_is_off_by_default_and_records_raw_and_delivered_when_on(self):
        log = Path(self.tmp) / "raw.jsonl"
        self.call(self.prompts["hourly_schedule"], purpose="planning")
        self.assertFalse(log.exists())
        os.environ["DEVMEM_RAW_REPLY_LOG"] = str(log)
        os.environ[on.ENV_FLAG] = "on"
        self.call(self.prompts["hourly_schedule"], purpose="planning", agent_id="Isabella Rodriguez")
        self.call(self.prompts["task_decomp"], purpose="planning")
        rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([r["normalizer_kind"] for r in rows], ["hourly_schedule", None])
        self.assertEqual(rows[0]["raw"], DIRTY)
        self.assertEqual(rows[0]["delivered"], CLEAN)
        self.assertEqual(rows[0]["agent_id"], "Isabella Rodriguez")
        self.assertEqual(rows[1]["raw"], rows[1]["delivered"])


if __name__ == "__main__":
    unittest.main()
