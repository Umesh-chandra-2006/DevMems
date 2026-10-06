"""
Stage 4 tests (Phase 6, Stop 2). Offline: vectors are `synthetic` (unit vectors with chosen cosines), the LLM is replaced
only where stated (summaries in consolidation, traits in identity, the scoring call in the episodic scorer), and the rest is
real: upstream Persona / AssociativeMemory, real SQLite, real save/reload, the real Stage 3 sweep and the real sleep hook.
The scripted fixture is devmem/memory/fixtures/scripted_four_nights_isabella.json (label: scripted).
"""
import devmem.testing_env  # noqa: F401  (offline by default)
import datetime
import json
import math
import os
import sqlite3
import unittest
from pathlib import Path
from unittest import mock

from devmem.memory import consolidation as cons
from devmem.memory import episodic, identity
from devmem.memory import test_consolidation as tc
from devmem.memory.test_consolidation import AGENT
from persona.memory_structures.associative_memory import AssociativeMemory  # noqa: E402  (path set by test_consolidation)

FIXTURE = json.loads((Path(__file__).resolve().parent / "fixtures" / "scripted_four_nights_isabella.json").read_text(encoding="utf-8"))
GOLDEN = json.loads((Path(__file__).resolve().parent / "fixtures" / "phase5_staged_prompts.json").read_text(encoding="utf-8"))
DIM = 16
STAGE4_TABLES = ["semantic_reinforcement", "identity_traits", "identity_sweeps", "consolidation_events", "event_scoring_context"]
FIRST_PERSON = ("I ", " my ", " me ", " we ", " our ")


def unit(i):
    v = [0.0] * DIM
    v[i] = 1.0
    return v


def at_cos(base, j, c):
    """A unit vector with cosine c to the unit vector `base`, tilted toward axis j (j must be orthogonal to base)."""
    s = math.sqrt(max(0.0, 1 - c * c))
    v = [c * x for x in base]
    v[j] += s
    return v


def norm_text(t):
    return " ".join(t.split())


class IdentityBase(tc.StageThreeBase):
    """The Stage 3 test base plus Stage 4 switched on, a fixture driver and stubs for the LLM and the embeddings."""

    def setUp(self):
        super().setUp()
        env = mock.patch.dict(os.environ, {"STAGE4_ENABLED": "on"})
        env.start()
        self.addCleanup(env.stop)
        self.icfg = identity.load_config()
        self.icfg.update(stage4_enabled=True)
        p = mock.patch.object(identity, "load_config", side_effect=lambda path=None: dict(self.icfg))
        p.start()
        self.addCleanup(p.stop)
        self.cfg.update(cluster_similarity=0.9, min_cluster_size=3, importance_floor=3)
        self.thr = self.icfg["reinforce_threshold"]
        identity.init_identity_db(self.db)
        identity._PENDING.clear()
        identity._RENDERED.clear()
        self.trait_prompts = []
        self.trait_calls = 0
        self._build_vectors()

    # ---- fixture plumbing
    def _build_vectors(self):
        thr = self.thr
        self.neg_base = at_cos(unit(0), 7, thr - 0.01)
        base = {"baking": unit(0), "conflict": unit(1), "letters": unit(2), "lease": unit(3), "cake_negative": self.neg_base}
        self.event_vec, k = {}, 0
        for night in FIXTURE["nights"]:
            for ev in night["events"]:
                self.event_vec[ev["text"]] = at_cos(base[ev["theme"]], 8 + (k % 7), 0.99)
                k += 1
        th = FIXTURE["themes"]
        self.text_vec = {
            th["baking"]["summaries"]["1"]: unit(0),
            th["baking"]["summaries"]["2"]: at_cos(unit(0), 5, 0.95),
            th["baking"]["summaries"]["4"]: at_cos(unit(0), 6, 0.95),
            th["conflict"]["summaries"]["3"]: unit(1),
            th["letters"]["summaries"]["2"]: unit(2),
            th["cake_negative"]["summaries"]["3"]: self.neg_base,
            th["baking"]["trait"]: unit(0), th["conflict"]["trait"]: unit(1), th["letters"]["trait"]: unit(2),
            th["lease"]["trait"]: unit(3),
        }
        self.theme_of_event = {ev["text"]: ev["theme"] for n in FIXTURE["nights"] for ev in n["events"]}
        self.night_no = 1

    def embed(self, text):
        return list(self.text_vec.get(text, unit(15)))

    def fake_summary_llm(self):
        def fake(prompt, **kw):
            body = prompt.split("recorded today:", 1)[1]
            theme = next(self.theme_of_event[t] for t in self.theme_of_event if t in body)
            return FIXTURE["themes"][theme]["summaries"][str(self.night_no)]
        return fake

    def fake_trait_llm(self, replies=None):
        def fake(prompt, **kw):
            self.trait_calls += 1
            self.trait_prompts.append(prompt)
            if replies is not None:
                return replies.pop(0) if len(replies) > 1 else replies[0]
            for theme, d in FIXTURE["themes"].items():
                if any(s in prompt for s in d["summaries"].values()):
                    return d["trait"]
            return FIXTURE["themes"]["lease"]["trait"]  # the pivotal event prompt
        return fake

    def add_event(self, text, vec, when, imp, traits=()):
        node = self.persona.a_mem.add_event(when, None, AGENT, "is", text, text, {"scripted"}, imp, (text, vec), None)
        identity.note_scoring_context(AGENT, when, text, list(traits), True)  # what the scorer does before the call
        episodic.log_episodic_node(AGENT, node, sim_time=when, importance_score=imp, db_path=self.db)
        return f"{AGENT}:{node.node_id}"

    def add_night_events(self, n, traits=(), only=None):
        night = FIXTURE["nights"][n - 1]
        day = datetime.datetime.strptime(night["sleep"], "%Y-%m-%d %H:%M:%S").date()
        ids = {}
        for ev in night["events"]:
            if only and ev["theme"] not in only:
                continue
            hh, mm = map(int, ev["t"].split(":"))
            when = datetime.datetime.combine(day, datetime.time(hh, mm))
            ids[ev["text"]] = self.add_event(ev["text"], self.event_vec[ev["text"]], when, ev["importance"], traits)
        return ids

    def sleep_time(self, n):
        return datetime.datetime.strptime(FIXTURE["nights"][n - 1]["sleep"], "%Y-%m-%d %H:%M:%S")

    def run_night(self, n, with_identity=True, trait_llm=None):
        self.night_no = n
        when = self.sleep_time(n)
        self.persona.scratch.curr_time = when
        self.persona.scratch.act_description = "sleeping"
        with mock.patch.object(cons, "call_llm", self.fake_summary_llm()), \
                mock.patch.object(identity, "call_llm", trait_llm or self.fake_trait_llm()), \
                mock.patch.object(cons.episodic, "score_importance_persona_conditioned", return_value=6):
            if with_identity:
                return cons.maybe_sweep_on_sleep(self.persona, db_path=self.db, config=self.cfg, ledger_db=self.ledger,
                                                 embed_fn=self.embed)
            return cons.run_nightly_sweep(self.persona, when, db_path=self.db, config=self.cfg, ledger_db=self.ledger,
                                          embed_fn=self.embed)

    def play(self, upto=4, skip_identity_on=None):
        out = []
        for n in range(1, upto + 1):
            self.add_night_events(n)
            out.append(self.run_night(n, with_identity=(n != skip_identity_on)))
        return out

    def fresh(self, name):
        """A new empty memory and database (a second, independent run of the same persona object)."""
        self.persona.a_mem = AssociativeMemory(str(self.empty))
        self.db = cons.init_consolidation_db(self.tmp / name / "memory.db")
        identity.init_identity_db(self.db)
        self.persona.__dict__.pop("_devmem_swept_nights", None)
        self.persona.__dict__.pop("_devmem_sleep_block_start", None)
        identity._PENDING.clear()
        identity._RENDERED.clear()
        self.trait_prompts, self.trait_calls = [], 0

    def dump(self):
        out = {}
        for t in STAGE4_TABLES + ["consolidation_sweeps", "semantic_memory"]:
            out[t] = [{k: v for k, v in r.items() if k not in ("created_at", "last_reinforced_at")} for r in self.rows(t)]
        out["episodic_flags"] = [(r["entry_id"], r["consolidated"]) for r in self.rows()]
        return out

    def reinforcement(self, sid=None):
        rows = {r["semantic_id"]: r for r in self.rows("semantic_reinforcement")}
        return rows if sid is None else rows.get(sid)

    def sem_id_for(self, theme, night=None):
        text = FIXTURE["themes"][theme]["summaries"][str(night or min(int(k) for k in FIXTURE["themes"][theme]["summaries"]))]
        row = next(r for r in self.rows("semantic_memory") if r["summary"] == text)
        return row["entry_id"]


