"""
Replays the scripted four-night fixture through the real Stage 3 sweep, the real sleep hook and the real Stage 4 step, and saves the raw
tables and logs as artifacts (docs/phase6_stop2_artifacts/fixture_run_*). Label: scripted events, SYNTHETIC vectors (unit vectors with
chosen cosines), stubbed summary and trait generators (the scripted sentences of the fixture). No LLM call, no embedding request.
Nothing here is a measurement of model behavior.
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
ART = ROOT / "docs" / "phase6_stop2_artifacts"


def main():
    import devmem.testing_env  # noqa: F401
    from unittest import mock
    from devmem.memory import episodic, identity
    from devmem.memory import test_identity as ti

    ART.mkdir(parents=True, exist_ok=True)
    case = ti.TestScriptedFourNights("test_each_theme_follows_its_path_night_by_night")
    ti.TestScriptedFourNights.setUpClass()
    case.setUp()
    try:
        case.play(4)
        dump = case.dump()
        (ART / "fixture_run_tables.json").write_text(json.dumps(
            {"label": "scripted events, synthetic vectors, stubbed generators; no live call", "reinforce_threshold": case.thr, **dump},
            indent=1), encoding="utf-8")
        for name in ("reinforcement_decisions.jsonl", "identity_log.jsonl", "consolidation_log.jsonl"):
            shutil.copy(case.db.parent / name, ART / f"fixture_run_{name}")
        # what the scoring model would see once traits exist: the exact rendered prompt (scripted traits, no call is made)
        seen = {}
        with mock.patch.object(episodic, "call_llm", side_effect=lambda **kw: seen.setdefault("prompt", kw["prompt"]) and "5"):
            episodic.score_importance_persona_conditioned("Isabella Rodriguez", "Isabella Rodriguez is stocking shelves at the cafe",
                                                          kind="event", db_path=case.db)
        (ART / "fixture_run_rendered_scoring_prompt.txt").write_text(
            "LABEL: rendered by the real scorer from the fixture run's stored traits (scripted trait sentences); no model was called.\n"
            "----\n" + seen["prompt"] + "\n", encoding="utf-8")
        renders = case.db.parent / "identity_prompt_renders.jsonl"
        if renders.exists():
            shutil.copy(renders, ART / "fixture_run_identity_prompt_renders.jsonl")
        print(json.dumps({"traits": [(t["trait_id"], t["path"], t["created_night"]) for t in dump["identity_traits"]],
                          "reinforcement": [(r["semantic_id"], r["day_set_json"], r["same_day_max"]) for r in dump["semantic_reinforcement"]]},
                         indent=1))
    finally:
        case.doCleanups()
        ti.TestScriptedFourNights.tearDownClass()


if __name__ == "__main__":
    main()
