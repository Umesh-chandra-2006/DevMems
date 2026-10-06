"""
Stage 3 tests (Phase 5). Offline by default: vectors are `synthetic` (or deterministic offline vectors), the LLM is
replaced only where stated (`call_llm` and the importance scorer inside consolidation), and everything else is
real: upstream Persona / AssociativeMemory / new_retrieve / reflect(), real SQLite, real save/reload.
With DEVMEM_LIVE_TESTS=1 the final class runs the scripted sweep against the live router and embeddings
(about 4 LLM calls and a handful of embedding requests).
"""
import devmem.testing_env  # noqa: F401  (offline by default)
import datetime
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND = ROOT / "reverie" / "reverie" / "backend_server"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import utils  # noqa: E402
from persona.persona import Persona  # noqa: E402
from persona.memory_structures.associative_memory import AssociativeMemory  # noqa: E402

from devmem.memory import consolidation as cons  # noqa: E402
from devmem.memory import episodic  # noqa: E402

AGENT = "Isabella Rodriguez"
PERSONA_DIR = ROOT / "reverie/environment/frontend_server/storage/base_the_ville_isabella_maria_klaus/personas" / AGENT
D1 = datetime.date(2023, 2, 13)


def vec(*xs, dim=8):
    v = list(xs) + [0.0] * (dim - len(xs))
    return v


class TestClustering(unittest.TestCase):
    """synthetic: fixed embeddings."""

    def test_groups_isolated_and_determinism(self):
        e = [vec(1, 0), vec(0.99, 0.1), vec(0, 1), vec(0.05, 0.99), vec(0, 0, 1)]
        out = cons.cluster_by_similarity(e, 0.9)
        self.assertEqual(out, [[0, 1], [2, 3], [4]])
        self.assertEqual(out, cons.cluster_by_similarity(list(e), 0.9))
        self.assertEqual(cons.cluster_by_similarity(e[::-1], 0.9), [[0], [1, 2], [3, 4]])  # order-dependent labels only

    def test_threshold_edges_and_single_linkage_chain(self):
        a, b = vec(1, 0), vec(1, 1)           # cosine = 1/sqrt(2)
        c = 0.7071067811865476
        self.assertEqual(cons.cluster_by_similarity([a, b], c - 1e-9), [[0, 1]])
        self.assertEqual(cons.cluster_by_similarity([a, b], c + 1e-6), [[0], [1]])
        chain = [vec(1, 0), vec(1, 0.4), vec(1, 0.8)]  # 0-1 and 1-2 similar, 0-2 less so: single linkage joins all
        self.assertEqual(cons.cluster_by_similarity(chain, 0.92), [[0, 1, 2]])
        self.assertEqual(cons.cluster_by_similarity([], 0.8), [])

    def test_average_linkage_resists_chaining_and_is_deterministic(self):
        chain = [vec(1, 0), vec(1, 0.4), vec(1, 0.8)]       # single linkage joins all three at 0.92 (chain)
        self.assertEqual(cons.cluster_by_similarity(chain, 0.92, "single"), [[0, 1, 2]])
        self.assertEqual(cons.cluster_by_similarity(chain, 0.92, "average"), [[0], [1, 2]])
        e = [vec(1, 0), vec(0.99, 0.1), vec(0, 1), vec(0.05, 0.99), vec(0, 0, 1)]
        self.assertEqual(cons.cluster_by_similarity(e, 0.9, "average"), [[0, 1], [2, 3], [4]])
        self.assertEqual(cons.cluster_by_similarity(e, 0.9, "average"), cons.cluster_by_similarity(list(e), 0.9, "average"))
        self.assertEqual(cons.cluster_by_similarity([], 0.9, "average"), [])
        with self.assertRaises(ValueError):
            cons.cluster_by_similarity(e, 0.9, "complete")

    def test_frozen_clustering_config_is_average_linkage_at_0_82(self):
        # frozen for the Phase 7/9 runs (pre-launch P3, docs/phase6_stop3_artifacts/linkage_check.json); the previous setting was single 0.78
        cfg = cons.load_config()
        self.assertEqual((cfg["linkage"], cfg["cluster_similarity"]), ("average", 0.82))

    def test_mixed_dimensions_refused(self):
        with self.assertRaises(ValueError):
            cons.cluster_by_similarity([vec(1, 0, dim=8), vec(1, 0, dim=4)], 0.8)

    def test_parse_summary(self):
        self.assertEqual(cons.parse_summary("**She values peace.**\nextra"), "She values peace.")
        self.assertEqual(cons.parse_summary("1. A takeaway"), "A takeaway")
        self.assertEqual(cons.parse_summary("\n- \"Quoted.\""), "Quoted.")
        self.assertEqual(cons.parse_summary(""), "")

    def test_night_key(self):
        n = lambda h, d=13: cons.night_id(datetime.datetime(2023, 2, d, h, 0))
        self.assertEqual(n(22), 1)
        self.assertEqual(n(2, 14), 1, "00:00 carry-over block belongs to the previous night")
        self.assertEqual(n(0, 13), 0, "day 1 at 00:00 is night 0")
        self.assertEqual(n(12), 1)


class StageThreeBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._mode = utils.MEMORY_MODE
        utils.MEMORY_MODE = "staged"
        cls.persona = Persona(AGENT, str(PERSONA_DIR))

    @classmethod
    def tearDownClass(cls):
        utils.MEMORY_MODE = cls._mode

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="p5_cons_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.empty = self.tmp / "empty"
        self.empty.mkdir()
        (self.empty / "nodes.json").write_text("{}")
        (self.empty / "embeddings.json").write_text("{}")
        (self.empty / "kw_strength.json").write_text(json.dumps({"kw_strength_event": {}, "kw_strength_thought": {}}))
        self.persona.a_mem = AssociativeMemory(str(self.empty))
        self.db = cons.init_consolidation_db(self.tmp / "memory.db")
        self.ledger = str(self.tmp / "ledger.db")
        self.cfg = cons.load_config()
        self.cfg.update(cluster_similarity=0.9, min_cluster_size=2, importance_floor=3)
        self.persona.scratch.curr_time = datetime.datetime.combine(D1, datetime.time(22, 0))
        self.persona.scratch.act_description = "sleeping"
        self.llm_calls = []
        self.persona.__dict__.pop("_devmem_swept_nights", None)  # in-memory guard state is per persona object
        self.persona.__dict__.pop("_devmem_sleep_block_start", None)

    def add(self, text, v, hh=9, mm=0, imp=5, day=D1):
        when = datetime.datetime.combine(day, datetime.time(hh, mm))
        node = self.persona.a_mem.add_event(when, None, AGENT, "is", text, text, {text.split()[0].lower()}, imp,
                                            (text, v), None)
        episodic.log_episodic_node(AGENT, node, sim_time=when, importance_score=imp, db_path=self.db)
        return f"{AGENT}:{node.node_id}"

    def llm(self, text="Isabella keeps her cafe running with steady, careful work.", fail=False):
        def fake(prompt, **kw):
            self.llm_calls.append(prompt)
            if fail:
                raise RuntimeError("router down")
            return text
        return fake

    def sweep(self, when=None, text=None, fail=False, embed=None, **kw):
        when = when or self.persona.scratch.curr_time
        with mock.patch.object(cons, "call_llm", self.llm(text or "Isabella keeps her cafe running with steady work.", fail)), \
             mock.patch.object(cons.episodic, "score_importance_persona_conditioned", return_value=6):
            return cons.run_nightly_sweep(self.persona, when, db_path=self.db, config=self.cfg, ledger_db=self.ledger,
                                          embed_fn=embed or (lambda t: vec(0, 0, 1)), **kw)

    def rows(self, table="episodic_memory"):
        c = sqlite3.connect(str(self.db))
        c.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in c.execute(f"SELECT * FROM {table}")]
        finally:
            c.close()


