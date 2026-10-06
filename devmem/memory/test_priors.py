"""
Unit tests for devmem.memory.priors module.
Verifies loading 6 hand-authored personas, prompt context generation,
error handling (PersonaNotFoundError, PersonaSchemaError), and baseline injection.
"""

import devmem.testing_env  # noqa: F401  (offline by default; DEVMEM_LIVE_TESTS=1 for live)
from datetime import datetime
import os
from pathlib import Path
import tempfile
import unittest

from devmem.memory.priors import (
    PersonaNotFoundError,
    PersonaSchemaError,
    get_prompt_context,
    inject_into_baseline,
    load_priors,
)


class MockScratch:
    def __init__(self, curr_time=None):
        self.curr_time = curr_time or datetime(2023, 2, 13, 8, 30, 0)


class MockAssociativeMemory:
    """Mock associative memory matching upstream reverie AssociativeMemory interface."""
    def __init__(self):
        self.id_to_node = {}
        self.seq_thought = []
        self.seq_event = []
        self.seq_chat = []
        self.kw_to_thought = {}
        self.kw_strength_thought = {}
        self.embeddings = {}

    def add_thought(
        self,
        created,
        expiration,
        s,
        p,
        o,
        description,
        keywords,
        poignancy,
        embedding_pair,
        filling,
    ):
        node_id = f"node_{len(self.id_to_node) + 1}"
        node_count = len(self.id_to_node) + 1
        type_count = len(self.seq_thought) + 1

        class MockNode:
            def __init__(self):
                self.node_id = node_id
                self.node_count = node_count
                self.type_count = type_count
                self.type = "thought"
                self.depth = 1
                self.created = created
                self.expiration = expiration
                self.subject = s
                self.predicate = p
                self.object = o
                self.description = description
                self.embedding_key = embedding_pair[0]
                self.poignancy = poignancy
                self.keywords = [k.lower() for k in keywords]
                self.filling = filling

        node = MockNode()
        self.seq_thought.insert(0, node)
        for kw in node.keywords:
            self.kw_to_thought.setdefault(kw, []).insert(0, node)
            self.kw_strength_thought[kw] = self.kw_strength_thought.get(kw, 0) + 1
        self.id_to_node[node_id] = node
        self.embeddings[embedding_pair[0]] = embedding_pair[1]
        return node


class MockPersona:
    def __init__(self, name="Isabella Rodriguez"):
        self.name = name
        self.scratch = MockScratch()
        self.a_mem = MockAssociativeMemory()


