"""
Router-level call counter and cap. The provider layer is stubbed (`synthetic` responses); `call_llm` itself, `episodic.py`'s
own import of it, and upstream's `GPT_request` wrapper are real. Proves that a call made through `episodic.py`'s import path
(the path that bypassed the earlier gpt_structure-level counter) is counted, and that a hard cap cannot be swallowed by
upstream's `except Exception`.
"""
import devmem.testing_env  # noqa: F401
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

from devmem.memory import episodic
from devmem.router import call_counter, llm_router
from devmem.router.cooldown import CooldownManager
from devmem.router.providers import ProviderResponse


class TestRouterCallCounter(unittest.TestCase):
    def setUp(self):
        call_counter.reset()
        self.addCleanup(call_counter.reset)
        self.tmp = tempfile.mkdtemp(prefix="p5_counter_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.cfg = os.path.join(self.tmp, "providers.yaml")
        self.db = os.path.join(self.tmp, "ledger.db")
        with open(self.cfg, "w", encoding="utf-8") as f:
            yaml.dump({"providers": [{"name": "groq", "priority": 1, "models": {"fast": "openai/gpt-oss-20b"},
                                      "keys": [{"env": "COUNTER_TEST_KEY"}], "rpm": 1000, "rpd": 100000,
                                      "tpd": 10 ** 9}]}, f)
        envp = mock.patch.dict(os.environ, {"COUNTER_TEST_KEY": "not-a-real-key"})
        envp.start()
        self.addCleanup(envp.stop)
        mgr = CooldownManager(state_file=Path(self.tmp) / "cd.json")
        p1 = mock.patch.object(llm_router, "cooldown_manager", mgr)
        p2 = mock.patch.object(llm_router, "send_request", return_value=ProviderResponse("7", 10, 2))
        p1.start(); p2.start()
        self.addCleanup(p1.stop)
        self.addCleanup(p2.stop)

    def test_calls_through_every_import_path_are_counted(self):
        # (a) directly through the router
        llm_router.call_llm("direct", tier="fast", purpose="planning", agent_id="A", config_path=self.cfg, db_path=self.db)
        # (b) through episodic.py's own `call_llm` import (the path the old wrapper-level counter missed)
        self.assertIs(episodic.call_llm, llm_router.call_llm)  # a by-value import: wrapping gpt_structure would not see it
        score = episodic.score_importance_persona_conditioned(
            "Isabella Rodriguez", "Isabella argued with a neighbor", kind="event",
            config_path=self.cfg, ledger_db_path=self.db)
        self.assertEqual(score, 7)
        # (c) through upstream's GPT_request wrapper in gpt_structure
        import persona.prompt_template.gpt_structure as gs
        real = llm_router.call_llm
        with mock.patch.object(gs, "call_llm", lambda *a, **k: real(*a, config_path=self.cfg, db_path=self.db, **k)), \
             mock.patch.object(gs, "temp_sleep"):
            gs.GPT_request("upstream path prompt", {"temperature": 0.1}, purpose="dialogue")
        snap = call_counter.snapshot()
        self.assertEqual(snap["count"], 3)
        self.assertEqual(snap["by_purpose"], {"planning": 1, "importance_scoring": 1, "dialogue": 1})
        self.assertEqual(snap["by_agent"]["A"], 1)
        self.assertEqual(snap["by_agent"]["Isabella Rodriguez"], 1)

    def test_failed_attempts_are_counted_too(self):
        with mock.patch.object(llm_router, "send_request", side_effect=RuntimeError("provider down")):
            with self.assertRaises(Exception):
                llm_router.call_llm("x", tier="fast", config_path=self.cfg, db_path=self.db)
        self.assertEqual(call_counter.snapshot()["count"], 1)

    def test_hard_cap_raises_and_is_not_swallowed_by_except_exception(self):
        call_counter.set_cap(2)
        for _ in range(2):
            llm_router.call_llm("ok", tier="fast", config_path=self.cfg, db_path=self.db)
        swallowed = False
        try:
            try:
                episodic.score_importance_persona_conditioned(  # scorer catches Exception and returns a fail-safe
                    "Isabella Rodriguez", "third call", kind="event", config_path=self.cfg, ledger_db_path=self.db)
            except Exception:
                swallowed = True
        except call_counter.CapReached:
            pass
        else:
            self.fail("the cap must propagate out of episodic's `except Exception`")
        self.assertFalse(swallowed)
        self.assertEqual(call_counter.snapshot()["count"], 2, "the refused call is not counted")
        self.assertTrue(issubclass(call_counter.CapReached, BaseException) and not issubclass(call_counter.CapReached, Exception))

    def test_counting_without_a_cap_and_reset(self):
        llm_router.call_llm("a", tier="fast", config_path=self.cfg, db_path=self.db)
        self.assertEqual(call_counter.snapshot()["cap"], None)
        self.assertEqual(call_counter.snapshot()["count"], 1)
        call_counter.reset()
        self.assertEqual(call_counter.snapshot()["count"], 0)


if __name__ == "__main__":
    unittest.main()
