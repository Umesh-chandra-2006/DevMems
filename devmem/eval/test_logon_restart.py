"""Tests for the at-logon restarter: it restarts only a FULL run that has not ended, has no ABORT and has no live process; nothing is launched in the tests."""
import json
import tempfile
import unittest
from pathlib import Path

from devmem.eval import logon_restart as lr


class TestLogonRestart(unittest.TestCase):
    def _root(self, label="FULL: live run in progress", state="running", abort=False):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        root = Path(t.name)
        rd = root / "devmem" / "storage" / "p7_baseline"
        rd.mkdir(parents=True)
        if label is not None:
            (rd / "run_label.json").write_text(json.dumps({"mode": label}))
        (rd / "run_status.json").write_text(json.dumps({"state": state}))
        if abort:
            (rd / "ABORT").write_text("x")
        return root, rd

    def test_decisions(self):
        cases = [(dict(), "", "restart"),
                 (dict(label="PILOT: live run"), "", "skip: label is not FULL"),
                 (dict(label=None), "", "skip: no readable run_label.json"),
                 (dict(abort=True), "", "skip: ABORT file present"),
                 (dict(state="finished: reached 2023-02-16 00:00:00"), "", "skip: the run ended cleanly"),
                 (dict(state="finished: upstream exception: TypeError: x"), "", "restart"),
                 (dict(state="starting"), "python -m devmem.eval.run_arm --arm baseline --sim p7_baseline", "skip: an arm process is already running")]
        for kw, procs, want in cases:
            root, rd = self._root(**kw)
            self.assertEqual(lr.decide(rd, "baseline", procs), want, kw)

    def test_main_launches_only_the_arm_that_needs_it_and_logs(self):
        root, rd = self._root()
        launched = []
        log = root / "logon.log"
        lr.main(popen=lambda cmd, **kw: launched.append(cmd), procs="", root=root, log=log)
        self.assertEqual(len(launched), 1)                                  # staged has no run folder: skipped
        self.assertIn("--arm", launched[0])
        self.assertIn("baseline", launched[0])
        text = log.read_text(encoding="utf-8")
        self.assertIn("baseline: supervisor started", text)
        self.assertIn("staged: skip: no readable run_label.json", text)


if __name__ == "__main__":
    unittest.main()
