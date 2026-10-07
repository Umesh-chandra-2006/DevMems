"""The Findings data: built offline from artifacts, every card carries an evidence path, no generated narrative marker, no em dash, the standing note is in the page code."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DATA = ROOT / "devmem" / "api" / "web" / "data" / "findings.json"
NOTE = "single run per arm; differences can be model noise; PILOT is not a result"


class TestFindingsData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = json.loads(DATA.read_text(encoding="utf-8"))

    def test_note_and_no_em_dash(self):
        self.assertEqual(self.d["note"], NOTE)
        text = DATA.read_text(encoding="utf-8")
        self.assertNotIn("—", text)
        for js in ("views.js", "common.js"):
            self.assertIn(NOTE, (ROOT / "devmem/api/web" / js).read_text(encoding="utf-8"))

    def test_every_card_has_an_evidence_path_that_exists(self):
        D = self.d["differs"]
        paths = [self.d["findings"]["injections"]["artifact"], self.d["findings"]["calls"]["artifact"], D["scoring"]["phase4"]["artifact"], D["consolidation"]["evidence"], D["identity"]["evidence"]]
        paths += [e["evidence"] for e in self.d["edge_cases"]] + [b["evidence"] for b in self.d["findings"]["bugs"]]
        for field in paths:
            for part in str(field).split(";"):
                part = part.strip().split(" (")[0].split(" section")[0].split(" TestInjected")[0].split(" test_")[0]
                for sub in part.split(", "):
                    sub = sub.strip()
                    if "*" in sub or not sub or " " in sub or "/" not in sub:   # shorthand names (same folder as the path before) are skipped
                        continue
                    self.assertTrue((ROOT / sub).exists() or any(ROOT.glob(sub)), sub)

    def test_scoring_cards_state_real_differences_and_the_two_scores(self):
        for e in self.d["differs"]["scoring"]["examples"]:
            self.assertTrue(e["available"])
            self.assertGreater(e["n_only_staged"], 0)
            self.assertIn("staged", e["why"])

    def test_divergence_card_carries_the_notice_and_the_rule(self):
        V = self.d["differs"]["divergence"]
        self.assertEqual(V["notice"], "single run per arm; this difference may be model noise; the candidate causes are not tested")
        self.assertTrue(V["rule"])
        self.assertIn("not logged", V["retrieval_note"])

    def test_consolidation_and_identity_use_recorded_logs(self):
        C, I = self.d["differs"]["consolidation"], self.d["differs"]["identity"]
        self.assertEqual(C["night"], 2)
        self.assertEqual(C["offline_relabel"]["settings"]["single_0.78 (what Stop 3 used)"]["cross_theme_pairs_merged"], 15)
        self.assertTrue(any(t["flag"] for t in I["traits"]))


if __name__ == "__main__":
    unittest.main()