class TestSweepAndSemanticMemory(StageThreeBase):
    def test_creates_semantic_memory_with_sources_and_flags(self):
        a = self.add("baking croissants", vec(1, 0))
        b = self.add("kneading dough", vec(0.99, 0.1), 9, 30)
        c = self.add("reading a letter", vec(0, 1), 10)                  # isolated
        d = self.add("brushing teeth", vec(1, 0), 7, imp=2)             # below floor
        e = self.add("bed is idle", vec(1, 0), 7, imp=5)                # idle filter
        res = self.sweep()
        self.assertEqual(res["status"], "done")
        self.assertEqual(res["summaries_written"], 1)
        sem = self.rows("semantic_memory")
        self.assertEqual(len(sem), 1)
        self.assertEqual(sorted(json.loads(sem[0]["source_entry_ids"])), sorted([a, b]))
        flags = {r["entry_id"]: r["consolidated"] for r in self.rows()}
        self.assertEqual(flags, {a: 1, b: 1, c: 0, d: 0, e: 0})
        # live memory: summary thought node with the source node ids in filling; derived consolidated set
        node = self.persona.a_mem.id_to_node[sem[0]["entry_id"].split(":", 1)[1]]
        self.assertEqual(node.type, "thought")
        self.assertEqual(sorted(node.filling), sorted(x.split(":", 1)[1] for x in (a, b)))
        self.assertEqual(cons.consolidated_node_ids(self.persona.a_mem), set(node.filling))
        self.assertEqual(node.depth, 1)
        self.assertIn(node.embedding_key, self.persona.a_mem.embeddings)
        # marker + log line
        self.assertEqual([m["status"] for m in self.rows("consolidation_sweeps")], ["done"])
        line = json.loads((self.db.parent / "consolidation_log.jsonl").read_text().splitlines()[-1])
        self.assertEqual(line["entries_considered"], 3)  # below-floor and idle never considered
        self.assertEqual(line["cluster_size_histogram"], {"1": 1, "2": 1})

    def test_second_sweep_same_night_is_a_noop_even_when_forced_marker_ignored(self):
        self.add("baking", vec(1, 0))
        self.add("kneading", vec(0.99, 0.1), 9, 30)
        self.sweep()
        nodes_before = len(self.persona.a_mem.id_to_node)
        again = self.sweep()
        self.assertEqual(again, {"skipped": "already swept", "night": 1})
        forced = self.sweep(force=True)  # marker ignored but nothing unconsolidated remains
        self.assertEqual(forced["summaries_written"], 0)
        self.assertEqual(len(self.persona.a_mem.id_to_node), nodes_before)
        self.assertEqual(len(self.rows("semantic_memory")), 1)

    def test_reinforce_appends_sources_without_duplicates_and_derives_distinct_days(self):
        a = self.add("baking", vec(1, 0))
        b = self.add("kneading", vec(0.99, 0.1), 9, 30)
        self.sweep(embed=lambda t: vec(0, 0, 1))
        first = self.rows("semantic_memory")[0]
        self.assertEqual((first["times_reinforced"], first["distinct_days_reinforced"]), (1, 1))
        # day 2: more entries on a different sim_day; the new summary embeds close to the old one -> reinforce
        day2 = D1 + datetime.timedelta(days=1)
        c = self.add("baking again", vec(1, 0.05), 9, day=day2)
        d = self.add("kneading again", vec(0.98, 0.1), 9, 30, day=day2)
        t2 = datetime.datetime.combine(day2, datetime.time(22, 0))
        res = self.sweep(when=t2, embed=lambda t: vec(0, 0.05, 1))
        self.assertEqual(res["summaries_reinforced"], 1)
        self.assertEqual(res["summaries_written"], 0)
        sem = self.rows("semantic_memory")
        self.assertEqual(len(sem), 1)
        self.assertEqual((sem[0]["times_reinforced"], sem[0]["distinct_days_reinforced"]), (2, 2))
        self.assertEqual(sorted(json.loads(sem[0]["source_entry_ids"])), sorted([a, b, c, d]))
        self.assertEqual(len(set(json.loads(sem[0]["source_entry_ids"]))), 4)
        node = self.persona.a_mem.id_to_node[sem[0]["entry_id"].split(":", 1)[1]]
        self.assertEqual(sorted(node.filling), sorted(x.split(":", 1)[1] for x in (a, b, c, d)))
        self.assertEqual(sorted(m["night"] for m in self.rows("consolidation_sweeps")), [1, 2])

    def test_dissimilar_summary_creates_a_second_semantic_memory(self):
        self.add("baking", vec(1, 0))
        self.add("kneading", vec(0.99, 0.1), 9, 30)
        self.sweep(embed=lambda t: vec(0, 0, 1))
        day2 = D1 + datetime.timedelta(days=1)
        self.add("arguing", vec(0, 1), 9, day=day2)
        self.add("shouting", vec(0.05, 1), 9, 30, day=day2)
        self.sweep(when=datetime.datetime.combine(day2, datetime.time(22, 0)), embed=lambda t: vec(1, 0, 0))
        self.assertEqual(len(self.rows("semantic_memory")), 2)

    def test_cap_prompt_size_and_summary_cap(self):
        self.cfg.update(max_entries_per_prompt=3, max_summaries_per_night=1)
        ids = [self.add(f"event {i}", vec(1, 0.01 * i), 9, i, imp=3 + (i % 3)) for i in range(6)]
        self.add("other a", vec(0, 1), 11)
        self.add("other b", vec(0.01, 1), 11, 5)
        res = self.sweep()
        self.assertEqual(res["summaries_written"], 1, "per-night cap")
        self.assertEqual(len(self.llm_calls), 1)
        entries_block = self.llm_calls[0].split("recorded today:")[1].split("Write ONE sentence")[0]
        self.assertEqual(entries_block.count("\n- "), 3, "at most max_entries_per_prompt entries in the prompt")
        sem = self.rows("semantic_memory")
        self.assertEqual(len(json.loads(sem[0]["source_entry_ids"])), 3)
        self.assertEqual(sum(r["consolidated"] for r in self.rows()), 3, "only entries that were summarized are flagged")

    def test_first_person_reply_gets_one_corrective_retry_then_fails_if_still_wrong(self):
        self.add("baking", vec(1, 0))
        self.add("kneading", vec(0.99, 0.1), 9, 30)
        replies = iter(["I like to keep things running.", "Isabella keeps the cafe running with steady work."])
        def fake(prompt, **kw):
            self.llm_calls.append(prompt)
            return next(replies)
        with mock.patch.object(cons, "call_llm", fake),              mock.patch.object(cons.episodic, "score_importance_persona_conditioned", return_value=6):
            res = cons.run_nightly_sweep(self.persona, self.persona.scratch.curr_time, db_path=self.db, config=self.cfg,
                                         ledger_db=self.ledger, embed_fn=lambda t: vec(0, 0, 1))
        self.assertEqual(res["summary_retries"], 1)
        self.assertEqual(len(self.llm_calls), 2)
        self.assertIn("not acceptable", self.llm_calls[1])
        self.assertEqual(self.rows("semantic_memory")[0]["summary"], "Isabella keeps the cafe running with steady work.")
        # still wrong after the retry -> counted failure, no semantic memory, failed marker
        self.persona.a_mem = AssociativeMemory(str(self.empty))
        self.db = cons.init_consolidation_db(self.tmp / "memory2.db")
        self.add("baking", vec(1, 0))
        self.add("kneading", vec(0.99, 0.1), 9, 30)
        res = self.sweep(text="I keep things running.")
        self.assertEqual(res["status"], "failed")
        self.assertEqual(self.rows("semantic_memory"), [])

    def test_is_third_person(self):
        self.assertTrue(cons.is_third_person("Isabella Rodriguez bakes every morning.", "Isabella Rodriguez"))
        self.assertTrue(cons.is_third_person("Isabella smooths over conflict.", "Isabella Rodriguez"))
        self.assertFalse(cons.is_third_person("She smooths over conflict.", "Isabella Rodriguez"))
        self.assertFalse(cons.is_third_person("I realize Isabella bakes.", "Isabella Rodriguez"))
        self.assertFalse(cons.is_third_person("Isabella thinks of my cafe.", "Isabella Rodriguez"))

    def test_failed_sweep_leaves_no_done_marker_and_retries_up_to_max_attempts(self):
        a = self.add("baking", vec(1, 0))
        self.add("kneading", vec(0.99, 0.1), 9, 30)
        r1 = self.sweep(fail=True)
        self.assertEqual(r1["status"], "failed")
        self.assertTrue(r1["failures"])
        self.assertEqual(self.rows("semantic_memory"), [])
        self.assertTrue(all(r["consolidated"] == 0 for r in self.rows()))
        m = self.rows("consolidation_sweeps")[0]
        self.assertEqual((m["status"], m["attempts"]), ("failed", 1))
        r2 = self.sweep()  # retry on a later tick succeeds
        self.assertEqual(r2["status"], "done")
        self.assertEqual(self.rows("consolidation_sweeps")[0]["attempts"], 2)
        # max attempts: a different night that keeps failing stops retrying
        self.cfg["max_attempts_per_night"] = 2
        day2 = D1 + datetime.timedelta(days=1)
        self.add("x1", vec(0, 1), 9, day=day2)
        self.add("x2", vec(0.01, 1), 9, 5, day=day2)
        t2 = datetime.datetime.combine(day2, datetime.time(22, 0))
        self.sweep(when=t2, fail=True)
        self.sweep(when=t2, fail=True)
        self.assertEqual(self.sweep(when=t2), {"skipped": "max attempts reached", "night": 2})

    def test_mixed_dimension_vectors_fail_loud_not_silently(self):
        self.add("a", vec(1, 0, dim=8))
        self.add("b", vec(1, 0, dim=4), 9, 30)
        with self.assertRaises(ValueError):
            self.sweep()