class TestScriptedFourNights(IdentityBase):
    def test_each_theme_follows_its_path_night_by_night(self):
        results = []
        for n in range(1, 5):
            self.add_night_events(n)
            results.append(self.run_night(n))
            traits = self.rows("identity_traits")
            if n == 1:
                self.assertEqual(traits, [])
                e1 = self.sem_id_for("baking", 1)
                self.assertEqual(json.loads(self.reinforcement(e1)["day_set_json"]), [1])
            if n == 2:
                # baking reinforced (day 2), letters born once, the pivotal event graduates (Path B) on its own night
                self.assertEqual(json.loads(self.reinforcement(e1)["day_set_json"]), [1, 2])
                self.assertEqual([t["path"] for t in traits], ["pivotal"])
                self.assertEqual(traits[0]["text"], FIXTURE["themes"]["lease"]["trait"])
            if n == 3:
                # conflict: five events on one night graduate by the same-day path; the negative adds no day to baking
                self.assertEqual(sorted(t["path"] for t in traits), ["pivotal", "same_day"])
                self.assertEqual(json.loads(self.reinforcement(e1)["day_set_json"]), [1, 2], "negative must not add night 3")
                self.assertNotIn(e1, [s for t in traits for s in json.loads(t["source_semantic_ids_json"])])
            if n == 4:
                self.assertEqual(sorted(t["path"] for t in traits), ["count_based", "pivotal", "same_day"])
                self.assertEqual(json.loads(self.reinforcement(e1)["day_set_json"]), [1, 2, 4])
        # letters (one theme, one night, three events) never graduates
        letters = self.sem_id_for("letters")
        self.assertEqual(self.reinforcement(letters)["distinct_days"], 1)
        self.assertEqual(self.reinforcement(letters)["same_day_max"], 3)
        self.assertNotIn(letters, [s for t in self.rows("identity_traits") for s in json.loads(t["source_semantic_ids_json"])])
        # conflict graduated through the same-day count
        conflict = self.sem_id_for("conflict")
        self.assertEqual(self.reinforcement(conflict)["same_day_max"], 5)
        paths = {t["trait_id"]: t["path"] for t in self.rows("identity_traits")}
        self.assertEqual(len(paths), 3)
        self.assertEqual([m["status"] for m in self.rows("identity_sweeps")], ["done"] * 4)
        # one trait call per graduating source and nothing else (3 traits, no retries)
        self.assertEqual(self.trait_calls, 3)
        self.assertTrue(all(r.get("identity", {}).get("status") == "done" for r in results))

    def test_negative_theme_decision_is_logged_with_its_cosine(self):
        self.play(3)
        log = [json.loads(l) for l in (self.db.parent / "reinforcement_decisions.jsonl").read_text().splitlines()]
        night3 = [d for d in log if d["kind"] == "reinforcement" and d["night"] == 3 and d["stage3_action"] == "reinforced"]
        self.assertEqual(len(night3), 1)
        self.assertEqual(night3[0]["decision"], "merged_by_stage3_below_stage4_threshold")
        self.assertAlmostEqual(night3[0]["cosine"], self.thr - 0.01, places=2)
        self.assertEqual(night3[0]["threshold"], self.thr)

    def test_trait_text_is_third_person_and_names_the_agent(self):
        self.play(4)
        traits = self.rows("identity_traits")
        self.assertEqual(len(traits), 3)
        for t in traits:
            self.assertTrue(cons.is_third_person(t["text"], AGENT), t["text"])
            padded = f" {t['text']} "
            self.assertFalse(any(p in padded for p in FIRST_PERSON), t["text"])
            self.assertLessEqual(len(t["text"].split()), self.icfg["trait_max_words"])
        for p in self.trait_prompts:
            self.assertIn("third person", p)

    def test_trait_prompts_use_the_proposed_templates(self):
        self.play(4)
        path_a = [p for p in self.trait_prompts if "pattern was observed" in p]
        pivotal = [p for p in self.trait_prompts if "single event was extremely important" in p]
        self.assertEqual((len(path_a), len(pivotal)), (2, 1))
        self.assertTrue(any("on 3 different days" in p for p in path_a))
        self.assertTrue(any("5 times on one day" in p for p in path_a))

    def test_stage3_events_and_scoring_context_rows(self):
        self.play(2)
        ev = self.rows("consolidation_events")
        self.assertEqual(sorted((r["night"], r["action"]) for r in ev), [(1, "created"), (2, "created"), (2, "reinforced")])
        ctx = self.rows("event_scoring_context")
        self.assertEqual({r["status"] for r in ctx}, {"ok"})
        self.assertTrue(all(json.loads(r["trait_ids_json"]) == [] for r in ctx))


