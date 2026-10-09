"""Tests of the results export on synthetic inputs (no run is written; the real ledger and run folders are read only by the build-with-no-copies smoke test)."""
import devmem.testing_env  # noqa: F401
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from devmem.eval.phase9 import grader, results_export as R


class TestE1Grouped(unittest.TestCase):
    def test_days_agents_and_replay_removal(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            db = t / "l.db"
            c = sqlite3.connect(db)
            c.execute("CREATE TABLE llm_call_log (call_id TEXT, provider TEXT, model TEXT, purpose TEXT, tokens_in INT, tokens_out INT, sim_day INT, agent_id TEXT, condition TEXT, created_at TEXT)")
            # UTC times; step files: step 100 (day 1) written at 10:00:30 UTC, step 9000 (day 2) written at 11:00:30 UTC
            rows = [("2026-10-08 10:00:10", "A", "planning"), ("2026-10-08 10:00:20", "A", "planning"), ("2026-10-08 11:00:10", "B", "dialogue"), ("2026-10-08 11:00:15", "B", "dialogue"), ("2026-10-08 11:00:16", "B", "eval_judge")]
            c.executemany("INSERT INTO llm_call_log (call_id, provider, model, purpose, agent_id, condition, created_at) VALUES ('x','p','m',?,?,'baseline',?)", [(p, a, ts) for ts, a, p in rows])
            c.commit()
            c.close()
            mv = t / "p7_baseline" / "movement"
            mv.mkdir(parents=True)
            import calendar
            import time
            for step, ts in ((100, "2026-10-08 10:00:30"), (9000, "2026-10-08 11:00:30")):
                f = mv / f"{step}.json"
                f.write_text("{}")
                e = calendar.timegm(time.strptime(ts, "%Y-%m-%d %H:%M:%S"))
                os.utime(f, (e, e))
            # restart at 16:30:00 IST (= 11:00:00 UTC) whose pre-kill step 9000 was rewritten at 16:30:30 IST: the two dialogue calls in between are the replay pass
            res = R.e1_grouped("baseline", "2026-10-08 17:00:00", db=db, restarts={"baseline": [("2026-10-08 16:30:00", 9000)]}, sim=t)
            tab = {(x["sim_day"], x["agent"], x["purpose"]): (x["raw"], x["unique"]) for x in res["by_day_agent_purpose"]}
            self.assertEqual(tab[(1, "A", "planning")], (2, 2))
            self.assertEqual(tab[(2, "B", "dialogue")], (2, 0))              # raw 2, both removed as the replay pass
            self.assertEqual((res["raw_total"], res["unique_total"]), (4, 2))   # the eval_ row is not an efficiency call


class TestPredictions(unittest.TestCase):
    def _ev(self, base, stag):
        qs = json.loads(R.QFILE.read_text(encoding="utf-8"))["questions"]
        mk = lambda sc: {"recall": [{"question_id": q["id"], "agent": q["agent"], "grade": {"score": sc(q), "strict": sc(q) == 1.0, "failure": False}} for q in qs]}
        return {"baseline": mk(base), "staged": mk(stag)}

    def test_day3_literal_rules(self):
        ev = self._ev(lambda q: 1.0, lambda q: 0.5 if q["type"] == "injected" and q["event_day"] == 1 else 1.0)
        rec = R.recall_table(3, ev, {"I6"})
        self.assertIn("Q_I6", rec["excluded_question_ids"])
        arms = {a: {"E1": {"unique_total": 100 if a == "baseline" else 105}, "E2_prompt_tokens": {"mean_tokens_in": 400 if a == "baseline" else 570},
                    "E3_consolidated_fraction": {"fraction": 0.0 if a == "baseline" else 0.1}} for a in R.ARMS}
        gv = grader.validate(R._read(R.LABELS), R._events())
        P = {p["id"]: p for p in R.predictions(3, "x", arms, rec, gv, {"available": False}, None, {"traits": 0, "available": 0, "flagged": 0})}
        self.assertEqual((P["E1"]["outcome"], P["E2"]["outcome"], P["E3"]["outcome"]), ("right", "right", "right"))
        self.assertEqual(P["R3"]["outcome"], "undecidable")                   # pivotal events are day-2 events: distance 1, the registered distance 2 matches no question
        self.assertIn("matches no question", P["R3"]["reason"])
        self.assertEqual(P["R1"]["outcome"], "undecidable")                   # n = 1 < 3
        self.assertEqual(P["R4"]["outcome"], "right")                         # mundane day-1 questions at distance 2 (I1, M1, K1): staged 0.5 against baseline 1.0 is at or below baseline
        self.assertEqual(P["R4"]["numbers"]["staged_minus_baseline_mean"], -0.5)

    def test_e1_wrong_when_staged_makes_fewer_calls(self):
        arms = {a: {"E1": {"unique_total": 100 if a == "baseline" else 90}, "E2_prompt_tokens": {"mean_tokens_in": 1}, "E3_consolidated_fraction": {"fraction": 0.0}} for a in R.ARMS}
        rec = {"rows": [], "excluded_question_ids": []}
        P = {p["id"]: p for p in R.predictions(2, "x", arms, rec, {"interpretable": True}, {"available": False}, None, {})}
        self.assertEqual(P["E1"]["outcome"], "wrong")
        self.assertEqual(P["R1"]["outcome"], "undecidable")

    def test_bootstrap_is_deterministic(self):
        rows = [{"question_id": f"q{i}", "agent": "A" if i < 3 else "B", "baseline": {"score": 1.0}, "staged": {"score": 0.5}} for i in range(6)]
        a, b = R.bootstrap(rows, n=200), R.bootstrap(rows, n=200)
        self.assertEqual(a, b)
        self.assertEqual(a["mean"], -0.5)


class TestM2Calibration(unittest.TestCase):
    def test_the_nested_calibration_file_is_read(self):
        import tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            (t / "judge_calibration.json").write_text(json.dumps({"calibration": {"accuracy": 1.0, "coherence_interpretable": True, "pairs": 20, "parse_failures": 0, "confusion_matrix_true_by_judged": {}}, "results": []}))
            ev = {a: {"judge": [{"agent": "A", "judge_label": "consistent"}]} for a in R.ARMS}
            with mock.patch.object(R, "EVAL", t):
                m = R.m2_section(ev)
            self.assertEqual((m["available"], m["calibration_accuracy"], m["coherence_interpretable"], m["calibration_pairs"]), (True, 1.0, True, 20))
            self.assertEqual(m["arms"]["baseline"]["contradiction_rate"], 0.0)


class TestBuildSmoke(unittest.TestCase):
    def test_build_and_markdown_with_no_copies(self):
        with tempfile.TemporaryDirectory() as t:
            r = R.build(2, interim_root=Path(t))
            self.assertTrue(r["label"].startswith("INTERIM day 2"))
            md = R.markdown(r)
            self.assertIn("## Predictions", md)
            self.assertTrue(all(p["outcome"] in ("right", "wrong", "undecidable", "no prediction") for p in r["predictions"]))


if __name__ == "__main__":
    unittest.main()
