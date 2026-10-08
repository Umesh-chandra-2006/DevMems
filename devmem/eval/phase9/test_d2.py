"""Tests of the D-2 offline reproduction and the D-1/D-2 embedding fetch plan, on synthetic vectors (no network, no key)."""
import devmem.testing_env  # noqa: F401
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import numpy as np

from devmem.eval.phase9 import d2_reproduction as D, fetch_embeddings as F, repair_copy as RC
from devmem.memory import consolidation


def _vectors(seed=3, groups=3, per=5, dim=24):
    rng = np.random.RandomState(seed)
    out = []
    for g in range(groups):
        base = rng.randn(dim)
        for _ in range(per):
            out.append((base + 0.35 * rng.randn(dim)).tolist())
    return out


class TestClustering(unittest.TestCase):
    def test_merge_recorder_gives_the_same_clusters_as_the_production_function(self):
        v = _vectors()
        for thr in (0.5, 0.82):
            mine, merges = D.average_linkage_with_heights(v, thr)
            self.assertEqual(mine, consolidation.cluster_by_similarity(v, thr, "average"))
            self.assertTrue(all(m["height"] >= thr for m in merges))

    def test_d2_count_uses_only_merges_inside_the_range(self):
        clusters = [[0, 1, 2], [3]]
        merges = [{"height": 0.85, "a": [0], "b": [1]}, {"height": 0.95, "a": [0, 1], "b": [2]}]
        self.assertEqual(D.d2_count(clusters, merges, 3), 2)          # entries 0 and 1 took part in the 0.85 merge; 2 joined at 0.95
        self.assertEqual(D.d2_count(clusters, merges, 4), 0)          # no final cluster of 4


class TestReproduce(unittest.TestCase):
    def _db(self, t, vecs):
        db = Path(t) / "m.db"
        c = sqlite3.connect(db)
        c.execute("CREATE TABLE episodic_memory (entry_id TEXT, agent_id TEXT, content TEXT, sim_timestamp TEXT, importance_score REAL)")
        c.executemany("INSERT INTO episodic_memory VALUES (?,?,?,?,?)", [(f"A:node_{i}", "A", f"event number {i}", f"2023-02-13 08:{i:02d}:00", 5.0) for i in range(len(vecs))])
        c.commit()
        c.close()
        return db

    def test_reproduced_when_the_record_matches_and_not_when_it_differs(self):
        cfg = {"cluster_similarity": 0.82, "min_cluster_size": 3, "importance_floor": 3, "exclude_description_substrings": ["idle"], "max_summaries_per_night": 6, "max_entries_per_prompt": 12}
        v = _vectors()
        with tempfile.TemporaryDirectory() as t:
            db = self._db(t, v)
            fn = lambda agent, eid, content: v[int(eid.split("_")[1])]
            clusters, merges = D.average_linkage_with_heights(v, 0.82)
            hist = {}
            for c in clusters:
                hist[str(len(c))] = hist.get(str(len(c)), 0) + 1
            hist = {k: hist[k] for k in sorted(hist, key=int)}
            flagged = sum(min(len(c), 12) for c in clusters if len(c) >= 3)
            row = {"agent": "A", "night": 1, "sim_time": "2023-02-13 13:00:00", "status": "done", "entries_considered": len(v), "cluster_size_histogram": hist, "entries_flagged": flagged}
            rep = D.reproduce(db, [row], fn, cfg)
            self.assertTrue(rep["agents"]["A"]["all_nights_reproduced"])
            self.assertEqual(D.score(rep)["outcome"] in ("right", "wrong"), True)
            bad = dict(row, cluster_size_histogram={"1": len(v)})
            rep2 = D.reproduce(db, [bad], fn, cfg)
            self.assertFalse(rep2["agents"]["A"]["all_nights_reproduced"])
            self.assertEqual(D.score(rep2)["outcome"], "undecidable")
            rep3 = D.reproduce(db, [row], lambda a, e, c: None, cfg)           # every embedding missing: not reproducible, the texts are listed
            self.assertEqual(D.score(rep3)["outcome"], "undecidable")
            self.assertEqual(len(rep3["missing_texts"]), len(v))


class TestRepair(unittest.TestCase):
    def test_truncated_embeddings_are_rebuilt_in_a_new_folder_and_the_original_is_untouched(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            src = t / "src"
            a = src / "sim" / "personas" / "A" / "bootstrap_memory" / "associative_memory"
            a.mkdir(parents=True)
            (a / "nodes.json").write_text(json.dumps({"node_1": {"embedding_key": "k1"}, "node_2": {"embedding_key": "k2"}}))
            (a / "embeddings.json").write_text('{"k1": [0.1, 0.2')                      # torn
            (src / "checkpoint.json").write_text("{}")
            rep = RC.repair(src, t / "dst", lambda k: [1.0, 2.0] if k in ("k1", "k2") else None)
            self.assertTrue(rep["usable"])
            self.assertEqual(rep["personas"]["A"]["rebuilt_keys"], 2)
            self.assertEqual(json.loads((t / "dst" / "sim" / "personas" / "A" / "bootstrap_memory" / "associative_memory" / "embeddings.json").read_text()), {"k1": [1.0, 2.0], "k2": [1.0, 2.0]})
            self.assertEqual((a / "embeddings.json").read_text(), '{"k1": [0.1, 0.2')   # the original copy is byte for byte unchanged
            self.assertIn("repaired_copy", json.loads((t / "dst" / "checkpoint.json").read_text()))
            bad = RC.repair(src, t / "dst2", lambda k: None)                           # keys missing from the cache: not usable
            self.assertFalse(bad["usable"])


class TestFetch(unittest.TestCase):
    def test_fetch_batches_the_missing_texts(self):
        calls = []
        n = F.fetch([f"t{i}" for i in range(120)], lambda chunk: (calls.append(len(chunk)), [[0.0]] * len(chunk))[1])
        self.assertEqual((n, calls), (120, [50, 50, 20]))


if __name__ == "__main__":
    unittest.main()