class TestIdempotenceAndCrash(IdentityBase):
    def test_rerun_of_a_night_changes_nothing(self):
        self.play(4)
        before, calls = self.dump(), self.trait_calls
        again = identity.run_identity_step(self.persona, self.sleep_time(4), db_path=self.db, embed_fn=self.embed)
        self.assertEqual(again, {"skipped": "already done", "night": 4})
        with mock.patch.object(identity, "call_llm", self.fake_trait_llm()):
            hook = cons.maybe_sweep_on_sleep(self.persona, db_path=self.db, config=self.cfg, embed_fn=self.embed)
        self.assertIsNone(hook, "in-memory guard: the night is finished")
        self.persona.__dict__.pop("_devmem_swept_nights", None)  # as after a reload
        self.persona.scratch.curr_time = self.sleep_time(4)
        with mock.patch.object(cons, "call_llm", self.fake_summary_llm()), mock.patch.object(identity, "call_llm", self.fake_trait_llm()):
            hook = cons.maybe_sweep_on_sleep(self.persona, db_path=self.db, config=self.cfg, embed_fn=self.embed)
        self.assertEqual(hook["skipped"], "already swept")
        self.assertEqual(hook["identity"], {"skipped": "already done", "night": 4})
        self.assertEqual(self.dump(), before)
        self.assertEqual(self.trait_calls, calls)

    def test_crash_between_consolidation_and_identity_then_reload_matches_a_clean_run(self):
        self.play(4)
        clean = self.dump()
        self.fresh("crash")
        self.play(4, skip_identity_on=4)           # night 4: consolidation commits, the process "dies" before the identity step
        mid = self.dump()
        self.assertEqual([m["night"] for m in self.rows("identity_sweeps")], [1, 2, 3])
        self.assertEqual(len(self.rows("identity_traits")), 2)
        self.assertNotEqual(mid, clean)
        # reload from the latest save: all three reconcilers run and change nothing
        reps = [episodic.reconcile_run({AGENT: self.persona}, db_path=self.db), cons.reconcile_consolidation(self.persona, self.db),
                identity.reconcile_identity(self.persona, self.db)]
        self.assertEqual(reps[2]["removed_traits"], [])
        self.assertEqual(reps[2]["removed_identity_markers"], [])
        self.assertEqual(self.dump(), mid)
        # the hook fires again for night 4: Stage 3 is skipped (marker), the identity step runs and completes
        self.persona.__dict__.pop("_devmem_swept_nights", None)
        self.persona.scratch.curr_time = self.sleep_time(4)
        self.persona.scratch.act_description = "sleeping"
        self.night_no = 4
        with mock.patch.object(cons, "call_llm", self.fake_summary_llm()), mock.patch.object(identity, "call_llm", self.fake_trait_llm()):
            res = cons.maybe_sweep_on_sleep(self.persona, db_path=self.db, config=self.cfg, embed_fn=self.embed)
        self.assertEqual(res["skipped"], "already swept")
        self.assertEqual(res["identity"]["status"], "done")
        self.assertEqual(self.dump(), clean)

    def test_failed_identity_step_leaves_no_done_marker_and_retries_next_tick(self):
        self.add_night_events(1)
        self.add_night_events(2)
        self.run_night(1)
        # night 2: the trait generator answers in the first person twice (original and one retry): counted failure
        bad = self.fake_trait_llm(replies=["I love my cafe."])
        res = self.run_night(2, trait_llm=bad)
        self.assertEqual(res["identity"]["status"], "failed")
        self.assertEqual(len(res["identity"]["failures"]), 1)
        self.assertEqual([m["status"] for m in self.rows("identity_sweeps") if m["night"] == 2], ["failed"])
        self.assertEqual(self.rows("identity_traits"), [])
        self.assertEqual(self.trait_calls, 2, "one original call and one corrective retry")
        # the hook did not mark the night finished, so the next sleeping tick retries and succeeds
        with mock.patch.object(identity, "call_llm", self.fake_trait_llm()), mock.patch.object(cons, "call_llm", self.fake_summary_llm()):
            res2 = cons.maybe_sweep_on_sleep(self.persona, db_path=self.db, config=self.cfg, embed_fn=self.embed)
        self.assertEqual(res2["identity"]["status"], "done")
        self.assertEqual(res2["identity"]["attempts"], 2)
        self.assertEqual([t["path"] for t in self.rows("identity_traits")], ["pivotal"])

    def test_pivotal_events_lost_after_the_last_attempt_are_counted_and_named(self):
        self.icfg["max_attempts_per_night"] = 2
        self.add_night_events(1)
        ids = self.add_night_events(2)
        self.run_night(1)
        bad = self.fake_trait_llm(replies=["I love my cafe."])
        first = self.run_night(2, trait_llm=bad)
        self.assertEqual((first["identity"]["status"], first["identity"]["pivotal_lost"]), ("failed", 0))
        with mock.patch.object(identity, "call_llm", bad), mock.patch.object(cons, "call_llm", self.fake_summary_llm()):
            second = cons.maybe_sweep_on_sleep(self.persona, db_path=self.db, config=self.cfg, embed_fn=self.embed)
        lost = second["identity"]
        self.assertEqual(lost["pivotal_lost"], 1)
        self.assertEqual(lost["pivotal_lost_events"], [ids[FIXTURE["nights"][1]["events"][-1]["text"]]])
        logged = json.loads((self.db.parent / "identity_log.jsonl").read_text().splitlines()[-1])
        self.assertEqual(logged["pivotal_lost"], 1)

    def test_first_person_reply_gets_one_corrective_retry_then_succeeds(self):
        self.add_night_events(1)
        self.add_night_events(2)
        self.run_night(1)
        llm = self.fake_trait_llm(replies=["I take pride in my work.", FIXTURE["themes"]["lease"]["trait"]])
        res = self.run_night(2, trait_llm=llm)
        self.assertEqual(res["identity"]["status"], "done")
        self.assertEqual(res["identity"]["trait_retries"], 1)
        self.assertIn("not acceptable", self.trait_prompts[-1])
        self.assertTrue(cons.is_third_person(self.rows("identity_traits")[0]["text"], AGENT))

    def test_identity_not_run_when_consolidation_has_not_finished(self):
        self.add_night_events(1)
        res = identity.run_identity_step(self.persona, self.sleep_time(1), db_path=self.db, embed_fn=self.embed)
        self.assertEqual(res["skipped"], "consolidation not done")
        self.assertEqual(self.rows("identity_sweeps"), [])


