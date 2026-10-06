"""
P5.0a tests: runner autosave and mirror reconciliation after a crash and reload.

All scenarios are SCRIPTED (events are inserted by the test, no LLM calls, no network).
Classes under test are the real upstream AssociativeMemory / Persona / ReverieServer and a real
SQLite file; the only scripted part is what happens inside each simulated step.
"""

import devmem.testing_env  # noqa: F401  (offline by default; DEVMEM_LIVE_TESTS=1 for live)
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

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = PROJECT_ROOT / "reverie" / "reverie" / "backend_server"
TEMP_STORAGE = PROJECT_ROOT / "reverie" / "environment" / "frontend_server" / "temp_storage"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from persona.memory_structures.associative_memory import AssociativeMemory  # noqa: E402

from devmem.memory.episodic import (  # noqa: E402
    init_episodic_db,
    log_episodic_node,
    reconcile_mirror,
)

T0 = datetime.datetime(2023, 2, 13, 9, 0, 0)


def _empty_memory_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "nodes.json").write_text("{}")
    (path / "embeddings.json").write_text("{}")
    (path / "kw_strength.json").write_text(json.dumps({"kw_strength_event": {}, "kw_strength_thought": {}}))


def _add_event(a_mem, db, agent, text, minute):
    when = T0 + datetime.timedelta(minutes=minute)
    node = a_mem.add_event(
        when, None, agent, "is", text, f"{agent} is {text}", {agent.lower(), text},
        3, (f"{agent} is {text}", [0.1, 0.2, 0.3]), None,
    )
    log_episodic_node(agent, node, sim_time=when, importance_score=3, db_path=db)
    return node


def _rows(db, agent):
    conn = sqlite3.connect(str(db))
    try:
        return conn.execute(
            "SELECT entry_id, content, importance_score, consolidated FROM episodic_memory "
            "WHERE agent_id = ? ORDER BY entry_id", (agent,)
        ).fetchall()
    finally:
        conn.close()


