"""Offline tests for follow-up A4 (T calibration): the event file, the pre-registered rule and the priors-overlap check. No live call."""
import devmem.testing_env  # noqa: F401
import json
import unittest

from devmem.memory import p6_t_calibration as t


class TestCalibrationSet(unittest.TestCase):
    def setUp(self):
        self.spec = json.loads(t.EVENTS.read_text(encoding="utf-8"))

    def test_about_24_authored_events_graded_four_ways_with_unique_ids_and_no_scores(self):
        ev = self.spec["events"]
        self.assertEqual(len(ev), 24)
        self.assertEqual({l: sum(1 for e in ev if e["label"] == l) for l in self.spec["labels"]},
                         {"mundane": 7, "moderate": 6, "significant": 5, "life_changing": 6})
        self.assertEqual(len({e["id"] for e in ev}), 24)
        self.assertEqual(len({e["text"] for e in ev}), 24)
        self.assertTrue(all("score" not in e for e in ev), "labels are written before any scoring")

    def test_no_event_shares_a_content_word_with_the_persona_priors(self):
        self.assertEqual(t.check_overlap(self.spec["events"], t.priors_text(self.spec["agent"])), {})

    def test_overlap_check_reports_a_shared_word(self):
        self.assertEqual(t.check_overlap([{"id": "X", "text": "A quiet company dinner"}], "Actively seeks out company"), {"X": ["company"]})


class TestRule(unittest.TestCase):
    def test_smallest_qualifying_integer(self):
        d = t.decide({"life_changing": [9, 10, 10], "mundane": [1, 2], "moderate": [4, 7]})
        self.assertEqual((d["T"], d["qualifying_integers"]), (8, [8, 9]))
        d = t.decide({"life_changing": [9, 10, 10], "mundane": [1], "moderate": [8]})
        self.assertEqual((d["T"], d["qualifying_integers"]), (9, [9]))

    def test_every_life_changing_event_must_reach_it_and_no_mundane_or_moderate_may(self):
        self.assertIsNone(t.decide({"life_changing": [8, 10], "mundane": [1], "moderate": [8]})["T"])   # a moderate event reaches 8
        d = t.decide({"life_changing": [9, 10], "mundane": [1], "moderate": [9]})                       # a moderate event reaches 9
        self.assertIsNone(d["T"])
        self.assertEqual(d["status"], "no integer in 8 to 10 qualifies")
        self.assertEqual(t.decide({"life_changing": [10, 10], "mundane": [2], "moderate": [9]})["T"], 10)
        self.assertIsNone(t.decide({"life_changing": [9, 10], "mundane": [1], "moderate": [10]})["T"])

    def test_significant_events_do_not_take_part_in_the_rule(self):
        d = t.decide({"life_changing": [9], "mundane": [1], "moderate": [3], "significant": [10, 10]})
        self.assertEqual(d["T"], 8)

    def test_no_life_changing_events_never_qualifies(self):
        self.assertIsNone(t.decide({"mundane": [1], "moderate": [2]})["T"])


if __name__ == "__main__":
    unittest.main()
