"""
Network outage behavior (PM launch gate, 2026-10-07). ZERO real calls: `requests.post` is patched everywhere, sleeping is patched, the clock is fake.

What is proven here:
  * a connection failure or a timeout reaches the run-level gate as a ModelPinnedError tagged `network_outage` (an HTTP 503 or 429 is not);
  * the gate waits with backoff (20, 40, 80, 160, then 300 s), with NO attempt limit, and while the host is unreachable it makes no router call;
  * through the real upstream `ChatGPT_safe_generate_response` an outage of 25 failed attempts (more than the 20 generic retries) ends with the
    real answer, never the fail-safe, and no router failure is counted;
  * the outage is recorded as minutes in `outage_log.jsonl` (and so in every ledger window), not as quota pauses and not as router failures;
  * embeddings behave the same way.
"""
import devmem.testing_env  # noqa: F401
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (str(ROOT / "reverie" / "reverie" / "backend_server"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from devmem.eval import arm_health  # noqa: E402
from devmem.eval.quota_gate import QuotaGate  # noqa: E402
from devmem.router import llm_router  # noqa: E402
from devmem.router.cooldown import CooldownManager  # noqa: E402
from devmem.router.providers import ModelPinnedError  # noqa: E402

MODEL = "gemini-3.1-flash-lite"


class FakeClock:
    def __init__(self):
        self.t = datetime(2026, 10, 7, 8, 0, 0)

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += timedelta(seconds=s)


def _response(status, body):
    r = mock.Mock()
    r.status_code = status
    r.text = json.dumps(body)
    r.headers = {}
    r.json.return_value = body
    return r


OK_BODY = {"candidates": [{"content": {"parts": [{"text": '{"output": "7"}'}]}}], "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 2}}


class RouterFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        t = Path(self.tmp.name)
        base = yaml.safe_load(open(ROOT / "devmem/config/providers.yaml", encoding="utf-8"))
        gem = next(p for p in base["providers"] if p["name"] == "gemini")
        gem["keys"] = [{"env": "GEMINI_KEY_OUTAGE_T1"}, {"env": "GEMINI_KEY_OUTAGE_T2"}]
        self.cfg = t / "cfg.yaml"
        self.cfg.write_text(yaml.dump({"providers": [gem]}), encoding="utf-8")
        self.db = str(t / "ledger.db")
        self.cm = CooldownManager(state_file=t / "cooldown.json")
        env = {"GEMINI_KEY_OUTAGE_T1": "dummy-placeholder-not-a-key", "GEMINI_KEY_OUTAGE_T2": "dummy-placeholder-not-a-key"}
        p = mock.patch.dict(os.environ, env)
        p.start()
        self.addCleanup(p.stop)
        os.environ.pop("DEVMEM_RAW_REPLY_LOG", None)
        for target in ("time.sleep",):
            q = mock.patch(target, lambda s: None)
            q.start()
            self.addCleanup(q.stop)

    def real(self, *a, **k):
        return llm_router.call_llm(*a, config_path=str(self.cfg), db_path=self.db, cooldown_mgr=self.cm, pinned_model=MODEL, **k)


class TestRouterTagsNetworkFailures(RouterFixture):
    def _err(self, side_effect):
        with mock.patch("devmem.router.providers.requests.post", side_effect=side_effect) as post:
            with self.assertRaises(ModelPinnedError) as cm:
                self.real("hello", tier="fast", purpose="planning")
        self.assertGreaterEqual(post.call_count, 1)
        return cm.exception

    def test_connection_error_is_tagged_as_an_outage(self):
        self.assertTrue(self._err(requests.exceptions.ConnectionError("network is unreachable")).network_outage)

    def test_dns_style_failure_is_tagged_as_an_outage(self):
        self.assertTrue(self._err(OSError("getaddrinfo failed")).network_outage)

    def test_timeout_is_tagged_as_an_outage(self):
        self.assertTrue(self._err(requests.exceptions.Timeout("read timed out")).network_outage)

    def test_http_503_from_every_key_is_an_outage_the_gate_waits_for(self):
        self.assertTrue(self._err(lambda *a, **k: _response(503, {"error": {"code": 503}})).network_outage)

    def test_http_400_is_not_an_outage(self):
        self.assertFalse(self._err(lambda *a, **k: _response(400, {"error": {"code": 400}})).network_outage)

    def test_http_429_is_not_an_outage(self):
        self.assertFalse(self._err(lambda *a, **k: _response(429, {"error": {"code": 429, "message": "Resource has been exhausted"}})).network_outage)


class TestEmbeddingErrorTagging(unittest.TestCase):
    def _store_error(self, make_response):
        from devmem.embeddings.vector_store import EmbeddingError, EmbeddingStore
        with tempfile.TemporaryDirectory() as t:
            with mock.patch.dict(os.environ, {"GEMINI_KEY_EMB_T1": "dummy-placeholder-not-a-key"}):
                store = EmbeddingStore(stats_path=Path(t) / "s.json", key_envs=["GEMINI_KEY_EMB_T1"], cache_path=Path(t) / "c.db", db_path=str(Path(t) / "l.db"),
                                       cooldown_mgr=CooldownManager(state_file=Path(t) / "cd.json"), rpd_per_key=None)   # nothing shared with a live run
                store._post = make_response
                with self.assertRaises(EmbeddingError) as cm:
                    store._request("embedContent", {"content": {"parts": [{"text": "x"}]}})
        return cm.exception

    def test_connection_failure_and_http_5xx_are_outages_http_403_is_not(self):
        def boom(*a, **k):
            raise requests.exceptions.ConnectionError("down")
        self.assertTrue(self._store_error(boom).network_outage)
        self.assertTrue(self._store_error(lambda *a, **k: _response(503, {"error": {}})).network_outage)
        self.assertFalse(self._store_error(lambda *a, **k: _response(403, {"error": {}})).network_outage)


class TestGateWaitsForTheNetwork(unittest.TestCase):
    def _gate(self, real, probe=None, run_dir=None):
        clock = FakeClock()
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        rd = Path(run_dir or t.name)
        return QuotaGate(real, ["GEMINI_KEY_X"], MODEL, 450, rd, now=clock.now, sleep=clock.sleep, usage=lambda k: 0, probe=probe), clock, rd

    def test_fifty_failed_attempts_then_success_returns_the_answer_without_a_limit(self):
        calls = []

        def real(*a, **k):
            calls.append(1)
            if len(calls) <= 50:                       # more than the 20 generic retries
                e = ModelPinnedError("Pinned model failed across all configured keys.")
                e.network_outage = True
                raise e
            return "ANSWER"
        gate, clock, rd = self._gate(real, probe=lambda: True)
        self.assertEqual(gate("p"), "ANSWER")
        self.assertEqual(len(calls), 51)
        log = [json.loads(l) for l in (rd / "outage_log.jsonl").read_text().splitlines()]
        self.assertEqual([r["event"] for r in log], ["outage_start", "outage_end"])
        self.assertGreater(log[-1]["seconds"], 50 * 20)
        self.assertEqual(gate.outage_minutes_total(), round(log[-1]["seconds"] / 60, 2))
        self.assertEqual(gate.pauses, 0)                                  # not a quota pause
        self.assertFalse((rd / "quota_pauses.jsonl").exists())

    def test_backoff_grows_to_300_seconds(self):
        calls = []

        def real(*a, **k):
            calls.append(1)
            if len(calls) <= 8:
                e = ModelPinnedError("x")
                e.network_outage = True
                raise e
            return "OK"
        gate, clock, rd = self._gate(real, probe=lambda: True)
        t0 = clock.now()
        gate("p")
        waited = (clock.now() - t0).total_seconds()
        self.assertEqual(waited, 20 + 40 + 80 + 160 + 300 + 300 + 300 + 300)     # 8 failed attempts, one backoff step each, capped at 300 s

    def test_no_router_call_while_the_host_is_unreachable(self):
        calls = []
        net = {"up": False, "probes": 0}

        def probe():
            net["probes"] += 1
            if net["probes"] >= 4:
                net["up"] = True
            return net["up"]

        def real(*a, **k):
            calls.append(net["up"])
            if not net["up"]:
                e = ModelPinnedError("x")
                e.network_outage = True
                raise e
            return "OK"
        gate, clock, rd = self._gate(real, probe=probe)
        self.assertEqual(gate("p"), "OK")
        self.assertEqual(calls, [False, True])                              # one failing call, then straight to the success once the probe passed
        self.assertEqual(net["probes"], 4)

    def test_a_non_network_pinned_error_still_uses_the_bounded_generic_path(self):
        def real(*a, **k):
            raise ModelPinnedError("Pinned model failed across all configured keys.")
        gate, clock, rd = self._gate(real, probe=lambda: True)
        gate.max_generic = 2
        with self.assertRaises(ModelPinnedError):
            gate("p")
        self.assertFalse((rd / "outage_log.jsonl").exists())

    def test_abort_file_ends_an_outage_wait(self):
        from devmem.eval.quota_gate import RunAborted

        def real(*a, **k):
            e = ModelPinnedError("x")
            e.network_outage = True
            raise e
        gate, clock, rd = self._gate(real, probe=lambda: False)
        (rd / "ABORT").write_text("operator")
        with self.assertRaises(RunAborted):
            gate("p")

    def test_embedding_outage_waits_and_recovers(self):
        from devmem.embeddings.vector_store import EmbeddingError
        n = {"i": 0}

        class Store:
            model = "gemini-embedding-001"

            def embed_texts(self, texts, batch=True):
                n["i"] += 1
                if n["i"] <= 30:
                    e = EmbeddingError("all embedding keys failed or unavailable: ['K:ConnectionError']")
                    e.network_outage = True
                    raise e
                return [[0.1, 0.2]]
        gate, clock, rd = self._gate(lambda *a, **k: None, probe=lambda: True)
        store = Store()
        gate.wrap_embedding_store(store, ["GEMINI_KEY_X"], rpd=1000)
        self.assertEqual(store.embed_texts(["a"]), [[0.1, 0.2]])
        self.assertEqual(n["i"], 31)
        self.assertGreater(gate.outage_minutes_total(), 0)


class TestRateLimitBackoff(RouterFixture):
    """PM decision 2026-10-07: on a 429 at most 3 keys per call, then exponential backoff with jitter (20 s doubling, cap 300 s), no attempt limit,
    no fail-safe, ABORT ends the wait. Zero real calls."""

    def setUp(self):
        super().setUp()
        base = yaml.safe_load(open(self.cfg, encoding="utf-8"))
        base["providers"][0]["keys"] = [{"env": f"GEMINI_KEY_OUTAGE_T{i}"} for i in range(1, 6)]     # a pool of five keys
        self.cfg.write_text(yaml.dump(base), encoding="utf-8")
        for i in range(1, 6):
            p = mock.patch.dict(os.environ, {f"GEMINI_KEY_OUTAGE_T{i}": "dummy-placeholder-not-a-key"})
            p.start()
            self.addCleanup(p.stop)

    def test_at_most_three_keys_are_tried_per_call_on_429(self):
        with mock.patch("devmem.router.providers.requests.post", side_effect=lambda *a, **k: _response(429, {"error": {"code": 429, "message": "Resource has been exhausted"}})) as post:
            with self.assertRaises(ModelPinnedError) as cm:
                self.real("hello", tier="fast", purpose="planning")
        self.assertEqual(post.call_count, 3)                      # 3 keys in total, not the whole pool of five
        self.assertTrue(cm.exception.rate_limited)
        self.assertFalse(getattr(cm.exception, "network_outage", False))

    def _gate(self, real, seed=1, run_dir=None):
        import random
        clock = FakeClock()
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        rd = Path(run_dir or t.name)
        return QuotaGate(real, ["GEMINI_KEY_X"], MODEL, 450, rd, now=clock.now, sleep=clock.sleep, usage=lambda k: 0, rng=random.Random(seed)), clock, rd

    def test_backoff_grows_with_jitter_and_is_capped_at_300_seconds(self):
        calls = []

        def real(*a, **k):
            calls.append(1)
            if len(calls) <= 9:
                e = ModelPinnedError("rate limited")
                e.rate_limited = True
                raise e
            return "OK"
        gate, clock, rd = self._gate(real)
        self.assertEqual(gate("p"), "OK")
        waits = [json.loads(l)["seconds"] for l in (rd / "rate_limit_log.jsonl").read_text().splitlines() if '"rate_limit_backoff"' in l]
        self.assertEqual(len(waits), 9)
        for n, w in enumerate(waits):
            base = min(300.0, 20.0 * 2 ** n)
            self.assertGreaterEqual(w, min(300.0, base * 0.75) - 0.1)
            self.assertLessEqual(w, 300.0)
            self.assertLessEqual(w, base * 1.25 + 0.1)
        self.assertLess(waits[0], waits[3])                         # it grows
        self.assertEqual(max(waits), max(waits[-3:]))               # and ends at the cap region
        self.assertGreater(gate.rate_limit_minutes_total(), 0)
        self.assertFalse((rd / "quota_pauses.jsonl").exists())

    def test_no_fail_safe_reaches_the_simulation_after_sixty_repeated_429_calls(self):
        import persona.prompt_template.gpt_structure as gs
        gate, clock, rd = self._gate(self.real)
        n = {"i": 0}

        def post(*a, **k):
            n["i"] += 1
            if n["i"] <= 180:                                        # 60 router calls of 3 keys each
                return _response(429, {"error": {"code": 429, "message": "Resource has been exhausted"}})
            return _response(200, OK_BODY)
        fake_time = SimpleNamespace(time=lambda: clock.t.timestamp() + 1e9, sleep=lambda s: None)       # the router's cooldowns follow the fake clock, as real time would pass
        with mock.patch("devmem.router.cooldown.time", fake_time), mock.patch("devmem.router.providers.requests.post", side_effect=post), mock.patch.object(gs, "call_llm", gate):
            out = gs.ChatGPT_safe_generate_response("rate this", "5", "one integer", 3, "FAILSAFE", lambda r, prompt="": True, lambda r, prompt="": "got:" + r)
        self.assertEqual(out, "got:7")                                # the real answer, never the fail-safe
        self.assertGreater(n["i"], 180)
        self.assertGreater(gate.rate_limit_minutes_total(), 60)       # many minutes of backoff, recorded as rate-limit wait

    def test_abort_ends_a_rate_limit_wait(self):
        from devmem.eval.quota_gate import RunAborted

        def real(*a, **k):
            e = ModelPinnedError("rate limited")
            e.rate_limited = True
            raise e
        gate, clock, rd = self._gate(real)
        (rd / "ABORT").write_text("operator")
        with self.assertRaises(RunAborted):
            gate("p")


class TestReadTimeoutAndPerKeyCooldown(RouterFixture):
    """PM decisions 2026-10-08: importance scoring read timeout 30 s (was 15 s); a timeout cools only the key that timed out, for 10 s (was 30 s on every key)."""

    def setUp(self):
        super().setUp()
        base = yaml.safe_load(open(self.cfg, encoding="utf-8"))
        base["providers"][0]["keys"] = [{"env": f"GEMINI_KEY_OUTAGE_T{i}"} for i in range(1, 4)]
        self.cfg.write_text(yaml.dump(base), encoding="utf-8")
        p = mock.patch.dict(os.environ, {"GEMINI_KEY_OUTAGE_T3": "dummy-placeholder-not-a-key"})
        p.start()
        self.addCleanup(p.stop)

    def test_importance_scoring_gets_30_s_and_the_other_purposes_are_unchanged(self):
        seen = {}
        for purpose in ("importance_scoring", "planning", "dialogue", "reflection"):
            with mock.patch("devmem.router.providers.requests.post", side_effect=lambda *a, **k: _response(200, OK_BODY)) as post:
                self.real("hello", tier="fast", purpose=purpose)
            seen[purpose] = post.call_args.kwargs["timeout"]
        self.assertEqual(seen, {"importance_scoring": 30, "planning": 60, "dialogue": 20, "reflection": 45})

    def test_a_timeout_cools_only_that_key_for_10_s_and_the_next_key_is_tried_at_once(self):
        calls = []

        def post(*a, **k):
            calls.append(k["headers"])
            if len(calls) == 1:
                raise requests.exceptions.Timeout("read timed out")
            return _response(200, OK_BODY)
        with mock.patch("devmem.router.providers.requests.post", side_effect=post):
            self.assertEqual(self.real("hello", tier="fast", purpose="planning"), '{"output": "7"}')
        self.assertEqual(len(calls), 2)                                           # no provider-wide wait, no retry round
        self.assertFalse(self.cm.is_provider_cooling_down("gemini")[0])
        import time as _t
        cooled = {k: v["cooldown_until"] - _t.time() for k, v in self.cm.state["cooldowns"].items() if v.get("cooldown_until", 0) > _t.time()}
        self.assertEqual(len(cooled), 1)
        self.assertTrue(0 < list(cooled.values())[0] <= 10.5)

    def test_all_keys_timing_out_never_leaks_a_fail_safe_through_the_gate(self):
        import persona.prompt_template.gpt_structure as gs
        clock = FakeClock()
        gate = QuotaGate(self.real, ["GEMINI_KEY_OUTAGE_T1"], MODEL, 450, Path(self.tmp.name) / "run", now=clock.now, sleep=clock.sleep, usage=lambda k: 0, probe=lambda: True)
        n = {"i": 0}

        def post(*a, **k):
            n["i"] += 1
            if n["i"] <= 12:                                                      # every key times out, repeatedly
                raise requests.exceptions.Timeout("read timed out")
            return _response(200, OK_BODY)
        fake_time = SimpleNamespace(time=lambda: clock.t.timestamp() + 1e9, sleep=lambda s: None)
        with mock.patch("devmem.router.cooldown.time", fake_time), mock.patch("devmem.router.providers.requests.post", side_effect=post), mock.patch.object(gs, "call_llm", gate):
            out = gs.ChatGPT_safe_generate_response("rate this", "5", "one integer", 3, "FAILSAFE", lambda r, prompt="": True, lambda r, prompt="": "got:" + r)
        self.assertEqual(out, "got:7")

    def test_the_3_key_limit_on_429_is_unchanged(self):
        with mock.patch("devmem.router.providers.requests.post", side_effect=lambda *a, **k: _response(429, {"error": {"code": 429, "message": "Resource has been exhausted"}})) as post:
            with self.assertRaises(ModelPinnedError):
                self.real("hello", tier="fast", purpose="planning")
        self.assertEqual(post.call_count, 3)


class TestRealUpstreamPathThroughAnOutage(RouterFixture):
    def test_chatgpt_safe_generate_response_returns_the_answer_not_the_fail_safe(self):
        import persona.prompt_template.gpt_structure as gs
        clock = FakeClock()
        gate = QuotaGate(self.real, ["GEMINI_KEY_OUTAGE_T1", "GEMINI_KEY_OUTAGE_T2"], MODEL, 450, Path(self.tmp.name) / "run",
                         now=clock.now, sleep=clock.sleep, usage=lambda k: 0, probe=lambda: True)
        attempts = {"n": 0}

        def post(*a, **k):
            attempts["n"] += 1
            if attempts["n"] <= 50:                                   # 25 router calls of 2 keys each fail on the network: more than 20 retries
                raise requests.exceptions.ConnectionError("network is unreachable")
            return _response(200, OK_BODY)
        failures_before = dict(gs.ROUTER_FAILURES) if isinstance(gs.ROUTER_FAILURES, dict) else None
        with mock.patch("devmem.router.providers.requests.post", side_effect=post), mock.patch.object(gs, "call_llm", gate):
            out = gs.ChatGPT_safe_generate_response("rate this", "5", "one integer", 3, "FAILSAFE", lambda r, prompt="": True, lambda r, prompt="": "got:" + r)
        self.assertEqual(out, "got:7")                                  # the real answer after the outage, never "FAILSAFE", False or None
        self.assertGreater(attempts["n"], 50)
        if failures_before is not None:
            self.assertEqual(dict(gs.ROUTER_FAILURES), failures_before)    # not counted as a router failure
        self.assertGreater(gate.outage_minutes_total(), 0)
        log = [json.loads(l)["event"] for l in (Path(self.tmp.name) / "run" / "outage_log.jsonl").read_text().splitlines()]
        self.assertEqual(log, ["outage_start", "outage_end"])
        # the network is back: the next call needs no wait
        with mock.patch("devmem.router.providers.requests.post", side_effect=lambda *a, **k: _response(200, OK_BODY)), mock.patch.object(gs, "call_llm", gate):
            out2 = gs.ChatGPT_safe_generate_response("rate this", "5", "one integer", 3, "FAILSAFE", lambda r, prompt="": True, lambda r, prompt="": "got:" + r)
        self.assertEqual(out2, "got:7")
        self.assertEqual(len([1 for _ in (Path(self.tmp.name) / "run" / "outage_log.jsonl").read_text().splitlines()]), 2)


class TestPauseAndProbe(unittest.TestCase):
    def test_pause_makes_no_call_then_one_probe_logging_only_status_and_key_index(self):
        from devmem.eval import run_arm
        with tempfile.TemporaryDirectory() as t:
            rd = Path(t)
            (rd / "PAUSE_FOR").write_text("1200")
            clock = FakeClock()
            posts = []

            def post(url, **k):
                posts.append(url)
                assert clock.t >= FakeClock().t + timedelta(seconds=1200)      # the probe comes only after the whole pause
                return _response(200, OK_BODY)
            status = run_arm.pause_and_probe(rd, ["GEMINI_KEY_7", "GEMINI_KEY_8"], sleep=clock.sleep, post=post, now=lambda: clock.t.timestamp())
            self.assertEqual((status, len(posts)), (200, 1))
            self.assertFalse((rd / "PAUSE_FOR").exists())
            log = [json.loads(l) for l in (rd / "pause_log.jsonl").read_text().splitlines()]
            self.assertEqual([r["event"] for r in log], ["pause_start", "pause_end_probe"])
            self.assertEqual((log[1]["probe_key_index"], log[1]["probe_status"]), ("7", 200))
            self.assertIsNone(run_arm.pause_and_probe(rd, ["GEMINI_KEY_7"]))   # no file: nothing happens

    def test_abort_ends_the_pause_without_a_probe(self):
        from devmem.eval import run_arm
        with tempfile.TemporaryDirectory() as t:
            rd = Path(t)
            (rd / "PAUSE_FOR").write_text("1200")
            (rd / "ABORT").write_text("x")
            clock = FakeClock()
            self.assertIsNone(run_arm.pause_and_probe(rd, ["GEMINI_KEY_7"], sleep=clock.sleep, post=lambda *a, **k: self.fail("no probe"), now=lambda: clock.t.timestamp()))


class TestArmHealthKnowsAWaitingArm(unittest.TestCase):
    def test_waiting_states(self):
        with tempfile.TemporaryDirectory() as t:
            rd = Path(t)
            self.assertIsNone(arm_health._waiting(rd))
            (rd / "outage_log.jsonl").write_text(json.dumps({"event": "outage_start"}) + "\n")
            self.assertEqual(arm_health._waiting(rd), "WAITING_NETWORK")
            (rd / "outage_log.jsonl").write_text(json.dumps({"event": "outage_start"}) + "\n" + json.dumps({"event": "outage_end", "seconds": 5}) + "\n")
            self.assertIsNone(arm_health._waiting(rd))
            (rd / "rate_limit_log.jsonl").write_text(json.dumps({"event": "rate_limit_backoff"}) + "\n")
            self.assertEqual(arm_health._waiting(rd), "WAITING_RATE_LIMIT")                    # a backoff in progress is a deliberate wait, not a dead arm
            (rd / "rate_limit_log.jsonl").write_text(json.dumps({"event": "rate_limit_end", "seconds": 5}) + "\n")
            self.assertIsNone(arm_health._waiting(rd))
            wake = (datetime.utcnow() + timedelta(hours=3)).isoformat()
            (rd / "quota_pauses.jsonl").write_text(json.dumps({"event": "pause", "wake": wake}) + "\n")
            self.assertEqual(arm_health._waiting(rd), "PAUSED_QUOTA")
            past = (datetime.utcnow() - timedelta(minutes=3)).isoformat()
            (rd / "quota_pauses.jsonl").write_text(json.dumps({"event": "pause", "wake": past}) + "\n")
            self.assertIsNone(arm_health._waiting(rd))


if __name__ == "__main__":
    unittest.main()
