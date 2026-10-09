"""
Chain of the live and offline steps for the BASELINE arm (PM order 2026-10-08, revised at night):
it STARTS AT ONCE when the baseline has passed its day-3 primary checkpoint (step 22,410: checkpoint "day3_end_awake" in run_status, or the arm finished), while the baseline is still running
its last night, and then runs:
  1. check that the day-3 PRIMARY checkpoint copy of the baseline exists, is complete and parses (the external copier writes it; this step waits up to 30 minutes, never writes to a run);
  2. baseline day-3 evaluation (recall, probes, judge; 93 calls) on a FINISHED arm's pool: the staged pool when the staged arm has finished, else the baseline pool once the baseline has
     finished (the step is held until one of the two is free; the key guard of eval_keys still refuses a pool whose arm is running);
  3. results export for day 3 (`results_export --day 3`: the full comparison, scored predictions; PARTIAL if a staged part is missing);
  4. check that the day-3 SECONDARY (23:45) copy exists and parses;
  5. the baseline 23:45 day-2 sensitivity evaluation (pre-registration 7g), last, on the same kind of pool.
Same rules as the staged chain: one process per step, an existing output file skips the step, the chain stops at the first failure, one line per event goes to
devmem/storage/phase9_eval/chain_status.jsonl with chain="baseline". The held staged steps (replay controls, embedding fetch, staged day-2 evaluations) are released when this chain has ended.

    python -m devmem.eval.phase9.run_baseline_chain [--poll 60] [--dry-run]
    python -m devmem.eval.phase9.run_baseline_chain --check-copies [--primary-only] [--out NAME]      (steps 1 and 4 on their own)
"""
import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

from devmem.eval.phase9 import run_staged_chain as C

ROOT = C.ROOT
OUT = C.OUT
BACKEND = C.BACKEND
POOL_HOLD = "evaluation_pool_available"


def baseline_day3_primary_exists(storage: Path = None, sim_root: Path = None) -> bool:
    """True when the baseline's day-3 primary checkpoint exists. run_status.json is rewritten only at the hourly windows, so it can lag the checkpoint by up to a simulated hour (seen at 05:43 on
    2026-10-09); the runner's checkpoint folder is therefore checked first."""
    st = storage or ROOT / "devmem" / "storage"
    sim = sim_root or ROOT / "reverie" / "environment" / "frontend_server" / "storage"
    if (sim / "p7_baseline__ckpt_day3_end_awake" / "reverie" / "meta.json").exists():
        return True
    try:
        rs = json.loads((st / "p7_baseline" / "run_status.json").read_text(encoding="utf-8"))
    except Exception:
        return False
    return "day3_end_awake" in (rs.get("checkpoints_made") or []) or str(rs.get("state", "")).startswith("finished")


def pool_arm(finished=None):
    """The finished arm whose key pool the evaluation uses: the staged pool when the staged arm has finished, else the baseline pool (None while neither has finished)."""
    if finished is None:
        from devmem.eval.phase9 import eval_keys
        finished = eval_keys.finished
    if finished("staged"):
        return "staged"
    if finished("baseline"):
        return "baseline"
    return None


def copies_ready(arm: str = "baseline", storage: Path = None, wait_s: float = 0.0, poll: float = 5.0, primary_only: bool = False) -> Dict[str, Any]:
    st = storage or ROOT / "devmem" / "storage"
    t0 = time.time()
    kinds = [("day3_primary", "interim_day3", 22410)] + ([] if primary_only else [("day3_secondary_2345", "interim_day3_secondary", 25830)])
    while True:
        res: Dict[str, Any] = {"arm": arm, "copies": {}}
        for kind, folder, step in kinds:
            d = st / folder / arm
            item: Dict[str, Any] = {"path": str(d), "exists": (d / "checkpoint.json").exists()}
            if item["exists"]:
                meta = json.loads((d / "checkpoint.json").read_text(encoding="utf-8"))
                bad = []
                for f in (d / "sim").rglob("*.json"):
                    try:
                        json.loads(f.read_text(encoding="utf-8"))
                    except Exception:
                        bad.append(f.relative_to(d).as_posix())
                item.update({"step": meta.get("step"), "sim_clock": meta.get("sim_clock"), "exact_first_autosave": meta.get("exact_first_autosave"), "json_files_not_parsing": bad,
                             "memory_db": (d / "memory.db").exists(), "complete": not bad})
            res["copies"][kind] = item
        res["all_ready"] = all(v.get("exists") and v.get("complete") for v in res["copies"].values())
        if res["all_ready"] or time.time() - t0 >= wait_s:
            return res
        time.sleep(poll)


