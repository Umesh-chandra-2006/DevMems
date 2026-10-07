"""
Phase 7 Stop 2a (run-readiness) tests, all OFFLINE: no network, no live LLM call. Integration is claimed only where the REAL upstream
classes are used: the real `plan._long_term_planning`, the real `Maze` and `perceive` with real Personas, a real `HeadlessRunner`-saved
simulation folder for the checkpoint, and the real router exception classes for the quota pause.
Labels: the LLM and the embeddings are stubbed (synthetic) where stated; schedules and events are the authored files.
"""
import devmem.testing_env  # noqa: F401  (offline embeddings by default)
import copy
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND = ROOT / "reverie" / "reverie" / "backend_server"
for p in (str(BACKEND), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from devmem.eval import canary, checks, run_arm  # noqa: E402
from devmem.eval.authored_plan import install  # noqa: E402
from devmem.eval.injector import EventInjector  # noqa: E402
from devmem.eval.quota_gate import QuotaGate, RunAborted, next_reset  # noqa: E402
from devmem.eval.run_support import LedgerWindows, make_checkpoint  # noqa: E402

START = datetime(2023, 2, 13)
SCHED = checks.load(checks.SCHEDULES)
EV = checks.load(checks.EVENTS)
STORAGE = ROOT / "reverie" / "environment" / "frontend_server" / "storage"
BASE_SIM = STORAGE / "base_the_ville_isabella_maria_klaus"


class TestScheduleAndEventCheckers(unittest.TestCase):
    def test_the_authored_files_pass_both_checkers(self):
        self.assertEqual(checks.check_schedules(), [])
        self.assertEqual(checks.check_events(), [])

    def mut(self, fn):
        s = copy.deepcopy(SCHED)
        fn(s)
        return checks.check_schedules(s)

    def test_schedule_violations_are_detected(self):
        self.assertTrue(any("not 1440" in v for v in self.mut(lambda s: s["agents"]["Maria Lopez"]["day_2"].__setitem__(0, ["sleeping", 350]))))

        def sleep_across_noon(s):  # a sleeping entry that starts at 06:00 and runs to 13:00 (the Step D artifact)
            d = s["agents"]["Klaus Mueller"]["day_1"]
            s["agents"]["Klaus Mueller"]["day_1"] = [["sleeping", 360], ["sleeping", 420], ["walking to the library", 60], ["sleeping", 600]]
        v = self.mut(sleep_across_noon)
        self.assertTrue(any("only 00:00 and 14:00 are allowed" in x for x in v), v)

        def nap(s):  # a nap between 12:00 and 14:00
            a = s["agents"]["Isabella Rodriguez"]["day_3"]
            a[5] = ["closing the cafe and cleaning the tables", 0]
            s["agents"]["Isabella Rodriguez"]["day_3"] = a[:4] + [["handling the lunch counter", 60], ["sleeping", 60], ["closing", 0]] + [a[-1]]
        v = self.mut(nap)
        self.assertTrue(any("nap" in x or "non-positive" in x or "only 00:00" in x for x in v), v)
        self.assertTrue(any("wake_up_hour" in x for x in self.mut(lambda s: s["agents"]["Klaus Mueller"].__setitem__("wake_up_hour", 7))))

        def differ(s):
            a = s["agents"]["Maria Lopez"]
            a["day_3"] = [["sleeping", 360], ["waking up", 120], ["studying", 360], ["sleeping", 600]]
        self.assertTrue(any("awake entries differ" in x for x in self.mut(differ)))

        def shifted(s):  # an agent with a different sleep structure
            a = s["agents"]["Klaus Mueller"]
            for k in ("day_1", "day_2", "day_3"):
                a[k] = [["sleeping", 420], ["reading", 420], ["sleeping", 600]]
        v = self.mut(shifted)
        self.assertTrue(any("do not share the same wake and sleep times" in x for x in v), v)

    def evmut(self, fn):
        e = copy.deepcopy(EV)
        fn(e)
        return checks.check_events(e, SCHED)

    def test_event_violations_are_detected(self):
        first = lambda e: next(x for x in e["events"] if x["id"] == "I1")
        self.assertTrue(any("shares content words with the priors" in v for v in self.evmut(
            lambda e: first(e).update(desc="parked outside the entrance and a harmony of strangers", rendered_memory_text="A blue delivery van is parked outside the entrance and a harmony of strangers"))))
        self.assertTrue(any("outside the awake window" in v for v in self.evmut(lambda e: first(e).update(time="15:00"))))
        self.assertTrue(any("no pivotal event" in v for v in self.evmut(lambda e: e["events"].remove(next(x for x in e["events"] if x["id"] == "I5")))))
        self.assertTrue(any("11 events" in v or "events, expected 8 to 10" in v for v in self.evmut(
            lambda e: e["events"].extend([{**first(e), "id": f"IX{i}", "time": f"1{i}:00"} for i in range(1, 3)]))))
        self.assertTrue(any("fact sheet lacks" in v for v in self.evmut(lambda e: first(e)["fact_sheet"].pop("key_detail"))))
        self.assertTrue(any("refers to unknown event" in v for v in self.evmut(lambda e: e["questions"][0].update(event_id="Z9"))))
        self.assertTrue(any("same day and time" in v for v in self.evmut(lambda e: next(x for x in e["events"] if x["id"] == "I2").update(day=1, time="08:20"))))
        self.assertTrue(any("no theme repeated on all three days" in v for v in self.evmut(
            lambda e: next(x for x in e["events"] if x["id"] == "I7").update(day=2, time="09:00"))))


class TestAuthoredPlanOnTheRealPlanFunction(unittest.TestCase):
    """The REAL plan._long_term_planning with real Personas; the LLM is made to fail loudly if anything calls it."""

    @classmethod
    def setUpClass(cls):
        cls._cwd = os.getcwd()
        os.chdir(BACKEND)

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls._cwd)

    def test_install_replaces_the_three_functions_and_uninstall_restores_them(self):
        import persona.cognitive_modules.plan as plan
        before = {n: getattr(plan, n) for n in ("generate_wake_up_hour", "generate_first_daily_plan", "generate_hourly_schedule")}
        un = install(SCHED, START.date())
        self.assertTrue(all(getattr(plan, n) is not before[n] for n in before))
        un()
        self.assertTrue(all(getattr(plan, n) is before[n] for n in before))

    def test_long_term_planning_stores_exactly_the_authored_schedule_and_calls_no_llm(self):
        import persona.cognitive_modules.plan as plan
        import persona.prompt_template.gpt_structure as gs
        from persona.persona import Persona
        from devmem.router import llm_router
        un = install(SCHED, START.date())
        boom = mock.Mock(side_effect=AssertionError("an LLM call was made"))
        try:
            with mock.patch.object(gs, "call_llm", boom), mock.patch.object(llm_router, "call_llm", boom), \
                    mock.patch.object(plan, "get_embedding", return_value=[0.0] * 8), mock.patch.object(plan, "revise_identity", lambda p: None):
                for name, a in SCHED["agents"].items():
                    p = Persona(name, str(BASE_SIM / "personas" / name))
                    for day, kind in ((1, "First day"), (2, "New day"), (3, "New day")):
                        p.scratch.curr_time = START + timedelta(days=day - 1)
                        plan._long_term_planning(p, kind)
                        self.assertEqual(p.scratch.f_daily_schedule, [list(x) for x in a[f"day_{day}"]], (name, day))
                        self.assertEqual(sum(m for _, m in p.scratch.f_daily_schedule), 1440)
                        self.assertEqual(p.scratch.daily_req, a["daily_req"])
            boom.assert_not_called()
        finally:
            un()

    def test_upstream_picks_the_authored_sleeping_entry_at_midnight_and_the_awake_entries_on_the_clock(self):
        from persona.persona import Persona
        name = "Maria Lopez"
        p = Persona(name, str(BASE_SIM / "personas" / name))
        p.scratch.f_daily_schedule = [list(x) for x in SCHED["agents"][name]["day_1"]]
        for hhmm, want in (((0, 0), "sleeping"), ((5, 59), "sleeping"), ((6, 0), "waking up and getting ready for the day"),
                           ((8, 0), "studying physics at the Oak Hill College library"), ((13, 59), "working on a physics problem set at Hobbs Cafe"),
                           ((14, 0), "sleeping"), ((23, 59), "sleeping")):
            p.scratch.curr_time = START.replace(hour=hhmm[0], minute=hhmm[1])
            idx = p.scratch.get_f_daily_schedule_index()
            self.assertEqual(p.scratch.f_daily_schedule[idx][0], want, hhmm)


