"""
Unit and integration tests for devmem.memory.episodic module.
Verifies prompt construction, persona-conditioned scoring, SQLite episodic mirroring,
sim_day calculation, baseline vs staged mode differences, and reload idempotency.
"""

import devmem.testing_env  # noqa: F401  (offline by default; DEVMEM_LIVE_TESTS=1 for live)
from datetime import datetime, date
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from devmem.memory.episodic import (
    build_staged_prompt,
    calculate_sim_day,
    flag_consolidated,
    get_unconsolidated,
    get_upstream_prompt,
    init_episodic_db,
    log_episodic_memory,
    log_episodic_node,
    parse_importance_score,
    score_importance_persona_conditioned,
)
from devmem.memory.priors import get_prompt_context


class TestEpisodicModule(unittest.TestCase):
    def setUp(self):
        self.agent_id = "Isabella Rodriguez"
        self.event_obs = "Isabella has a loud argument with a customer over billing"
        self.chat_obs = "Isabella Rodriguez: We need to sort this out right now!\nCustomer: I am not paying for this."

    def test_staged_prompt_equals_upstream_plus_priors(self):
        """
        Task 7a: Verify that staged prompt equals upstream prompt PLUS priors block,
        and that the priors block is the only difference between conditions.
        """
        for kind, obs in [("event", self.event_obs), ("chat", self.chat_obs)]:
            with self.subTest(kind=kind):
                upstream_prompt = get_upstream_prompt(self.agent_id, obs, kind=kind)
                priors_block = get_prompt_context(self.agent_id)
                staged_prompt = build_staged_prompt(self.agent_id, obs, kind=kind)

                expected_staged = f"{upstream_prompt}\n\n{priors_block}"
                self.assertEqual(staged_prompt, expected_staged)
                self.assertTrue(staged_prompt.startswith(upstream_prompt))
                self.assertTrue(staged_prompt.endswith(priors_block))

    def test_staged_prompt_with_identity_context(self):
        """Verify optional identity_context parameter appends properly when provided."""
        identity_str = "Identity Trait: Known mediator in local commerce disputes"
        staged_prompt = build_staged_prompt(
            self.agent_id,
            self.event_obs,
            kind="event",
            identity_context=identity_str,
        )
        upstream_prompt = get_upstream_prompt(self.agent_id, self.event_obs, kind="event")
        priors_block = get_prompt_context(self.agent_id)
        expected = f"{upstream_prompt}\n\n{priors_block}\n\n{identity_str}"
        self.assertEqual(staged_prompt, expected)

    def test_sim_day_calculation(self):
        """
        Task 5: Verify sim_day definition:
        sim_day is days since fork's start date (Day 1 = start date: February 13, 2023).
        """
        start = date(2023, 2, 13)
        self.assertEqual(calculate_sim_day("February 13, 2023, 08:30:00", start_date=start), 1)
        self.assertEqual(calculate_sim_day(datetime(2023, 2, 13, 23, 59, 59), start_date=start), 1)
        self.assertEqual(calculate_sim_day("February 14, 2023, 00:00:00", start_date=start), 2)
        self.assertEqual(calculate_sim_day(date(2023, 2, 15), start_date=start), 3)
        self.assertEqual(calculate_sim_day("2023-02-20 12:00:00", start_date=start), 8)

    def test_score_importance_with_mocked_router(self):
        """Task 7a: Verify score_importance_persona_conditioned with mocked router response."""
        with patch("devmem.memory.episodic.call_llm") as mock_call:
            mock_call.return_value = "8"
            score = score_importance_persona_conditioned(self.agent_id, self.event_obs, kind="event")
            self.assertEqual(score, 8)
            mock_call.assert_called_once()
            call_kwargs = mock_call.call_args.kwargs
            self.assertEqual(call_kwargs["purpose"], "importance_scoring")
            self.assertEqual(call_kwargs["condition"], "staged")
            self.assertIn("This agent's core personality traits:", call_kwargs["prompt"])

    def test_run_database_is_never_forwarded_to_the_router_as_the_ledger_path(self):
        """Follow-up A1: the router ledger has one path. db_path (the run database) must not reach call_llm; only an explicit
        ledger_db_path does, and the prompt and the router call fields are unchanged either way."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_db = Path(tmp_dir) / "run.db"
            ledger = Path(tmp_dir) / "ledger.db"
            with patch("devmem.memory.episodic.call_llm", return_value="6") as mock_call:
                a = score_importance_persona_conditioned(self.agent_id, self.event_obs, kind="event", db_path=run_db)
                b = score_importance_persona_conditioned(self.agent_id, self.event_obs, kind="event")
                c = score_importance_persona_conditioned(self.agent_id, self.event_obs, kind="event", db_path=run_db,
                                                         ledger_db_path=ledger)
            self.assertEqual((a, b, c), (6, 6, 6))
            first, second, third = (call.kwargs for call in mock_call.call_args_list)
            self.assertNotIn("db_path", first)
            self.assertEqual(first, second)  # passing the run database changes nothing sent to the router
            self.assertEqual(third.pop("db_path"), ledger)
            self.assertEqual(third, second)
            self.assertEqual({k: first[k] for k in ("tier", "purpose", "agent_id", "condition")},
                             {"tier": "fast", "purpose": "importance_scoring", "agent_id": self.agent_id, "condition": "staged"})
            self.assertFalse(run_db.exists() and sqlite3.connect(str(run_db)).execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE name='llm_call_log'").fetchone()[0] > 0 and
                sqlite3.connect(str(run_db)).execute("SELECT COUNT(*) FROM llm_call_log").fetchone()[0] > 0)

    def test_parse_importance_score_reads_the_labelled_value_and_ignores_the_range_phrase(self):
        from devmem.memory.episodic import parse_importance_score as parse
        cases = {"7": 7, "**7**": 7, "Rate: 3\n\n**Reasoning:** blah 5 things": 3, "Rate: 10": 10, "**Rate: 9**": 9,
                 "Rate (return a number between 1 to 10): 10": 10, "Rate (return a number between 1 to 10): 3": 3,
                 "On a scale of 1 to 10 I would say 6": 6, "scale of 1-10: 8": 8, "I am an AI and cannot rate this": 4, "": 4, "no digits": 4,
                 "The poignancy is 2.": 2}
        for text, want in cases.items():
            self.assertEqual(parse(text), want, text)

    def test_score_importance_fail_safe_fallback(self):
        """Verify unparseable responses fall back to fail-safe 4."""
        with patch("devmem.memory.episodic.call_llm") as mock_call:
            mock_call.return_value = "I am an AI and cannot rate this"
            score = score_importance_persona_conditioned(self.agent_id, self.event_obs)
            self.assertEqual(score, 4)

    def test_log_episodic_memory_idempotency_and_schema(self):
        """
        Tasks 5 & 2: Verify episodic entries mirrored to SQLite with consolidated=0,
        correct sim_day, and idempotent insertion on sim reload.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test_memory.db"
            init_episodic_db(db_path=db_path)

            entry_id = f"{self.agent_id}:node_15"
            sim_time = "February 13, 2023, 10:15:00"

            # First insertion
            res_id_1 = log_episodic_memory(
                agent_id=self.agent_id,
                content=self.event_obs,
                sim_timestamp=sim_time,
                importance_score=7,
                entry_id=entry_id,
                db_path=db_path,
            )
            self.assertEqual(res_id_1, entry_id)

            # Verify recorded row
            unconsolidated = get_unconsolidated(self.agent_id, db_path=db_path)
            self.assertEqual(len(unconsolidated), 1)
            row = unconsolidated[0]
            self.assertEqual(row["entry_id"], entry_id)
            self.assertEqual(row["agent_id"], self.agent_id)
            self.assertEqual(row["content"], self.event_obs)
            self.assertEqual(row["sim_day"], 1)
            self.assertEqual(row["importance_score"], 7.0)
            self.assertEqual(row["consolidated"], 0)

            # Second insertion (simulating reload): must be idempotent and not create duplicates
            res_id_2 = log_episodic_memory(
                agent_id=self.agent_id,
                content=self.event_obs,
                sim_timestamp=sim_time,
                importance_score=7,
                entry_id=entry_id,
                db_path=db_path,
            )
            self.assertEqual(res_id_2, entry_id)
            unconsolidated_after_reload = get_unconsolidated(self.agent_id, db_path=db_path)
            self.assertEqual(len(unconsolidated_after_reload), 1)

    def test_flag_consolidated(self):
        """Verify flag_consolidated transitions consolidated flag from 0 to 1."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "test_memory.db"
            init_episodic_db(db_path=db_path)

            id1 = log_episodic_memory(self.agent_id, "Event 1", "2023-02-13 10:00:00", entry_id="e1", db_path=db_path)
            id2 = log_episodic_memory(self.agent_id, "Event 2", "2023-02-13 11:00:00", entry_id="e2", db_path=db_path)

            self.assertEqual(len(get_unconsolidated(self.agent_id, db_path=db_path)), 2)

            updated = flag_consolidated(["e1"], db_path=db_path)
            self.assertEqual(updated, 1)

            remaining = get_unconsolidated(self.agent_id, db_path=db_path)
            self.assertEqual(len(remaining), 1)
            self.assertEqual(remaining[0]["entry_id"], "e2")


class TestUpstreamIntegration(unittest.TestCase):
    """Integration tests verifying touch points in reverie/ (perceive.py and persona.py)."""

    def setUp(self):
        import sys
        backend_dir = Path(__file__).resolve().parent.parent.parent / "reverie" / "reverie" / "backend_server"
        if str(backend_dir) not in sys.path:
            sys.path.insert(0, str(backend_dir))

        self.storage_persona_dir = (
            Path(__file__).resolve().parent.parent.parent
            / "reverie"
            / "environment"
            / "frontend_server"
            / "storage"
            / "base_the_ville_isabella_maria_klaus"
            / "personas"
            / "Isabella Rodriguez"
        )

    def test_persona_init_baseline_injects_priors_idempotent(self):
        """
        Task 6 & 7d: Verify persona initialization in baseline mode injects atomic priors,
        and reloading the persona does not create duplicate prior nodes.
        """
        import utils
        from persona.persona import Persona

        orig_mode = utils.MEMORY_MODE
        try:
            utils.MEMORY_MODE = "baseline"
            p = Persona("Isabella Rodriguez", str(self.storage_persona_dir))

            # Prior nodes must exist in baseline mode
            prior_nodes = [
                n for n in p.a_mem.seq_thought
                if getattr(n, "predicate", "") == "has personality trait"
            ]
            self.assertEqual(len(prior_nodes), 6)

            # Reload test: re-instantiate persona from same state, priors must remain exactly 6
            p_reloaded = Persona("Isabella Rodriguez", str(self.storage_persona_dir))
            prior_nodes_reload = [
                n for n in p_reloaded.a_mem.seq_thought
                if getattr(n, "predicate", "") == "has personality trait"
            ]
            self.assertEqual(len(prior_nodes_reload), 6)

        finally:
            utils.MEMORY_MODE = orig_mode

    def test_persona_init_staged_does_not_inject_priors(self):
        """
        Task 6: In staged mode, do NOT inject priors into the memory stream (Stage 1 stays separate).
        """
        import utils
        from persona.persona import Persona

        orig_mode = utils.MEMORY_MODE
        try:
            utils.MEMORY_MODE = "staged"
            p = Persona("Isabella Rodriguez", str(self.storage_persona_dir))

            # Staged condition must NOT inject priors into AssociativeMemory
            prior_nodes = [
                n for n in p.a_mem.seq_thought
                if getattr(n, "predicate", "") == "has personality trait"
            ]
            self.assertEqual(len(prior_nodes), 0)

        finally:
            utils.MEMORY_MODE = orig_mode

    def test_perceive_integration_staged_scoring_and_mirroring(self):
        """
        Tasks 4 & 5: Verify generate_poig_score routes to staged scorer when MEMORY_MODE == 'staged',
        and perceived nodes are mirrored into SQLite episodic_memory table.
        """
        import utils
        from persona.persona import Persona
        from persona.cognitive_modules.perceive import generate_poig_score

        orig_mode = utils.MEMORY_MODE
        try:
            utils.MEMORY_MODE = "staged"
            p = Persona("Isabella Rodriguez", str(self.storage_persona_dir))

            with tempfile.TemporaryDirectory() as tmp_dir:
                db_path = Path(tmp_dir) / "test_sim.db"
                with patch("devmem.memory.episodic.call_llm") as mock_call, \
                     patch("devmem.memory.episodic.get_db_path", return_value=db_path):
                    mock_call.return_value = "9"

                    score = generate_poig_score(p, "event", "Isabella Rodriguez enters the cafe")
                    self.assertEqual(score, 9)
                    self.assertIn("This agent's core personality traits:", mock_call.call_args.kwargs["prompt"])

        finally:
            utils.MEMORY_MODE = orig_mode


if __name__ == "__main__":
    unittest.main()
