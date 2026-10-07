"""Watchdog tests with simulated failures only: temporary folders, a fake process list, a fake clock and a fake supervisor start. Nothing live is killed or started."""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from devmem.eval import watchdog


class TestWatchdog(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.root = Path(self.t.name)
        self.run = self.root / "devmem" / "storage" / "p7_baseline"
        self.run.mkdir(parents=True)
        self.mov = self.root / "reverie" / "environment" / "frontend_server" / "storage" / "p7_baseline" / "movement"
        self.mov.mkdir(parents=True)
        (self.run / "run_label.json").write_text(json.dumps({"mode": "FULL: live run in progress"}))
        (self.run / "run_status.json").write_text(json.dumps({"state": "running"}))
        f = self.mov / "10.json"
        f.write_text("{}")
        self.old = time.time() - 1000
        os.utime(f, (self.old, self.old))                     # a heartbeat 1,000 s old
        self.started = []
        self.log = self.root / "wd.log"

    def check(self, procs=None, **kw):
        return watchdog.check_arm("baseline", root=self.root, procs_fn=lambda: procs or [], start_fn=lambda a: (self.started.append(a), True)[1], log=self.log, **kw)

    def test_a_dead_arm_with_a_stale_heartbeat_is_restarted_and_logged_as_an_external_kill(self):
        self.assertEqual(self.check(), "restarted")
        self.assertEqual(self.started, ["baseline"])
        rows = [json.loads(l) for l in (self.run / "resume_log.jsonl").read_text().splitlines()]
        self.assertEqual(rows[0]["event"], "external_kill_watchdog_restart")
        self.assertIn("not counted", rows[0]["note"])
        self.assertFalse((self.root / "devmem" / "storage" / "p7_baseline.watchdog.lock").exists())      # the lock is released

    def test_nothing_is_done_when_any_condition_fails(self):
        self.assertTrue(self.check(procs=["python -m devmem.eval.supervisor --arm baseline"]).startswith("skip"))
        (self.mov / "11.json").write_text("{}")               # a fresh heartbeat
        self.assertTrue(self.check().startswith("skip"))
        os.utime(self.mov / "11.json", (self.old, self.old))
        (self.run / "ABORT").write_text("x")
        self.assertTrue(self.check().startswith("skip"))      # never restart over an ABORT
        (self.run / "ABORT").unlink()
        (self.run / "PAUSE_FOR").write_text("1200")
        self.assertTrue(self.check().startswith("skip"))      # an operator pause file
        (self.run / "PAUSE_FOR").unlink()
        (self.run / "pause_log.jsonl").write_text(json.dumps({"event": "pause_start"}) + "\n")
        self.assertTrue(self.check().startswith("skip"))      # a pause in progress
        (self.run / "pause_log.jsonl").write_text(json.dumps({"event": "pause_end_probe"}) + "\n")
        (self.run / "run_label.json").write_text(json.dumps({"mode": "PILOT: live run"}))
        self.assertTrue(self.check().startswith("skip"))      # not FULL
        (self.run / "run_label.json").write_text(json.dumps({"mode": "FULL: live run"}))
        (self.run / "run_status.json").write_text(json.dumps({"state": "finished: reached 2023-02-16 00:00:00"}))
        self.assertTrue(self.check().startswith("skip"))      # ended cleanly
        self.assertEqual(self.started, [])

    def test_a_second_watchdog_cannot_start_a_second_supervisor(self):
        lock = self.root / "devmem" / "storage" / "p7_baseline.watchdog.lock"
        lock.write_text("other watchdog")
        self.assertEqual(self.check(), "skip: lock held")
        self.assertEqual(self.started, [])

    def test_the_supervisor_that_appears_while_taking_the_lock_is_respected(self):
        seq = [[], ["python -m devmem.eval.supervisor --arm baseline"]]
        got = watchdog.check_arm("baseline", root=self.root, procs_fn=lambda: seq.pop(0) if seq else [], start_fn=lambda a: self.started.append(a) or True, log=self.log)
        self.assertEqual(got, "skip: supervisor appeared")
        self.assertEqual(self.started, [])

    def test_cap_of_six_restarts_per_hour_then_a_flag_and_no_seventh(self):
        results = []
        for i in range(8):
            results.append(self.check())
        self.assertEqual(results[:6], ["restarted"] * 6)
        self.assertEqual(results[6:], ["flag: cap reached"] * 2)
        self.assertEqual(len(self.started), 6)
        flag = json.loads((self.run / "watchdog_flag.json").read_text())
        self.assertEqual(flag["arm"], "baseline")
        self.assertIn("watchdog_flag", json.loads((self.run / "run_status.json").read_text()))

    def test_restarts_older_than_an_hour_do_not_count(self):
        old = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 7200))
        with open(self.run / "resume_log.jsonl", "w", encoding="utf-8") as f:
            for _ in range(10):
                f.write(json.dumps({"ts": old, "event": "external_kill_watchdog_restart"}) + "\n")
        self.assertEqual(self.check(), "restarted")


if __name__ == "__main__":
    unittest.main()