class TestInjectorOnRealPerceive(unittest.TestCase):
    """Real Maze, real Personas, the real perceive(); the LLM is stubbed (synthetic), embeddings are the offline deterministic vectors."""

    @classmethod
    def setUpClass(cls):
        cls._cwd = os.getcwd()
        os.chdir(BACKEND)
        import utils
        from maze import Maze
        cls.utils = utils
        cls.maze = Maze("the_ville")
        cls.sim = "p7_test_injector"
        cls.run_dir = ROOT / "devmem" / "storage" / cls.sim
        env0 = json.loads((BASE_SIM / "environment" / "0.json").read_text(encoding="utf-8"))
        cls.tiles = {n: tuple(env0[n]["x"] and (env0[n]["x"], env0[n]["y"])) for n in SCHED["agents"]}

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls._cwd)
        shutil.rmtree(cls.run_dir, ignore_errors=True)

    def setUp(self):
        from persona.persona import Persona
        shutil.rmtree(self.run_dir, ignore_errors=True)
        self.run_dir.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, self.run_dir, True)
        self.personas = {}
        for name in SCHED["agents"]:
            p = Persona(name, str(BASE_SIM / "personas" / name))
            p.scratch.curr_tile = self.tiles[name]
            p.scratch.act_description = "working"
            self.personas[name] = p
        self.rs = SimpleNamespace(personas=self.personas, personas_tile=dict(self.tiles), maze=self.maze, step=1000,
                                  curr_time=START + timedelta(days=0, hours=8, minutes=19, seconds=50))
        self._env = mock.patch.dict(os.environ, {"SIM_CODE": self.sim})
        self._env.start()
        self.addCleanup(self._env.stop)

    def run_perceive(self, mode):
        self.utils.MEMORY_MODE = mode
        import persona.prompt_template.gpt_structure as gs
        from devmem.memory import episodic
        patches = [mock.patch.object(episodic, "call_llm", return_value="6"), mock.patch.object(gs, "call_llm", return_value='{"output": "5"}')]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def step(self, injector, mode_persona=None):
        injector.tick(self.rs)
        for name, p in self.personas.items():
            p.scratch.curr_time = self.rs.curr_time
            p.perceive(self.maze)
        self.rs.step += 1
        self.rs.curr_time += timedelta(seconds=10)

    def test_every_one_of_the_27_events_is_perceived_stored_verbatim_and_scored_in_both_arms(self):
        for arm, mode, score in (("staged", "staged", 6), ("baseline", "baseline", 5)):
            self.setUp()
            self.run_perceive(mode)
            for e in EV["events"]:
                log = self.run_dir / f"inj_{arm}_{e['id']}.jsonl"
                inj = EventInjector([e], START, log, arm)
                self.rs.curr_time = inj.planned(e)
                self.step(inj)
                self.step(inj)
                recs = [json.loads(l) for l in log.read_text().splitlines()]
                self.assertEqual(len(recs), 1, (arm, e["id"]))
                r = recs[0]
                self.assertEqual((r["result"], r["stored_text"], r["perceived_and_stored"]), ("PASS", e["rendered_memory_text"], True), (arm, e["id"]))
                self.assertEqual(r["importance"], score, (arm, e["id"]))
                self.assertFalse(r["agent_asleep_at_injection"])
                tile = tuple(r["tile"])
                self.assertFalse(any(x[3] == e["desc"] for x in self.maze.tiles[tile[1]][tile[0]]["events"]), "the event was removed after verification")

    def test_the_injection_step_is_identical_in_both_arms_and_depends_only_on_the_clock(self):
        steps = {}
        for arm, mode in (("baseline", "baseline"), ("staged", "staged")):
            self.setUp()
            self.run_perceive(mode)
            e = EV["events"][0]
            inj = EventInjector([e], START, self.run_dir / f"{arm}.jsonl", arm)
            self.rs.curr_time = inj.planned(e) - timedelta(seconds=30)
            for _ in range(8):
                self.step(inj)
            steps[arm] = json.loads((self.run_dir / f"{arm}.jsonl").read_text().splitlines()[0])["injected_step"]
        self.assertEqual(steps["baseline"], steps["staged"])
        self.assertEqual(steps["staged"], 1000 + 3, "injected at the first step boundary at or after the authored time")

    def test_an_event_that_is_not_perceived_gets_a_FAIL_line_after_six_steps_and_is_removed(self):
        self.run_perceive("staged")
        e = EV["events"][0]
        inj = EventInjector([e], START, self.run_dir / "fail.jsonl", "staged")
        self.rs.curr_time = inj.planned(e)
        inj.tick(self.rs)
        tile = self.tiles[e["agent"]]
        self.assertTrue(any(x[3] == e["desc"] for x in self.maze.tiles[tile[1]][tile[0]]["events"]))
        for _ in range(7):                                    # nobody calls perceive
            self.rs.step += 1
            self.rs.curr_time += timedelta(seconds=10)
            inj.tick(self.rs)
        recs = [json.loads(l) for l in (self.run_dir / "fail.jsonl").read_text().splitlines()]
        self.assertEqual([(r["id"], r["result"]) for r in recs], [(e["id"], "FAIL")])
        self.assertFalse(any(x[3] == e["desc"] for x in self.maze.tiles[tile[1]][tile[0]]["events"]))
        self.assertEqual(inj.summary()["fail"], [e["id"]])

    def test_a_sleeping_agent_at_injection_is_recorded_and_resume_skips_logged_events(self):
        self.run_perceive("staged")
        e = EV["events"][0]
        self.personas[e["agent"]].scratch.act_description = "sleeping"
        log = self.run_dir / "resume.jsonl"
        inj = EventInjector([e], START, log, "staged")
        self.rs.curr_time = inj.planned(e)
        self.step(inj)
        self.step(inj)
        self.assertTrue(json.loads(log.read_text().splitlines()[0])["agent_asleep_at_injection"])
        again = EventInjector([e], START, log, "staged")           # as after a resume
        self.rs.curr_time = inj.planned(e) + timedelta(hours=1)
        again.tick(self.rs)
        self.assertEqual(again.pending, [])
        self.assertEqual(len(log.read_text().splitlines()), 1)


