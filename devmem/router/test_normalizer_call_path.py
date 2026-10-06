"""
Offline tests (zero live calls) that the revised normalizer behaves as specified on the real upstream call path.

Everything is built from upstream's real template files and upstream's real functions; the provider layer is the only stub (see
devmem/memory/p6_normalizer_harness.py). The evidence table is produced by devmem/memory/p6_normalizer_table.py; these tests assert it.
"""
import devmem.testing_env  # noqa: F401
import unittest
from pathlib import Path

from devmem.memory import p6_normalizer_harness as h
from devmem.memory import p6_normalizer_table as table
from devmem.router import output_normalizer as on


class TestVetoSetOnAllRealTemplates(unittest.TestCase):
    def test_every_template_file_is_vetoed_exactly_when_it_is_a_decomposition_template(self):
        files = sorted(p for p in h.TEMPLATE_ROOT.rglob("*.txt"))
        self.assertGreater(len(files), 60)
        vetoed = []
        for f in files:
            rel = "persona/prompt_template/" + f.relative_to(h.TEMPLATE_ROOT).as_posix()
            rendered = h.render_template(rel)
            is_decomp = any(part in f.stem for part in ("task_decomp", "new_decomp_schedule"))
            if on.vetoed(rendered):
                vetoed.append(f.stem)
            self.assertEqual(on.vetoed(rendered), is_decomp, f"{rel}")
        # every task_decomp file (all versions, both folders) and every new_decomp_schedule file, and nothing else
        self.assertEqual(set(vetoed), {"task_decomp_v1", "task_decomp_v2", "task_decomp_v3", "new_decomp_schedule_v1"})
        self.assertGreaterEqual(len(vetoed), 7)

    def test_code_read_only_the_decomposition_parser_reads_the_annotation(self):
        src = (h.TEMPLATE_ROOT / "run_gpt_prompt.py").read_text(encoding="utf-8")
        lines = [i + 1 for i, l in enumerate(src.splitlines()) if "duration in minutes" in l or "minutes left" in l]
        self.assertEqual(lines, [374, 381])
        owner = [l for l in src.splitlines()[:374] if l.startswith("def run_gpt_prompt_")][-1]
        self.assertTrue(owner.startswith("def run_gpt_prompt_task_decomp"), owner)  # the function that contains line 374 and 381


class TestEvidenceTable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = table.build()

    def test_templates_table(self):
        rows = self.result["templates"]
        self.assertGreaterEqual(len(rows), 49 + 2)
        self.assertTrue(all(r["veto_matches_expectation"] for r in rows))
        vetoed = sorted(Path(r["template"]).stem for r in rows if not r["stripped"])
        self.assertEqual(vetoed, ["new_decomp_schedule_v1", "task_decomp_v3"])  # the two decomposition templates in the call path
        devmem_rows = [r for r in rows if r["template"].startswith("devmem")]
        self.assertTrue(all(r["stripped"] for r in devmem_rows))
        unreadable = [r["template"] for r in rows if not r["upstream_can_read_it_here"]]
        self.assertEqual(unreadable, ["persona/prompt_template/v2/generate_pronunciatio_v1.txt"])

    def test_step_c_replays_use_the_live_prompt_and_nothing_gets_worse(self):
        reps = [r for r in self.result["stepc_replays"] if "before" in r]
        self.assertEqual(len(reps), 1 + 1 + 18 + 2)  # wake-up, daily plan, 18 hourly, sector, arena
        for r in reps:
            self.assertTrue(r["prompt_equals_live_prompt"], r["prompt_type"])
            self.assertFalse(r["delivered_after_has_annotation"])
            self.assertGreaterEqual(sum(r["after"]["validate"]), sum(r["before"]["validate"]), r["prompt_type"])
            self.assertIsNone(r["after"]["error"])

    def test_sector_and_arena_go_from_all_rejected_to_accepted_on_the_first_attempt(self):
        by = {r["prompt_type"]: r for r in self.result["stepc_replays"] if "before" in r}
        for kind in ("action_sector", "action_arena"):
            self.assertEqual(by[kind]["before"]["validate"], [False] * 5, kind)
            self.assertEqual(by[kind]["after"]["validate"], [True], kind)
        self.assertEqual(by["action_arena"]["before"]["result"], "kitchen")      # the fail-safe that crashed the live run
        self.assertEqual(by["action_arena"]["after"]["result"], "main room")
        self.assertEqual(by["action_sector"]["after"]["result"], "Isabella Rodriguez's apartment")

    def test_decomposition_reply_keeps_its_annotation_through_the_real_router(self):
        veto_rows = [r for r in self.result["stepc_replays"] if r["prompt_type"] == "task_decomp"]
        self.assertEqual(len(veto_rows), 1)
        self.assertFalse(veto_rows[0]["stripped_by_rule"])

    def test_synthetic_checks_flag_on_equals_the_clean_result_for_every_function(self):
        checks = self.result["synthetic_validator_checks"]
        self.assertEqual(len(checks), 7)
        self.assertTrue(all(c["flag_on_equals_clean"] for c in checks))
        self.assertTrue(all(c["annotated_flag_on"]["error"] is None for c in checks))
        broken_without = [c["function"] for c in checks if not c["flag_off_equals_clean"]]
        self.assertGreaterEqual(len(broken_without), 4)  # evidence that the strip matters (label: synthetic)


if __name__ == "__main__":
    unittest.main()
