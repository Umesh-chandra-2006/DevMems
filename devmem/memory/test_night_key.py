"""
Night-key design checkpoint (Phase 6 follow-up A3). Offline, synthetic schedules, NO product code changed.

The tests drive the REAL Stage 3 sleep hook (`maybe_sweep_on_sleep`) on a real upstream Persona and AssociativeMemory with scripted hourly ticks:
  1. reproduce the defect: an agent that is "sleeping" at noon (Step D: the run starts at 06:00 and upstream starts a `sleeping 420` entry
     for its full duration) gets the EVENING night's marker at 12:00, and the real evening sleep is then skipped as "already swept";
  2. cover the Phase 7 compressed-day schedule (run starts 00:00, awake 06:00 to 14:00, asleep 14:00 to 06:00, three days): the current
     key behaves correctly there;
  3. a PROTOTYPE of the proposed fix (key the night by the START of the current sleep block, not by the current tick), implemented
     inside this test file only, gives the same keys everywhere the current rule is correct and fixes case 1;
  4. a brute-force table of where the current rule and the prototype differ.
"""
import devmem.testing_env  # noqa: F401
import datetime
import itertools
import json
import sqlite3
import unittest
from pathlib import Path
from unittest import mock

from devmem.memory import consolidation as cons
from devmem.memory import test_consolidation as tc

D1 = datetime.datetime(2023, 2, 13)
BOUNDARY = 12


def at(day, hour, minute=0):
    return D1 + datetime.timedelta(days=day - 1, hours=hour, minutes=minute)


class SleepBlockKey:
    """PROTOTYPE of the proposed rule (not product code): the night of a sleep block is night_id(start of the block). The block start
    is remembered across ticks; after a reload it falls back to the current action's start time."""

    def __init__(self, boundary=BOUNDARY):
        self.boundary, self.block_start = boundary, None

    def key(self, sleeping, act_start, curr):
        if not sleeping:
            self.block_start = None
            return None
        if self.block_start is None:
            self.block_start = act_start or curr
        return cons.night_id(self.block_start, self.boundary)


class NightKeyBase(tc.StageThreeBase):
    def tick(self, when, sleeping, act_start=None):
        self.persona.scratch.curr_time = when
        self.persona.scratch.act_description = "sleeping" if sleeping else "working"
        self.persona.scratch.act_start_time = act_start
        with mock.patch.object(cons, "call_llm", self.llm()), \
                mock.patch.object(cons.episodic, "score_importance_persona_conditioned", return_value=6):
            return cons.maybe_sweep_on_sleep(self.persona, db_path=self.db, config=self.cfg, ledger_db=self.ledger,
                                             embed_fn=lambda t: tc.vec(0, 0, 1))

    def markers(self):
        return [(m["night"], m["sweep_time"], m["status"]) for m in self.rows("consolidation_sweeps")]

    def flagged(self):
        return sum(1 for r in self.rows() if r["consolidated"])

    def add_pair(self, day, hour, tag):
        a = self.add(f"{tag} one", tc.vec(1, 0), hour, 0, day=(D1 + datetime.timedelta(days=day - 1)).date())
        b = self.add(f"{tag} two", tc.vec(0.99, 0.1), hour, 30, day=(D1 + datetime.timedelta(days=day - 1)).date())
        return a, b