class TestQuotaGate(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="p7_gate_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.slept = []
        self.clock = [datetime(2026, 10, 7, 5, 0, 0)]

    def gate(self, real, usage, **kw):
        def sleep(s):
            self.slept.append(s)
            self.clock[0] += timedelta(seconds=s)
        return QuotaGate(real, ["K1", "K2"], "m", 450, self.tmp, sleep=sleep, now=lambda: self.clock[0], usage=usage, **kw)

    def test_all_keys_at_the_cap_pauses_until_the_reset_then_retries_the_same_call_without_crashing(self):
        from devmem.router.providers import ModelPinnedError
        used = {"K1": 450, "K2": 450}
        calls = []

        def real(*a, **k):
            calls.append((a, k))
            if len(calls) == 1:
                raise ModelPinnedError("Pinned model 'm' failed across all configured keys.")
            return "answer"
        g = self.gate(real, lambda k: used[k])
        orig_wait = g.wait

        def wait(seconds, reason):
            orig_wait(seconds, reason)
            used.update(K1=0, K2=0)                      # the quota day rolled over
        g.wait = wait
        self.assertEqual(g("prompt", tier="fast", pinned_model="m"), "answer")
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0], calls[1], "the identical call is retried; no other model, no changed argument")
        self.assertAlmostEqual(sum(self.slept), 7200 + 120, delta=31)       # 05:00 to the 07:00 UTC reset plus the margin
        recs = [json.loads(l) for l in (self.tmp / "quota_pauses.jsonl").read_text().splitlines()]
        self.assertEqual([r["event"] for r in recs], ["pause", "resume"])
        self.assertIn("per-key daily cap 450", recs[0]["reason"])

    def test_a_provider_lockout_longer_than_the_router_wait_is_waited_out(self):
        from devmem.router.providers import ModelPinnedError
        seq = [ModelPinnedError("Pinned model 'm' exhausted or cooling down across all keys. Earliest available key at x (in 4000s)."), "ok"]

        def real(*a, **k):
            r = seq.pop(0)
            if isinstance(r, Exception):
                raise r
            return r
        g = self.gate(real, lambda k: 0)
        self.assertEqual(g("p"), "ok")
        self.assertAlmostEqual(sum(self.slept), 4005, delta=31)

    def test_a_generic_pinned_failure_is_retried_a_bounded_number_of_times_and_then_raised(self):
        from devmem.router.providers import ModelPinnedError

        def real(*a, **k):
            raise ModelPinnedError("Pinned model 'm' failed across all configured keys.")
        g = self.gate(real, lambda k: 0, max_generic_retries=3, generic_wait=10)
        with self.assertRaises(ModelPinnedError):
            g("p")
        self.assertEqual(sum(self.slept), 30)

    def test_other_exceptions_and_the_call_cap_pass_through_untouched(self):
        from devmem.router import call_counter
        g = self.gate(mock.Mock(side_effect=ValueError("bad prompt")), lambda k: 0)
        with self.assertRaises(ValueError):
            g("p")
        g = self.gate(mock.Mock(side_effect=call_counter.CapReached("cap")), lambda k: 0)
        with self.assertRaises(call_counter.CapReached):
            g("p")
        self.assertEqual(self.slept, [])

    def test_the_abort_file_ends_a_pause(self):
        from devmem.router.providers import ModelPinnedError
        g = self.gate(mock.Mock(side_effect=ModelPinnedError("Pinned model 'm' failed across all configured keys.")), lambda k: 450)
        (self.tmp / "ABORT").write_text("stop")
        with self.assertRaises(RunAborted):
            g("p")

    def test_next_reset_is_the_following_0700_utc(self):
        self.assertEqual(next_reset(datetime(2026, 10, 7, 5, 0)), datetime(2026, 10, 7, 7, 0))
        self.assertEqual(next_reset(datetime(2026, 10, 7, 7, 0)), datetime(2026, 10, 8, 7, 0))
        self.assertEqual(next_reset(datetime(2026, 10, 7, 23, 59)), datetime(2026, 10, 8, 7, 0))

    def test_embedding_exhaustion_pauses_and_retries(self):
        from devmem.embeddings.vector_store import EmbeddingError
        seq = [EmbeddingError("all embedding keys failed or unavailable: none usable"), [[1.0]]]

        class Store:
            model = "gemini-embedding-001"

            def embed_texts(self, texts, batch=True):
                r = seq.pop(0)
                if isinstance(r, Exception):
                    raise r
                return r
        g = self.gate(mock.Mock(), lambda k: 0, generic_wait=5)
        store = Store()
        g.wrap_embedding_store(store, [], rpd=1000)
        self.assertEqual(store.embed_texts(["x"]), [[1.0]])
        self.assertEqual(sum(self.slept), 5)