class TestSleepGuardAndReload(StageThreeBase):
    def _seed(self):
        self.add("baking", vec(1, 0))
        self.add("kneading", vec(0.99, 0.1), 9, 30)

    def test_hook_fires_once_per_night_across_many_sleeping_ticks(self):
        self._seed()
        results = []
        with mock.patch.object(cons, "call_llm", self.llm()), \
             mock.patch.object(cons.episodic, "score_importance_persona_conditioned", return_value=6):
            for minute in range(0, 300, 10):  # 30 ticks asleep, including a new "sleeping" action description
                self.persona.scratch.curr_time = datetime.datetime.combine(D1, datetime.time(22, 0)) + \
                    datetime.timedelta(minutes=minute)
                self.persona.scratch.act_description = "sleeping" if minute % 20 == 0 else "asleep in bed"
                results.append(cons.maybe_sweep_on_sleep(self.persona, db_path=self.db, config=self.cfg,
                                                         ledger_db=self.ledger, embed_fn=lambda t: vec(0, 0, 1)))
        fired = [r for r in results if r]
        self.assertEqual(len(fired), 1)
        self.assertEqual(len(self.llm_calls), 1)
        self.assertEqual([m["night"] for m in self.rows("consolidation_sweeps")], [1],
                         "the 00:00 carry-over block belongs to the same night")

    def test_not_sleeping_does_nothing(self):
        self._seed()
        self.persona.scratch.act_description = "baking croissants"
        self.assertIsNone(cons.maybe_sweep_on_sleep(self.persona, db_path=self.db, config=self.cfg))
        self.assertEqual(self.rows("consolidation_sweeps"), [])

    def test_hook_swallows_errors_and_retries_next_tick(self):
        self._seed()
        with mock.patch.object(cons, "run_nightly_sweep", side_effect=[RuntimeError("db locked"), {"status": "done"}]):
            r1 = cons.maybe_sweep_on_sleep(self.persona, db_path=self.db, config=self.cfg)
            r2 = cons.maybe_sweep_on_sleep(self.persona, db_path=self.db, config=self.cfg)
        self.assertIn("error", r1)
        self.assertEqual(r2, {"status": "done"})

    def test_reload_after_sweep_does_not_resweep_but_reload_from_older_save_rolls_back(self):
        a = self.add("baking", vec(1, 0))
        b = self.add("kneading", vec(0.99, 0.1), 9, 30)
        save_k = self.tmp / "save_k"
        save_k.mkdir()
        self.persona.a_mem.save(str(save_k))                      # autosave BEFORE the sweep
        self.sweep()
        save_after = self.tmp / "save_after"
        save_after.mkdir()
        self.persona.a_mem.save(str(save_after))                  # autosave AFTER the sweep
        # (1) reload from the later save: reconcile changes nothing; the marker still blocks a re-sweep
        self.persona.a_mem = AssociativeMemory(str(save_after))
        rec = cons.reconcile_consolidation(self.persona, self.db)
        self.assertEqual((rec["removed_semantic"], rec["removed_markers"]), ([], []))
        self.assertEqual(self.sweep(), {"skipped": "already swept", "night": 1})
        # (2) reload from the older save: semantic row, marker and flags are rolled back, then the sweep fires again
        self.persona.a_mem = AssociativeMemory(str(save_k))
        rec = cons.reconcile_consolidation(self.persona, self.db)
        self.assertEqual(len(rec["removed_semantic"]), 1)
        self.assertEqual(rec["removed_markers"], [1])
        self.assertEqual(self.rows("semantic_memory"), [])
        self.assertEqual(self.rows("consolidation_sweeps"), [])
        self.assertTrue(all(r["consolidated"] == 0 for r in self.rows()))
        again = cons.reconcile_consolidation(self.persona, self.db)  # idempotent
        self.assertEqual((again["removed_semantic"], again["removed_markers"]), ([], []))
        res = self.sweep()
        self.assertEqual(res["summaries_written"], 1)
        self.assertEqual({r["entry_id"] for r in self.rows() if r["consolidated"]}, {a, b})

    def test_marker_after_loaded_clock_is_removed_even_without_new_nodes(self):
        self.add("lonely", vec(1, 0))
        self.sweep()  # nothing to cluster: marker only, no nodes added
        self.assertEqual(len(self.rows("consolidation_sweeps")), 1)
        self.persona.scratch.curr_time = datetime.datetime.combine(D1, datetime.time(20, 0))  # loaded clock earlier
        rec = cons.reconcile_consolidation(self.persona, self.db)
        self.assertEqual(rec["removed_markers"], [1])