class TestDefectReproduced(NightKeyBase):
    def test_noon_sleep_writes_the_evening_marker_and_the_evening_sweep_is_skipped(self):
        # Step D situation: run starts 06:00, the agent's `sleeping 420` entry starts at 06:00 and lasts until 13:00
        r0 = self.tick(at(1, 6), True, act_start=at(1, 6))
        self.assertEqual(r0["night"], 0)                      # 06:00 is before the boundary: night 0, correct
        r1 = self.tick(at(1, 12), True, act_start=at(1, 6))   # still the same sleep action at noon
        self.assertEqual(r1["night"], 1, "noon is keyed as the EVENING night of day 1")
        self.assertEqual(r1["entries_considered"], 0)
        self.assertEqual([m[0] for m in self.markers()], [0, 1])
        self.assertEqual(self.markers()[1][2], "done")
        # the agent wakes at 13:00, acts all afternoon (entries are logged), and really goes to sleep at 22:00
        self.add_pair(1, 15, "afternoon")
        r2 = self.tick(at(1, 22), True, act_start=at(1, 22))
        self.assertIsNone(r2, "the real night 1 is skipped (in-memory guard: the hook returns nothing)")
        self.persona.__dict__.pop("_devmem_swept_nights", None)  # after a reload the SQLite marker decides, with the same outcome
        self.assertEqual(self.tick(at(1, 22), True, act_start=at(1, 22)), {"skipped": "already swept", "night": 1})
        self.assertEqual(self.flagged(), 0, "the day's entries were not consolidated")
        # they are only picked up one night late, when night 2 comes
        r3 = self.tick(at(2, 22), True, act_start=at(2, 22))
        self.assertEqual((r3["night"], r3["summaries_written"]), (2, 1))

    def test_the_clean_exit_final_sweep_of_an_awake_agent_in_the_afternoon_has_the_same_effect(self):
        # D7 final sweep (HeadlessRunner._final_sweep -> force_sweep) at a clean exit at 13:45: the agent is awake
        self.add_pair(1, 9, "morning")
        self.persona.scratch.curr_time = at(1, 13, 45)
        self.persona.scratch.act_description = "working"
        with mock.patch.object(cons, "call_llm", self.llm()),                 mock.patch.object(cons.episodic, "score_importance_persona_conditioned", return_value=6):
            res = cons.force_sweep(self.persona, db_path=self.db, config=self.cfg, ledger_db=self.ledger,
                                   embed_fn=lambda t: tc.vec(0, 0, 1))
        self.assertEqual(res["night"], 1, "an afternoon exit writes the evening night marker")
        self.add_pair(1, 18, "evening")
        self.assertEqual(self.tick(at(1, 22), True, act_start=at(1, 22)), {"skipped": "already swept", "night": 1},
                         "the real night 1 sweep is skipped by the SQLite marker")

    def test_a_nap_after_noon_has_the_same_effect(self):
        self.add_pair(1, 9, "morning")
        r = self.tick(at(1, 13), True, act_start=at(1, 13))   # a one-hour nap
        self.assertEqual((r["night"], r["summaries_written"]), (1, 1))
        self.add_pair(1, 18, "evening")
        self.assertIsNone(self.tick(at(1, 22), True, act_start=at(1, 22)))
        self.assertEqual(self.flagged(), 2, "only the entries before the nap were consolidated; the evening pair was not")


class TestPhase7CompressedDay(NightKeyBase):
    """Run starts 00:00; awake 06:00 to 14:00; asleep 14:00 to 06:00; three days. Hourly ticks."""

    def run_days(self, keyer=None):
        keys = []
        for day in (1, 2, 3):
            for hour in range(24):
                sleeping = hour < 6 or hour >= 14
                # the sleep block that is current: it began at 14:00 of the previous day (hour < 6) or today (hour >= 14);
                # on day 1 at 00:00 the run starts asleep and the entry starts at 00:00
                if hour >= 14:
                    start = at(day, 14)
                elif hour < 6:
                    start = at(day - 1, 14) if day > 1 else at(1, 0)
                else:
                    start = None
                if hour == 8:
                    self.add_pair(day, 8, f"day{day}")
                res = self.tick(at(day, hour), sleeping, act_start=start)
                if keyer is not None:
                    keys.append((day, hour, keyer.key(sleeping, start, at(day, hour))))
                if res is not None and "skipped" not in res:
                    keys.append(("sweep", day, hour, res["night"], res["entries_considered"],
                              res["summaries_written"] + res["summaries_reinforced"]))
        return keys

    def test_current_rule_is_correct_on_the_compressed_schedule(self):
        out = self.run_days()
        sweeps = [k for k in out if k[0] == "sweep"]
        # night 0 at the start (nothing to consolidate), then one real sweep at 14:00 on each of the three days, with that day's pair
        self.assertEqual([(s[1], s[2], s[3], s[4], s[5]) for s in sweeps],
                         [(1, 0, 0, 0, 0), (1, 14, 1, 2, 1), (2, 14, 2, 2, 1), (3, 14, 3, 2, 1)])
        self.assertEqual([m[0] for m in self.markers()], [0, 1, 2, 3])
        self.assertEqual(self.flagged(), 6)
        # the after-midnight ticks of days 2 and 3 (hour < 6) hit the existing night markers and do nothing
        self.assertTrue(all(m[2] == "done" for m in self.markers()))

    def test_prototype_gives_identical_keys_on_the_compressed_schedule(self):
        keyer = SleepBlockKey()
        keys = [k for k in self.run_days(keyer) if k[0] != "sweep"]
        for day, hour, key in keys:
            sleeping = hour < 6 or hour >= 14
            if not sleeping:
                self.assertIsNone(key)
                continue
            current_rule = cons.night_id(at(day, hour), BOUNDARY)
            self.assertEqual(key, current_rule, (day, hour))


