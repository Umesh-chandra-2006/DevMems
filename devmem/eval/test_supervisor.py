"""Supervisor tests with a stub child process (no simulation, no calls). The stub plays the part of run_arm: it writes the same report files."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

from devmem.eval import supervisor

STUB = '''
import json, sys, time
from pathlib import Path
run_dir = Path(sys.argv[1]); plan = json.loads(sys.argv[2])
n_file = run_dir / "n.txt"
n = int(n_file.read_text()) if n_file.exists() else 0
n_file.write_text(str(n + 1))
(run_dir / "arm_state.json").write_text("{}")
step = plan[min(n, len(plan) - 1)]
kind, clock, st = step
if kind == "kill":
    sys.exit(1)                                  # no report: the child was killed
rep = {"outcome": "upstream exception: TypeError: x" if kind == "crash" else "reached 2023-02-13 09:00:00", "final_clock": clock, "final_step": st}
(run_dir / ("arm_report_resume.json" if n else "arm_report_first.json")).write_text(json.dumps(rep))
'''


class TestSupervisor(unittest.TestCase):
    def _run(self, plan, pre_abort=False, **kw):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        rd = Path(t.name) / "run"
        rd.mkdir()
        if pre_abort:
            (rd / "ABORT").write_text("operator")
        stub = Path(t.name) / "stub.py"
        stub.write_text(STUB, encoding="utf-8")
        calls = []

        def build(resume):
            calls.append(resume)
            return [sys.executable, str(stub), str(rd), json.dumps(plan)]
        out = supervisor.supervise(rd, build, pause_s=0, **kw)
        log = [json.loads(l) for l in (rd / "resume_log.jsonl").read_text().splitlines()]
        return out, calls, log, rd

    def test_crash_then_clean_end_resumes_once_and_logs(self):
        out, calls, log, rd = self._run([("crash", "2023-02-13 07:10:00", 2600), ("ok", "2023-02-13 09:00:00", 3240)])
        self.assertEqual((out, calls), ("final", [False, True]))
        self.assertEqual([r["event"] for r in log], ["start", "exit", "resume", "start", "exit", "final"])
        self.assertFalse((rd / "ABORT").exists())

    def test_kill_without_report_is_resumed(self):
        out, calls, log, rd = self._run([("kill", "", 0), ("ok", "2023-02-13 09:00:00", 3240)])
        self.assertEqual((out, calls), ("final", [False, True]))
        self.assertFalse(log[1]["report"])

    def test_same_step_twice_creates_abort(self):
        out, calls, log, rd = self._run([("crash", "2023-02-13 07:10:00", 2600), ("crash", "2023-02-13 07:10:00", 2600)])
        self.assertEqual(out, "abort_same_step")
        self.assertTrue((rd / "ABORT").exists())
        self.assertEqual(len(calls), 2)

    def test_abort_file_after_an_exception_exit_is_never_resumed(self):
        out, calls, log, rd = self._run([("crash", "2023-02-13 07:10:00", 2600), ("ok", "2023-02-13 09:00:00", 3240)], pre_abort=True)
        self.assertEqual((out, calls), ("final", [False]))

    def test_limit_of_three_resumes_per_sim_day(self):
        plan = [("crash", "2023-02-13 07:10:00", 2600 + 10 * i) for i in range(6)]
        out, calls, log, rd = self._run(plan)
        self.assertEqual(out, "abort_per_day_limit")
        self.assertEqual(len(calls), 4)                      # the first start plus three resumes
        self.assertEqual(sum(1 for r in log if r["event"] == "resume"), 3)
        self.assertTrue((rd / "ABORT").exists())

    def test_a_new_sim_day_resets_the_count(self):
        plan = [("crash", "2023-02-13 10:00:00", 1), ("crash", "2023-02-13 11:00:00", 2), ("crash", "2023-02-13 12:00:00", 3),
                ("crash", "2023-02-14 01:00:00", 4), ("ok", "2023-02-14 09:00:00", 5)]
        out, calls, log, rd = self._run(plan)
        self.assertEqual(out, "final")
        self.assertEqual(len(calls), 5)


if __name__ == "__main__":
    unittest.main()
