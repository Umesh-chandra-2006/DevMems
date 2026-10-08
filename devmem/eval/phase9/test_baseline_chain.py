"""Tests of the baseline chain: step list, copy-readiness check (complete, torn, missing), and the chain label in the status events."""
import json
import tempfile
import unittest
from pathlib import Path

from devmem.eval.phase9 import run_baseline_chain as B, run_staged_chain as C


def _copy(st: Path, folder: str, step: int, bad_json: bool = False):
    d = st / folder / "baseline"
    (d / "sim" / "personas" / "A").mkdir(parents=True)
    (d / "sim" / "personas" / "A" / "x.json").write_text('{"k": [1' if bad_json else "{}")
    (d / "memory.db").write_text("")
    (d / "checkpoint.json").write_text(json.dumps({"step": step, "sim_clock": "c", "exact_first_autosave": True}))


class TestBaselineChain(unittest.TestCase):
    def test_copies_ready_requires_both_complete_copies(self):
        with tempfile.TemporaryDirectory() as t:
            st = Path(t)
            self.assertFalse(B.copies_ready("baseline", st)["all_ready"])                       # nothing yet
            _copy(st, "interim_day3", 22410)
            _copy(st, "interim_day3_secondary", 25830, bad_json=True)
            r = B.copies_ready("baseline", st)
            self.assertFalse(r["all_ready"])                                                   # the secondary has a truncated JSON
            self.assertEqual(r["copies"]["day3_secondary_2345"]["json_files_not_parsing"], ["sim/personas/A/x.json"])
            (st / "interim_day3_secondary" / "baseline" / "sim" / "personas" / "A" / "x.json").write_text("{}")
            self.assertTrue(B.copies_ready("baseline", st)["all_ready"])

    def test_steps_follow_the_pm_order_and_the_chain_is_labelled_baseline(self):
        self.assertEqual([s["name"] for s in B.STEPS], ["baseline_checkpoint_copies_ready", "baseline_day3_evaluation", "results_export_day3", "baseline_secondary_copy_ready", "baseline_day2_secondary_evaluation"])
        self.assertEqual(B.STEPS[1]["hold"], B.POOL_HOLD)
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            steps = [{"name": "s", "args": [], "output": t / "o.json", "cwd": t}]

            def run_fn(s):
                Path(s["output"]).write_text("{}")
                return 0
            self.assertTrue(C.run_chain(lambda: True, run_fn, t / "st.jsonl", steps=steps, sleep_fn=lambda x: None, chain="baseline"))
            ev = [json.loads(l) for l in (t / "st.jsonl").read_text().splitlines()]
            self.assertEqual({e["chain"] for e in ev}, {"baseline"})
            self.assertEqual(ev[0]["event"], "baseline_finished_chain_starts")      # default name; the real chain passes start_event="baseline_day3_primary_chain_starts"


class TestStartAndPool(unittest.TestCase):
    def test_the_chain_starts_when_the_baseline_passes_its_day3_primary_checkpoint(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            (t / "p7_baseline").mkdir()
            rs = t / "p7_baseline" / "run_status.json"
            self.assertFalse(B.baseline_day3_primary_exists(t))                                  # no status file
            rs.write_text(json.dumps({"state": "running", "checkpoints_made": ["day1_end_awake"]}))
            self.assertFalse(B.baseline_day3_primary_exists(t))
            rs.write_text(json.dumps({"state": "running", "checkpoints_made": ["day1_end_awake", "day3_end_awake"]}))
            self.assertTrue(B.baseline_day3_primary_exists(t))                                   # still running its last night: the chain starts at once
            rs.write_text(json.dumps({"state": "finished: reached end", "checkpoints_made": []}))
            self.assertTrue(B.baseline_day3_primary_exists(t))

    def test_the_pool_is_a_finished_arms_never_a_running_arms(self):
        self.assertEqual(B.pool_arm(lambda arm: arm == "staged"), "staged")
        self.assertEqual(B.pool_arm(lambda arm: True), "staged")
        self.assertEqual(B.pool_arm(lambda arm: arm == "baseline"), "baseline")
        self.assertIsNone(B.pool_arm(lambda arm: False))                                         # neither finished: the evaluation step stays held

    def test_primary_only_check_needs_just_the_primary_copy(self):
        with tempfile.TemporaryDirectory() as t:
            st = Path(t)
            _copy(st, "interim_day3", 22410)
            self.assertTrue(B.copies_ready("baseline", st, primary_only=True)["all_ready"])
            self.assertFalse(B.copies_ready("baseline", st)["all_ready"])                        # the full check also wants the 23:45 copy


if __name__ == "__main__":
    unittest.main()
