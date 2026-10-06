"""
Night-key fix tests (Phase 6 follow-up A3, PM-approved rule 4.1 and final-sweep rule 4.3 (i); docs/phase6_night_key_checkpoint.md).
Offline, synthetic scripted ticks on the REAL Stage 3 sleep hook, a real upstream Persona and AssociativeMemory and real SQLite.

  * TestFixedBehavior: the Step D case (a sleep that began at 06:00 and is still current at noon) no longer writes the evening
    night's marker, so the real evening sweep happens; the clean-exit sweep of an awake agent uses a separate key namespace and never
    blocks a real night; a reload mid-sleep falls back to the current action's start time.
  * TestPhase7CompressedDay: the compressed schedule (run starts 00:00, awake 06:00 to 14:00, asleep 14:00 to 06:00, three days) is keyed
    exactly as before the fix.
  * TestResidualAndTable: what the rule does NOT change (a nap that starts after noon is excluded by schedule constraint (b)) and a
    brute-force table of where the old key (current tick) and the new key (block start) differ.
  * TestManualRepairOnACopy: the documented repair of the stale marker, on a temporary copy of the Step D database.
"""
import devmem.testing_env  # noqa: F401
import datetime
import itertools
import os
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


class NightKeyBase(tc.StageThreeBase):
    def setUp(self):
        super().setUp()
        self.persona.__dict__.pop("_devmem_sleep_block_start", None)  # the persona object is shared by the tests of the class

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
        d = (D1 + datetime.timedelta(days=day - 1)).date()
        a = self.add(f"{tag} one", tc.vec(1, 0), hour, 0, day=d)
        b = self.add(f"{tag} two", tc.vec(0.99, 0.1), hour, 30, day=d)
        return a, b

    def final_sweep(self, when, sleeping):
        self.persona.scratch.curr_time = when
        self.persona.scratch.act_description = "sleeping" if sleeping else "working"
        with mock.patch.object(cons, "call_llm", self.llm()), \
                mock.patch.object(cons.episodic, "score_importance_persona_conditioned", return_value=6):
            return cons.force_sweep(self.persona, db_path=self.db, config=self.cfg, ledger_db=self.ledger,
                                    embed_fn=lambda t: tc.vec(0, 0, 1))