def _eval_args(extra):
    def fn():
        return ["-m", "devmem.eval.phase9.run_arm_evaluation", "--arm", "baseline"] + extra + ["--pool-arm", pool_arm()]
    return fn


SECONDARY_COPY = str(ROOT / "devmem" / "storage" / "interim_day2_secondary_repaired" / "baseline" / "sim")
STEPS: List[Dict] = [
    {"name": "baseline_checkpoint_copies_ready", "args": ["-m", "devmem.eval.phase9.run_baseline_chain", "--check-copies", "--primary-only"], "output": OUT / "baseline_copies_ready.json", "cwd": ROOT},
    {"name": "baseline_day3_evaluation", "hold": POOL_HOLD, "args": ["-m", "devmem.eval.phase9.run_arm_evaluation", "--arm", "baseline", "--pool-arm", "<staged if finished, else baseline>"],
     "args_fn": _eval_args([]), "output": OUT / "baseline" / "evaluation.json", "cwd": BACKEND},
    {"name": "results_export_day3", "args": ["-m", "devmem.eval.phase9.results_export", "--day", "3"], "output": ROOT / "docs" / "phase9_results_export_day3.json", "cwd": BACKEND},
    {"name": "baseline_secondary_copy_ready", "args": ["-m", "devmem.eval.phase9.run_baseline_chain", "--check-copies", "--out", "baseline_copies_secondary_ready.json"],
     "output": OUT / "baseline_copies_secondary_ready.json", "cwd": ROOT},
    # sensitivity analysis (pre-registration 7g), last: the baseline 23:45 copy, Isabella's embeddings repaired
    {"name": "baseline_day2_secondary_evaluation", "hold": POOL_HOLD, "args": ["-m", "devmem.eval.phase9.run_arm_evaluation", "--arm", "baseline", "--day", "2", "--tag", "secondary", "--day3", SECONDARY_COPY,
                                                                          "--pool-arm", "<staged if finished, else baseline>"],
     "args_fn": _eval_args(["--day", "2", "--tag", "secondary", "--day3", SECONDARY_COPY]), "output": OUT / "baseline_day2_secondary" / "evaluation.json", "cwd": BACKEND},
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--poll", type=float, default=60.0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check-copies", action="store_true")
    ap.add_argument("--primary-only", action="store_true")
    ap.add_argument("--out", default="baseline_copies_ready.json")
    a = ap.parse_args()
    sys.path.insert(0, str(ROOT))
    if a.check_copies:
        res = copies_ready("baseline", wait_s=1800, primary_only=a.primary_only)
        OUT.mkdir(parents=True, exist_ok=True)
        if res["all_ready"]:
            (OUT / a.out).write_text(json.dumps(res, indent=1), encoding="utf-8")
        print(json.dumps(res))
        sys.exit(0 if res["all_ready"] else 1)
    if a.dry_run:
        for s in STEPS:
            print(s["name"], " ".join(s["args"]), "->", s["output"], "(exists)" if Path(s["output"]).exists() else "", ("HOLD " + s["hold"]) if s.get("hold") else "")
        return
    C.run_chain(baseline_day3_primary_exists, C._subprocess_run, OUT / "chain_status.jsonl", steps=STEPS, poll=a.poll, chain="baseline",
                hold_fns={POOL_HOLD: lambda: pool_arm() is not None}, start_event="baseline_day3_primary_chain_starts")


if __name__ == "__main__":
    main()
