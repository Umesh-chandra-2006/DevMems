"""
Phase 9 evaluation driver for ONE arm (recall answers, probe interviews at two checkpoints, judge on the day-1 against day-3 probe pairs), to run as soon as THAT arm has finished,
on that arm's OWN key pool only (eval_keys: it refuses while the arm is running; a stub run makes no call and uses no key).

Inputs: the arm's day-1 checkpoint copy (devmem/storage/interim_day1/<arm>/sim, or any folder with personas/ and reverie/meta.json) and its day-3 checkpoint (made by the runner,
reverie/.../storage/p7_<arm>__ckpt_day3_end_awake). Retrieval runs on temporary COPIES with real embeddings (identical top-k for both arms). Calls: purposes eval_recall, eval_probe and
eval_judge, sequential (about 113 calls for the staged side including the calibration, about 93 for the baseline side), the pinned model, the router's 3-key limit and backoff.
Output: devmem/storage/phase9_eval/<arm>/evaluation.json (answers, grades, judge labels) and a one-line summary. Everything is labelled with the arm, the checkpoint steps and the clocks.

    cd reverie/reverie/backend_server && python -m devmem.eval.phase9.run_arm_evaluation --arm staged [--stub]
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
SIM = ROOT / "reverie" / "environment" / "frontend_server" / "storage"


def _load_persona(sim_dir: Path, name: str):
    from persona.persona import Persona
    return Persona(name, str(sim_dir / "personas" / name))


def _copy(src: Path, tmp: Path) -> Path:
    d = tmp / src.name
    shutil.copytree(src, d)
    return d


def run(arm: str, day1: Path, day3: Path, call_fn, out_dir: Path = None, stub: bool = False, load_persona=None, retrieve_fn=None) -> dict:
    from devmem.eval.phase9 import answer_harness, judge
    questions = json.loads((ROOT / "docs" / "phase7_stop1_events_questions.json").read_text(encoding="utf-8"))
    recall_q = questions["questions"]
    probe_q = [{"id": p["id"], "question": p["text"], "checklist": None} for p in questions["probe_questions"]]
    tmp = Path(tempfile.mkdtemp(prefix=f"p9_eval_{arm}_"))
    res = {"arm": arm, "label": "Phase 9 evaluation of one arm; single run per arm", "stub": stub, "started": time.strftime("%Y-%m-%d %H:%M:%S"), "recall": [], "probe_day1": [], "probe_day3": [], "judge": []}
    try:
        d1, d3 = _copy(day1, tmp), _copy(day3, tmp)
        meta3 = json.loads((d3 / "reverie" / "meta.json").read_text(encoding="utf-8"))
        res["day3_checkpoint"] = {"step": meta3["step"], "curr_time": meta3["curr_time"]}
        res["day1_checkpoint"] = {"step": json.loads((d1 / "reverie" / "meta.json").read_text(encoding="utf-8"))["step"]}
        for name in meta3["persona_names"]:
            p1, p3 = (load_persona or _load_persona)(d1, name), (load_persona or _load_persona)(d3, name)
            mine = [q for q in recall_q if q["agent"] == name]
            res["recall"] += answer_harness.answer_questions(name, mine, lambda p: call_fn(p, "eval_recall"), persona=p3, retrieve_fn=retrieve_fn)
            res["probe_day1"] += answer_harness.answer_questions(name, probe_q, lambda p: call_fn(p, "eval_probe"), persona=p1, retrieve_fn=retrieve_fn)
            res["probe_day3"] += answer_harness.answer_questions(name, probe_q, lambda p: call_fn(p, "eval_probe"), persona=p3, retrieve_fn=retrieve_fn)
        by1 = {(a["agent"], a["question_id"]): a for a in res["probe_day1"]}
        pairs = [{"agent": a["agent"], "question_id": a["question_id"], "question": next(q["question"] for q in probe_q if q["id"] == a["question_id"]),
                  "day1_answer": by1[(a["agent"], a["question_id"])]["answer"], "day3_answer": a["answer"]} for a in res["probe_day3"]]
        res["judge"] = judge.judge_pairs(pairs, lambda prompt: call_fn(prompt, "eval_judge"))
        res["counts"] = {"recall": len(res["recall"]), "probe_day1": len(res["probe_day1"]), "probe_day3": len(res["probe_day3"]), "judge_pairs": len(res["judge"]),
                         "judge_parse_failures": sum(1 for j in res["judge"] if j["judge_label"] is None)}
        if out_dir:
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "evaluation.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
        return res
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True, choices=["baseline", "staged"])
    ap.add_argument("--stub", action="store_true", help="no chat call, no arm check: answers are a fixed string (embeddings are still real, on --stub-embedding-key)")
    ap.add_argument("--day1", help="day-1 checkpoint copy folder (default devmem/storage/interim_day1/<arm>/sim)")
    ap.add_argument("--day3", help="day-3 checkpoint folder (default the runner's p7_<arm>__ckpt_day3_end_awake)")
    ap.add_argument("--stub-embedding-key", help="env NAME of one embedding key for the stub run (never printed)")
    a = ap.parse_args()
    sys.path.insert(0, str(ROOT))
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    os.environ.setdefault("DEVMEM_EMBEDDING_MODE", "live")
    day1 = Path(a.day1) if a.day1 else ROOT / "devmem" / "storage" / "interim_day1" / a.arm / "sim"
    day3 = Path(a.day3) if a.day3 else SIM / f"p7_{a.arm}__ckpt_day3_end_awake"
    import persona.prompt_template.gpt_structure as gs
    from devmem.embeddings.vector_store import EmbeddingStore
    if a.stub:
        keys = [a.stub_embedding_key] if a.stub_embedding_key else None
        gs._EMBEDDING_STORE = EmbeddingStore(stats_path=Path(tempfile.mkdtemp()) / "s.json", key_envs=keys)
        call_fn = lambda prompt, purpose: "stub answer (no chat call)" if purpose != "eval_judge" else "consistent"
        out_dir = ROOT / "devmem" / "storage" / "phase9_eval" / f"{a.arm}_stub"
    else:
        from devmem.eval import run_arm
        from devmem.eval.phase9 import eval_keys
        from devmem.router import llm_router
        cfg = eval_keys.provider_config(a.arm, Path(tempfile.mkdtemp(prefix="p9_eval_cfg_")) / "providers.yaml")      # raises ArmStillRunning unless the arm has finished
        pool = eval_keys.pool(a.arm)
        eval_keys.assert_no_running_arm_key(pool, [x for x in ("baseline", "staged") if x != a.arm and not eval_keys.finished(x)] + [])
        os.environ["DEVMEM_PINNED_MODEL"] = run_arm.MODEL
        os.environ.setdefault("DEVMEM_OUTPUT_NORMALIZER", "on")
        emb_keys = [k for k in run_arm.EMBED_KEYS[a.arm]]
        gs._EMBEDDING_STORE = EmbeddingStore(stats_path=Path(tempfile.mkdtemp()) / "s.json", key_envs=emb_keys)

        def call_fn(prompt, purpose):
            return llm_router.call_llm(prompt, tier="fast", purpose=purpose, condition=f"eval_{a.arm}_keys", config_path=str(cfg), pinned_model=run_arm.MODEL, max_tokens=300)
        out_dir = ROOT / "devmem" / "storage" / "phase9_eval" / a.arm
    res = run(a.arm, day1, day3, call_fn, out_dir=out_dir, stub=a.stub)
    print(json.dumps(res["counts"]))


if __name__ == "__main__":
    main()