class TestPathBThreshold(IdentityBase):
    def _night_with_scores(self, scores):
        when = datetime.datetime(2023, 2, 13, 10, 0)
        ids = {}
        for i, s in enumerate(scores):
            text = f"Isabella Rodriguez experienced distinct life event number {i} scored {s}"
            self.text_vec[text] = unit(15)
            ids[s] = self.add_event(text, at_cos(unit(4 + i), 14, 0.5), when + datetime.timedelta(minutes=i), s)
        self.persona.scratch.curr_time = datetime.datetime(2023, 2, 13, 22, 0)
        self.persona.scratch.act_description = "sleeping"
        with mock.patch.object(cons, "call_llm", self.fake_summary_llm()), \
                mock.patch.object(identity, "call_llm", self.fake_trait_llm(replies=["Isabella Rodriguez holds a lasting belief."])), \
                mock.patch.object(cons.episodic, "score_importance_persona_conditioned", return_value=6):
            res = cons.maybe_sweep_on_sleep(self.persona, db_path=self.db, config=self.cfg, embed_fn=self.embed)
        return ids, res

    def test_fires_at_the_threshold_and_above_not_below(self):
        self.assertEqual(self.icfg["pivotal_threshold"], 9)
        ids, res = self._night_with_scores([8, 9, 10])
        sources = sorted(e for t in self.rows("identity_traits") for e in json.loads(t["source_event_ids_json"]))
        self.assertEqual(sources, sorted([ids[9], ids[10]]))
        self.assertNotIn(ids[8], sources)
        self.assertEqual({t["path"] for t in self.rows("identity_traits")}, {"pivotal"})

    def test_threshold_is_config_not_hard_coded(self):
        self.icfg["pivotal_threshold"] = 10
        ids, _ = self._night_with_scores([8, 9, 10])
        sources = [e for t in self.rows("identity_traits") for e in json.loads(t["source_event_ids_json"])]
        self.assertEqual(sources, [ids[10]])

    def test_each_event_is_evaluated_once_and_never_graduates_twice(self):
        ids, _ = self._night_with_scores([10])
        self.assertEqual(len(self.rows("identity_traits")), 1)
        # a later night with no new pivotal event creates nothing
        self.persona.__dict__.pop("_devmem_swept_nights", None)
        self.persona.scratch.curr_time = datetime.datetime(2023, 2, 14, 22, 0)
        with mock.patch.object(cons, "call_llm", self.fake_summary_llm()), mock.patch.object(identity, "call_llm", self.fake_trait_llm()):
            res = cons.maybe_sweep_on_sleep(self.persona, db_path=self.db, config=self.cfg, embed_fn=self.embed)
        self.assertEqual(res["identity"]["traits_created"], [])
        self.assertEqual(len(self.rows("identity_traits")), 1)