class TestQuotaDayAndKeyPlan(unittest.TestCase):
    def test_default_quota_day_is_the_local_date_and_the_env_gate_moves_the_boundary_to_the_reset_hour(self):
        from devmem.router import key_pool
        with mock.patch.dict(os.environ, {"DEVMEM_QUOTA_RESET_UTC_HOUR": ""}):
            self.assertEqual(key_pool.get_today_str(), date.today().isoformat())
        with mock.patch.dict(os.environ, {"DEVMEM_QUOTA_RESET_UTC_HOUR": "7"}):
            self.assertEqual(key_pool.get_today_str(), (datetime.utcnow() - timedelta(hours=7)).date().isoformat())
        with mock.patch.dict(os.environ, {"DEVMEM_QUOTA_RESET_UTC_HOUR": "0"}):
            self.assertEqual(key_pool.get_today_str(), datetime.utcnow().date().isoformat())

    def test_arm_key_sets_are_disjoint_gemini_verified_and_seven_each(self):
        b, s = run_arm.ARM_KEYS["baseline"], run_arm.ARM_KEYS["staged"]
        self.assertEqual((len(b), len(s)), (7, 7))
        self.assertFalse(set(b) & set(s))
        self.assertTrue(set(b + s) <= set(run_arm.VERIFIED_CHAT_KEYS))
        self.assertFalse(any("GROQ" in k or "NIM" in k for k in b + s))
        self.assertNotIn("GEMINI_KEY_9", b + s)
        verified = (ROOT / "docs" / "key_verification_2026_10_07.md").read_text(encoding="utf-8")
        self.assertIn("GEMINI_KEY_9 returns 403", verified)

    def test_plan_matches_the_launch_spec(self):
        for arm in ("baseline", "staged"):
            p = run_arm.plan(arm, f"p7_{arm}")
            self.assertTrue(p["keys_disjoint"])
            self.assertEqual((p["pinned_model"], p["normalizer"], p["per_key_daily_cap"], p["hard_cap_calls"], p["soft_stop_calls"], p["autosave_sim_minutes"]),
                             ("gemini-3.1-flash-lite", "on", 450, 9500, 8500, 15))
            self.assertEqual(p["stage4"], arm == "staged")
            self.assertFalse(p["groq_or_nim_used"])
        self.assertEqual(run_arm.preflight("baseline"), [])
        self.assertEqual(run_arm.preflight("staged"), [])

    def test_dry_run_prints_the_plan_and_touches_nothing(self):
        import io
        import contextlib
        before = set(p.name for p in (ROOT / "devmem" / "storage").glob("p7_*"))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            run_arm.main(["--arm", "staged", "--dry-run"])
        self.assertIn("preflight: clean", buf.getvalue())
        self.assertEqual(before, set(p.name for p in (ROOT / "devmem" / "storage").glob("p7_*")))

    def test_the_checkpoint_steps_coincide_with_autosave_steps(self):
        from devmem.run_headless import load_autosave_interval_minutes
        interval_steps = (load_autosave_interval_minutes() * 60) // 10
        for when in run_arm.CHECKPOINTS.values():
            step = int((when - START).total_seconds() // 10)
            self.assertEqual(step % interval_steps, 0, when)
        self.assertEqual(run_arm.UNTIL, datetime(2023, 2, 16))


class TestCheckpointAndLedgerWindows(unittest.TestCase):
    def test_checkpoint_copies_personas_meta_one_environment_file_and_a_consistent_database(self):
        tmp = Path(tempfile.mkdtemp(prefix="p7_ckpt_"))
        self.addCleanup(shutil.rmtree, tmp, True)
        storage, sim, run_dir = tmp / "storage", "simX", tmp / "run"
        shutil.copytree(BASE_SIM, storage / sim)                       # the real base simulation folder as a stand-in for a saved run
        (storage / sim / "movement").mkdir(exist_ok=True)
        (storage / sim / "movement" / "5.json").write_text("{}")
        (storage / sim / "environment" / "5.json").write_text("{}")
        run_dir.mkdir()
        db = sqlite3.connect(str(run_dir / "memory.db"))
        db.execute("CREATE TABLE episodic_memory (entry_id TEXT, content TEXT)")
        db.executemany("INSERT INTO episodic_memory VALUES (?,?)", [(f"e{i}", "x") for i in range(7)])
        db.commit()
        dst = make_checkpoint(storage, sim, 5, run_dir, "day1_end_awake", "2023-02-13 14:00:00")
        self.assertTrue((dst / "personas" / "Isabella Rodriguez" / "bootstrap_memory" / "scratch.json").exists())
        self.assertTrue((dst / "reverie" / "meta.json").exists())
        self.assertTrue((dst / "environment" / "5.json").exists())
        self.assertFalse((dst / "movement").exists(), "per-step movement files are not copied into a checkpoint")
        copy_db = run_dir / "checkpoints" / "day1_end_awake" / "memory.db"
        self.assertEqual(sqlite3.connect(str(copy_db)).execute("SELECT COUNT(*) FROM episodic_memory").fetchone()[0], 7)
        db.execute("INSERT INTO episodic_memory VALUES ('later','x')")
        db.commit()
        db.close()
        self.assertEqual(sqlite3.connect(str(copy_db)).execute("SELECT COUNT(*) FROM episodic_memory").fetchone()[0], 7, "the copy is independent of the live run")
        meta = json.loads((dst / "checkpoint.json").read_text())
        self.assertEqual((meta["label"], meta["step"], meta["sim_clock"]), ("day1_end_awake", 5, "2023-02-13 14:00:00"))

    def test_ledger_windows_split_by_hour_filter_by_arm_and_record_sleep_fractions(self):
        from devmem.router import key_pool
        tmp = Path(tempfile.mkdtemp(prefix="p7_led_"))
        self.addCleanup(shutil.rmtree, tmp, True)
        dbp = str(tmp / "ledger.db")
        kp = SimpleNamespace(get_db_connection=lambda: key_pool.get_db_connection(dbp))
        win = LedgerWindows(kp, tmp, "staged", ["A", "B"])
        conn = key_pool.get_db_connection(dbp)

        def log(purpose, agent, cond, ti, to):
            conn.execute("INSERT INTO llm_call_log (call_id, provider, model, purpose, tokens_in, tokens_out, agent_id, condition) VALUES (?,?,?,?,?,?,?,?)",
                         (os.urandom(6).hex(), "gemini", "m", purpose, ti, to, agent, cond))
            conn.commit()
        log("planning", "A", "staged", 100, 10)
        log("importance_scoring", "A", "staged", 50, 2)
        log("planning", "A", "baseline", 999, 9)           # the other arm shares the ledger and is excluded from this arm's window
        for i in range(10):
            win.observe_step({"A": False, "B": i < 6})
        r1 = win.record("hour_ending_x", "2023-02-13 07:00:00", 360, {"router_calls_total": 2})
        self.assertEqual((r1["calls"], r1["tokens_in"], r1["tokens_out"]), (2, 150, 12))
        self.assertEqual(r1["by_purpose"]["planning"]["calls"], 1)
        self.assertEqual(r1["sleeping_step_fraction"], {"A": 0.0, "B": 0.6})
        log("planning", "B", "staged", 7, 1)
        r2 = win.record("hour_ending_y", "2023-02-13 08:00:00", 720, {})
        self.assertEqual((r2["calls"], r2["tokens_in"]), (1, 7))
        self.assertEqual(len((tmp / "hourly_ledger.jsonl").read_text().splitlines()), 2)
        conn.close()


class TestMovementExporterAndPilotPlan(unittest.TestCase):
    def _sim(self, d, steps):
        (d / "movement").mkdir(parents=True)
        (d / "reverie").mkdir()
        (d / "reverie" / "meta.json").write_text(json.dumps({"curr_time": "February 13, 2023, 00:10:00", "sec_per_step": 10, "step": 60,
                                                             "persona_names": ["A"], "maze_name": "the_ville"}))
        for s in steps:
            (d / "movement" / f"{s}.json").write_text(json.dumps({"persona": {"A": {"movement": [1, 2], "pronunciatio": "x", "description": "d", "chat": None}}}))

    def test_incremental_export_is_readable_and_grows(self):
        import zipfile
        from devmem.api.movement_archive import MovementExporter, MovementSource
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            self._sim(t / "sim", [0, 1, 2])
            ex = MovementExporter(t / "sim", t / "run" / "movement.zip")
            self.assertEqual(ex.export()["frames"], 3)
            self._sim_more = (t / "sim" / "movement" / "3.json").write_text((t / "sim" / "movement" / "2.json").read_text())
            self.assertEqual(ex.export()["frames"], 4)
            self.assertFalse((t / "run" / "movement.zip.tmp").exists())
            self.assertIn("thoughts.json", zipfile.ZipFile(t / "run" / "movement.zip").namelist())
            src = MovementSource.open(t / "run", "x")
            self.assertEqual(len(src.frames(0, 10)["frames"]), 4)

    def test_pilot_plan_uses_only_new_disjoint_keys_and_small_caps(self):
        for arm in ("baseline", "staged"):
            self.assertEqual(run_arm.preflight(arm, pilot=True), [])
            pl = run_arm.plan(arm, f"p7pilot_{arm}", pilot=True)
            self.assertTrue(pl["PILOT"] and pl["keys_disjoint"])
            self.assertEqual((pl["hard_cap_calls"], pl["soft_stop_calls"], pl["until"]), (1100, 1000, "2023-02-13 09:00:00"))
            self.assertTrue(set(pl["chat_keys"]) <= set(run_arm.NEW_KEYS_2026_10_07))


class TestFenceCountFromRawLog(unittest.TestCase):
    def test_counts_only_replies_whose_fence_was_removed(self):
        from devmem.eval.run_support import count_fence_strips
        fenced = '```json\n{"output": "a"}\n```'
        nonjson = '```json\nnot json\n```'
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / "raw_replies.jsonl"
            rows = [{"raw": fenced, "delivered": '{"output": "a"}'},      # stripped
                    {"raw": nonjson, "delivered": nonjson},              # left alone
                    {"raw": '{"output": "a"}', "delivered": '{"output": "a"}'}]
            f.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
            self.assertEqual(count_fence_strips(f), 1)
            self.assertEqual(count_fence_strips(Path(t) / "missing.jsonl"), 0)


class TestCanaryEvaluator(unittest.TestCase):
    def build(self, tmp, steps=720, drift=False):
        run_dir, sim_dir = tmp / "run", tmp / "sim"
        (sim_dir / "movement").mkdir(parents=True)
        run_dir.mkdir()
        for step in range(steps):
            clock = START + timedelta(seconds=10 * step)
            minute = clock.hour * 60 + clock.minute
            persona = {}
            for name, a in SCHED["agents"].items():
                t, desc = 0, "sleeping"
                for d, m in a["day_1"]:
                    if t <= minute < t + m:
                        desc = d + " (subtask)" if "sleep" not in d else "sleeping"
                    t += m
                if drift and name == "Klaus Mueller":
                    desc = "wandering"
                persona[name] = {"description": f"{desc} @ the Ville:somewhere", "movement": [1, 1]}
            (sim_dir / "movement" / f"{step}.json").write_text(json.dumps({"persona": persona}))
        windows = [{"label": f"hour_ending_h{h}", "calls": 100, "steps_in_window": 360, "sleeping_step_fraction": {n: 0.0 if h > 6 else 1.0 for n in SCHED["agents"]}} for h in range(1, steps // 360 + 1)]
        (run_dir / "hourly_ledger.jsonl").write_text("\n".join(json.dumps(w) for w in windows) + "\n")
        (run_dir / "injection_log.jsonl").write_text("\n".join(json.dumps({"id": f"E{i}", "type": "mundane", "result": "PASS", "injected_step": 100 + i}) for i in range(3)) + "\n")
        (run_dir / "run_status.json").write_text(json.dumps({"step": steps, "router_calls_total": 400, "router_failures": 0}))
        (run_dir / "raw_replies.jsonl").write_text(json.dumps({"model": "gemini-3.1-flash-lite"}) + "\n")
        c = sqlite3.connect(str(run_dir / "memory.db"))
        c.execute("CREATE TABLE consolidation_sweeps (agent_id TEXT, night INTEGER, sweep_time TEXT, max_node_id INTEGER, attempts INTEGER, status TEXT)")
        c.execute("INSERT INTO consolidation_sweeps VALUES ('Isabella Rodriguez', 0, '2023-02-13 00:00:00', 0, 1, 'done')")
        c.commit(); c.close()
        return run_dir, sim_dir

    def test_clean_run_passes_every_check(self):
        tmp = Path(tempfile.mkdtemp(prefix="p7_canary_"))
        self.addCleanup(shutil.rmtree, tmp, True)
        run_dir, sim_dir = self.build(tmp)
        out = canary.evaluate(run_dir, sim_dir, SCHED, "baseline")
        self.assertTrue(out["all_ok"], out["abort"])
        adh = out["checks"]["schedule_adherence"]["per_agent"]
        self.assertTrue(all(v["rate"] == 1.0 for v in adh.values()), adh)

    def test_each_abort_criterion_fires_on_its_own_violation(self):
        tmp = Path(tempfile.mkdtemp(prefix="p7_canary2_"))
        self.addCleanup(shutil.rmtree, tmp, True)
        run_dir, sim_dir = self.build(tmp)
        # A3: one agent ignores its schedule
        d2 = tmp / "d2"
        d2.mkdir()
        r2, s2 = self.build(d2, drift=True)
        self.assertTrue(any(x.startswith("A3") for x in canary.evaluate(r2, s2, SCHED, "baseline")["abort"]))
        # A2: a pivotal event not perceived; and a low pass rate
        (run_dir / "injection_log.jsonl").write_text(json.dumps({"id": "I5", "type": "pivotal", "result": "FAIL", "injected_step": 1}) + "\n")
        self.assertTrue(any(x.startswith("A2") for x in canary.evaluate(run_dir, sim_dir, SCHED, "baseline")["abort"]))
        (run_dir / "injection_log.jsonl").write_text("\n".join(json.dumps({"id": f"E{i}", "type": "mundane", "result": "PASS" if i == 0 else "FAIL", "injected_step": i}) for i in range(4)) + "\n")
        self.assertTrue(any("only 1 of 4" in x for x in canary.evaluate(run_dir, sim_dir, SCHED, "baseline")["abort"]))
        # A4 router failures, A6 call rate, A7 other model, A5 night key
        (run_dir / "run_status.json").write_text(json.dumps({"step": 720, "router_calls_total": 100, "router_failures": 5}))
        self.assertTrue(any(x.startswith("A4") for x in canary.evaluate(run_dir, sim_dir, SCHED, "baseline")["abort"]))
        (run_dir / "run_status.json").write_text(json.dumps({"step": 720, "router_calls_total": 100, "router_failures": 0}))
        (run_dir / "raw_replies.jsonl").write_text(json.dumps({"model": "openai/gpt-oss-20b"}) + "\n")
        self.assertTrue(any(x.startswith("A7") for x in canary.evaluate(run_dir, sim_dir, SCHED, "baseline")["abort"]))
        c = sqlite3.connect(str(run_dir / "memory.db"))
        c.execute("INSERT INTO consolidation_sweeps VALUES ('Maria Lopez', 1, '2023-02-13 12:00:00', 0, 1, 'done')")
        c.commit(); c.close()
        self.assertTrue(any(x.startswith("A5") for x in canary.evaluate(run_dir, sim_dir, SCHED, "baseline")["abort"]))
        # A6 needs at least 4 awake agent-hours at more than 165 calls per awake agent-hour
        w = [{"label": f"hour_ending_h{h}", "calls": 3000, "steps_in_window": 360, "sleeping_step_fraction": {n: 0.0 for n in SCHED["agents"]}} for h in range(1, 3)]
        (run_dir / "hourly_ledger.jsonl").write_text("\n".join(json.dumps(x) for x in w) + "\n")
        self.assertTrue(any(x.startswith("A6") for x in canary.evaluate(run_dir, sim_dir, SCHED, "baseline")["abort"]))

    def test_call_rate_counts_partial_windows_by_their_own_length(self):
        # the pilot case: no whole hourly window, only partial windows after resumes (3 agents awake, 180 steps = half an hour each)
        tmp = Path(tempfile.mkdtemp(prefix="p7_canary_rate_"))
        self.addCleanup(shutil.rmtree, tmp, True)
        run_dir, sim_dir = tmp / "run", tmp / "sim"
        run_dir.mkdir()
        sim_dir.mkdir()
        (run_dir / "run_status.json").write_text(json.dumps({"step": 1080, "router_calls_total": 600, "router_failures": 0}))
        awake = {n: 0.0 for n in SCHED["agents"]}
        w = [{"label": f"final_partial_window", "calls": 100, "steps_in_window": 180, "sleeping_step_fraction": awake} for _ in range(6)]
        (run_dir / "hourly_ledger.jsonl").write_text("\n".join(json.dumps(x) for x in w) + "\n")
        rate = canary.evaluate(run_dir, sim_dir, SCHED, "baseline")["checks"]["call_rate"]
        self.assertEqual(rate["awake_agent_hours"], 9.0)               # 6 windows x 0.5 h x 3 agents
        self.assertEqual(rate["calls_per_awake_agent_hour"], 66.7)     # 600 calls / 9 awake agent-hours

    def test_cross_arm_injection_steps_must_match(self):
        tmp = Path(tempfile.mkdtemp(prefix="p7_canary3_"))
        self.addCleanup(shutil.rmtree, tmp, True)
        a, b = tmp / "a", tmp / "b"
        a.mkdir(); b.mkdir()
        (a / "injection_log.jsonl").write_text(json.dumps({"id": "E1", "injected_step": 10}) + "\n" + json.dumps({"id": "E2", "injected_step": 20}) + "\n")
        (b / "injection_log.jsonl").write_text(json.dumps({"id": "E1", "injected_step": 10}) + "\n" + json.dumps({"id": "E2", "injected_step": 21}) + "\n")
        out = canary.compare_injections(a, b)
        self.assertEqual((out["common_events"], out["different_step"], out["ok"]), (2, ["E2"], False))


if __name__ == "__main__":
    unittest.main()
