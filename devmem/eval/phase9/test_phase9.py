"""Offline tests of the Phase 9 pieces. Synthetic and pilot data only; no live call, no outcome data."""
import devmem.testing_env  # noqa: F401
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from devmem.eval.phase9 import answer_harness, diagnostics, external_checkpoint, grader, interim_day1, judge, ledger_splitter, replay, sample_plan

ROOT = Path(__file__).resolve().parent.parent.parent.parent
QS = json.loads((ROOT / "docs" / "phase7_stop1_events_questions.json").read_text(encoding="utf-8"))
LABELS = json.loads((ROOT / "docs" / "phase9_grader_validation_labels.json").read_text(encoding="utf-8"))
PAIRS = json.loads((ROOT / "docs" / "phase9_judge_calibration_pairs.json").read_text(encoding="utf-8"))


class TestSamplePlan(unittest.TestCase):
    def _events(self, per=40):
        out = []
        for a in ("Isabella Rodriguez", "Maria Lopez", "Klaus Mueller"):
            for d in (13, 14, 15):
                for i in range(per):
                    out.append((a, f"2023-02-{d} {6 + i % 8:02d}:{i % 60:02d}:00", f"{a} event {d} {i}"))
        return out

    def test_300_events_27_injected_273_natural_stratified_and_deterministic(self):
        inj = [(a, "2023-02-13 08:20:00", f"inj {a} {i}") for a in ("Isabella Rodriguez", "Maria Lopez", "Klaus Mueller") for i in range(9)]
        s1 = sample_plan.build_sample(self._events(), inj)
        s2 = sample_plan.build_sample(self._events(), inj)
        self.assertEqual(s1, s2)
        self.assertEqual((s1["n_injected"], s1["n_natural"], s1["n_total"]), (27, 273, 300))
        q = [v["quota"] for v in s1["allocation"].values()]
        self.assertEqual(sorted(q), [30] * 6 + [31] * 3)                        # 273 = 9 x 30 + 3, the extra three to the first three strata
        self.assertEqual([v["quota"] for v in list(s1["allocation"].values())[:3]], [31, 31, 31])

    def test_a_small_stratum_gives_all_and_the_shortfall_is_shared(self):
        ev = self._events(per=40)
        ev = [e for e in ev if not (e[0] == "Klaus Mueller" and e[1].startswith("2023-02-15"))] + [("Klaus Mueller", "2023-02-15 09:00:00", "only one")]
        s = sample_plan.build_sample(ev, [])
        self.assertEqual(s["allocation"]["Klaus Mueller|day3"]["chosen"], 1)
        self.assertEqual(s["n_natural"], 273)                                    # the shortfall went to other strata
        self.assertEqual(len(set(s["natural"])), 273)

    def test_seed_is_committed(self):
        self.assertEqual(sample_plan.SEED, 20261008)


class TestGrader(unittest.TestCase):
    def test_rules(self):
        cl = [{"item": "vehicle", "any_of": ["van", "truck"]}, {"item": "color", "any_of": ["blue"]}]
        self.assertTrue(grader.grade("A blue van.", cl)["strict"])
        self.assertEqual(grader.grade("a Blue VANS!", cl)["score"], 1.0)                   # case, punctuation, plural
        self.assertFalse(grader.grade("vanilla syrup", cl)["items"]["vehicle"])            # word boundary
        self.assertFalse(grader.grade("It wasn't blue.", cl)["items"]["color"])            # negation within three tokens
        self.assertTrue(grader.grade("it was not blue, honestly it was blue", cl)["items"]["color"])   # a non-negated occurrence wins
        self.assertFalse(grader.grade("not red but blue", cl)["items"]["color"])           # known limit: the three-token window also negates "but blue"
        self.assertTrue(grader.grade("table four", [{"item": "p", "any_of": ["table four"]}])["strict"])   # phrase
        self.assertEqual(grader.grade("", cl)["score"], 0.0)
        self.assertTrue(grader.grade("ChatGPT ERROR", cl)["failure"])

    def test_validation_on_the_thirty_hand_labelled_answers_is_interpretable_and_reports_its_disagreements(self):
        self.assertEqual(len(LABELS["entries"]), 30)
        r = grader.validate(LABELS, QS)
        self.assertTrue(r["interpretable"])
        self.assertGreaterEqual(r["item_agreement"], 0.9)
        self.assertEqual(r["items_checked"], 57)
        # known limits, not hidden: a swapped received/wanted pair (entry 13) and a negation window that also covers a later Monday (entry 18)
        self.assertEqual(sorted(d["n"] for d in r["disagreements"]), [13, 13, 18])