class TestPriorsModule(unittest.TestCase):
    def setUp(self):
        self.expected_agents = [
            "Isabella Rodriguez",
            "Klaus Mueller",
            "Maria Lopez",
            "Wolfgang Schulz",
            "Giorgio Rossi",
            "Sam Moore",
        ]

    def test_load_all_six_authored_personas(self):
        """Verify all 6 delivered persona YAMLs load successfully and contain >= 5 prior statements."""
        for agent_id in self.expected_agents:
            with self.subTest(agent=agent_id):
                priors = load_priors(agent_id)
                self.assertIsInstance(priors, list)
                self.assertGreaterEqual(len(priors), 5)
                for stmt in priors:
                    self.assertIsInstance(stmt, str)
                    self.assertTrue(len(stmt.strip()) > 0)

    def test_load_priors_with_snake_case_and_id_variants(self):
        """Verify loader works with snake_case and lowercased agent identifiers."""
        priors_exact = load_priors("Isabella Rodriguez")
        priors_snake = load_priors("isabella_rodriguez")
        priors_lower = load_priors("isabella rodriguez")
        self.assertEqual(priors_exact, priors_snake)
        self.assertEqual(priors_exact, priors_lower)

    def test_get_prompt_context_formatting(self):
        """Verify prompt context block matches the standardized format."""
        agent_id = "Isabella Rodriguez"
        context = get_prompt_context(agent_id)
        self.assertIsInstance(context, str)
        self.assertTrue(context.startswith("This agent's core personality traits:\n"))
        lines = context.strip().split("\n")
        # 1 header line + 6 prior bullet lines
        self.assertEqual(len(lines), 7)
        for line in lines[1:]:
            self.assertTrue(line.startswith("- "))
            self.assertGreater(len(line), 5)

    def test_missing_persona_file_raises_not_found(self):
        """Verify PersonaNotFoundError is raised when an agent file is missing."""
        with self.assertRaises(PersonaNotFoundError):
            load_priors("Nonexistent Agent 12345")

    def test_malformed_yaml_raises_schema_error(self):
        """Verify PersonaSchemaError is raised when YAML is malformed or invalid."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            bad_yaml_1 = tmp_path / "bad1.yaml"
            bad_yaml_1.write_text("agent_id: Bad Agent\nversion: 1.0\n", encoding="utf-8")
            with self.assertRaises(PersonaSchemaError):
                load_priors("bad1", personas_dir=tmp_path)

            bad_yaml_2 = tmp_path / "bad2.yaml"
            bad_yaml_2.write_text("agent_id: Bad Agent 2\npriors: 'not a list'\n", encoding="utf-8")
            with self.assertRaises(PersonaSchemaError):
                load_priors("bad2", personas_dir=tmp_path)

            bad_yaml_3 = tmp_path / "bad3.yaml"
            bad_yaml_3.write_text("agent_id: Bad Agent 3\npriors: []\n", encoding="utf-8")
            with self.assertRaises(PersonaSchemaError):
                load_priors("bad3", personas_dir=tmp_path)

    def test_inject_into_baseline_bundled(self):
        """Verify inject_into_baseline with mode='bundled' creates a single high-poignancy thought node."""
        persona = MockPersona(name="Isabella Rodriguez")
        node = inject_into_baseline("Isabella Rodriguez", persona, mode="bundled")

        self.assertIsNotNone(node)
        self.assertEqual(node.poignancy, 10)
        self.assertEqual(len(persona.a_mem.seq_thought), 1)
        self.assertIn("Isabella Rodriguez's core personality traits:", node.description)
        self.assertIn("personality", node.keywords)
        self.assertEqual(persona.a_mem.id_to_node[node.node_id], node)
        self.assertIn(node.description, persona.a_mem.embeddings)

    def test_inject_into_baseline_atomic(self):
        """Verify inject_into_baseline default mode is 'atomic' creating individual thought nodes per prior."""
        persona = MockPersona(name="Klaus Mueller")
        # Test default mode (should be atomic per approved plan amendment)
        nodes = inject_into_baseline("Klaus Mueller", persona)

        priors = load_priors("Klaus Mueller")
        self.assertEqual(len(nodes), len(priors))
        self.assertEqual(len(persona.a_mem.seq_thought), len(priors))
        for idx, node in enumerate(nodes):
            self.assertEqual(node.poignancy, 10)
            self.assertIn(f"prior_{idx+1}", node.object)
            self.assertIn("Klaus Mueller:", node.description)
            self.assertIn(node.description, persona.a_mem.embeddings)
            self.assertEqual(persona.a_mem.id_to_node[node.node_id], node)

    def test_inject_into_baseline_real_associative_memory(self):
        """Integration test: verify injection and retrieval against real upstream AssociativeMemory."""
        import sys
        backend_dir = Path(__file__).resolve().parent.parent.parent / "reverie" / "reverie" / "backend_server"
        if str(backend_dir) not in sys.path:
            sys.path.insert(0, str(backend_dir))

        from persona.persona import Persona
        from persona.cognitive_modules.retrieve import new_retrieve
        from persona.memory_structures.associative_memory import ConceptNode

        storage_persona_dir = (
            Path(__file__).resolve().parent.parent.parent
            / "reverie"
            / "environment"
            / "frontend_server"
            / "storage"
            / "base_the_ville_isabella_maria_klaus"
            / "personas"
            / "Isabella Rodriguez"
        )
        if not storage_persona_dir.exists():
            self.skipTest(f"Bootstrap storage directory not found: {storage_persona_dir}")

        import utils
        orig = utils.MEMORY_MODE
        try:
            # Instantiate in staged mode to isolate direct inject_into_baseline call
            utils.MEMORY_MODE = "staged"
            real_persona = Persona("Isabella Rodriguez", str(storage_persona_dir))
            self.assertEqual(len(real_persona.a_mem.seq_thought), 0)

            injected_nodes = inject_into_baseline("Isabella Rodriguez", real_persona, mode="atomic")
            self.assertEqual(len(injected_nodes), 6)
            self.assertEqual(len(real_persona.a_mem.seq_thought), 6)
            self.assertIsInstance(injected_nodes[0], ConceptNode)

            # Idempotency check: second injection call must return existing nodes without duplicating
            second_call_nodes = inject_into_baseline("Isabella Rodriguez", real_persona, mode="atomic")
            self.assertEqual(len(second_call_nodes), 6)
            self.assertEqual(len(real_persona.a_mem.seq_thought), 6)
        finally:
            utils.MEMORY_MODE = orig

        # Confirm retrieval through real new_retrieve
        focal_pts = ["Isabella has a disagreement and potential confrontation with a neighbour"]
        retrieved = new_retrieve(real_persona, focal_pts, n_count=5)
        self.assertIn(focal_pts[0], retrieved)
        retrieved_descriptions = [node.description for node in retrieved[focal_pts[0]]]
        self.assertTrue(
            any("Isabella Rodriguez:" in desc for desc in retrieved_descriptions),
            "Expected at least one injected personality prior in retrieved memories",
        )

    def test_inject_into_baseline_invalid_persona_raises(self):
        """Verify passing an object without a_mem raises AttributeError."""
        class InvalidPersona:
            name = "Test"

        with self.assertRaises(AttributeError):
            inject_into_baseline("Isabella Rodriguez", InvalidPersona())


if __name__ == "__main__":
    unittest.main()