class TestGuard(IdentityBase):
    """Spec 3.5 and addendum A1: events scored with a matching trait present do not add a night or graduate by Path B."""

    def _seed_trait_for_baking(self):
        self.add_night_events(1)
        self.run_night(1)
        e1 = self.sem_id_for("baking", 1)
        conn = sqlite3.connect(str(self.db))
        conn.execute("INSERT INTO identity_traits VALUES (?,?,?,?,?,?,?,?,1)",
                     (AGENT, f"{AGENT}:trait_1", FIXTURE["themes"]["baking"]["trait"], "count_based", json.dumps([e1]), "[]", 1,
                      "2023-02-13 22:00:00"))
        conn.commit()
        conn.close()
        return e1, f"{AGENT}:trait_1"

    def test_night_scored_with_the_matching_trait_is_recorded_but_not_counted(self):
        e1, tid = self._seed_trait_for_baking()
        self.add_night_events(2, traits=[tid], only={"baking"})
        self.run_night(2)
        r = self.reinforcement(e1)
        self.assertEqual(json.loads(r["day_set_json"]), [1])
        self.assertEqual(json.loads(r["self_reinforced_json"]), [2])
        log = [json.loads(l) for l in (self.db.parent / "reinforcement_decisions.jsonl").read_text().splitlines()]
        self.assertIn("self_reinforced", [d["decision"] for d in log if d["night"] == 2])

    def test_one_event_scored_without_the_trait_makes_the_night_count(self):
        e1, tid = self._seed_trait_for_baking()
        ids = self.add_night_events(2, traits=[tid], only={"baking"})
        conn = sqlite3.connect(str(self.db))
        first = sorted(ids.values())[0]
        conn.execute("UPDATE event_scoring_context SET trait_ids_json = '[]' WHERE entry_id = ?", (first,))
        conn.commit()
        conn.close()
        self.run_night(2)
        self.assertEqual(json.loads(self.reinforcement(e1)["day_set_json"]), [1, 2])

    def test_a_non_matching_trait_present_does_not_exclude_the_night(self):
        e1, _ = self._seed_trait_for_baking()
        conn = sqlite3.connect(str(self.db))
        conn.execute("INSERT INTO identity_traits VALUES (?,?,?,?,?,?,?,?,1)",
                     (AGENT, f"{AGENT}:trait_2", FIXTURE["themes"]["letters"]["trait"], "pivotal", "[]", json.dumps(["x:1"]), 1,
                      "2023-02-13 22:00:00"))
        conn.commit()
        conn.close()
        self.add_night_events(2, traits=[f"{AGENT}:trait_2"], only={"baking"})  # the letters trait vector is orthogonal to baking
        self.run_night(2)
        self.assertEqual(json.loads(self.reinforcement(e1)["day_set_json"]), [1, 2])

    def test_unknown_scoring_context_is_treated_as_self_reinforced(self):
        self.add_night_events(1)
        self.run_night(1)
        e1 = self.sem_id_for("baking", 1)
        ids = self.add_night_events(2, only={"baking"})
        conn = sqlite3.connect(str(self.db))
        conn.execute("UPDATE event_scoring_context SET status = 'unknown' WHERE entry_id IN (%s)" % ",".join("?" * len(ids)), list(ids.values()))
        conn.commit()
        conn.close()
        self.run_night(2)
        r = self.reinforcement(e1)
        self.assertEqual(json.loads(r["day_set_json"]), [1])
        self.assertEqual(json.loads(r["self_reinforced_json"]), [2])

    def test_feedback_off_nothing_is_ever_excluded(self):
        # IDENTITY_FEEDBACK=false: no trait is ever in a scoring context, so every night counts (the ablation compares like with like)
        self.icfg["identity_feedback"] = False
        self.play(2)
        e1 = self.sem_id_for("baking", 1)
        self.assertEqual(json.loads(self.reinforcement(e1)["day_set_json"]), [1, 2])
        self.assertEqual(json.loads(self.reinforcement(e1)["self_reinforced_json"]), [])

    def test_pivotal_event_scored_with_a_matching_trait_does_not_graduate(self):
        self.add_night_events(1)
        self.run_night(1)
        conn = sqlite3.connect(str(self.db))
        conn.execute("INSERT INTO identity_traits VALUES (?,?,?,?,?,?,?,?,1)",
                     (AGENT, f"{AGENT}:trait_1", "Isabella Rodriguez fears losing the cafe.", "pivotal", "[]", "[]", 1,
                      "2023-02-13 22:00:00"))
        conn.commit()
        conn.close()
        self.text_vec["Isabella Rodriguez fears losing the cafe."] = unit(3)
        when = datetime.datetime(2023, 2, 14, 16, 0)
        match = self.add_event("Isabella Rodriguez learned the cafe lease will end", unit(3), when, 10, traits=[f"{AGENT}:trait_1"])
        other = self.add_event("Isabella Rodriguez won a regional baking prize", unit(12), when, 10, traits=[f"{AGENT}:trait_1"])
        unknown = self.add_event("Isabella Rodriguez heard a shocking rumor", unit(13), when, 10, traits=[f"{AGENT}:trait_1"])
        conn = sqlite3.connect(str(self.db))
        conn.execute("UPDATE event_scoring_context SET status = 'unknown' WHERE entry_id = ?", (unknown,))
        conn.commit()
        conn.close()
        res = self.run_night(2, trait_llm=self.fake_trait_llm(replies=["Isabella Rodriguez cherishes recognition for her baking."]))
        self.assertEqual(res["identity"]["self_reinforced_pivotal"], 2)
        sources = [e for t in self.rows("identity_traits") for e in json.loads(t["source_event_ids_json"])]
        self.assertEqual(sources, [other])
        self.assertNotIn(match, sources)
        self.assertNotIn(unknown, sources)


