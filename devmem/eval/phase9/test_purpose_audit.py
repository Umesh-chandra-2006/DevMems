"""Tests of the purpose-tag audit on synthetic delivered-reply rows (no run folder is read)."""
import json
import tempfile
import unittest
from pathlib import Path

from devmem.eval.phase9 import purpose_audit as P

REFLECT = 'Statements above. Given only the information above, what are 3 most salient high-level questions we can answer about the subjects grounded in the statements? 1)'
ACTION = "Current activity: sleep in bed\nObjects available: {bed, easel}\nPick ONE most relevant object from the objects available: bed"
CONVO = "Given the above, what should Maria Lopez say to Klaus Mueller next in the conversation? And did it end the conversation?"
SCORE = "On the scale of 1 to 10, where 1 is purely mundane and 10 is extremely poignant, rate the likely poignancy of the following piece of memory. Memory: waking up and a wake up routine"


class TestClassify(unittest.TestCase):
    def test_rules_identify_the_family_by_what_the_prompt_asks(self):
        T = []
        self.assertEqual(P.classify(REFLECT, T)["family"], "reflection")
        self.assertEqual(P.classify(ACTION, T)["family"], "planning")
        self.assertEqual(P.classify(CONVO, T)["family"], "dialogue")
        self.assertEqual(P.classify(SCORE, T)["family"], "importance")          # memory text containing "wake up" must not turn a scoring prompt into planning
        self.assertIsNone(P.classify("hello there", T))

    def test_false_match_rates_and_the_sample_are_deterministic(self):
        rows = [{"purpose": "dialogue", "prompt": ACTION}] * 30 + [{"purpose": "dialogue", "prompt": REFLECT}] * 10 + [{"purpose": "dialogue", "prompt": CONVO}] * 60 + [{"purpose": "dialogue", "prompt": "zzz"}] * 5
        a = P.audit_arm(rows, [], tags=("dialogue",))["dialogue"]
        self.assertEqual((a["true_family"], a["false_match"], a["unclassified"]), (60, 40, 5))
        self.assertEqual(a["false_match_rate_of_classified"], 0.4)
        self.assertEqual(a["false_matches_belong_to"], {"planning": 30, "reflection": 10})
        big = [{"purpose": "planning", "prompt": ACTION if i % 4 else CONVO} for i in range(900)]
        s1, s2 = P.audit_arm(big, [], tags=("planning",)), P.audit_arm(big, [], tags=("planning",))
        self.assertEqual(s1, s2)
        self.assertEqual((s1["planning"]["audited"], s1["planning"]["sampled"]), (200, True))

    def test_audit_reads_the_delivered_log_and_counts_the_reflection_family_on_the_whole_log(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t) / "p7_staged"
            d.mkdir()
            rows = [{"purpose": "dialogue", "prompt": REFLECT}, {"purpose": "reflection", "prompt": "Action: checking her reflection. Objects available: {sink}"}, {"purpose": "planning", "prompt": ACTION}]
            (d / "raw_replies.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
            res = P.audit(Path(t), arms=("staged",), templates=[])
            self.assertEqual(res["arms"]["staged"]["log_rows"], 3)
            self.assertEqual(res["arms"]["staged"]["reflection_family_prompts_whole_log"]["by_tag_and_template"], {"dialogue": {"generate_focal_pt": 1}})
            self.assertEqual(res["arms"]["staged"]["tags"]["reflection"]["false_match"], 1)             # the word "reflection" inside an action prompt


if __name__ == "__main__":
    unittest.main()