class TestFixedBehavior(NightKeyBase):
    def test_noon_tick_inside_a_sleep_that_began_at_0600_stays_in_night_0_and_the_evening_sweep_happens(self):
        # the Step D situation: run starts 06:00, the agent's `sleeping 420` entry starts at 06:00 and lasts until 13:00
        r0 = self.tick(at(1, 6), True, act_start=at(1, 6))
        self.assertEqual(r0["night"], 0)
        self.assertIsNone(self.tick(at(1, 12), True, act_start=at(1, 6)), "noon belongs to the block that began at 06:00 (night 0, done)")
        self.assertEqual([m[0] for m in self.markers()], [0], "no night 1 marker was written at noon")
        self.assertIsNone(self.tick(at(1, 13), False))           # wakes at 13:00 (block cleared), acts, entries are logged
        self.add_pair(1, 15, "afternoon")
        r2 = self.tick(at(1, 22), True, act_start=at(1, 22))     # the real night 1
        self.assertEqual((r2["night"], r2["entries_considered"], r2["summaries_written"]), (1, 2, 1))
        self.assertEqual([m[0] for m in self.markers()], [0, 1])
        self.assertEqual(self.flagged(), 2, "the day's entries were consolidated that evening, not one night late")

    def test_a_reload_mid_sleep_falls_back_to_the_current_action_start(self):
        self.tick(at(1, 6), True, act_start=at(1, 6))
        self.persona.__dict__.pop("_devmem_sleep_block_start", None)       # in-memory block start lost, as after a reload
        self.persona.__dict__.pop("_devmem_swept_nights", None)
        r = self.tick(at(1, 12), True, act_start=at(1, 6))
        self.assertEqual(r, {"skipped": "already swept", "night": 0}, "keyed night 0 through the action start; the SQLite marker stops it")
        self.assertEqual([m[0] for m in self.markers()], [0])

    def test_a_stale_remembered_block_start_is_discarded(self):
        self.tick(at(1, 22), True, act_start=at(1, 22))                    # block remembered at day 1 22:00
        self.persona.scratch.act_start_time = at(2, 22)                    # the new sleeping action starts now
        self.assertEqual(cons.sleep_block_night(self.persona, at(2, 22), self.cfg), 2, "a day old: stale, the current action starts a new block")
        self.persona.__dict__["_devmem_sleep_block_start"] = at(5, 22)
        self.assertEqual(cons.sleep_block_night(self.persona, at(1, 22), self.cfg), 1, "in the future: stale")

    def test_without_an_action_start_the_current_tick_is_the_fallback(self):
        r = self.tick(at(1, 22), True, act_start=None)
        self.assertEqual(r["night"], 1)

    def test_awake_final_sweep_uses_a_separate_namespace_and_never_blocks_the_real_night(self):
        self.add_pair(1, 9, "morning")
        res = self.final_sweep(at(1, 13, 45), sleeping=False)          # D7 clean exit in the afternoon, agent awake
        self.assertEqual((res["night"], res["final_sweep_of_awake_agent"], res["summaries_written"]), (-1, True, 1))
        self.assertEqual([m[0] for m in self.markers()], [-1])
        self.add_pair(1, 18, "evening")
        r = self.tick(at(1, 22), True, act_start=at(1, 22))
        self.assertEqual((r["night"], r["summaries_written"] + r["summaries_reinforced"]), (1, 1),
                         "the real night 1 sweep still happens and consolidates the evening pair")
        self.assertEqual(sorted(m[0] for m in self.markers()), [-1, 1])
        self.assertEqual(self.flagged(), 4)

    def test_sleeping_final_sweep_uses_the_sleep_block_key(self):
        self.add_pair(1, 9, "morning")
        self.persona.scratch.act_start_time = at(1, 6)
        res = self.final_sweep(at(1, 12), sleeping=True)               # asleep across noon
        self.assertEqual((res["night"], res["final_sweep_of_awake_agent"]), (0, False))

    def test_final_sweep_of_an_awake_agent_does_not_run_stage_4(self):
        with mock.patch.dict(os.environ, {"STAGE4_ENABLED": "on"}):
            self.add_pair(1, 9, "morning")
            res = self.final_sweep(at(1, 13, 45), sleeping=False)
            self.assertEqual(res["identity"]["skipped"], "final sweep of an awake agent: no identity step")
            conn = sqlite3.connect(str(self.db))
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM consolidation_events").fetchone()[0], 0, "no Stage 4 record for a final sweep")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM identity_sweeps").fetchone()[0], 0)
            conn.close()

    def test_the_identity_step_uses_the_same_block_key_as_stage_3(self):
        with mock.patch.dict(os.environ, {"STAGE4_ENABLED": "on"}):
            self.add_pair(1, 9, "morning")
            r = self.tick(at(1, 6), True, act_start=at(1, 6))
            self.assertEqual((r["night"], r["identity"]["night"]), (0, 0))
            self.tick(at(1, 12), True, act_start=at(1, 6))
            conn = sqlite3.connect(str(self.db))
            self.assertEqual([x[0] for x in conn.execute("SELECT night FROM identity_sweeps")], [0])
            conn.close()