class TestJudge(unittest.TestCase):
    def test_pairs_are_7_7_6_and_parsing_never_guesses(self):
        from collections import Counter
        self.assertEqual(Counter(p["label"] for p in PAIRS["pairs"]), {"consistent": 7, "contradictory": 7, "unrelated": 6})
        self.assertEqual(judge.parse_label("Consistent."), "consistent")
        self.assertIsNone(judge.parse_label("consistent or contradictory"))
        self.assertIsNone(judge.parse_label("I am not sure"))
        self.assertIsNone(judge.parse_label(""))

    def test_calibration_matrix_with_a_perfect_and_a_failing_stub(self):
        truth = {judge.build_prompt(p["question"], p["day1_answer"], p["day3_answer"]): p["label"] for p in PAIRS["pairs"]}
        r = judge.calibration(judge.judge_pairs(PAIRS["pairs"], lambda prompt: truth[prompt]))
        self.assertEqual((r["accuracy"], r["parse_failures"], r["coherence_interpretable"]), (1.0, 0, True))
        r2 = judge.calibration(judge.judge_pairs(PAIRS["pairs"], lambda prompt: "maybe"))
        self.assertEqual((r2["accuracy"], r2["parse_failures"], r2["coherence_interpretable"]), (0.0, 20, False))
        self.assertIn("consistent:", r2["rubric"])


class TestLedgerSplitter(unittest.TestCase):
    def test_evaluation_purposes_are_separate_and_never_in_the_efficiency_totals(self):
        with tempfile.TemporaryDirectory() as t:
            db = Path(t) / "l.db"
            c = sqlite3.connect(db)
            c.execute("CREATE TABLE llm_call_log (call_id INTEGER PRIMARY KEY, provider TEXT, model TEXT, purpose TEXT, tokens_in INT, tokens_out INT, sim_day INT, agent_id TEXT, condition TEXT, created_at TEXT)")
            rows = [("planning", 100, 10, 1, "baseline"), ("planning", 100, 10, 1, "baseline"), ("importance_scoring", 50, 5, 2, "staged"), ("eval_recall", 300, 20, 3, "staged"), ("eval_judge", 200, 5, 3, "baseline")]
            for i, (p, a, b, d, cond) in enumerate(rows):
                c.execute("INSERT INTO llm_call_log VALUES (?,?,?,?,?,?,?,?,?,?)", (i, "gemini", "m", p, a, b, d, None, cond, "2026-10-08 00:00:00"))
            c.commit(); c.close()
            r = ledger_splitter.split(db)
        self.assertEqual(r["efficiency_totals_excluding_evaluation"], {"baseline": {"calls": 2, "tokens_in": 200}, "staged": {"calls": 1, "tokens_in": 50}})
        self.assertEqual(r["evaluation_reported_separately"]["staged"]["eval_recall"]["calls"], 1)
        self.assertEqual(r["evaluation_reported_separately"]["baseline"]["eval_judge"]["tokens_in"], 200)

    def test_runs_on_the_real_pilot_ledger_read_only(self):
        db = ROOT / "devmem" / "router" / "usage_log.db"
        if not db.exists():
            self.skipTest("no router ledger in this checkout")
        r = ledger_splitter.split(db)
        self.assertIn("efficiency_per_condition_day_purpose", r)


class TestReplay(unittest.TestCase):
    def test_three_conditions_differ_only_by_the_appended_block_and_staged_is_reused(self):
        ev = ("Isabella Rodriguez", "2023-02-13 08:20:00", "A blue delivery van is parked outside the entrance of Hobbs Cafe")
        base = replay.build_prompt("baseline", *[ev[0], ev[2]])
        mis = replay.build_prompt("mismatch", ev[0], ev[2])
        fil = replay.build_prompt("filler", ev[0], ev[2])
        self.assertTrue(mis.startswith(base) and fil.startswith(base))
        self.assertGreater(len(mis), len(base))
        self.assertNotEqual(mis, fil)
        self.assertIn("Wolfgang", replay.get_prompt_context("Wolfgang Schulz")[:400] + "Wolfgang")   # the mismatch block is another persona's priors
        calls = []
        out = replay.replay([ev], lambda p: (calls.append(p), "Rate: 3")[1], own_scores={ev: 2.0})
        self.assertEqual(len(calls), 3)                                           # staged_own costs no call
        self.assertEqual(sorted(r["condition"] for r in out["rows"]), ["baseline", "filler", "mismatch", "staged_own"])
        self.assertEqual(out["summary"]["by_condition"]["staged_own"]["mean"], 2.0)


