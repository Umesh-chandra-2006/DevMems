"""Tests of the rule-based purpose classes and of the ledger/log pairing on synthetic rows (no run folder, no call)."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from devmem.eval.phase9 import purpose_classes as PC

REFLECT = "Given only the information above, what are 3 most salient high-level questions we can answer about the subjects grounded in the statements? 1)"
INSIGHT = "What 5 high-level insights can you infer from the above statements? (example format: insight (because of 1, 5, 3))"
MEMO = "Write down if there is anything from the conversation that Maria Lopez might have found interesting, from Maria Lopez's perspective, in a full sentence."
PLANTHOUGHT = "Write down if there is anything from the conversation that Maria Lopez need to remember for her planning, from Maria Lopez's perspective, in a full sentence."
CONVO = "Given the above, what should Maria Lopez say to Klaus Mueller next in the conversation? And did it end the conversation?"
OBJECT = "Current activity: sleep in bed\nObjects available: {bed, easel}\nPick ONE most relevant object from the objects available: bed"
EMOJI = "Convert an action description to an emoji (important: use two or less emojis). Action description: open"
TRIPLE = "Task: Turn the input into (subject, predicate, object).\nInput: Sam Johnson is eating breakfast."
PLAN = "Here is Isabella Rodriguez's plan today in broad-strokes (with the time of the day.). Follow this format"
SCORE = "On the scale of 1 to 10, where 1 is purely mundane and 10 is extremely poignant, rate the likely poignancy of: waking up and a wake up routine"
FALSE_REFLECTION = "Isabella Rodriguez is waking up and getting ready. For checking her reflection and heading out the door, Isabella Rodriguez should go to the following area: {kitchen, bathroom}"


class TestClasses(unittest.TestCase):
    def test_each_prompt_goes_to_its_class_by_what_it_asks(self):
        want = {REFLECT: "periodic_reflection", INSIGHT: "periodic_reflection", MEMO: "post_conversation_memo", PLANTHOUGHT: "post_conversation_memo", CONVO: "dialogue",
                OBJECT: "action_object_description", EMOJI: "action_object_description", TRIPLE: "action_object_description", PLAN: "planning", SCORE: "importance_scoring"}
        for prompt, cls in want.items():
            self.assertEqual(PC.classify_prompt(prompt, "dialogue", [])["class"], cls, prompt[:40])
        self.assertEqual(PC.classify_prompt("zzz", "planning", [])["class"], "other")
        self.assertEqual(PC.classify_prompt("anything", "consolidation_summary", [])["class"], "consolidation")      # set by the code, not by the keyword rule
        self.assertEqual(PC.classify_prompt("anything", "identity_trait", [])["class"], "identity")
        # the word "reflection" inside an action prompt does not make it reflection (the keyword tag did)
        self.assertNotEqual(PC.classify_prompt(FALSE_REFLECTION, "reflection", [])["class"], "periodic_reflection")

    def test_pairing_attaches_times_and_refuses_a_disagreeing_log(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            db = t / "l.db"
            c = sqlite3.connect(db)
            c.execute("CREATE TABLE llm_call_log (purpose TEXT, agent_id TEXT, condition TEXT, created_at TEXT)")
            seq = [("dialogue", "A", REFLECT), ("planning", "A", PLAN), ("importance_scoring", "B", SCORE)]
            c.executemany("INSERT INTO llm_call_log VALUES (?,?,?,?)", [(p, a, "staged", f"2026-10-08 10:00:0{i}") for i, (p, a, _) in enumerate(seq)])
            c.commit()
            c.close()
            d = t / "p7_staged"
            d.mkdir()
            (d / "raw_replies.jsonl").write_text("\n".join(json.dumps({"purpose": p, "agent_id": a, "prompt": pr}) for p, a, pr in seq) + "\n")
            res = PC.aligned("staged", db, t, templates=[])
            self.assertEqual((res["paired"], res["positions_disagreeing"]), (3, 0))
            self.assertEqual([r["class"] for r in res["rows"]], ["periodic_reflection", "planning", "importance_scoring"])
            self.assertEqual(res["rows"][1]["created_at"], "2026-10-08 10:00:01")
            self.assertEqual(PC.keyword_vs_class(res["rows"])["dialogue"], {"periodic_reflection": 1})           # a real reflection prompt under the dialogue keyword tag
            (d / "raw_replies.jsonl").write_text("\n".join(json.dumps({"purpose": "planning", "agent_id": "Z", "prompt": "x"}) for _ in seq) + "\n")
            with self.assertRaises(RuntimeError):
                PC.aligned("staged", db, t, templates=[])


if __name__ == "__main__":
    unittest.main()
