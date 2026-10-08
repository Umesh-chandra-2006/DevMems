"""Test of the call-gap report on a synthetic ledger (no run folder is read)."""
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from devmem.eval import call_gap_report as G


class TestGapReport(unittest.TestCase):
    def test_percentiles_rate_and_the_120_second_view(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            db = t / "l.db"
            c = sqlite3.connect(db)
            c.execute("CREATE TABLE llm_call_log (purpose TEXT, condition TEXT, created_at TEXT)")
            base = datetime(2026, 10, 8, 10, 0, 0)                                    # UTC text; 15:30 IST
            offsets = [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 400]                          # nine gaps of 2 s, then one of 382 s
            c.executemany("INSERT INTO llm_call_log VALUES (?,?,?)", [("planning", "baseline", (base + timedelta(seconds=o)).strftime("%Y-%m-%d %H:%M:%S")) for o in offsets]
                          + [("eval_judge", "baseline", base.strftime("%Y-%m-%d %H:%M:%S"))])    # an evaluation row is excluded
            c.commit()
            c.close()
            start = datetime(2026, 10, 8, 15, 29, 0)
            end = start + timedelta(minutes=10)
            r = G.window_stats("baseline", start, end, db, t / "none.jsonl")
            self.assertEqual((r["calls"], r["gaps"]), (11, 10))
            self.assertEqual(r["calls_per_minute"], 1.1)
            self.assertEqual(r["all_gaps_s"]["median"], 2.0)
            self.assertEqual(r["all_gaps_s"]["share_above_60s"], 0.1)
            self.assertEqual(r["gaps_up_to_120s"], {"n": 9, "median": 2.0, "p90": 2.0})
            self.assertEqual(r["all_gaps_s"]["p99"], 347.8)                                # interpolated between 2 and 382
            self.assertEqual(G.pct([1, 2, 3, 4], 0.5), 2.5)

    def test_report_runs_for_both_arms_and_both_windows(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            db = t / "l.db"
            c = sqlite3.connect(db)
            c.execute("CREATE TABLE llm_call_log (purpose TEXT, condition TEXT, created_at TEXT)")
            c.commit()
            c.close()
            (t / "s.jsonl").write_text("\n".join(json.dumps({"t": 1000.0 + 60 * i, "baseline": {"n429": 10 * i, "n503": i, "ntimeout": 0}, "staged": {"n429": 5 * i, "n503": 0, "ntimeout": 1}}) for i in range(5)) + "\n")
            r = G.report(120, ["2026-10-08 01:10:00", "2026-10-08 08:00:00"], now=datetime(2026, 10, 8, 22, 0, 0), db=db, samples=t / "s.jsonl", extra=[("awake_day1", "2026-10-07 17:00:00", "2026-10-07 19:00:00")])
            self.assertEqual(set(r["arms"]), {"baseline", "staged"})
            self.assertEqual(set(r["arms"]["staged"]), {"last_120_min", "overnight", "awake_day1"})
            self.assertEqual(r["arms"]["staged"]["overnight"]["calls"], 0)


if __name__ == "__main__":
    unittest.main()
