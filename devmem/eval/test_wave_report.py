"""Tests of the 429 wave report on a synthetic rate_limit_log (no run folder is read)."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from devmem.eval import wave_report


class TestWaveReport(unittest.TestCase):
    def test_waves_are_paired_counted_and_filtered_by_time(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            d = root / "devmem" / "storage" / "p7_baseline"
            d.mkdir(parents=True)
            ev = [{"at": "2026-10-08T10:00:00", "event": "rate_limit_start"}, {"at": "2026-10-08T10:00:20", "event": "rate_limit_backoff", "attempt": 1, "seconds": 20},
                  {"at": "2026-10-08T10:01:00", "event": "rate_limit_end", "seconds": 60.0, "attempts": 2},              # before the cut: ignored
                  {"at": "2026-10-08T11:00:00", "event": "rate_limit_start"}, {"at": "2026-10-08T11:01:30", "event": "rate_limit_end", "seconds": 90.0, "attempts": 3},
                  {"at": "2026-10-08T11:05:00", "event": "rate_limit_start"}]                                             # still open
            (d / "rate_limit_log.jsonl").write_text("\n".join(json.dumps(e) for e in ev) + "\n")
            with mock.patch.object(wave_report, "ROOT", root):
                w = wave_report.waves("baseline", "2026-10-08 16:14:00")        # 16:14 IST = 10:44 UTC
            self.assertEqual(len(w), 2)
            self.assertEqual((w[0]["start_ist"], w[0]["seconds"], w[0]["attempts"]), ("16:30:00", 90.0, 3))
            self.assertTrue(w[1].get("open"))

    def test_main_runs_on_a_synthetic_log(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            for arm in ("baseline", "staged"):
                d = root / "devmem" / "storage" / f"p7_{arm}"
                d.mkdir(parents=True)
                (d / "rate_limit_log.jsonl").write_text("")
            with mock.patch.object(wave_report, "ROOT", root), mock.patch("sys.argv", ["x", "--since", "2026-10-08 16:14:00"]):
                wave_report.main()                                              # must not raise


if __name__ == "__main__":
    unittest.main()
