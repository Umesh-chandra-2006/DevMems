"""
Chain of the live evaluation steps that run on the STAGED arm's own key pool once the staged arm has FINISHED, in the order the PM fixed (2026-10-08):
  1. staged day-3 evaluation (recall, probes, judge; 93 calls)
  2. judge calibration (20 authored pairs)
  3. staged day-2 primary evaluation follows step 3 (staged pool, registered 14:15 copy as taken; its Maria and Klaus persona files are one save old, disclosed)
  3. baseline day-2 interim evaluation on the staged pool (--pool-arm staged --day 2; 78 calls; refuses unless the staged arm has finished), on the REPAIRED baseline day-2 copy
     (interim_day2_repaired/baseline: the original copy has a truncated embeddings.json for two personas; see repair_copy.py)
  4. staged replay controls (stratified sample, 300 events x 3 conditions; seed 20261008)
  5. embedding fetch for D-1 (traits, their sources, the priors) and for any entry vector D-2 found missing, gemini-embedding-001, staged embedding keys, cache first
Each step is a separate process (the existing, tested scripts). A step whose output file already exists is skipped (re-run safe). The chain stops at the first failing step and
records it; nothing is retried or skipped silently. One line per event goes to devmem/storage/phase9_eval/chain_status.jsonl (and stdout), so each result can be reported as it is
written. It makes no call itself and uses no key; it waits (polling) until eval_keys.finished("staged").

    python -m devmem.eval.phase9.run_staged_chain [--poll 60] [--dry-run]
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent.parent.parent
OUT = ROOT / "devmem" / "storage" / "phase9_eval"
BACKEND = ROOT / "reverie" / "reverie" / "backend_server"
PY = sys.executable

HOLD = "baseline_past_day3_primary_and_its_chain_ended"
STEPS: List[Dict] = [
    {"name": "staged_day3_evaluation", "args": ["-m", "devmem.eval.phase9.run_arm_evaluation", "--arm", "staged"], "output": OUT / "staged" / "evaluation.json", "cwd": BACKEND},
    {"name": "judge_calibration", "args": ["-m", "devmem.eval.phase9.run_judge_calibration", "--poll", "5"], "output": OUT / "judge_calibration.json", "cwd": ROOT},
    {"name": "baseline_day2_evaluation_on_staged_pool", "args": ["-m", "devmem.eval.phase9.run_arm_evaluation", "--arm", "baseline", "--day", "2", "--pool-arm", "staged", "--day3", str(ROOT / "devmem" / "storage" / "interim_day2_repaired" / "baseline" / "sim")],
     "output": OUT / "baseline_day2" / "evaluation.json", "cwd": BACKEND},
    {"name": "staged_day2_evaluation", "hold": "baseline_past_day3_primary_and_its_chain_ended", "args": ["-m", "devmem.eval.phase9.run_arm_evaluation", "--arm", "staged", "--day", "2", "--day3", str(ROOT / "devmem" / "storage" / "interim_day2_repaired" / "staged" / "sim")], "output": OUT / "staged_day2" / "evaluation.json", "cwd": BACKEND},
    {"name": "staged_replay_controls", "hold": "baseline_past_day3_primary_and_its_chain_ended", "args": ["-m", "devmem.eval.phase9.run_replay_controls"], "output": OUT / "replay_controls.json", "cwd": ROOT},
    {"name": "d1_d2_embedding_fetch", "hold": "baseline_past_day3_primary_and_its_chain_ended", "args": ["-m", "devmem.eval.phase9.fetch_embeddings"], "output": OUT / "fetch_embeddings.json", "cwd": ROOT},
    # sensitivity analysis (pre-registration 7g), always last so that it never delays a day-3 result: the 23:45 copies, Isabella's embeddings repaired the same way in both arms
    {"name": "staged_day2_secondary_evaluation", "hold": "baseline_past_day3_primary_and_its_chain_ended", "args": ["-m", "devmem.eval.phase9.run_arm_evaluation", "--arm", "staged", "--day", "2", "--tag", "secondary", "--day3",
                                                          str(ROOT / "devmem" / "storage" / "interim_day2_secondary_repaired" / "staged" / "sim")], "output": OUT / "staged_day2_secondary" / "evaluation.json", "cwd": BACKEND},
]


def baseline_released(storage: Path = None, status_path: Path = None, now=time.time, grace_s: float = 1800.0) -> bool:
    """The held staged steps are released when the baseline arm has passed its day-3 primary checkpoint (step 22,410) AND the baseline chain has ended (chain_done or a halted step), so
    the replay controls (900 calls) never compete with the baseline for the shared free-tier limit while the baseline is still running its day 3. Fallback: the baseline arm finished more
    than grace_s ago and its chain never ended."""
    st = storage or ROOT / "devmem" / "storage"
    status_path = status_path or OUT / "chain_status.jsonl"
    try:
        rs = json.loads((st / "p7_baseline" / "run_status.json").read_text(encoding="utf-8"))
    except Exception:
        return False
    passed = "day3_end_awake" in (rs.get("checkpoints_made") or []) or str(rs.get("state", "")).startswith("finished")
    if not passed:
        return False
    ended = False
    try:
        for line in Path(status_path).read_text(encoding="utf-8").splitlines():
            e = json.loads(line)
            if e.get("chain") == "baseline" and e.get("event") in ("chain_done", "step_failed_chain_halted"):
                ended = True
    except Exception:
        pass
    if ended:
        return True
    if str(rs.get("state", "")).startswith("finished"):
        try:
            return now() - (st / "p7_baseline" / "run_status.json").stat().st_mtime > grace_s
        except OSError:
            return False
    return False


def _event(status_path: Path, **kw) -> None:
    kw.setdefault("chain", "staged")
    kw["at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    status_path.parent.mkdir(parents=True, exist_ok=True)
    with open(status_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(kw) + "\n")
    print(json.dumps(kw), flush=True)


def run_chain(finished_fn: Callable[[], bool], run_fn: Callable[[Dict], int], status_path: Path, steps: List[Dict] = None, poll: float = 60.0, sleep_fn=time.sleep, chain: str = "staged",
              hold_fns: Dict[str, Callable[[], bool]] = None, start_event: str = None) -> bool:
    """A step may carry "hold": a name in hold_fns; the step does not start until that condition is true (logged once as step_held, then hold_released)."""
    steps = STEPS if steps is None else steps
    hold_fns = hold_fns or {}
    while not finished_fn():
        sleep_fn(poll)
    _event(status_path, event=start_event or f"{chain}_finished_chain_starts", chain=chain)
    for s in steps:
        if Path(s["output"]).exists():
            _event(status_path, chain=chain, event="step_skipped_output_exists", step=s["name"], output=str(s["output"]))
            continue
        if s.get("hold"):
            fn = hold_fns.get(s["hold"])
            if fn is not None and not fn():
                _event(status_path, chain=chain, event="step_held", step=s["name"], hold=s["hold"])
                while not fn():
                    sleep_fn(poll)
                _event(status_path, chain=chain, event="hold_released", step=s["name"], hold=s["hold"])
        _event(status_path, chain=chain, event="step_start", step=s["name"])
        rc = run_fn(s)
        if rc != 0 or not Path(s["output"]).exists():
            _event(status_path, chain=chain, event="step_failed_chain_halted", step=s["name"], returncode=rc, output_exists=Path(s["output"]).exists())
            return False
        _event(status_path, chain=chain, event="step_done", step=s["name"], output=str(s["output"]))
    _event(status_path, chain=chain, event="chain_done")
    return True


def _subprocess_run(step: Dict) -> int:
    if step.get("args_fn"):
        step = dict(step, args=step["args_fn"]())                         # arguments that depend on the state when the step starts (for example which pool is free)
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONPATH=f"{BACKEND}{os.pathsep}{ROOT}")
    log = ROOT / "devmem" / "storage" / "pilot_logs" / f"chain_{step['name']}"
    with open(str(log) + ".log", "a", encoding="utf-8") as o, open(str(log) + ".err", "a", encoding="utf-8") as e:
        return subprocess.call([PY] + step["args"], cwd=str(step["cwd"]), env=env, stdout=o, stderr=e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--poll", type=float, default=60.0)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    sys.path.insert(0, str(ROOT))
    if a.dry_run:
        for s in STEPS:
            print(s["name"], " ".join(s["args"]), "->", s["output"], "(exists)" if Path(s["output"]).exists() else "")
        return
    from devmem.eval.phase9 import eval_keys
    run_chain(lambda: eval_keys.finished("staged"), _subprocess_run, OUT / "chain_status.jsonl", poll=a.poll, hold_fns={HOLD: baseline_released})


if __name__ == "__main__":
    main()
