"""Tests of the checkpoint-copy integrity tests and of the day-3 source choice, on synthetic folders."""
import json
import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from devmem.eval.phase9 import copy_integrity as CI


def _sim(root: Path, scratch_newer=True, truncated=False, extra_mirror_node=False, with_db=True):
    sim = root / "sim"
    (sim / "reverie").mkdir(parents=True)
    (sim / "reverie" / "meta.json").write_text(json.dumps({"step": 1, "persona_names": ["A"]}))
    b = sim / "personas" / "A" / "bootstrap_memory"
    (b / "associative_memory").mkdir(parents=True)
    (b / "associative_memory" / "nodes.json").write_text(json.dumps({"node_1": {"embedding_key": "k"}}))
    (b / "associative_memory" / "embeddings.json").write_text('{"k": [1.0' if truncated else '{"k": [1.0]}')
    (b / "scratch.json").write_text("{}")
    now = time.time()
    os.utime(sim / "reverie" / "meta.json", (now, now))
    t = now + 5 if scratch_newer else now - 60
    os.utime(b / "scratch.json", (t, t))
    if with_db:
        c = sqlite3.connect(root / "memory.db")
        c.execute("CREATE TABLE episodic_memory (entry_id TEXT, agent_id TEXT)")
        rows = [("A:node_1", "A")] + ([("A:node_9", "A")] if extra_mirror_node else [])
        c.executemany("INSERT INTO episodic_memory VALUES (?,?)", rows)
        c.commit()
        c.close()
    return sim


class TestIntegrity(unittest.TestCase):
    def test_each_test_fails_for_its_own_defect(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            self.assertTrue(CI.check_copy_folder(_sim(t / "ok", True) and t / "ok")["passes"])
            r = CI.check_copy_folder(_sim(t / "old", scratch_newer=False) and t / "old")
            self.assertFalse(r["passes"])
            self.assertFalse(r["personas"]["A"]["T1_scratch_at_least_as_new_as_meta"])                   # persona saved before meta.json: a stale copy
            r = CI.check_copy_folder(_sim(t / "torn", truncated=True) and t / "torn")
            self.assertFalse(r["passes"])
            self.assertEqual(r["json_not_parsing"], ["personas/A/bootstrap_memory/associative_memory/embeddings.json"])
            r = CI.check_copy_folder(_sim(t / "stale", extra_mirror_node=True) and t / "stale")
            self.assertEqual(r["personas"]["A"]["T3_mirror_rows_without_a_node"], 1)                      # a mirror row whose node is not in nodes.json
            self.assertFalse(r["passes"])

    def test_day3_source_prefers_the_runners_own_checkpoint_when_it_passes(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            simroot, st = t / "sim", t / "st"
            own = simroot / "p7_baseline__ckpt_day3_end_awake"
            _sim(t / "tmp_own", True, with_db=False)
            (simroot).mkdir()
            os.rename(t / "tmp_own" / "sim", own)
            ext = st / "interim_day3" / "baseline"
            _sim(ext, True)
            self.assertEqual(CI.choose_day3("baseline", simroot, st)["chosen"], "runner")
            # the runner's checkpoint has a truncated file: the external copy is used
            (own / "personas" / "A" / "bootstrap_memory" / "associative_memory" / "embeddings.json").write_text('{"k": [1.0')
            r = CI.choose_day3("baseline", simroot, st)
            self.assertEqual((r["chosen"], r["path"]), ("external", str(ext / "sim")))
            # both fail: nothing is chosen
            (ext / "sim" / "personas" / "A" / "bootstrap_memory" / "associative_memory" / "embeddings.json").write_text('{"k": [1.0')
            self.assertIsNone(CI.choose_day3("baseline", simroot, st)["chosen"])


if __name__ == "__main__":
    unittest.main()