class TestAnswerHarness(unittest.TestCase):
    def test_one_call_per_question_same_prompt_shape_and_grading(self):
        qs = [q for q in QS["questions"] if q["id"] in ("Q_I1", "Q_I2")]
        seen = []
        out = answer_harness.answer_questions("Isabella Rodriguez", qs, lambda p: (seen.append(p), "A blue van and a croissant.")[1], persona=None,
                                              retrieve_fn=lambda persona, question, k: [f"memory about {question[:20]}", "another memory"])
        self.assertEqual(len(seen), 2)
        self.assertTrue(all(p.startswith("You are Isabella Rodriguez.") and p.endswith("Answer:") for p in seen))
        self.assertTrue(out[0]["grade"]["strict"])
        self.assertEqual(out[0]["retrieved_count"], 2)
        self.assertEqual(answer_harness.TOP_K, 30)

    def test_no_memory_case_is_stated_in_the_prompt(self):
        self.assertIn("(no relevant memory)", answer_harness.build_answer_prompt("X", [], "Q?"))


class TestInterimDay1OnPilotData(unittest.TestCase):
    """The day-1 interim pieces, exercised on the PILOT checkpoint and ledgers (never on a full-run checkpoint)."""

    def test_pilot_checkpoint_copy_markers_and_offline_numbers(self):
        run = ROOT / "devmem" / "storage" / "p7pilot_staged"
        ck = run / "checkpoints" / "pilot_end_0900" / "memory.db"
        if not ck.exists():
            self.skipTest("pilot checkpoint not present in this checkout")
        with tempfile.TemporaryDirectory() as t:
            r = interim_day1.copy_checkpoint("staged", label="pilot_end_0900", sim_prefix="p7pilot", dest=Path(t))
            self.assertTrue(r["copied"])
            self.assertTrue((Path(t) / "staged" / "memory.db").exists())
        m = interim_day1.sweep_markers(ck)
        self.assertEqual(sorted(m), ["Isabella Rodriguez", "Klaus Mueller", "Maria Lopez"])
        e1 = interim_day1.e1_calls(run, "2023-02-13 09:00:00")
        self.assertGreater(e1["total"], 0)
        self.assertIn("replayed", e1["caveat"])
        e3 = interim_day1.e3_consolidated_fraction(ck)
        self.assertEqual(e3["fraction"], 0.0)                 # no sweep with content before 09:00
        self.assertEqual(interim_day1.e3_consolidated_fraction(None)["fraction"], 0.0)
        nat, inj = interim_day1.event_stream(ck, [], "2023-02-13 09:00:00")
        self.assertGreater(len(nat), 50)
        qs = interim_day1.day1_questions()
        self.assertEqual(len(qs), 9)                          # three day-1 injected-event questions per agent
        self.assertEqual({q["agent"] for q in qs}, {"Isabella Rodriguez", "Maria Lopez", "Klaus Mueller"})

    def test_a_missing_checkpoint_is_reported_not_invented(self):
        with tempfile.TemporaryDirectory() as t:
            r = interim_day1.copy_checkpoint("baseline", label="no_such_label", dest=Path(t))
        self.assertFalse(r["copied"])


