"""Tests of the staged evaluation chain: order, waiting for the finish, skipping finished outputs, halting at the first failure (no call, no key, no process)."""
import json
import tempfile
import unittest
from pathlib import Path

from devmem.eval.phase9 import run_staged_chain


def _steps(t: Path):
    return [{"name": n, "args": [], "output": t / f"{n}.json", "cwd": t} for n in ("one", "two", "three")]


class TestChain(unittest.TestCase):
    def test_runs_in_order_after_the_finish_and_skips_existing_outputs(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            steps = _steps(t)
            (t / "one.json").write_text("{}")                          # already written: skipped
            ran, polls = [], []
            states = iter([False, False, True])

            def run_fn(s):
                ran.append(s["name"])
                Path(s["output"]).write_text("{}")
                return 0
            ok = run_staged_chain.run_chain(lambda: next(states), run_fn, t / "status.jsonl", steps=steps, poll=0, sleep_fn=lambda x: polls.append(x))
            self.assertTrue(ok)
            self.assertEqual(ran, ["two", "three"])
            self.assertEqual(len(polls), 2)                            # waited until the staged arm had finished
            ev = [json.loads(l)["event"] for l in (t / "status.jsonl").read_text().splitlines()]
            self.assertEqual(ev[0], "staged_finished_chain_starts")
            self.assertEqual(ev[-1], "chain_done")

    def test_halts_at_the_first_failing_step(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            ran = []

            def run_fn(s):
                ran.append(s["name"])
                return 1 if s["name"] == "two" else (Path(s["output"]).write_text("{}") and 0) or 0
            ok = run_staged_chain.run_chain(lambda: True, run_fn, t / "status.jsonl", steps=_steps(t), sleep_fn=lambda x: None)
            self.assertFalse(ok)
            self.assertEqual(ran, ["one", "two"])                      # step three never started
            last = json.loads((t / "status.jsonl").read_text().splitlines()[-1])
            self.assertEqual((last["event"], last["step"]), ("step_failed_chain_halted", "two"))

    def test_the_real_step_list_follows_the_pm_order(self):
        names = [s["name"] for s in run_staged_chain.STEPS]
        self.assertEqual(names, ["staged_day3_evaluation", "judge_calibration", "baseline_day2_evaluation_on_staged_pool", "staged_replay_controls", "d1_d2_embedding_fetch"])
        self.assertIn("--pool-arm", run_staged_chain.STEPS[2]["args"])
        self.assertIn("staged", run_staged_chain.STEPS[2]["args"])


if __name__ == "__main__":
    unittest.main()