class TestCapAndRendering(IdentityBase):
    def test_sixth_trait_evicts_the_oldest_and_five_remain_active(self):
        when = datetime.datetime(2023, 2, 13, 10, 0)
        ids = []
        for i in range(6):
            text = f"Isabella Rodriguez lived through pivotal moment {i}"
            ids.append(self.add_event(text, unit(4 + i), when + datetime.timedelta(minutes=i), 10))
        self.persona.scratch.curr_time = datetime.datetime(2023, 2, 13, 22, 0)
        self.persona.scratch.act_description = "sleeping"
        count = {"n": 0}

        def llm(prompt, **kw):
            count["n"] += 1
            return f"Isabella Rodriguez holds lasting belief number {count['n']}."
        with mock.patch.object(cons, "call_llm", self.fake_summary_llm()), mock.patch.object(identity, "call_llm", llm), \
                mock.patch.object(cons.episodic, "score_importance_persona_conditioned", return_value=6):
            res = cons.maybe_sweep_on_sleep(self.persona, db_path=self.db, config=self.cfg, embed_fn=self.embed)
        traits = self.rows("identity_traits")
        self.assertEqual(len(traits), 6)
        self.assertEqual([t["active"] for t in traits], [0, 1, 1, 1, 1, 1])
        self.assertEqual(res["identity"]["evicted"], [f"{AGENT}:trait_1"])
        # a trait is never re-created after eviction: the evicted source stays in the source set
        self.assertEqual(sorted(e for t in traits for e in json.loads(t["source_event_ids_json"])), sorted(ids))

    def test_context_has_at_most_five_traits_newest_first_and_stays_within_the_token_cap(self):
        cfg = dict(self.icfg)
        short = [f"Isabella Rodriguez trait {i} is brief." for i in range(7)]
        text, n = identity.render_identity_context(short, cfg)
        self.assertEqual(n, 5)
        self.assertEqual(text.splitlines()[1:], [f"- {t}" for t in short[:5]])
        long_ = [("Isabella Rodriguez " + " ".join(f"word{i}x{j}" for j in range(27)) + ".") for i in range(5)]
        text, n = identity.render_identity_context(long_, cfg)
        self.assertLess(n, 5)
        self.assertGreaterEqual(n, 1)
        from devmem.router import llm_router
        self.assertLessEqual(llm_router.estimate_tokens(text, max_tokens=0), cfg["identity_token_cap"])
        self.assertEqual(text.splitlines()[1:], [f"- {t}" for t in long_[:n]], "whole traits only, the oldest are dropped")
        # a single trait that cannot fit is dropped rather than cut
        huge = ["Isabella Rodriguez " + " ".join("w" * 5 for _ in range(150)) + "."]
        self.assertEqual(identity.render_identity_context(huge, cfg), ("", 0))

    def test_context_order_ties_broken_by_reinforcement_count(self):
        self.add_night_events(1)
        self.run_night(1)
        e1 = self.sem_id_for("baking", 1)
        conn = sqlite3.connect(str(self.db))
        conn.execute("UPDATE semantic_reinforcement SET distinct_days = 3 WHERE semantic_id = ?", (e1,))
        for i, (txt, sems) in enumerate((("Isabella Rodriguez trait low.", []), ("Isabella Rodriguez trait high.", [e1]))):
            conn.execute("INSERT INTO identity_traits VALUES (?,?,?,?,?,?,?,?,1)",
                         (AGENT, f"{AGENT}:trait_{i + 1}", txt, "count_based", json.dumps(sems), "[]", 2, "2023-02-14 22:00:00"))
        conn.commit()
        conn.close()
        text, ids = identity.load_identity_context(AGENT, self.db, self.icfg)
        self.assertEqual(ids, [f"{AGENT}:trait_2", f"{AGENT}:trait_1"])
        self.assertTrue(text.splitlines()[1].endswith("trait high."))


class TestFeedForwardPrompt(IdentityBase):
    """The flag-off prompt is byte-identical to Phase 5 (golden file captured from the Phase 5 code before any Stage 4 edit)."""

    def _score(self, agent, obs, kind):
        seen = {}

        def fake(**kw):
            seen["prompt"] = kw["prompt"]
            return "5"
        with mock.patch.object(episodic, "call_llm", side_effect=lambda **kw: fake(**kw)):
            episodic.score_importance_persona_conditioned(agent, obs, kind=kind, db_path=self.db)
        return seen["prompt"]

    def _add_trait(self, text="Isabella Rodriguez is devoted to the careful craft of baking."):
        conn = sqlite3.connect(str(self.db))
        conn.execute("INSERT INTO identity_traits VALUES (?,?,?,?,?,?,?,?,1)",
                     (AGENT, f"{AGENT}:trait_1", text, "count_based", "[]", "[]", 1, "2023-02-13 22:00:00"))
        conn.commit()
        conn.close()
        return text

    def test_flag_off_prompt_is_byte_identical_to_the_phase_5_golden_prompt(self):
        self.assertEqual(len(GOLDEN["cases"]), 4)
        with mock.patch.dict(os.environ, {"STAGE4_ENABLED": "off"}):
            self._add_trait()  # even with a trait in the database, flag off means nothing is injected
            for key, case in GOLDEN["cases"].items():
                agent, kind = key.split("|")
                self.assertEqual(episodic.build_staged_prompt(agent, case["observation"], kind=kind), case["prompt"], key)
                self.assertEqual(self._score(agent, case["observation"], kind), case["prompt"], key)

    def test_feedback_off_leaves_identity_context_empty_although_traits_are_stored(self):
        self._add_trait()
        self.icfg["identity_feedback"] = False
        for key, case in GOLDEN["cases"].items():
            agent, kind = key.split("|")
            self.assertEqual(self._score(agent, case["observation"], kind), case["prompt"], key)
        with mock.patch.dict(os.environ, {"IDENTITY_FEEDBACK": "false"}):
            self.icfg["identity_feedback"] = True
            self.assertEqual(self._score("Isabella Rodriguez", "x", "event"),
                             episodic.build_staged_prompt("Isabella Rodriguez", "x", kind="event"))

    def test_feedback_on_appends_the_traits_after_the_priors_block(self):
        text = self._add_trait()
        case = GOLDEN["cases"]["Isabella Rodriguez|event"]
        prompt = self._score("Isabella Rodriguez", case["observation"], "event")
        context = identity.load_identity_context(AGENT, self.db, self.icfg)[0]
        self.assertTrue(prompt.startswith(case["prompt"] + "\n\n"))
        self.assertEqual(prompt, case["prompt"] + "\n\n" + context)
        self.assertIn(text, context)
        self.assertTrue(context.startswith(self.icfg["identity_header"]))
        # the exact rendered prompt is saved once per agent per night
        renders = [json.loads(l) for l in (self.db.parent / "identity_prompt_renders.jsonl").read_text().splitlines()]
        self.assertEqual(len(renders), 1)
        self._score("Isabella Rodriguez", case["observation"], "event")
        self.assertEqual(len((self.db.parent / "identity_prompt_renders.jsonl").read_text().splitlines()), 1)

    def test_scoring_context_is_recorded_with_the_trait_ids_that_were_in_the_prompt(self):
        self._add_trait()
        when = datetime.datetime(2023, 2, 13, 11, 0)
        persona = mock.Mock()
        persona.scratch.curr_time = when
        with mock.patch.object(episodic, "call_llm", return_value="5"):
            episodic.score_importance_persona_conditioned(AGENT, "Isabella Rodriguez is stocking shelves", kind="event",
                                                          persona=persona, db_path=self.db)
        node = self.persona.a_mem.add_event(when, None, AGENT, "is", "stocking", "Isabella Rodriguez is stocking shelves", {"k"}, 5,
                                            ("Isabella Rodriguez is stocking shelves", unit(1)), None)
        episodic.log_episodic_node(AGENT, node, sim_time=when, importance_score=5, db_path=self.db)
        idle = self.persona.a_mem.add_event(when, None, AGENT, "is", "idle", "bed is idle", {"k"}, 1, ("bed is idle", unit(2)), None)
        episodic.log_episodic_node(AGENT, idle, sim_time=when, importance_score=1, db_path=self.db)
        lost = self.persona.a_mem.add_event(when, None, AGENT, "is", "x", "never scored text", {"k"}, 5, ("never scored text", unit(3)), None)
        episodic.log_episodic_node(AGENT, lost, sim_time=when, importance_score=5, db_path=self.db)
        by = {r["entry_id"]: r for r in self.rows("event_scoring_context")}
        self.assertEqual((by[f"{AGENT}:{node.node_id}"]["status"], json.loads(by[f"{AGENT}:{node.node_id}"]["trait_ids_json"])),
                         ("ok", [f"{AGENT}:trait_1"]))
        self.assertEqual(by[f"{AGENT}:{idle.node_id}"]["status"], "rule")
        self.assertEqual(by[f"{AGENT}:{lost.node_id}"]["status"], "unknown")


