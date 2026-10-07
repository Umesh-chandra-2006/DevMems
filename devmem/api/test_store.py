"""
Offline tests of the memory inspector data layer (Phase 8 Stop 1) against the committed recordings: the Step D recording
(docs/phase6_stepd_artifacts, natural run) and the Stop 3 fixture run (docs/phase6_stop3_artifacts, Stages 1 to 4). Standard library
plus the project's own modules for cross-checks. No LLM call, no network, no write to a run.
"""
import hashlib
import json
import os
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from devmem.api import store

ROOT = Path(__file__).resolve().parent.parent.parent
STEPD, STOP3 = "phase6_stepd_artifacts", "phase6_stop3_artifacts"
ISA = "Isabella Rodriguez"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class TestRunsAndLabels(unittest.TestCase):
    def test_both_recordings_are_discovered_with_agents_time_range_and_stages(self):
        runs = {r["run"]: r for r in store.list_runs()}
        d, s = runs[STEPD], runs[STOP3]
        self.assertEqual(d["agents"], ["Isabella Rodriguez", "Klaus Mueller", "Maria Lopez"])
        self.assertEqual((d["sim_time_min"][:10], d["sim_time_max"][:10]), ("2023-02-13", "2023-02-13"))
        self.assertLessEqual(d["sim_time_max"], "2023-02-13 13:45:00")
        self.assertFalse(d["stages_present"]["stage4_identity"])
        self.assertFalse(d["stages_present"]["stage3_semantic"], "Step D produced no semantic summary")
        self.assertEqual(s["agents"], [ISA])
        self.assertTrue(s["stages_present"]["stage4_identity"] and s["stages_present"]["stage3_semantic"])

    def test_label_bar_fields_come_from_the_recording_and_unknown_stays_unknown(self):
        d = store.run_label(STEPD)
        self.assertEqual((d["mode"], d["model"], d["normalizer"]), ("recorded", "gemini-3.1-flash-lite", "on"))
        self.assertTrue(d["origin"].startswith("natural"))
        s = store.run_label(STOP3)
        self.assertTrue(s["origin"].startswith("scripted events"))
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "bare_run"
            run.mkdir()
            sqlite3.connect(str(run / "memory.db")).close()
            old = time_ago(run / "memory.db", 10_000)
            with mock.patch.dict(os.environ, {"DEVMEM_API_ROOTS": tmp}):
                lab = store.run_label("bare_run")
        self.assertEqual((lab["origin"], lab["model"], lab["normalizer"]), ("unknown", "unknown", "unknown"))
        self.assertTrue(lab["mode"].startswith("recorded (inferred"), lab["mode"])
        self.assertIn("none", lab["label_source"])

    def test_a_label_that_declares_recorded_wins_over_a_fresh_file_but_a_running_status_file_makes_it_live(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "r"
            run.mkdir()
            sqlite3.connect(str(run / "memory.db")).close()                       # just created: very fresh
            (run / "run_label.json").write_text(json.dumps({"mode": "recorded", "origin": "natural", "model": "m"}))
            with mock.patch.dict(os.environ, {"DEVMEM_API_ROOTS": tmp}):
                self.assertEqual(store.run_label("r")["mode"], "recorded")
                (run / "run_status.json").write_text(json.dumps({"state": "running", "router_calls_total": 1}))
                self.assertTrue(store.run_label("r")["mode"].startswith("live"))
                (run / "run_status.json").write_text(json.dumps({"state": "finished: completed"}))
                self.assertEqual(store.run_label("r")["mode"], "recorded")

    def test_a_database_written_in_the_last_two_minutes_is_labelled_live(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "r"
            run.mkdir()
            sqlite3.connect(str(run / "memory.db")).close()
            with mock.patch.dict(os.environ, {"DEVMEM_API_ROOTS": tmp}):
                self.assertTrue(store.run_label("r")["mode"].startswith("live"))

    def test_agents_and_priors_match_the_persona_files(self):
        import yaml
        agents = {a["agent"]: a for a in store.list_agents(STEPD)}
        self.assertEqual(set(agents), {"Isabella Rodriguez", "Klaus Mueller", "Maria Lopez"})
        for name in agents:
            real = yaml.safe_load(open(ROOT / "devmem/config/personas" / f"{store.slug(name)}.yaml", encoding="utf-8"))["priors"]
            self.assertEqual([p["statement"] for p in store.priors_for(name)], [p["statement"] for p in real])
            self.assertEqual([p["category"] for p in store.priors_for(name)], [p["category"] for p in real])
            self.assertEqual(agents[name]["priors_count"], len(real))


def time_ago(path, seconds):
    t = os.path.getmtime(path) - seconds
    os.utime(path, (t, t))


class TestAgentState(unittest.TestCase):
    def test_step_d_state_shows_only_entries_up_to_t_with_the_recorded_scores(self):
        st = store.agent_state(STEPD, ISA, "2023-02-13 09:00:00")
        conn = sqlite3.connect(str(ROOT / STEPD.replace("phase6", "docs/phase6") / "memory.db")) if False else sqlite3.connect(str(ROOT / "docs" / STEPD / "memory.db"))
        want = conn.execute("SELECT COUNT(*) FROM episodic_memory WHERE agent_id = ? AND sim_timestamp <= ?", (ISA, "2023-02-13 09:00:00")).fetchone()[0]
        self.assertEqual(st["stage2_episodic"]["entries_total_up_to_t"], want)
        self.assertTrue(all(e["sim_time"] <= "2023-02-13 09:00:00" for e in st["stage2_episodic"]["entries"]))
        by_id = {r[0]: r[1] for r in conn.execute("SELECT entry_id, importance_score FROM episodic_memory WHERE agent_id = ?", (ISA,))}
        self.assertTrue(all(by_id[e["entry_id"]] == e["importance"] for e in st["stage2_episodic"]["entries"]))
        self.assertEqual(len(st["stage1_priors"]["statements"]), 6)
        self.assertEqual(st["stage3_semantic"]["summaries"], [])
        self.assertEqual(st["stage4_identity"]["traits"], [])
        self.assertTrue(all(e["scoring"] == {"status": "not recorded"} for e in st["stage2_episodic"]["entries"]), "Step D predates the scoring-context table")
        self.assertEqual(st["identity_context_at_t"]["text"], "")
        later = store.agent_state(STEPD, ISA, "2023-02-13 13:45:00")
        self.assertGreater(later["stage2_episodic"]["entries_total_up_to_t"], want)

    def test_default_t_is_the_end_of_the_recording_and_bad_times_are_rejected(self):
        end = store.agent_state(STEPD, "Maria Lopez")
        self.assertEqual(end["stage2_episodic"]["entries_total_up_to_t"], 8)
        self.assertEqual(store.norm_t("2023-02-13T09:30"), "2023-02-13 09:30:00")
        self.assertEqual(store.norm_t("2023-02-13"), "2023-02-13 23:59:59")
        with self.assertRaises(ValueError):
            store.agent_state(STEPD, ISA, "yesterday")
        with self.assertRaises(store.NotFound):
            store.agent_state(STEPD, "Nobody Here")
        with self.assertRaises(store.NotFound):
            store.agent_state("no_such_run", ISA)

    def test_stop3_state_has_four_stages_and_traits_with_sources(self):
        st = store.agent_state(STOP3, ISA)
        self.assertEqual(len(st["stage3_semantic"]["summaries"]), 2)
        summ = {s["entry_id"]: s for s in st["stage3_semantic"]["summaries"]}
        node4 = summ["Isabella Rodriguez:node_4"]
        self.assertEqual(node4["stage4_reinforcement"]["day_set"], [1, 2, 3, 4])
        self.assertEqual(node4["sources_total_in_record"], len(node4["source_entry_ids"]))
        traits = {t["trait_id"]: t for t in st["stage4_identity"]["traits"]}
        self.assertEqual({k.split(":")[1]: v["path"] for k, v in traits.items()}, {"trait_1": "same_day", "trait_2": "pivotal", "trait_3": "same_day"})
        self.assertEqual(traits["Isabella Rodriguez:trait_2"]["source_event_ids"], ["Isabella Rodriguez:node_11"])
        self.assertEqual(traits["Isabella Rodriguez:trait_1"]["source_semantic_ids"], ["Isabella Rodriguez:node_4"])
        ids = {e["entry_id"] for e in st["stage2_episodic"]["entries"]}
        for t in traits.values():
            self.assertTrue(set(t["source_event_ids"]) <= ids)
        self.assertIn("unknown", traits["Isabella Rodriguez:trait_1"]["active_at_t"])

    def test_state_at_an_earlier_time_hides_later_stages(self):
        st = store.agent_state(STOP3, ISA, "2023-02-14 12:00:00")   # before night 2's sweep
        self.assertEqual([s["entry_id"] for s in st["stage3_semantic"]["summaries"]], ["Isabella Rodriguez:node_4"])
        self.assertEqual(st["stage4_identity"]["traits"], [])
        self.assertEqual(st["stage3_semantic"]["sweeps"][0]["night"], 1)

    def test_identity_context_equals_the_block_the_scoring_model_saw_in_stop_3(self):
        st = store.agent_state(STOP3, ISA)
        saved = json.loads((ROOT / "docs" / STOP3 / "stop3_report.json").read_text(encoding="utf-8"))["new_event_scoring"]
        block = st["identity_context_at_t"]["text"]
        self.assertTrue(block.startswith("Traits this agent has developed through experience:"))
        for s in saved:
            self.assertTrue(s["prompt"].rstrip().endswith(block.rstrip()), "the inspector's rendering is byte-identical to the saved prompt tail")
        self.assertEqual(st["identity_context_at_t"]["traits_included"], 2)
        self.assertEqual(st["identity_context_at_t"]["traits_dropped_by_caps"], 1)

    def test_scoring_context_is_shown_per_entry_when_recorded(self):
        st = store.agent_state(STOP3, ISA)
        last = st["stage2_episodic"]["entries"][-1]
        self.assertEqual(last["scoring"]["status"], "ok")
        self.assertEqual(last["scoring"]["trait_ids_in_prompt"], ["Isabella Rodriguez:trait_3", "Isabella Rodriguez:trait_1"])
        self.assertEqual(st["stage2_episodic"]["entries"][0]["scoring"]["trait_ids_in_prompt"], [])

    def test_summary_source_entries_resolve_to_episodic_entries_and_are_flagged_consolidated(self):
        st = store.agent_state(STOP3, ISA)
        by = {e["entry_id"]: e for e in st["stage2_episodic"]["entries"]}
        for s in st["stage3_semantic"]["summaries"]:
            for src in s["source_entry_ids"]:
                self.assertIn(src, by)
                self.assertIsNotNone(by[src]["consolidated_into"])

    def test_render_matches_the_project_renderer_including_the_caps(self):
        try:
            from devmem.memory import identity
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"project modules not importable here: {exc}")
        cfg = identity.load_config()
        cases = [[], ["Isabella Rodriguez is brief."], [f"Isabella Rodriguez trait {i} is brief." for i in range(7)],
                 [("Isabella Rodriguez " + " ".join(f"w{i}x{j}" for j in range(27)) + ".") for i in range(5)],
                 ["Isabella Rodriguez " + " ".join("w" * 5 for _ in range(150)) + "."]]
        for traits in cases:
            mine = store.render_identity_context(traits)
            ref = identity.render_identity_context(traits, cfg)
            self.assertEqual((mine["text"], mine["traits_included"]), ref)


class TestTimelineLedgerCompare(unittest.TestCase):
    def test_timeline_is_ordered_and_covers_stage_kinds(self):
        tl = store.timeline(STOP3)
        times = [e["t"] for e in tl["events"]]
        self.assertEqual(times, sorted(times))
        kinds = {e["kind"] for e in tl["events"]}
        self.assertTrue({"priors", "episodic", "sweep", "summary", "identity_sweep", "trait"} <= kinds)
        self.assertEqual(sum(1 for e in tl["events"] if e["kind"] == "trait"), 3)
        self.assertEqual({e["stage"] for e in tl["events"]}, {1, 2, 3, 4})

    def test_step_d_timeline_has_sleep_state_and_ledger_windows_and_no_invented_call_events(self):
        tl = store.timeline(STEPD)
        self.assertEqual(tl["count"], len(tl["events"]))
        sleep = [e for e in tl["events"] if e["kind"] == "sleep_state" and e["agent"] == "Maria Lopez"]
        self.assertEqual(len(sleep), 9)
        self.assertTrue(all(e["fraction_asleep"] == 1.0 for e in sleep))
        self.assertEqual(sum(e["calls"] for e in tl["events"] if e["kind"] == "ledger_window"), 904)
        self.assertFalse(any(e["kind"] == "call" for e in tl["events"]))
        self.assertTrue(any("carry no simulated time" in n for n in tl["notes"]))

    def test_ledger_summary_reproduces_the_recorded_totals(self):
        led = store.ledger_summary(STEPD)
        self.assertTrue(led["available"])
        self.assertEqual(led["totals"]["calls"], 904)
        self.assertEqual(len(led["windows"]), 9)
        self.assertEqual(sum(w["tokens_in"] for w in led["windows"]), led["totals"]["tokens_in"])
        iso = [w for w in led["windows"] if w["window"] == "hour_ending_2023-02-13_09:00"][0]
        self.assertEqual(iso["calls"], 157)
        self.assertEqual(sum(v["calls"] for k, v in iso["by_agent_and_prompt_type"].items() if k.startswith("Isabella")), 157)
        self.assertFalse(store.ledger_summary(STOP3)["available"])

    def test_compare_returns_the_same_agent_from_two_runs(self):
        c = store.compare(STEPD, STOP3, ISA, "2023-02-13 13:00:00")
        self.assertEqual((c["a"]["run"], c["b"]["run"]), (STEPD, STOP3))
        self.assertEqual(c["a"]["agent"], c["b"]["agent"])
        self.assertEqual(c["a"]["sim_time"], c["b"]["sim_time"])


class TestReadOnlyAndGraceful(unittest.TestCase):
    def test_no_call_to_the_store_changes_a_recording_and_connections_refuse_writes(self):
        before = {r: sha(ROOT / "docs" / r / "memory.db") for r in (STEPD, STOP3)}
        for r in (STEPD, STOP3):
            store.list_runs(); store.list_agents(r); store.timeline(r); store.ledger_summary(r)
            for a in [x["agent"] for x in store.list_agents(r)]:
                store.agent_state(r, a, diagnostics=True)
        conn = store.connect(STEPD)
        with self.assertRaises(sqlite3.OperationalError):
            conn.execute("INSERT INTO episodic_memory (entry_id, agent_id, content, sim_timestamp, sim_day) VALUES ('x','x','x','x',1)")
        with self.assertRaises(sqlite3.OperationalError):
            conn.execute("CREATE TABLE t (a)")
        conn.close()
        self.assertEqual(before, {r: sha(ROOT / "docs" / r / "memory.db") for r in (STEPD, STOP3)})
        self.assertFalse([p for p in (ROOT / "docs" / STEPD).glob("memory.db-*")], "no journal or wal file was created")

    def test_missing_stage_tables_degrade_to_unavailable_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "only_episodic"
            run.mkdir()
            c = sqlite3.connect(str(run / "memory.db"))
            c.execute("CREATE TABLE episodic_memory (entry_id TEXT PRIMARY KEY, agent_id TEXT, content TEXT, sim_timestamp TEXT, sim_day INTEGER, "
                      "recency_score REAL, importance_score REAL, relevance_score REAL, consolidated BOOLEAN)")
            c.execute("INSERT INTO episodic_memory VALUES ('Isabella Rodriguez:node_1','Isabella Rodriguez','Isabella Rodriguez is reading','2023-02-13 08:00:00',1,0,4,0,0)")
            c.commit(); c.close()
            with mock.patch.dict(os.environ, {"DEVMEM_API_ROOTS": tmp}):
                st = store.agent_state("only_episodic", ISA)
                self.assertFalse(st["stage3_semantic"]["available"])
                self.assertFalse(st["stage4_identity"]["available"])
                self.assertEqual(st["stage2_episodic"]["entries"][0]["scoring"], {"status": "not recorded"})
                self.assertEqual(st["identity_context_at_t"]["text"], "")
                tl = store.timeline("only_episodic")
                self.assertEqual({e["kind"] for e in tl["events"]}, {"episodic", "priors"})
                self.assertFalse(store.ledger_summary("only_episodic")["available"])

    def test_store_source_has_no_network_llm_or_write_code(self):
        src = (ROOT / "devmem" / "api" / "store.py").read_text(encoding="utf-8")
        for banned in ("import requests", "urllib", "socket", "call_llm", "llm_router", "INSERT", "UPDATE ", "DELETE", "executescript", ".commit("):
            self.assertNotIn(banned, src, banned)
        self.assertEqual(len(re.findall(r"\?mode=ro\"", src)), 2)  # run databases and the embedding cache, both read-only


class TestProvenanceDiagnostic(unittest.TestCase):
    """synthetic: a tiny embedding cache built in a temp folder (the real cache is never touched)."""

    def make_cache(self, tmp, vectors):
        import array
        path = Path(tmp) / "cache.db"
        c = sqlite3.connect(str(path))
        c.execute("CREATE TABLE embedding_cache (model TEXT NOT NULL, text_hash TEXT NOT NULL, dim INTEGER NOT NULL, vec BLOB NOT NULL, PRIMARY KEY (model, text_hash))")
        for text, v in vectors.items():
            h = hashlib.sha256(text.encode("utf-8")).hexdigest()
            c.execute("INSERT INTO embedding_cache VALUES (?,?,?,?)", (store.EMBEDDING_MODEL, h, len(v), array.array("f", v).tobytes()))
        c.commit(); c.close()
        return path

    def test_flags_a_trait_closer_to_the_priors_than_to_its_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = self.make_cache(tmp, {"trait": [1, 0, 0], "source": [0, 1, 0], "priors": [0.9, 0.1, 0]})
            with mock.patch.object(store, "EMBEDDING_CACHE", cache):
                d = store.provenance("trait", ["source"], "priors")
        self.assertTrue(d["available"])
        self.assertTrue(d["closer_to_priors_than_to_best_source"])
        self.assertAlmostEqual(d["cosine_to_sources"][0]["cosine"], 0.0, places=3)

    def test_a_vector_missing_from_the_cache_makes_it_unavailable_and_nothing_is_estimated(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = self.make_cache(tmp, {"trait": [1, 0, 0]})
            with mock.patch.object(store, "EMBEDDING_CACHE", cache):
                d = store.provenance("trait", ["source"], "priors")
        self.assertEqual(d["available"], False)
        self.assertIn("not in the embedding cache", d["reason"])

    def test_real_cache_diagnostic_is_either_available_or_says_why(self):
        st = store.agent_state(STOP3, ISA, diagnostics=True)
        for t in st["stage4_identity"]["traits"]:
            p = t["provenance"]
            self.assertIn("available", p)
            self.assertTrue(p["available"] or p["reason"])


if __name__ == "__main__":
    unittest.main()


class TestBaselineFromNodeFile(unittest.TestCase):
    """The baseline arm writes no memory mirror: its memory panel is read, read-only, from upstream's own node file (2026-10-07)."""

    def test_state_agents_and_timeline_come_from_nodes_json_and_nothing_is_written(self):
        from devmem.api import movement_archive
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "devmem_root" / "base_run"
            run.mkdir(parents=True)
            c = sqlite3.connect(str(run / "memory.db"))
            c.execute("CREATE TABLE episodic_memory (entry_id TEXT, agent_id TEXT, content TEXT, sim_timestamp TEXT, sim_day INT, recency_score REAL, importance_score REAL, relevance_score REAL, consolidated INT, created_at TEXT)")
            c.commit(); c.close()
            sim = Path(tmp) / "sim" / "base_run" / "personas" / ISA / "bootstrap_memory" / "associative_memory"
            sim.mkdir(parents=True)
            nodes = {"node_1": {"type": "thought", "created": "2023-02-13 00:00:00", "description": "prior", "poignancy": "10"},
                     "node_2": {"type": "event", "created": "2023-02-13 07:00:00", "description": "A janitor is mopping", "poignancy": "1"},
                     "node_3": {"type": "event", "created": "2023-02-13 08:00:00", "description": "later", "poignancy": "2"}}
            (sim / "nodes.json").write_text(json.dumps(nodes))
            before = sha(sim / "nodes.json")
            with mock.patch.dict(os.environ, {"DEVMEM_API_ROOTS": str(Path(tmp) / "devmem_root")}), mock.patch.object(movement_archive, "SIM_STORAGE", Path(tmp) / "sim"):
                self.assertEqual([a["agent"] for a in store.list_agents("base_run")], [ISA])
                st = store.agent_state("base_run", ISA, "2023-02-13 07:30:00")
                self.assertEqual([e["text"] for e in st["stage2_episodic"]["entries"]], ["prior", "A janitor is mopping"])      # created up to t only
                self.assertEqual(st["stage2_episodic"]["entries"][1]["importance"], 1.0)
                self.assertFalse(st["stage3_semantic"]["available"])
                self.assertIn("node file", st["stage2_episodic"]["source_note"])
                tl = store.timeline("base_run")
                self.assertEqual(sum(1 for e in tl["events"] if e["kind"] == "episodic"), 3)
            self.assertEqual(sha(sim / "nodes.json"), before)                                                                 # read-only


class TestRunWithoutMemoryDatabase(unittest.TestCase):
    def test_a_folder_with_label_and_status_is_a_run_and_nothing_is_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "nomem_test_run"
            run.mkdir()
            (run / "run_label.json").write_text(json.dumps({"mode": "FULL: live run in progress", "model": "m"}))
            (run / "run_status.json").write_text(json.dumps({"state": "running"}))
            with mock.patch.dict(os.environ, {"DEVMEM_API_ROOTS": tmp}):
                self.assertIn("nomem_test_run", store.discover())
                self.assertEqual(store.list_agents("nomem_test_run"), [])           # no node folder for this run in the test: no agents, no error
                self.assertEqual(store.timeline("nomem_test_run")["count"], 0)
                self.assertTrue(store.run_label("nomem_test_run")["mode"].startswith("live"))
            self.assertFalse((run / "memory.db").exists())                       # read-only: no database was created