class TestReconcileRealMemory(unittest.TestCase):
    """scripted: real AssociativeMemory save/load + real SQLite, crash after save k."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="p5_0a_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.db = init_episodic_db(db_path=self.tmp / "memory.db")
        self.agent = "Isabella Rodriguez"
        self.save_dir = self.tmp / "save_k"
        _empty_memory_dir(self.save_dir)

    def test_crash_and_reload_from_save_k(self):
        a_mem = AssociativeMemory(str(self.save_dir))
        # run to step k: 5 events, autosave
        for i in range(5):
            _add_event(a_mem, self.db, self.agent, f"original event {i}", i)
        a_mem.save(str(self.save_dir))
        rows_at_k = _rows(self.db, self.agent)
        self.assertEqual(len(rows_at_k), 5)

        # continue to k+m (3 more events), then "crash": no save
        for i in range(5, 8):
            _add_event(a_mem, self.db, self.agent, f"original event {i}", i)
        self.assertEqual(len(_rows(self.db, self.agent)), 8)

        # reload from save k
        reloaded = AssociativeMemory(str(self.save_dir))
        self.assertEqual(len(reloaded.id_to_node), 5)

        # Without reconciliation replay would collide: INSERT OR IGNORE keeps the stale rows.
        # (documented here as the failure being fixed)
        res = reconcile_mirror(
            self.agent, list(reloaded.id_to_node.keys()),
            {nid: n.description for nid, n in reloaded.id_to_node.items()}, db_path=self.db,
        )
        self.assertEqual(res["removed_orphans"], [f"{self.agent}:node_{i}" for i in (6, 7, 8)])
        self.assertEqual(res["content_mismatch"], [])
        self.assertEqual(_rows(self.db, self.agent), rows_at_k, "rows at or before k must be unchanged")

        # replay with DIFFERENT content: no collision, new rows carry the replayed content
        for i in range(5, 8):
            _add_event(reloaded, self.db, self.agent, f"replayed event {i}", i)
        after = _rows(self.db, self.agent)
        self.assertEqual(len(after), 8)
        self.assertEqual(sorted(r[1] for r in after[5:]),
                         sorted(f"{self.agent} is replayed event {i}" for i in (5, 6, 7)))
        # mirror equals live memory exactly
        live = {f"{self.agent}:{nid}": n.description for nid, n in reloaded.id_to_node.items()}
        self.assertEqual({r[0]: r[1] for r in after}, live)

        # idempotent: second reconcile removes nothing and changes nothing
        res2 = reconcile_mirror(self.agent, list(reloaded.id_to_node.keys()), db_path=self.db)
        self.assertEqual(res2["removed_orphans"], [])
        self.assertEqual(_rows(self.db, self.agent), after)

    def test_stale_row_without_reconcile_would_collide(self):
        """Control: shows the collision that reconciliation prevents (INSERT OR IGNORE keeps stale)."""
        a_mem = AssociativeMemory(str(self.save_dir))
        _add_event(a_mem, self.db, self.agent, "original event 0", 0)
        a_mem.save(str(self.save_dir))
        _add_event(a_mem, self.db, self.agent, "original event 1", 1)  # lost in the crash
        reloaded = AssociativeMemory(str(self.save_dir))
        _add_event(reloaded, self.db, self.agent, "replayed event 1", 1)
        stale = dict((r[0], r[1]) for r in _rows(self.db, self.agent))
        self.assertEqual(stale[f"{self.agent}:node_2"], f"{self.agent} is original event 1")
        self.assertNotEqual(stale[f"{self.agent}:node_2"], reloaded.id_to_node["node_2"].description)

    def test_content_mismatch_is_reported_not_modified(self):
        a_mem = AssociativeMemory(str(self.save_dir))
        _add_event(a_mem, self.db, self.agent, "original event 0", 0)
        conn = sqlite3.connect(str(self.db))
        conn.execute("UPDATE episodic_memory SET content = 'tampered'")
        conn.commit()
        conn.close()
        res = reconcile_mirror(
            self.agent, list(a_mem.id_to_node.keys()),
            {nid: n.description for nid, n in a_mem.id_to_node.items()}, db_path=self.db,
        )
        self.assertEqual(res["content_mismatch"], [f"{self.agent}:node_1"])
        self.assertEqual(_rows(self.db, self.agent)[0][1], "tampered")

    def test_other_agents_untouched(self):
        a_mem = AssociativeMemory(str(self.save_dir))
        _add_event(a_mem, self.db, self.agent, "event", 0)
        other_mem = AssociativeMemory(str(self.save_dir))
        # other agent has rows for a node id that does not exist in THIS agent's memory
        _add_event(other_mem, self.db, "Maria Lopez", "event", 0)
        _add_event(other_mem, self.db, "Maria Lopez", "event two", 1)
        reconcile_mirror(self.agent, list(a_mem.id_to_node.keys()), db_path=self.db)
        self.assertEqual(len(_rows(self.db, "Maria Lopez")), 2)


class TestHeadlessRunnerCrashReload(unittest.TestCase):
    """scripted: real ReverieServer + real Persona save/load; step bodies are scripted (no LLM)."""

    SIM = "p5_0a_scripted_crash_test"
    FORK = "base_the_ville_isabella_maria_klaus"

    @classmethod
    def setUpClass(cls):
        cls._orig_cwd = os.getcwd()
        # ReverieServer.__init__ rewrites these tracked runtime files; restored in tearDownClass
        cls._temp_files = {p: p.read_bytes() for p in TEMP_STORAGE.glob("*.json")}

    @classmethod
    def tearDownClass(cls):
        for p in TEMP_STORAGE.glob("*.json"):
            if p not in cls._temp_files:
                p.unlink()  # runtime file created by ReverieServer.__init__ (e.g. curr_step.json)
        for p, data in cls._temp_files.items():
            p.write_bytes(data)
        os.chdir(cls._orig_cwd)

    def _cleanup(self):
        import utils
        for base in (BACKEND_DIR / utils.fs_storage / self.SIM, PROJECT_ROOT / "devmem" / "storage" / self.SIM):
            shutil.rmtree(base, ignore_errors=True)

    def setUp(self):
        from devmem.run_headless import HeadlessRunner
        self._cleanup()
        self.addCleanup(self._cleanup)
        self.Runner = HeadlessRunner

    def _scripted_runner(self, tag="original", crash_after=None, **kwargs):
        """HeadlessRunner whose step body is scripted: one new event per persona (mirrored the way
        perceive.py does), a movement file like start_server writes, then the clock advances.
        crash_after=N raises on the N-th step after construction."""
        Runner = self.Runner

        class Scripted(Runner):
            def _advance(inner):
                rs = inner.rs
                if crash_after is not None and rs.step == inner.first_step + crash_after:
                    raise RuntimeError("simulated crash")
                from devmem.memory.episodic import log_episodic_node
                for name, persona in rs.personas.items():
                    persona.scratch.curr_time = rs.curr_time  # persona.move() does this; save() needs it
                    if persona.scratch.act_start_time is None:  # set by add_new_action in a real step
                        persona.scratch.act_start_time = rs.curr_time
                    desc = f"{name} is {tag} step {rs.step}"
                    node = persona.a_mem.add_event(
                        rs.curr_time, None, name, "is", f"{tag}{rs.step}", desc,
                        {name.lower()}, 3, (desc, [0.1, 0.2, 0.3]), None,
                    )
                    log_episodic_node(name, node, sim_time=rs.curr_time, importance_score=3,
                                      db_path=inner.db_path)
                import utils
                moves = {n: {"movement": list(rs.personas_tile[n])} for n in rs.personas}
                mv = Path(f"{utils.fs_storage}/{inner.sim_code}/movement/{rs.step}.json")
                mv.write_text(json.dumps({"persona": moves, "meta": {}}))
                rs.step += 1
                rs.curr_time += datetime.timedelta(seconds=rs.sec_per_step)

        kwargs.setdefault("final_sweep", False)
        runner = Scripted(fork_sim_code=self.FORK, sim_code=self.SIM, memory_mode="staged",
                          autosave_interval_sim_minutes=1, **kwargs)
        runner.first_step = runner.rs.step
        return runner

    def test_autosave_interval_and_crash_reload(self):
        # 10 s/step and a 1-minute interval = autosave every 6 steps
        r1 = self._scripted_runner(crash_after=8)
        k0 = r1.rs.step
        self.assertEqual(r1.autosave_interval_steps, 6)
        names = list(r1.rs.personas.keys())
        base_nodes = {n: len(r1.rs.personas[n].a_mem.id_to_node) for n in names}

        with self.assertRaises(RuntimeError):
            r1.run(20)
        self.assertEqual(r1.autosave_steps, [k0 + 6], "one autosave at the interval; none on the exception")
        self.assertEqual(r1.rs.step, k0 + 8)

        db = r1.db_path
        for n in names:
            self.assertEqual(len(_rows(db, n)), 8, "mirror holds rows for steps 0..7 before reload")
        saved_rows = {n: _rows(db, n)[:6] for n in names}  # entry ids sort node_10 < node_2, so compare sets below

        # reload the autosave in place and reconcile
        r2 = self._scripted_runner(tag="replayed", resume=True)
        self.assertEqual(r2.rs.step, k0 + 6)
        for n in names:
            self.assertEqual(len(r2.rs.personas[n].a_mem.id_to_node), base_nodes[n] + 6)
        removed = {r["agent_id"]: r["removed_orphans"] for r in r2.reconcile_results}
        saved_ids = {n: {f"{n}:{nid}" for nid in r2.rs.personas[n].a_mem.id_to_node} for n in names}
        for n in names:
            self.assertEqual(len(removed[n]), 2, f"steps 6 and 7 are orphans for {n}")
            now = _rows(db, n)
            self.assertEqual(len(now), 6)
            self.assertTrue({r[0] for r in now} <= saved_ids[n])
            self.assertEqual(set(now), set(saved_rows[n]), "rows at or before k unchanged")

        # stale step files from the crashed run are gone: environment up to k, movement up to k-1
        import utils
        sim_folder = Path(f"{utils.fs_storage}/{self.SIM}")
        env_left = sorted(int(p.stem) for p in (sim_folder / "environment").glob("*.json"))
        mov_left = sorted(int(p.stem) for p in (sim_folder / "movement").glob("*.json"))
        self.assertEqual(env_left[-1], k0 + 6)
        self.assertEqual(mov_left[-1], k0 + 5)
        self.assertEqual(sorted(r2.purged_files),
                         sorted([f"environment/{k0 + 7}.json", f"environment/{k0 + 8}.json",
                                 f"movement/{k0 + 6}.json", f"movement/{k0 + 7}.json"]))

        # idempotent second reconcile
        from devmem.memory.episodic import reconcile_run
        self.assertTrue(all(r["removed_orphans"] == [] for r in reconcile_run(r2.rs.personas, db_path=db)))

        # replay steps 6 and 7 with different content: no collision; mirror equals live memory
        r2.run(2)
        for n in names:
            live = {f"{n}:{nid}": node.description for nid, node in r2.rs.personas[n].a_mem.id_to_node.items()}
            mirror = {r[0]: r[1] for r in _rows(db, n)}
            self.assertEqual(len(mirror), 8)
            for eid, content in mirror.items():
                self.assertEqual(live[eid], content)
            self.assertTrue(any("replayed step 6" in c for c in mirror.values()))
            self.assertFalse(any("original step 6" in c for c in mirror.values()))
        self.assertEqual(r2.autosave_steps[-1], r2.rs.step, "clean exit saved")

    def test_runner_sets_fail_loud_and_scan_flags_router_failure_strings(self):
        import utils
        from devmem.run_headless import scan_saved_schedules, load_runner_config
        orig = getattr(utils, "FAIL_LOUD_LLM", None)
        self.addCleanup(lambda: setattr(utils, "FAIL_LOUD_LLM", orig) if orig is not None
                        else (delattr(utils, "FAIL_LOUD_LLM") if hasattr(utils, "FAIL_LOUD_LLM") else None))
        r = self._scripted_runner()
        self.assertTrue(utils.FAIL_LOUD_LLM)
        self.assertEqual(load_runner_config()["autosave_interval_sim_minutes"], 15)
        r.run(1)  # saves on exit
        markers = r.markers
        self.assertIn("TOKEN LIMIT EXCEEDED", markers)
        self.assertEqual(scan_saved_schedules(self.SIM, markers), [], "a clean saved run has no findings")
        scratch_f = Path(BACKEND_DIR) / utils.fs_storage / self.SIM / "personas" / "Isabella Rodriguez" /             "bootstrap_memory" / "scratch.json"
        data = json.loads(scratch_f.read_text(encoding="utf-8"))
        data["f_daily_schedule_hourly_org"].append(["TOKEN LIMIT EXCEEDED", 60])
        data["f_daily_schedule"].append(["[(ID:A1B2C3) Monday February 13 -- 09:00 AM] Activity: Isabella is x", 60])
        scratch_f.write_text(json.dumps(data), encoding="utf-8")
        found = scan_saved_schedules(self.SIM, markers)
        self.assertEqual(sorted(f["marker"] for f in found), ["TOKEN LIMIT EXCEEDED", "model_echo"])
        self.assertTrue(all(f["agent"] == "Isabella Rodriguez" for f in found))

    def test_clean_exit_forces_a_sweep_for_every_agent_staged_only(self):
        from devmem.memory import consolidation as cons
        calls = []
        def fake_llm(prompt, **kw):
            calls.append(kw.get("agent_id"))
            return f"{kw.get('agent_id')} shows a steady pattern of scripted events."
        sweep_kwargs = {"embed_fn": lambda t: [0.1, 0.2, 0.3], "config": {**cons.load_config(), "min_cluster_size": 2}}
        r = self._scripted_runner(sweep_kwargs=sweep_kwargs)
        r.final_sweep = True  # _scripted_runner disables it by default so other tests make no LLM calls
        with mock.patch.object(cons, "call_llm", fake_llm),              mock.patch.object(cons.episodic, "score_importance_persona_conditioned", return_value=5):
            r.run(3)
        self.assertEqual(sorted(r.final_sweep_results), sorted(r.rs.personas))
        for name, res in r.final_sweep_results.items():
            self.assertEqual(res["status"], "done", name)
            self.assertEqual(res["summaries_written"], 1, name)
        self.assertEqual(sorted(calls), sorted(r.rs.personas))

    def test_persona_move_runs_with_agent_tag_for_ledger_logging(self):
        from persona.persona import Persona
        from devmem.router.agent_context import get_current_agent
        seen = []

        def fake_move(self, maze, personas, tile, when):
            seen.append((self.name, get_current_agent()))
            return ((1, 1), "x", "y")

        with mock.patch.object(Persona, "move", fake_move):
            r = self._scripted_runner()
            name = list(r.rs.personas)[0]
            r.rs.personas[name].move(None, {}, (1, 1), None)
        self.assertEqual(seen, [(name, name)])
        self.assertIsNone(get_current_agent(), "tag is cleared after move()")


if __name__ == "__main__":
    unittest.main()