class TestBaselineIsUnchangedAndGates(StageThreeBase):
    def setUp(self):
        super().setUp()
        self.addCleanup(lambda: setattr(utils, "MEMORY_MODE", "staged"))

    def test_helpers_are_noops_in_baseline(self):
        utils.MEMORY_MODE = "baseline"
        d = {"node_1": 1.0, "node_2": 2.0}
        self.assertIs(cons.apply_consolidated_weight(self.persona, d), d)
        self.assertFalse(cons.staged_reflection_disabled())

    def test_d1_flag_matrix_on_real_reflect_function(self):
        from persona.cognitive_modules import reflect as reflect_mod
        self.add("baking", vec(1, 0))
        self.persona.scratch.importance_trigger_curr = -1  # trigger is due
        cases = [("baseline", False, 1), ("staged", False, 0), ("staged", True, 1)]
        for mode, flag, expected_calls in cases:
            with self.subTest(mode=mode, staged_reflection=flag):
                utils.MEMORY_MODE = mode
                cfg = dict(cons._CONFIG_CACHE or cons.load_config())
                with mock.patch.dict(cons._CONFIG_CACHE, {**cfg, "staged_reflection": flag}, clear=True), \
                     mock.patch.object(reflect_mod, "run_reflect") as run, \
                     mock.patch.object(reflect_mod, "reset_reflection_counter"):
                    reflect_mod.reflect(self.persona)
                self.assertEqual(run.call_count, expected_calls)

    def test_d2_weight_demotes_consolidated_sources_in_real_new_retrieve(self):
        from persona.cognitive_modules.retrieve import new_retrieve
        from devmem.embeddings.vector_store import deterministic_fallback_vector as dv
        texts = ["Isabella is baking bread", "Isabella is kneading dough", "Isabella is baking pastries",
                 "Isabella is reading a book", "Isabella is walking the dog"]
        focal = "Isabella is baking bread"
        for i, t in enumerate(texts):  # the three baking events share the focal vector, so they rank first
            self.add(t, dv(focal) if i < 3 else dv(t), 9, i, imp=5)
        self.cfg.update(cluster_similarity=0.99, min_cluster_size=3)
        res = self.sweep(embed=dv)
        self.assertEqual(res["summaries_written"], 1)
        sources = cons.consolidated_node_ids(self.persona.a_mem)
        self.assertEqual(len(sources), 3)

        def ranks(weight):
            saved = {k: n.last_accessed for k, n in self.persona.a_mem.id_to_node.items()}
            with mock.patch.dict(cons._CONFIG_CACHE, {**cons.load_config(), "consolidated_weight": weight}, clear=True):
                out = new_retrieve(self.persona, [focal], n_count=50)[focal]
            for k, n in self.persona.a_mem.id_to_node.items():
                n.last_accessed = saved[k]
            order = [n.node_id for n in out]
            return {nid: order.index(nid) for nid in sources}
        full, half = ranks(1.0), ranks(0.5)
        self.assertTrue(all(half[k] >= full[k] for k in sources))
        self.assertTrue(any(half[k] > full[k] for k in sources), "down-weighting must move some source down")
        utils.MEMORY_MODE = "baseline"
        base = ranks(0.5)  # baseline mode ignores the weight entirely
        self.assertEqual(base, full)


