"""Test of the offline fail-safe counter on synthetic delivered-reply rows."""
import unittest

from devmem.eval import failsafe_count as F
from devmem.eval.phase9 import purpose_audit as PA

TALK = "Task -- given context, determine whether the subject will initiate a conversation with another. Answer in yes or no:"
ARENA = "Jane is going to a house that has the following areas: {kitchen}\nx (MUST pick one of {cafe}):\nAnswer: {"


def _rows(prompt, replies, agent="A"):
    return [{"prompt": prompt, "agent_id": agent, "delivered": r} for r in replies]


class TestFailsafeCount(unittest.TestCase):
    def test_identical_attempts_up_to_the_limit_are_a_certain_fail_safe(self):
        rows = (_rows(TALK, ["long reply"] * 5)                                        # five identical rejected replies: fail-safe 'yes'
                + _rows(TALK, ["no"], "C")                                                # one attempt, accepted
                + _rows(ARENA, ["cafe} a, b"] * 5, "B")                                # arena fail-safe
                + _rows(ARENA, ["x", "y", "z", "w", "cafe}"], "D"))                    # differing attempts, last one valid: ambiguous without the validator
        res = F.count(rows, lambda p: PA.classify(p, []))
        talk, arena = res["by_function"]["decide_to_talk"], res["by_function"]["action_location_object"]
        self.assertEqual((talk["calls"], talk["certain"], talk["ambiguous"]), (2, 1, 0))
        self.assertEqual((arena["calls"], arena["certain"], arena["ambiguous"]), (2, 1, 1))
        self.assertEqual(res["certain_fail_safe_calls"], 2)
        self.assertEqual(res["upstream_function_calls"], 4)


if __name__ == "__main__":
    unittest.main()
