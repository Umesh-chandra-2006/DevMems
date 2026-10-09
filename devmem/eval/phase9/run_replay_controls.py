"""
Runner for the Stage 2 replay controls on the fixed stratified sample (sample_plan.py, seed 20261008; 27 injected + 273 natural events, 3 conditions, 900 calls at most),
on the FINISHED staged arm's own key pool (eval_keys refuses otherwise), purpose `eval_replay`. The staged condition reuses the run's recorded scores (no call).
Events and the run's own scores come from the staged arm's memory mirror and its injection log. Delivered replies are cached in a jsonl file keyed by the prompt, so a re-run after a
crash makes no repeated call. `--dry-run` reads a given mirror and uses a stub scorer (no call, no key).

    python -m devmem.eval.phase9.run_replay_controls [--dry-run --memory-db PATH --injection-log PATH]
"""
import argparse
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent.parent.parent
CAP = 900
FRICTION_EVENTS = ["I3", "I9", "M3", "M9", "K3", "K9"]


def build_events(memory_db: Path, injection_log: Path, until: str = "2023-02-16 00:00:00"):
    """(natural, injected, own_scores, friction_keys): events as (agent, sim time, text); own_scores maps the same tuple to the run's recorded importance."""
    from devmem.eval.phase9 import interim_day1
    inj_rows = [json.loads(l) for l in Path(injection_log).read_text(encoding="utf-8").splitlines() if l.strip()]
    inj_rows = [r for r in inj_rows if r.get("perceived_and_stored") and r.get("stored_text")]
    nat, ij_all = interim_day1.event_stream(memory_db, [r["stored_text"] for r in inj_rows], until)
    # one row per injected event: the injected agent's earliest mirror row with the stored text at or after the injection clock (the same text is also stored again when the agent perceives it
    # on later steps, and by other agents who see the tile; found 2026-10-09 when 37 rows made 930 calls for 26 injected events and the 900-call cap stopped the step)
    ij = []
    for r in inj_rows:
        cands = sorted(e for e in ij_all if e[0] == r["agent"] and e[2] == r["stored_text"] and e[1] >= r.get("injected_clock", ""))
        if cands:
            ij.append(min(cands, key=lambda e: e[1]))
    c = sqlite3.connect(f"file:{Path(memory_db).as_posix()}?mode=ro", uri=True)
    own = {(a, t, x): s for a, t, x, s in c.execute("SELECT agent_id, sim_timestamp, content, importance_score FROM episodic_memory WHERE sim_timestamp <= ?", (until,)) if s is not None}
    c.close()
    text_to_id = {r["stored_text"]: r["id"] for r in inj_rows}
    friction = {e for e in ij if text_to_id.get(e[2]) in FRICTION_EVENTS}
    return nat, ij, own, friction


def _cached(call_fn: Callable[[str], str], cache_path: Path) -> Callable[[str], str]:
    cache: Dict[str, str] = {}
    if cache_path.exists():
        for line in cache_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                cache[r["k"]] = r["v"]

    def f(prompt: str) -> str:
        k = hashlib.md5(prompt.encode("utf-8")).hexdigest()
        if k not in cache:
            cache[k] = call_fn(prompt)
            with open(cache_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"k": k, "v": cache[k]}) + "\n")
        return cache[k]
    return f


def friction_table(rows: List[Dict[str, Any]], friction: set) -> Dict[str, Any]:
    """Per persona, mean importance of the social-friction events under each condition (staged_own = recorded in the run)."""
    out: Dict[str, Dict[str, List[float]]] = {}
    for r in rows:
        if (r["agent"], r["sim_time"], r["text"]) in friction:
            out.setdefault(r["agent"], {}).setdefault(r["condition"], []).append(float(r["score"]))
    return {a: {c: {"n": len(v), "mean": round(sum(v) / len(v), 3)} for c, v in conds.items()} for a, conds in out.items()}


def run(memory_db: Path, injection_log: Path, call_fn: Callable[[str], str], out_path: Path, label: str, cache_path: Path = None) -> Dict[str, Any]:
    from devmem.eval.phase9 import replay, sample_plan
    nat, ij, own, friction = build_events(memory_db, injection_log)
    sample = sample_plan.build_sample(nat, ij)
    events: List[Tuple[str, str, str]] = [tuple(e) for e in sample["injected"]] + [tuple(e) for e in sample["natural"]]
    if len(events) * len(replay.CONDITIONS) > CAP:
        raise RuntimeError(f"{len(events) * len(replay.CONDITIONS)} calls exceed the cap {CAP}")
    fn = _cached(call_fn, cache_path) if cache_path else call_fn
    res = replay.replay(events, fn, own_scores={e: own[e] for e in events if e in own})
    res.update({"label": label, "seed": sample["seed"], "n_injected": sample["n_injected"], "n_natural": sample["n_natural"], "allocation": sample["allocation"],
                "friction_events_staged_minus_baseline_inputs": friction_table(res["rows"], friction), "calls_made_at_most": len(events) * len(replay.CONDITIONS)})
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--memory-db")
    ap.add_argument("--injection-log")
    a = ap.parse_args()
    sys.path.insert(0, str(ROOT))
    mdb = Path(a.memory_db) if a.memory_db else ROOT / "devmem" / "storage" / "p7_staged" / "memory.db"
    ilog = Path(a.injection_log) if a.injection_log else ROOT / "devmem" / "storage" / "p7_staged" / "injection_log.jsonl"
    out_dir = ROOT / "devmem" / "storage" / "phase9_eval"
    if a.dry_run:
        res = run(mdb, ilog, lambda p: "5", out_dir / "replay_controls_dry_run.json", "DRY RUN (stub scorer, no call)")
        print(json.dumps({"n_injected": res["n_injected"], "n_natural": res["n_natural"], "rows": len(res["rows"])}))
        return
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    from devmem.eval import run_arm
    from devmem.eval.phase9 import eval_keys
    from devmem.router import llm_router
    cfg = eval_keys.provider_config("staged", Path(tempfile.mkdtemp(prefix="p9_replay_cfg_")) / "providers.yaml")      # raises ArmStillRunning unless the staged arm has finished
    pool = eval_keys.pool("staged")
    eval_keys.assert_no_running_arm_key(pool, [x for x in ("baseline", "staged") if not eval_keys.finished(x)])
    os.environ["DEVMEM_PINNED_MODEL"] = run_arm.MODEL
    os.environ.setdefault("DEVMEM_OUTPUT_NORMALIZER", "on")

    def call_fn(prompt: str) -> str:
        return llm_router.call_llm(prompt, tier="fast", purpose="eval_replay", condition="eval_replay_staged_keys", config_path=str(cfg), pinned_model=run_arm.MODEL, max_tokens=150)
    res = run(mdb, ilog, call_fn, out_dir / "replay_controls.json", "Stage 2 replay controls on the fixed sample, staged pool, live", cache_path=out_dir / "replay_cache.jsonl")
    print(json.dumps({"n_injected": res["n_injected"], "n_natural": res["n_natural"], "rows": len(res["rows"]), "by_condition": res["summary"]["by_condition"]}))


if __name__ == "__main__":
    main()