class TestSleepHookInsideRealMove(StageThreeBase):
    """scripted, no network: the REAL Persona.move() runs; only perceive, plan and execute are stubbed (plan returns a
    sleeping action). The hook is reached inside move(), the real sweep runs (LLM and scorer patched), and a second
    move() the same night does nothing. In baseline mode the hook is not reached."""

    SIM = "p5_move_hook_test"

    def setUp(self):
        super().setUp()
        self.addCleanup(shutil.rmtree, ROOT / "devmem" / "storage" / self.SIM, ignore_errors=True)
        env = mock.patch.dict(os.environ, {"SIM_CODE": self.SIM})
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(lambda: setattr(utils, "MEMORY_MODE", "staged"))
        self.real_db = cons.init_consolidation_db(episodic.get_db_path())
        from devmem.embeddings.vector_store import deterministic_fallback_vector as dv
        self.vec = dv("same vector")
        for i in range(3):  # identical vectors cluster at any threshold; default config needs >= 3 entries
            when = datetime.datetime.combine(D1, datetime.time(9, i))
            n = self.persona.a_mem.add_event(when, None, AGENT, "is", f"task {i}", f"Isabella is doing task {i}",
                                             {"isabella"}, 5, (f"Isabella is doing task {i}", self.vec), None)
            episodic.log_episodic_node(AGENT, n, sim_time=when, importance_score=5, db_path=self.real_db)

    def _move(self, when):
        p = self.persona

        def fake_plan(maze, personas, new_day, retrieved):
            p.scratch.act_description = "sleeping"
            return "the Ville:Isabella Rodriguez's apartment:main room:bed"

        with mock.patch.object(type(p), "perceive", lambda self, maze: []),              mock.patch.object(type(p), "plan", lambda self, maze, personas, new_day, retrieved: fake_plan(maze, personas, new_day, retrieved)),              mock.patch.object(type(p), "execute", lambda self, maze, personas, plan: ((1, 1), "zzz", "sleeping")),              mock.patch.object(cons, "call_llm", self.llm()),              mock.patch.object(cons.episodic, "score_importance_persona_conditioned", return_value=5),              mock.patch.object(cons.episodic, "get_db_path", return_value=self.real_db):
            return p.move(None, {}, (1, 1), when)

    def test_hook_fires_inside_move_once_per_night_in_staged_mode(self):
        utils.MEMORY_MODE = "staged"
        t = datetime.datetime.combine(D1, datetime.time(22, 0))
        self.persona.scratch.curr_time = t - datetime.timedelta(seconds=10)
        out = self._move(t)
        self.assertEqual(out, ((1, 1), "zzz", "sleeping"))
        self.assertEqual(len(self.llm_calls), 1, "the sweep ran inside move()")
        sem = [r for r in self._rows_in(self.real_db, "semantic_memory")]
        self.assertEqual(len(sem), 1)
        for k in range(1, 6):  # five more ticks the same night
            self._move(t + datetime.timedelta(seconds=10 * k))
        self.assertEqual(len(self.llm_calls), 1)
        self.assertEqual(len(self._rows_in(self.real_db, "consolidation_sweeps")), 1)

    def test_hook_not_reached_in_baseline_mode(self):
        utils.MEMORY_MODE = "baseline"
        t = datetime.datetime.combine(D1, datetime.time(22, 0))
        self.persona.scratch.curr_time = t - datetime.timedelta(seconds=10)
        self._move(t)
        self.assertEqual(self.llm_calls, [])
        self.assertEqual(self._rows_in(self.real_db, "consolidation_sweeps"), [])

    @staticmethod
    def _rows_in(db, table):
        c = sqlite3.connect(str(db))
        c.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in c.execute(f"SELECT * FROM {table}")]
        finally:
            c.close()


