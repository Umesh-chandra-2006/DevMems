"""
Chain of the live and offline steps that run when the BASELINE arm has FINISHED, on the baseline arm's own key pool (PM order 2026-10-08):
  1. check that the day-3 primary and secondary checkpoint copies of the baseline exist, read-only, complete and parse (the external copiers write them; this step waits for them
     up to 30 minutes and never writes to a run);
  2. baseline day-3 evaluation (recall, probes, judge; 93 calls) on the baseline pool, on the runner's own day-3 checkpoint;
  3. results export for day 3 (`results_export --day 3`: the full comparison, scored predictions; PARTIAL if a staged part is missing).
Same rules as the staged chain: one process per step, an existing output file skips the step, the chain stops at the first failure, one line per event goes to
devmem/storage/phase9_eval/chain_status.jsonl with chain="baseline". It makes no call itself; it waits until eval_keys.finished("baseline").

    python -m devmem.eval.phase9.run_baseline_chain [--poll 60] [--dry-run]
    python -m devmem.eval.phase9.run_baseline_chain --check-copies      (step 1 on its own)
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


def copies_ready(arm: str = "baseline", storage: Path = None, wait_s: float = 0.0, poll: float = 5.0) -> Dict[str, Any]:
    st = storage or ROOT / "devmem" / "storage"
    t0 = time.time()
    while True:
        res: Dict[str, Any] = {"arm": arm, "copies": {}}
        for kind, folder, step in (("day3_primary", "interim_day3", 22410), ("day3_secondary_2345", "interim_day3_secondary", 25830)):
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


STEPS: List[Dict] = [
    {"name": "baseline_checkpoint_copies_ready", "args": ["-m", "devmem.eval.phase9.run_baseline_chain", "--check-copies"], "output": OUT / "baseline_copies_ready.json", "cwd": ROOT},
    {"name": "baseline_day3_evaluation", "args": ["-m", "devmem.eval.phase9.run_arm_evaluation", "--arm", "baseline"], "output": OUT / "baseline" / "evaluation.json", "cwd": BACKEND},
    {"name": "results_export_day3", "args": ["-m", "devmem.eval.phase9.results_export", "--day", "3"], "output": ROOT / "docs" / "phase9_results_export_day3.json", "cwd": BACKEND},
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--poll", type=float, default=60.0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check-copies", action="store_true")
    a = ap.parse_args()
    sys.path.insert(0, str(ROOT))
    if a.check_copies:
        res = copies_ready("baseline", wait_s=1800)
        OUT.mkdir(parents=True, exist_ok=True)
        if res["all_ready"]:
            (OUT / "baseline_copies_ready.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
        print(json.dumps(res))
        sys.exit(0 if res["all_ready"] else 1)
    if a.dry_run:
        for s in STEPS:
            print(s["name"], " ".join(s["args"]), "->", s["output"], "(exists)" if Path(s["output"]).exists() else "")
        return
    from devmem.eval.phase9 import eval_keys
    C.run_chain(lambda: eval_keys.finished("baseline"), C._subprocess_run, OUT / "chain_status.jsonl", steps=STEPS, poll=a.poll, chain="baseline")


if __name__ == "__main__":
    main()
