"""Replay-mode demo test (scripted data, no network: socket creation is blocked while it runs)."""
import devmem.testing_env  # noqa: F401
import contextlib
import io
import json
import socket
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from devmem.demo import run_demo


class TestReplayDemo(unittest.TestCase):
    def _run(self, which=None):
        buf = io.StringIO()
        with mock.patch.object(socket, "socket", side_effect=AssertionError("network used in replay mode")), \
             contextlib.redirect_stdout(buf):
            run_demo.replay(which)
        return buf.getvalue()

    def test_replay_prints_entries_clusters_summaries_and_both_rankings_offline(self):
        text = self._run()
        data = json.loads(run_demo.REPLAY.read_text(encoding="utf-8"))
        self.assertIn("SCRIPTED", text)
        self.assertIn("1. EPISODIC ENTRIES", text)
        self.assertIn("2. CLUSTERS", text)
        self.assertIn("3. SEMANTIC MEMORIES", text)
        self.assertIn("consolidated_weight 0.5", text)
        self.assertIn("consolidated_weight 1.0", text)
        for run in data["runs"].values():
            for s in run["summaries"]:
                self.assertIn(s["summary"], text)
                for t in s["source_texts"]:
                    self.assertIn(t, text)
            self.assertEqual(len(run["ranking"]), 3)
            for entry in run["ranking"].values():
                self.assertEqual(len(entry["weight_0.5"]), len(entry["weight_1.0"]))

    def test_run_filter_selects_one_threshold(self):
        text = self._run("0.82")
        self.assertIn("threshold 0.82", text)
        self.assertNotIn("# RUN: threshold 0.78", text)


if __name__ == "__main__":
    unittest.main()
