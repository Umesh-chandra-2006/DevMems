"""
Tests for the sanctioned `gpt_structure.py` edits (touch point 1 extension, Phase 5):
  * get_embedding routes through EmbeddingStore (offline mode returns deterministic vectors; live mode is
    fail-loud when no key works);
  * router failures are counted; with utils.FAIL_LOUD_LLM they are re-raised, otherwise upstream's
    fail-safe strings are returned unchanged.
Runs against the real upstream module; only the router call / environment keys are patched.
"""
import devmem.testing_env  # noqa: F401  (offline by default)
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent / "reverie" / "reverie" / "backend_server"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import utils  # noqa: E402
from persona.prompt_template import gpt_structure as gs  # noqa: E402
from devmem.embeddings.vector_store import EmbeddingError, FALLBACK_DIM, deterministic_fallback_vector  # noqa: E402


class TestRouterFailureHandling(unittest.TestCase):
    def setUp(self):
        self._orig = getattr(utils, "FAIL_LOUD_LLM", None)
        gs.ROUTER_FAILURES.update({"count": 0, "by_function": {}, "last_errors": []})
        self.addCleanup(self._restore)

    def _restore(self):
        if self._orig is None and hasattr(utils, "FAIL_LOUD_LLM"):
            del utils.FAIL_LOUD_LLM
        elif self._orig is not None:
            utils.FAIL_LOUD_LLM = self._orig

    def test_default_preserves_upstream_failsafe_but_counts(self):
        if hasattr(utils, "FAIL_LOUD_LLM"):
            del utils.FAIL_LOUD_LLM
        with mock.patch.object(gs, "call_llm", side_effect=RuntimeError("boom")), mock.patch.object(gs, "temp_sleep"):
            self.assertEqual(gs.GPT_request("p", {}), "TOKEN LIMIT EXCEEDED")
            self.assertEqual(gs.ChatGPT_request("p"), "ChatGPT ERROR")
            self.assertEqual(gs.GPT4_request("p"), "ChatGPT ERROR")
            self.assertEqual(gs.ChatGPT_single_request("p"), "ChatGPT ERROR")
        self.assertEqual(gs.ROUTER_FAILURES["count"], 4)
        self.assertEqual(sorted(gs.ROUTER_FAILURES["by_function"]),
                         ["ChatGPT_request", "ChatGPT_single_request", "GPT4_request", "GPT_request"])

    def test_fail_loud_flag_reraises_after_counting(self):
        utils.FAIL_LOUD_LLM = True
        with mock.patch.object(gs, "call_llm", side_effect=RuntimeError("boom")), mock.patch.object(gs, "temp_sleep"):
            with self.assertRaises(RuntimeError):
                gs.GPT_request("p", {})
        self.assertEqual(gs.ROUTER_FAILURES["count"], 1)

    def test_success_is_not_counted(self):
        utils.FAIL_LOUD_LLM = True
        with mock.patch.object(gs, "call_llm", return_value="ok"), mock.patch.object(gs, "temp_sleep"):
            gs.GPT_request("p", {})
        self.assertEqual(gs.ROUTER_FAILURES["count"], 0)


class TestGetEmbeddingRouting(unittest.TestCase):
    def setUp(self):
        self._store = gs._EMBEDDING_STORE
        gs._EMBEDDING_STORE = None
        self.addCleanup(lambda: setattr(gs, "_EMBEDDING_STORE", self._store))

    def test_offline_mode_returns_deterministic_768_vectors(self):
        with mock.patch.dict(os.environ, {"DEVMEM_EMBEDDING_MODE": "offline"}):
            text = "p5 offline routing probe sentence one"
            vec = gs.get_embedding(text)
            self.assertEqual(len(vec), FALLBACK_DIM)
            self.assertEqual(vec, deterministic_fallback_vector(text))
            self.assertEqual(gs._EMBEDDING_STORE.stats["fallbacks"], 1)
            self.assertEqual(gs._EMBEDDING_STORE.stats["http_requests"], 0)

    def test_live_mode_is_fail_loud_when_no_key_works(self):
        from devmem.embeddings.vector_store import load_config
        no_keys = {k: "" for k in load_config()["key_envs"]}  # blank every key the production config uses
        with mock.patch.dict(os.environ, {"DEVMEM_EMBEDDING_MODE": "live", **no_keys}):
            with self.assertRaises(EmbeddingError):
                import uuid  # unique text: a persistent-cache hit must never mask the fail-loud path
                gs.get_embedding(f"p5 live routing probe sentence {uuid.uuid4()}")
            self.assertEqual(gs._EMBEDDING_STORE.stats["http_requests"], 0)


if __name__ == "__main__":
    unittest.main()
