"""Tests of the 429 wave report on a synthetic rate_limit_log (no run folder is read)."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from devmem.eval import wave_report


def _make(root, arm, ev):
    d = root / "devmem" / "storage" / f"p7_{arm}"
    d.mkdir(parents=True)
    (d / "rate_limit_log.jsonl").write_text("\n".join(json.dumps(e) for e in ev) + ("\n" if ev else ""))


class TestWaveReport(unittest.TestCase):
    def test_waves_are_paired_counted_and_filtered_by_time(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            ev = [{"at": "2026-10-08T10:00:00", "event": "rate_limit_start"}, {"at": "2026-10-08T10:00:20", "event": "rate_limit_backoff", "attempt": 1, "seconds": 20},
                  {"at": "2026-10-08T10:01:00", "event": "rate_limit_end", "seconds": 60.0, "attempts": 2},              # before the cut: ignored
                  {"at": "2026-10-08T11:00:00", "event": "rate_limit_start"}, {"at": "2026-10-08T11:01:30", "event": "rate_limit_end", "seconds": 90.0, "attempts": 3},
                  {"at": "2026-10-08T11:05:00", "event": "rate_limit_start"}]                                             # still open
            _make(root, "baseline", ev)
            with mock.patch.object(wave_report, "ROOT", root):
                w = wave_report.waves("baseline", "2026-10-08 16:14:00")        # 16:14 IST = 10:44 UTC
            self.assertEqual(len(w), 2)
            self.assertEqual((w[0]["start_ist"], w[0]["seconds"], w[0]["attempts"]), ("16:30:00", 90.0, 3))
            self.assertTrue(w[1].get("open"))

    def test_report_hours_share_overlap_and_halves(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            # baseline (UTC): 10:45:00 to 10:46:00 (60 s) and 11:50:00 to 11:52:00 (120 s); staged: 10:45:30 to 10:47:30 (120 s)
            _make(root, "baseline", [{"at": "2026-10-08T10:45:00", "event": "rate_limit_start"}, {"at": "2026-10-08T10:46:00", "event": "rate_limit_end", "seconds": 60.0, "attempts": 2},
                                     {"at": "2026-10-08T11:50:00", "event": "rate_limit_start"}, {"at": "2026-10-08T11:52:00", "event": "rate_limit_end", "seconds": 120.0, "attempts": 3}])
            _make(root, "staged", [{"at": "2026-10-08T10:45:30", "event": "rate_limit_start"}, {"at": "2026-10-08T10:47:30", "event": "rate_limit_end", "seconds": 120.0, "attempts": 3}])
            with mock.patch.object(wave_report, "ROOT", root):
                r = wave_report.report("2026-10-08 16:14:00", "2026-10-08 18:14:00")
            b = r["baseline"]
            self.assertEqual((b["waves"], b["waited_seconds_total"], b["mean_wave_seconds"], b["max_wave_seconds"]), (2, 180, 90.0, 120.0))
            self.assertEqual(b["share_of_wall_time"], round(180 / 7200, 4))
            self.assertEqual((b["first_half"]["waves"], b["second_half"]["waves"]), (1, 1))
            self.assertEqual([h["waves_started"] for h in b["per_hour"]], [1, 1, 0])          # 16:00 bucket (from 16:14), 17:00, 18:00 (to 18:14)
            self.assertEqual(b["per_hour"][0]["window_minutes"], 46.0)
            self.assertEqual(r["overlapping_waves_between_arms"], [{"baseline_start": "16:15:00", "staged_start": "16:15:30", "overlap_seconds": 30}])

    def test_main_runs_on_a_synthetic_log(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            for arm in ("baseline", "staged"):
                _make(root, arm, [])
            with mock.patch.object(wave_report, "ROOT", root), mock.patch("sys.argv", ["x", "--since", "2026-10-08 16:14:00", "--until", "2026-10-08 18:14:00"]):
                wave_report.main()                                              # must not raise


if __name__ == "__main__":
    unittest.main()