class TestReconcile(IdentityBase):
    def test_reload_from_an_older_save_restores_the_exact_older_state_and_is_idempotent(self):
        self.play(2)
        snap = self.dump()
        save2 = self.tmp / "save_after_night2"
        save2.mkdir()
        self.persona.a_mem.save(str(save2))
        self.add_night_events(3)
        self.run_night(3)
        self.add_night_events(4)
        self.run_night(4)
        self.assertEqual(len(self.rows("identity_traits")), 3)
        # reload from the night 2 save with the clock of that save
        self.persona.a_mem = AssociativeMemory(str(save2))
        self.persona.scratch.curr_time = self.sleep_time(2)
        episodic.reconcile_run({AGENT: self.persona}, db_path=self.db)
        cons.reconcile_consolidation(self.persona, self.db)
        rep = identity.reconcile_identity(self.persona, self.db)
        self.assertEqual(sorted(rep["removed_identity_markers"]), [3, 4])
        self.assertEqual(len(rep["removed_traits"]), 2)
        after = self.dump()
        for table in ("identity_traits", "identity_sweeps", "consolidation_events", "event_scoring_context"):
            self.assertEqual(after[table], snap[table], table)
        rows_after = {r["semantic_id"]: r for r in after["semantic_reinforcement"]}
        for r in snap["semantic_reinforcement"]:
            self.assertEqual(rows_after[r["semantic_id"]], r)
        self.assertEqual(len(rows_after), len(snap["semantic_reinforcement"]))
        again = identity.reconcile_identity(self.persona, self.db)
        self.assertEqual((again["removed_traits"], again["removed_identity_markers"], again["removed_consolidation_events"],
                          again["rebuilt_reinforcement_rows"]), ([], [], 0, 0))
        self.assertEqual(self.dump(), after)

    def test_traits_evicted_only_by_a_deleted_newer_trait_become_active_again(self):
        conn = sqlite3.connect(str(self.db))
        conn.execute("INSERT INTO consolidation_sweeps VALUES (?,?,?,?,?,?)", (AGENT, 1, "2023-02-13 22:00:00", 0, 1, "done"))
        for i in range(1, 7):
            night = 1 if i < 6 else 2
            conn.execute("INSERT INTO identity_traits VALUES (?,?,?,?,?,?,?,?,?)",
                         (AGENT, f"{AGENT}:trait_{i}", f"Isabella Rodriguez trait {i}.", "pivotal", "[]", "[]", night,
                          "2023-02-13 22:00:00" if night == 1 else "2023-02-14 22:00:00", 0 if i == 1 else 1))
        conn.execute("INSERT INTO identity_sweeps VALUES (?,?,?,?,?)", (AGENT, 1, "done", "2023-02-13 22:00:00", 1))
        conn.execute("INSERT INTO identity_sweeps VALUES (?,?,?,?,?)", (AGENT, 2, "done", "2023-02-14 22:00:00", 1))
        conn.commit()
        conn.close()
        self.persona.scratch.curr_time = datetime.datetime(2023, 2, 13, 23, 0)
        rep = identity.reconcile_identity(self.persona, self.db)
        self.assertEqual(rep["removed_traits"], [f"{AGENT}:trait_6"])
        active = {t["trait_id"]: t["active"] for t in self.rows("identity_traits")}
        self.assertEqual(active[f"{AGENT}:trait_1"], 1, "trait_1 was evicted only because of trait_6")
        self.assertEqual(sum(active.values()), 5)