@unittest.skipUnless(os.environ.get("DEVMEM_LIVE_TESTS") == "1", "live test: set DEVMEM_LIVE_TESTS=1")
class TestScriptedSweepLive(unittest.TestCase):
    """live: real embeddings, real router (pinned gpt-oss-20b), 2 summaries + 2 scores = about 4 LLM calls."""

    def test_scripted_day_end_to_end(self):
        from devmem.memory.scripted_sweep import run_scripted_sweep
        r = run_scripted_sweep("live_test", threshold=0.82)
        try:
            self.assertLessEqual(r["llm_calls_made"], 8)
            sem = r["semantic_rows"]
            self.assertGreaterEqual(len(sem), 1)
            groups = r["event_groups"]
            flagged = {row["entry_id"] for row in r["episodic_rows"] if row["consolidated"]}
            for row in sem:
                src = json.loads(row["source_entry_ids"])
                self.assertGreaterEqual(len(src), 2)
                self.assertTrue(set(src) <= flagged)
                self.assertEqual(len({groups[s] for s in src}), 1, "sources of one summary come from one scripted group")
            self.assertEqual(flagged, {s for row in sem for s in json.loads(row["source_entry_ids"])})
            idle_or_low = {e for e, g in groups.items() if g in ("idle", "below_floor", "isolated")}
            self.assertFalse(flagged & idle_or_low, "idle, below-floor and isolated entries stay untouched")
            self.assertIsNone(r["second_sweep_via_hook"])
            self.assertEqual(r["second_sweep_direct"]["skipped"], "already swept")
            runs = r["retrieval"]["runs"]["weight_configured"]
            self.assertTrue(all(sid in v["summary_ranks"] for v in runs.values() for sid in
                                [n["node_id"] for n in r["summary_nodes"]]), "summary nodes are retrievable")
        finally:
            shutil.rmtree(ROOT / "devmem" / "storage" / "p5_scripted_sweep_live_test", ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
