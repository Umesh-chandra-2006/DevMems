"""
Offline smoke test of the REAL `devmem.eval.run_arm.main()` (the arm runner's wiring): environment, fork copy, temporary provider configs,
quota gate, embedding wrapper, authored plan install and uninstall, event injector, hourly ledger windows, checkpoint copies at the
autosave step, run_status.json, soft-stop and the final report. Only the step body is scripted (as in test_reconcile): the simulation clock
advances and a movement file is written; NO LLM call and NO network request is made. The key variables are set to dummy placeholder
strings (never real keys, never used). The checkpoint times are moved to 01:00 and the end to 02:00 so the run is 720 steps long.
Run it as its own module (it uses the shared ReverieServer state): python -m unittest devmem.eval.test_run_arm_smoke
"""
import devmem.testing_env  # noqa: F401
import json
import os
import shutil
import sqlite3
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent.parent
TEMP_STORAGE = ROOT / "reverie" / "environment" / "frontend_server" / "temp_storage"


class TestRunArmSmoke(unittest.TestCase):
    SIM = "p7_smoke_staged"

    @classmethod
    def setUpClass(cls):
        cls._cwd = os.getcwd()
        cls._temp = {p: p.read_bytes() for p in TEMP_STORAGE.glob("*.json")}

    @classmethod
    def tearDownClass(cls):
        for p in TEMP_STORAGE.glob("*.json"):
            if p not in cls._temp:
                p.unlink()
        for p, data in cls._temp.items():
            p.write_bytes(data)
        os.chdir(cls._cwd)

    def cleanup(self):
        import utils
        storage = Path(utils.fs_storage) if hasattr(utils, "fs_storage") else None
        for base in ([ROOT / "reverie/environment/frontend_server/storage" / n for n in (self.SIM, f"base_the_ville_isabella_maria_klaus__start_{self.SIM}")]
                     + [ROOT / "devmem" / "storage" / self.SIM]):
            shutil.rmtree(base, ignore_errors=True)
        for p in (ROOT / "reverie/environment/frontend_server/storage").glob(f"{self.SIM}__*"):
            shutil.rmtree(p, ignore_errors=True)

    def test_a_scripted_two_hour_run_produces_windows_checkpoint_status_and_report_without_any_call(self):
        from devmem.eval import run_arm
        from devmem.eval import run_support  # noqa: F401
        import devmem.run_headless as rh
        self.cleanup()
        self.addCleanup(self.cleanup)
        start = run_arm.START
        env = {k: "dummy-placeholder-not-a-key" for k in run_arm.ARM_KEYS["staged"]}
        calls = {"network_or_llm": 0}

        def scripted_advance(inner):
            rs = inner.rs
            import utils
            for name, p in rs.personas.items():
                p.scratch.curr_time = rs.curr_time
                if p.scratch.act_start_time is None:
                    p.scratch.act_start_time = rs.curr_time
            moves = {n: {"movement": list(rs.personas_tile[n]), "description": "sleeping @ x"} for n in rs.personas}
            mv = Path(f"{utils.fs_storage}/{inner.sim_code}/movement/{rs.step}.json")
            mv.write_text(json.dumps({"persona": moves, "meta": {}}))
            rs.step += 1
            rs.curr_time += timedelta(seconds=rs.sec_per_step)

        def no_call(*a, **k):
            calls["network_or_llm"] += 1
            raise AssertionError("a router call was made in the offline smoke test")

        patches = [mock.patch.dict(os.environ, env), mock.patch.object(rh.HeadlessRunner, "_advance", scripted_advance),
                   mock.patch.object(run_arm, "CHECKPOINTS", {"day1_end_awake": start + timedelta(hours=1)}),
                   mock.patch.object(run_arm, "UNTIL", start + timedelta(hours=2)),
                   mock.patch("devmem.router.llm_router.call_llm", no_call)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        os.environ.pop("DEVMEM_RAW_REPLY_LOG", None)
        stdout = sys.stdout
        run_arm.main(["--arm", "staged", "--sim", self.SIM])
        sys.stdout = stdout
        run_dir = ROOT / "devmem" / "storage" / self.SIM
        report = json.loads((run_dir / "arm_report_first.json").read_text(encoding="utf-8"))
        self.assertEqual(report["outcome"], f"reached {start + timedelta(hours=2)}")
        self.assertEqual(report["final_step"], 720)
        self.assertEqual(calls["network_or_llm"], 0)
        self.assertIsNone(report["exception"])
        self.assertEqual(report["checkpoints"], {"day1_end_awake": 360})
        lines = [json.loads(l) for l in (run_dir / "hourly_ledger.jsonl").read_text().splitlines()]
        self.assertEqual([l["label"] for l in lines], ["step_0_day_start_planning", "hour_ending_2023-02-13_01:00", "hour_ending_2023-02-13_02:00", "final_partial_window"])
        self.assertEqual({k for l in lines for k in l["sleeping_step_fraction"]}, {"Isabella Rodriguez", "Maria Lopez", "Klaus Mueller"})
        status = json.loads((run_dir / "run_status.json").read_text(encoding="utf-8"))
        self.assertTrue(status["state"].startswith("finished"))
        self.assertEqual(status["checkpoints_made"], ["day1_end_awake"])
        ck = ROOT / "reverie/environment/frontend_server/storage" / f"{self.SIM}__ckpt_day1_end_awake"
        self.assertTrue((ck / "personas" / "Maria Lopez" / "bootstrap_memory" / "scratch.json").exists())
        self.assertEqual(json.loads((ck / "checkpoint.json").read_text())["step"], 360)
        self.assertTrue(sqlite3.connect(str(run_dir / "checkpoints" / "day1_end_awake" / "memory.db")).execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0] >= 1)
        self.assertEqual(report["autosave_steps"][:3], [90, 180, 270])
        self.assertEqual(report["injection"]["resolved"], 0, "no event is due before 08:20")
        movement = list((ROOT / "reverie/environment/frontend_server/storage" / self.SIM / "movement").glob("*.json"))
        self.assertGreaterEqual(len(movement), 720, "the movement files are kept")
        import persona.cognitive_modules.plan as plan
        self.assertNotEqual(plan.generate_hourly_schedule.__module__, "devmem.eval.authored_plan", "the plan functions were restored at the end")


if __name__ == "__main__":
    unittest.main()