class TestPhase7CompressedDay(NightKeyBase):
    """Run starts 00:00; awake 06:00 to 14:00; asleep 14:00 to 06:00; three days. Hourly ticks."""

    def run_days(self, collect_keys=False):
        sweeps, keys = [], []
        for day in (1, 2, 3):
            for hour in range(24):
                sleeping = hour < 6 or hour >= 14
                if hour >= 14:
                    start = at(day, 14)
                elif hour < 6:
                    start = at(day - 1, 14) if day > 1 else at(1, 0)
                else:
                    start = None
                if hour == 8:
                    self.add_pair(day, 8, f"day{day}")
                res = self.tick(at(day, hour), sleeping, act_start=start)
                if sleeping and collect_keys:
                    keys.append((day, hour, cons.sleep_block_night(self.persona, at(day, hour), self.cfg)))
                if res is not None and "skipped" not in res:
                    sweeps.append((day, hour, res["night"], res["entries_considered"], res["summaries_written"] + res["summaries_reinforced"]))
        return sweeps, keys

    def test_the_fixed_rule_keys_the_compressed_schedule_exactly_as_before(self):
        sweeps, keys = self.run_days(collect_keys=True)
        self.assertEqual(sweeps, [(1, 0, 0, 0, 0), (1, 14, 1, 2, 1), (2, 14, 2, 2, 1), (3, 14, 3, 2, 1)])
        self.assertEqual([m[0] for m in self.markers()], [0, 1, 2, 3])
        self.assertEqual(self.flagged(), 6)
        self.assertTrue(all(m[2] == "done" for m in self.markers()))
        for day, hour, key in keys:
            self.assertEqual(key, cons.night_id(at(day, hour), BOUNDARY), (day, hour))

    def test_stage_4_gets_its_three_distinct_nights_on_the_compressed_schedule(self):
        with mock.patch.dict(os.environ, {"STAGE4_ENABLED": "on"}):
            from devmem.memory import identity
            identity.init_identity_db(self.db)
            for day in (1, 2, 3):
                for hour in (8, 14):
                    if hour == 8:
                        self.add_pair(day, 8, f"day{day}")
                    sleeping = hour >= 14
                    with mock.patch.object(identity, "call_llm", lambda *a, **k: "Isabella Rodriguez keeps her cafe running with steady work."):
                        self.tick(at(day, hour), sleeping, act_start=at(day, 14) if sleeping else None)
            conn = sqlite3.connect(str(self.db))
            self.assertEqual([r[0] for r in conn.execute("SELECT night FROM identity_sweeps ORDER BY night")], [1, 2, 3])
            conn.close()


class TestResidualAndTable(NightKeyBase):
    def test_a_nap_that_starts_after_noon_is_not_changed_by_the_rule_and_schedule_constraint_b_excludes_it(self):
        self.add_pair(1, 9, "morning")
        r = self.tick(at(1, 13), True, act_start=at(1, 13))      # a one-hour nap: a new block that starts after the boundary
        self.assertEqual(r["night"], 1)
        self.add_pair(1, 18, "evening")
        self.tick(at(1, 14), False)
        self.assertIsNone(self.tick(at(1, 22), True, act_start=at(1, 22)), "documented residual: the night is already claimed")

    def test_the_old_and_new_keys_differ_exactly_when_the_sleep_block_spans_a_boundary_hour(self):
        diffs = same = 0
        for sh, ch in itertools.product(range(24), range(24)):
            for add_days in (0, 1):
                start, curr = at(1, sh), at(1 + add_days, ch)
                if curr < start or curr - start > datetime.timedelta(hours=16):
                    continue
                differ = cons.night_id(curr, BOUNDARY) != cons.night_id(start, BOUNDARY)
                spans_noon = any(start < n <= curr for n in (at(1, BOUNDARY), at(2, BOUNDARY)))
                self.assertEqual(differ, spans_noon, (sh, add_days, ch))
                diffs += differ
                same += not differ
        self.assertGreater(diffs, 0)
        self.assertGreater(same, 0)
        print("pairs where the old and new keys differ / agree:", diffs, same)


class TestManualRepairOnACopy(unittest.TestCase):
    """The documented repair (unused: the Step D resume is no longer planned), run on a temporary COPY of the real Step D mirror database."""

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
            self.assertEqual(repair(copy, self.ART / "consolidation_log.jsonl", apply=True)["removed"], [])
            orig = sqlite3.connect(str(self.ART / "memory.db")).execute("SELECT COUNT(*) FROM consolidation_sweeps").fetchone()[0]
            self.assertEqual(orig, len(before))
            self.assertEqual(len(done["removed"]), 2)


if __name__ == "__main__":
    unittest.main()
