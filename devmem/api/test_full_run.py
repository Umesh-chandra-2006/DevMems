"""Tests of the full-run viewer data builder and of the run-label rendering (no run folder is written; the committed full_run.json is only read)."""
import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from devmem.api import build_full_run as B  # noqa: E402
from devmem.api import store  # noqa: E402

WEB = ROOT / "devmem" / "api" / "web"


class TestHelpers(unittest.TestCase):
    def test_action_text_is_cleaned_like_the_side_by_side_view(self):
        self.assertEqual(B.clean_action("opening the cafe (duration in minutes: 15, minutes left: 105) @ the Ville:Hobbs Cafe:cafe"), "opening the cafe")
        self.assertEqual(B.clock_of(2970), "2023-02-13 08:15:00")

    def test_first_divergence_is_the_first_step_whose_cleaned_action_text_differs(self):
        fa = [{"s": s, "p": {"A": [0, 0, "", t, None]}} for s, t in ((10, "sleeping"), (11, "waking up (duration in minutes: 5, minutes left: 5)"), (12, "painting"))]
        fb = [{"s": s, "p": {"A": [0, 0, "", t, None]}} for s, t in ((10, "sleeping"), (11, "waking up"), (12, "reading"))]
        d = B.first_divergence(fa, fb, "A")
        self.assertEqual((d["step"], d["left_action"], d["right_action"]), (12, "painting", "reading"))       # step 11 differs only by the duration annotation
        self.assertIsNone(B.first_divergence(fa[:2], fb[:2], "A"))

    def test_recall_by_distance_groups_and_excludes(self):
        rows = [{"type": "injected", "distance_days": 0, "baseline": {"score": 1.0}, "staged": {"score": 0.5}}, {"type": "natural", "distance_days": 0, "baseline": {"score": 0.0}, "staged": {"score": 0.0}},
                {"type": "injected", "distance_days": 2, "baseline": {"score": 1.0}, "staged": {"score": 1.0}, "excluded": "x"}, {"type": "theme_count", "distance_days": None, "baseline": {"score": 0.5}, "staged": {"score": 0.0}}]
        g = {x["group"]: x for x in B.by_distance(rows)}
        self.assertEqual((g["same day"]["n"], g["same day"]["baseline_mean"], g["same day"]["staged_mean"]), (2, 0.5, 0.25))
        self.assertEqual(g["2 days"]["n"], 0)                                                                    # the excluded row is not counted
        self.assertEqual((g["theme count"]["n"], g["theme count"]["staged_mean"]), (1, 0.0))

    def test_persona_scoring_rows_say_being_re_run_until_the_staged_condition_is_replayed(self):
        exp = {"predictions": [{"id": "S-Isabella", "prediction": "p", "outcome": "right", "reason": "r", "numbers": {}}, {"id": "E2", "prediction": "p", "outcome": "right", "reason": "r", "numbers": {}}]}
        old = {"summary": {"by_condition": {"baseline": {}, "staged_own": {}}}}
        new = {"summary": {"by_condition": {"baseline": {}, "staged_own": {}, "staged_replayed": {}}}}
        s = {x["id"]: x for x in B.scorecard(exp, old)}
        self.assertEqual((s["S-Isabella"]["outcome"], s["E2"]["outcome"]), ("being re-run", "right"))
        self.assertEqual(B.scorecard(exp, new)[0]["outcome"], "right")


class TestLabel(unittest.TestCase):
    def test_full_run_label_comes_from_the_run_status_and_pilots_keep_theirs(self):
        self.assertEqual(store.full_run_mode("p7_staged", "finished: reached 2023-02-16 00:00:00"), "FULL RUN, 3 simulated days, finished")
        self.assertEqual(store.full_run_mode("p7_baseline", "running"), "FULL RUN, 3 simulated days, running")
        self.assertIsNone(store.full_run_mode("p7pilot_staged", "finished: x"))
        self.assertIsNone(store.full_run_mode("p5_staged_live", "finished: x"))


class TestCommittedData(unittest.TestCase):
    def test_the_built_file_has_every_section_the_views_read(self):
        f = WEB / "data" / "full_run.json"
        if not f.exists():
            self.skipTest("full_run.json not built")
        d = json.loads(f.read_text(encoding="utf-8"))
        for k in ("scorecard", "recall", "tiles", "calls_by_class", "replay", "m2", "injections", "nights", "baseline_reflections", "scoring_card", "divergence", "incidents", "d1_wording"):
            self.assertIn(k, d)
        self.assertEqual(len(d["injections"]), 27)
        self.assertEqual(len(d["scoring_card"]["rows"]), 26)
        self.assertEqual(d["nights"]["provenance_n"], 14)
        self.assertEqual(d["nights"]["provenance_flagged"], 1)
        self.assertIn("periodic reflection (focal-point and insight generation) is off in the staged arm", d["d1_wording"])
        self.assertTrue(all(i["ledger"] for i in d["incidents"]))
        self.assertEqual({r["question_id"] for r in d["recall"]["rows"] if r["question_id"] in ("Q_I2", "Q_K7")}, {"Q_I2", "Q_K7"})

    def test_the_javascript_files_parse(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node not available")
        for name in ("full.js", "app.js", "common.js"):
            r = subprocess.run([node, "--check", str(WEB / name)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, name + ": " + r.stderr[:300])


if __name__ == "__main__":
    unittest.main()