class TestFlagOffIsPhaseFive(tc.StageThreeBase):
    def test_no_stage_4_table_is_created_and_the_hook_result_is_phase_5(self):
        with mock.patch.dict(os.environ, {"STAGE4_ENABLED": "off"}):
            a = self.add("baking", tc.vec(1, 0))
            b = self.add("kneading", tc.vec(0.99, 0.1), 9, 30)
            c = self.add("mixing", tc.vec(0.98, 0.1), 9, 40)
            self.cfg.update(min_cluster_size=3)
            with mock.patch.object(cons, "call_llm", self.llm()), \
                    mock.patch.object(cons.episodic, "score_importance_persona_conditioned", return_value=6):
                res = cons.maybe_sweep_on_sleep(self.persona, db_path=self.db, config=self.cfg, ledger_db=self.ledger,
                                                embed_fn=lambda t: tc.vec(0, 0, 1))
        self.assertNotIn("identity", res)
        conn = sqlite3.connect(str(self.db))
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        conn.close()
        self.assertFalse(tables & set(STAGE4_TABLES), tables & set(STAGE4_TABLES))
        self.assertEqual(res["summaries_written"], 1)


class TestTuningProtocol(unittest.TestCase):
    """The pre-registered REINFORCE_THRESHOLD protocol (docs/phase6_preregistration.md section 2), as code."""

    def _pairs(self, pos, neg):
        return [{"cosine": c} for c in pos], [{"cosine": c} for c in neg]

    def test_separated_groups_choose_one_hundredth_below_min_positive_rounded_down(self):
        from devmem.memory.p6_tune_reinforce import decide
        d = decide(*self._pairs([0.8923, 0.92, 0.94], [0.8583, 0.85]))
        self.assertEqual((d["chosen"], d["margin"]), (0.88, 0.034))

    def test_clipped_to_the_allowed_range(self):
        from devmem.memory.p6_tune_reinforce import decide
        self.assertEqual(decide(*self._pairs([0.97, 0.98], [0.5]))["chosen"], 0.90)
        self.assertEqual(decide(*self._pairs([0.83, 0.9], [0.5]))["chosen"], 0.82)
        self.assertEqual(decide(*self._pairs([0.80, 0.9], [0.5]))["chosen"], 0.80)  # 0.79 candidate clipped up to 0.80

    def test_overlap_or_too_small_a_margin_keeps_the_starting_value(self):
        from devmem.memory.p6_tune_reinforce import decide
        d = decide(*self._pairs([0.86, 0.9], [0.88]))
        self.assertEqual(d["chosen"], 0.85)
        self.assertIn("overlap", d["rule"])
        d = decide(*self._pairs([0.86, 0.9], [0.855]))   # separated, but max negative is not below the candidate 0.85
        self.assertEqual(d["chosen"], 0.85)
        self.assertIn("cannot place", d["rule"])

    def test_the_frozen_config_value_is_the_artifact_decision_recomputed_from_its_saved_cosines(self):
        from devmem.memory.p6_tune_reinforce import decide
        art = json.loads((Path(__file__).resolve().parent.parent.parent / "docs/phase6_stop2_artifacts/reinforce_tuning.json").read_text())
        again = decide(art["positives"], art["negatives"])
        self.assertEqual(again["chosen"], art["decision"]["chosen"])
        self.assertEqual(identity.load_config()["reinforce_threshold"], art["decision"]["chosen"])
        self.assertLessEqual(art["embedding_requests_made"], art["embedding_request_cap"])


class TestRunnerStage4Wiring(unittest.TestCase):
    """scripted: the real HeadlessRunner (real ReverieServer and Persona save/load) calls reconcile_identity on resume, only when
    Stage 4 is on. Reuses the scripted runner of test_reconcile without re-running its tests."""
    from devmem.memory import test_reconcile as _trc
    _base = _trc.TestHeadlessRunnerCrashReload
    SIM = "p6_stage4_wiring_test"
    FORK = _base.FORK
    setUpClass = classmethod(_base.setUpClass.__func__)
    tearDownClass = classmethod(_base.tearDownClass.__func__)
    _cleanup = _base._cleanup
    setUp = _base.setUp
    _scripted_runner = _base._scripted_runner

    def _crash_then_seed_a_future_trait(self):
        r1 = self._scripted_runner(crash_after=8)
        with self.assertRaises(RuntimeError):
            r1.run(20)
        name = next(iter(r1.rs.personas))
        identity.init_identity_db(r1.db_path)
        conn = sqlite3.connect(str(r1.db_path))
        conn.execute("INSERT INTO identity_traits VALUES (?,?,?,?,?,?,?,?,1)",
                     (name, f"{name}:trait_1", f"{name} is persistent.", "pivotal", "[]", "[]", 1, "2099-01-01 00:00:00"))
        conn.commit()
        conn.close()
        return name

    def test_resume_with_stage_4_on_rolls_back_a_trait_created_after_the_loaded_clock(self):
        with mock.patch.dict(os.environ, {"STAGE4_ENABLED": "on"}):
            name = self._crash_then_seed_a_future_trait()
            r2 = self._scripted_runner(tag="replayed", resume=True)
        self.assertEqual(len(r2.identity_reconcile), len(r2.rs.personas))
        removed = {r["agent_id"]: r["removed_traits"] for r in r2.identity_reconcile}
        self.assertEqual(removed[name], [f"{name}:trait_1"])
        conn = sqlite3.connect(str(r2.db_path))
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM identity_traits").fetchone()[0], 0)
        conn.close()

    def test_resume_with_stage_4_off_does_not_touch_stage_4_state(self):
        with mock.patch.dict(os.environ, {"STAGE4_ENABLED": "on"}):
            self._crash_then_seed_a_future_trait()
        with mock.patch.dict(os.environ, {"STAGE4_ENABLED": "off"}):
            r2 = self._scripted_runner(tag="replayed", resume=True)
        self.assertEqual(r2.identity_reconcile, [])
        conn = sqlite3.connect(str(r2.db_path))
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM identity_traits").fetchone()[0], 1)
        conn.close()


if __name__ == "__main__":
    unittest.main()
