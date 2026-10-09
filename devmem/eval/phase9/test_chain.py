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

    def test_held_steps_wait_for_the_release_and_the_small_steps_do_not(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            steps = [{"name": "small", "args": [], "output": t / "small.json", "cwd": t},
                     {"name": "big", "hold": "H", "args": [], "output": t / "big.json", "cwd": t}]
            ran, polls = [], []
            released = iter([False, False, True])

            def run_fn(s):
                ran.append(s["name"])
                Path(s["output"]).write_text("{}")
                return 0
            ok = run_staged_chain.run_chain(lambda: True, run_fn, t / "st.jsonl", steps=steps, poll=0, sleep_fn=lambda x: polls.append(x), hold_fns={"H": lambda: next(released)})
            self.assertTrue(ok)
            ev = [(json.loads(l)["event"], json.loads(l).get("step")) for l in (t / "st.jsonl").read_text().splitlines()]
            names = [e[0] for e in ev]
            self.assertLess(names.index("step_done"), names.index("step_held"))                  # the small step finished before the held one was even announced
            self.assertLess(names.index("step_held"), names.index("hold_released"))
            self.assertLess(names.index("hold_released"), len(names) - 1 - names[::-1].index("step_start"))
            self.assertEqual(ran, ["small", "big"])
            self.assertGreaterEqual(len(polls), 1)                                                # it waited

    def test_the_real_chain_holds_everything_after_the_three_small_steps(self):
        held = [s["name"] for s in run_staged_chain.STEPS if s.get("hold")]
        free = [s["name"] for s in run_staged_chain.STEPS if not s.get("hold")]
        self.assertEqual(free, ["staged_day3_evaluation", "judge_calibration", "baseline_day2_evaluation_on_staged_pool"])
        self.assertEqual(held, ["staged_day2_evaluation", "staged_replay_controls", "d1_d2_embedding_fetch", "staged_day2_secondary_evaluation"])
        self.assertEqual({s["hold"] for s in run_staged_chain.STEPS if s.get("hold")}, {run_staged_chain.HOLD})

    def test_release_needs_the_baseline_day3_primary_and_the_end_of_its_chain(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            (t / "p7_baseline").mkdir()
            rs, st = t / "p7_baseline" / "run_status.json", t / "chain_status.jsonl"
            rs.write_text(json.dumps({"state": "running", "checkpoints_made": ["day1_end_awake"]}))
            self.assertFalse(run_staged_chain.baseline_released(t, st, sim_root=t / "none"))                          # baseline has not passed step 22,410
            rs.write_text(json.dumps({"state": "running", "checkpoints_made": ["day1_end_awake", "day3_end_awake"]}))
            st.write_text(json.dumps({"chain": "baseline", "event": "step_done"}) + "\n")
            self.assertFalse(run_staged_chain.baseline_released(t, st, sim_root=t / "none"))                          # passed, but its chain is still running
            st.write_text(json.dumps({"chain": "baseline", "event": "chain_done"}) + "\n")
            self.assertTrue(run_staged_chain.baseline_released(t, st, sim_root=t / "none"))
            st.write_text(json.dumps({"chain": "baseline", "event": "step_failed_chain_halted"}) + "\n")
            self.assertTrue(run_staged_chain.baseline_released(t, st, sim_root=t / "none"))                          # a halted chain also releases
            st.write_text("")
            rs.write_text(json.dumps({"state": "running", "checkpoints_made": ["day1_end_awake"]}))        # status file lags the checkpoint folder
            (t / "sim" / "p7_baseline__ckpt_day3_end_awake" / "reverie").mkdir(parents=True)
            (t / "sim" / "p7_baseline__ckpt_day3_end_awake" / "reverie" / "meta.json").write_text("{}")
            st.write_text(json.dumps({"chain": "baseline", "event": "chain_done"}) + "\n")
            self.assertTrue(run_staged_chain.baseline_released(t, st, sim_root=t / "sim"))
            st.write_text("")
            rs.write_text(json.dumps({"state": "finished: reached end", "checkpoints_made": ["day3_end_awake"]}))
            self.assertFalse(run_staged_chain.baseline_released(t, st, now=lambda: rs.stat().st_mtime + 10, sim_root=t / "none"))
            self.assertTrue(run_staged_chain.baseline_released(t, st, now=lambda: rs.stat().st_mtime + 4000, sim_root=t / "none"))   # fallback: finished long ago and no chain end

    def test_the_real_step_list_follows_the_pm_order(self):
        names = [s["name"] for s in run_staged_chain.STEPS]
        self.assertEqual(names, ["staged_day3_evaluation", "judge_calibration", "baseline_day2_evaluation_on_staged_pool", "staged_day2_evaluation", "staged_replay_controls", "d1_d2_embedding_fetch", "staged_day2_secondary_evaluation"])
        self.assertIn("--pool-arm", run_staged_chain.STEPS[2]["args"])
        self.assertIn("staged", run_staged_chain.STEPS[2]["args"])
        self.assertIn("secondary", run_staged_chain.STEPS[-1]["args"])               # the 7g sensitivity run is the LAST step: it never delays a day-3 result
        self.assertIn("interim_day2_repaired", " ".join(run_staged_chain.STEPS[3]["args"]))


if __name__ == "__main__":
    unittest.main()