class TestProposedRule(unittest.TestCase):
    def test_prototype_fixes_the_step_d_case(self):
        k = SleepBlockKey()
        self.assertEqual(k.key(True, at(1, 6), at(1, 6)), 0)
        self.assertEqual(k.key(True, at(1, 6), at(1, 12)), 0, "noon tick stays in night 0: no evening marker")
        self.assertIsNone(k.key(False, None, at(1, 13)))
        self.assertEqual(k.key(True, at(1, 22), at(1, 22)), 1)
        self.assertEqual(k.key(True, at(1, 22), at(2, 3)), 1)

    def test_after_a_reload_mid_sleep_it_falls_back_to_the_current_action_start(self):
        fresh = SleepBlockKey()          # in-memory block start lost
        self.assertEqual(fresh.key(True, at(1, 6), at(1, 12)), 0)

    def test_the_two_rules_differ_exactly_when_the_sleep_block_spans_a_boundary_hour(self):
        """Brute force over blocks of up to 16 hours: the current rule (key by the current tick) and the prototype (key by the block
        start) differ if and only if a 12:00 instant lies in (start, current]. A normal night (start 12:00 to 23:59, current until
        11:59 next day) never contains one; a sleep-in past noon or a nap after noon always does."""
        diffs = same = 0
        for sh, ch in itertools.product(range(24), range(24)):
            for add_days in (0, 1):
                start, curr = at(1, sh), at(1 + add_days, ch)
                if curr < start or curr - start > datetime.timedelta(hours=16):
                    continue
                differ = cons.night_id(curr, BOUNDARY) != cons.night_id(start, BOUNDARY)
                noons = [at(d, BOUNDARY) for d in (1, 2)]
                spans_noon = any(start < n <= curr for n in noons)
                self.assertEqual(differ, spans_noon, (sh, add_days, ch))
                diffs += differ
                same += not differ
        self.assertGreater(diffs, 0)
        self.assertGreater(same, 0)
        print("pairs where the rules differ / agree:", diffs, same)


class TestManualRepairOnACopy(unittest.TestCase):
    """The documented repair, run on a temporary COPY of the real Step D mirror database (offline-captured artifact)."""

    ART = Path(__file__).resolve().parent.parent.parent / "docs" / "phase6_stepd_artifacts"

    def test_dry_run_apply_and_idempotence_on_a_copy_of_the_step_d_database(self):
        import shutil
        import tempfile
        from devmem.memory.p6_repair_night_marker import repair
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "memory.db"
            shutil.copy(self.ART / "memory.db", copy)
            before = sqlite3.connect(str(copy)).execute("SELECT agent_id, night, sweep_time FROM consolidation_sweeps ORDER BY 1, 2").fetchall()
            self.assertIn(("Maria Lopez", 1, "2023-02-13 12:00:00"), before)
            self.assertIn(("Klaus Mueller", 1, "2023-02-13 12:00:00"), before)
            dry = repair(copy, self.ART / "consolidation_log.jsonl", apply=False)
            self.assertEqual({(e["agent"], e["night"]) for e in dry["removed"]}, {("Maria Lopez", 1), ("Klaus Mueller", 1)})
            self.assertEqual(sqlite3.connect(str(copy)).execute("SELECT COUNT(*) FROM consolidation_sweeps").fetchone()[0], len(before))
            done = repair(copy, self.ART / "consolidation_log.jsonl", apply=True)
            after = sqlite3.connect(str(copy)).execute("SELECT agent_id, night, sweep_time FROM consolidation_sweeps ORDER BY 1, 2").fetchall()
            self.assertEqual(sorted(set(before) - set(after)), [("Klaus Mueller", 1, "2023-02-13 12:00:00"), ("Maria Lopez", 1, "2023-02-13 12:00:00")])
            self.assertTrue(all(n == 0 for _, n, _ in after), "only the legitimate night 0 rows (06:00, before the boundary) remain")
            self.assertTrue((copy.parent / "memory.db.repair.json").exists())
            again = repair(copy, self.ART / "consolidation_log.jsonl", apply=True)
            self.assertEqual(again["removed"], [])
            # the original artifact is untouched
            orig = sqlite3.connect(str(self.ART / "memory.db")).execute("SELECT COUNT(*) FROM consolidation_sweeps").fetchone()[0]
            self.assertEqual(orig, len(before))
            self.assertEqual(len(done["removed"]), 2)


if __name__ == "__main__":
    unittest.main()