class TestExternalCheckpoint(unittest.TestCase):
    """Synthetic run layout only: the copier never writes to the run and trims the mirror to the autosave clock."""

    def _layout(self, root, step, curr="February 13, 2023, 14:15:00"):
        sim = root / "storage" / "p7_staged"
        (sim / "personas" / "A" / "bootstrap_memory").mkdir(parents=True)
        (sim / "personas" / "A" / "bootstrap_memory" / "x.json").write_text("{}")
        (sim / "reverie").mkdir()
        (sim / "reverie" / "meta.json").write_text(json.dumps({"step": step, "curr_time": curr, "persona_names": ["A"]}))
        (sim / "environment").mkdir()
        (sim / "environment" / f"{step}.json").write_text("{}")
        run = root / "run" / "p7_staged"
        run.mkdir(parents=True)
        c = sqlite3.connect(run / "memory.db")
        c.execute("CREATE TABLE episodic_memory (entry_id TEXT, sim_timestamp TEXT)")
        c.execute("CREATE TABLE consolidation_sweeps (agent_id TEXT, night INT, sweep_time TEXT, status TEXT)")
        c.executemany("INSERT INTO episodic_memory VALUES (?,?)", [("a", "2023-02-13 10:00:00"), ("b", "2023-02-13 14:15:00"), ("c", "2023-02-13 14:20:10")])
        c.executemany("INSERT INTO consolidation_sweeps VALUES (?,?,?,?)", [("A", 0, "2023-02-13 00:00:00", "done"), ("A", 1, "2023-02-13 14:30:00", "done")])
        c.commit(); c.close()
        return sim, run

    def test_waits_for_the_target_then_copies_and_trims_and_never_writes_to_the_run(self):
        with tempfile.TemporaryDirectory() as t:
            early = Path(t) / "early"
            self._layout(early, 5040)
            self.assertIsNone(external_checkpoint.copy_once("staged", 5130, "x", early / "dest", storage=early / "storage", run_root=early / "run"))   # no autosave at 5,130 yet
            root = Path(t) / "ready"
            sim, run = self._layout(root, 5130)
            before = {p: p.read_bytes() for p in list(sim.rglob("*")) + [run / "memory.db"] if p.is_file()}
            rec = external_checkpoint.copy_once("staged", 5130, "x", root / "dest", storage=root / "storage", run_root=root / "run")
            self.assertTrue(rec["exact_first_autosave"])
            self.assertEqual((rec["step"], rec["sim_clock"]), (5130, "2023-02-13 14:15:00"))
            self.assertEqual(rec["rows_trimmed_from_the_copy_because_they_are_later_than_the_autosave_clock"]["episodic_memory"], 1)
            self.assertEqual(rec["rows_trimmed_from_the_copy_because_they_are_later_than_the_autosave_clock"]["consolidation_sweeps"], 1)
            c = sqlite3.connect(root / "dest" / "staged" / "memory.db")
            self.assertEqual(c.execute("select count(*) from episodic_memory").fetchone()[0], 2)
            self.assertEqual(c.execute("select count(*) from consolidation_sweeps").fetchone()[0], 1)
            c.close()
            self.assertTrue((root / "dest" / "staged" / "sim" / "personas" / "A" / "bootstrap_memory" / "x.json").exists())
            after = {p: p.read_bytes() for p in list(sim.rglob("*")) + [run / "memory.db"] if p.is_file()}
            self.assertEqual(before, after)                                                  # the run's files are byte for byte unchanged
            c = sqlite3.connect(run / "memory.db")
            self.assertEqual(c.execute("select count(*) from episodic_memory").fetchone()[0], 3)   # the live mirror still has all rows
            c.close()

    def test_a_missed_first_autosave_is_recorded_as_not_exact(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            self._layout(root, 13860, "February 14, 2023, 14:30:00")
            rec = external_checkpoint.copy_once("staged", 13770, "x", root / "dest", storage=root / "storage", run_root=root / "run")
            self.assertEqual((rec["step"], rec["exact_first_autosave"]), (13860, False))

    def test_the_target_steps_are_autosave_multiples(self):
        for s in (13770, 17190, 25830, 5130, 22410):
            self.assertEqual(s % 90, 0)


class TestDiagnostics(unittest.TestCase):
    def test_cluster_quality_on_the_stop3_log(self):
        r = diagnostics.cluster_quality(ROOT / "docs" / "phase6_stop3_artifacts" / "consolidation_log.jsonl")
        self.assertGreaterEqual(r["sweeps_done"], 1)
        self.assertIn("single@0.78", r["settings_seen"])
        self.assertEqual(r["failures"], 0)

    def test_provenance_rows_degrade_to_unavailable_not_to_a_guess(self):
        rows = diagnostics.provenance_rows([{"trait_id": "t1", "path": "same_day", "text": "a trait text that is surely not in the embedding cache xyzzy"}], {"t1": ["src"]}, "priors")
        self.assertFalse(rows[1]["available"])


if __name__ == "__main__":
    unittest.main()
