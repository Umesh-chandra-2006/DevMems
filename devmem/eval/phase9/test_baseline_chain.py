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
        self.assertEqual([s["name"] for s in B.STEPS], ["baseline_checkpoint_copies_ready", "baseline_day3_evaluation", "results_export_day3"])
        self.assertEqual(B.STEPS[1]["args"][-2:], ["--arm", "baseline"])
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            steps = [{"name": "s", "args": [], "output": t / "o.json", "cwd": t}]

            def run_fn(s):
                Path(s["output"]).write_text("{}")
                return 0
            self.assertTrue(C.run_chain(lambda: True, run_fn, t / "st.jsonl", steps=steps, sleep_fn=lambda x: None, chain="baseline"))
            ev = [json.loads(l) for l in (t / "st.jsonl").read_text().splitlines()]
            self.assertEqual({e["chain"] for e in ev}, {"baseline"})
            self.assertEqual(ev[0]["event"], "baseline_finished_chain_starts")


if __name__ == "__main__":
    unittest.main()
