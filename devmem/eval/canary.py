"""
Canary evaluator for the first 20 minutes (wall clock) of a Phase 7 or 9 arm run, and the abort criteria WRITTEN DOWN BEFORE LAUNCH.
Reads a run folder only (no network, no LLM, no write to the run). Usage (while the run executes):
    python -m devmem.eval.canary --arm baseline            (reads devmem/storage/p7_baseline and the movement files of the sim folder)

ABORT CRITERIA (any one stops the arm; the operator creates the file ABORT in the run folder and reports):
  A1  an upstream exception that is not cleared by the single allowed --resume;
  A2  injection: with at least 3 events resolved, fewer than 90 percent PASS, or any `pivotal` event FAIL;
  A3  schedule adherence: for any agent, fewer than 85 percent of the steps in a finished authored entry carry that entry's text
      (a decomposed subtask begins with the entry text, a sleep step says sleeping) once at least 60 simulated minutes have been checked;
  A4  router failures above 1 percent of the calls so far (ROUTER_FAILURES in run_status.json) or any fail-safe scoring above 2 percent;
  A5  night-key anomaly: a consolidation marker whose night is not 0 or the simulated day of its sweep time, or a marker for night k written
      at an hour other than 14 (the first sleeping tick of the block) for k above 0, or a negative night in a run that has not exited;
  A6  call rate: more than 1.5 times the budgeted 110 calls per awake agent-hour averaged over at least 4 awake simulated hours;
  A7  integrity: any raw-reply record whose model is not the pinned model, any Groq or NIM provider in the ledger for this arm, or any chat
      key above 450 requests in the quota day;
  A8  ledger or status: no hourly ledger window for a simulated hour that has elapsed, or an agent asleep for more than two consecutive
      windows that the authored schedule says are awake;
  A9  cross-arm (checked when both arms have run the same simulated time): an injection logged at a different step in the two arms.
`evaluate()` implements A2 to A8 on the files; A1 and A9 are read from the run reports and by `compare_injections()`.
"""
import argparse
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent.parent
START = datetime(2023, 2, 13, 0, 0, 0)
SEC_PER_STEP = 10
BUDGET_CALLS_PER_AWAKE_AGENT_HOUR = 110


def _jsonl(path: Path) -> List[Dict[str, Any]]:
    try:
        return [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
    except OSError:
        return []


def adherence(movement_dir: Path, schedules: Dict[str, Any], upto_step: int) -> Dict[str, Any]:
    """Per agent: share of steps whose recorded description carries the authored entry active at that minute (only entries that have ended)."""
    out: Dict[str, Dict[str, int]] = {n: {"checked": 0, "match": 0} for n in schedules["agents"]}
    day_cache = {}
    for step in range(0, upto_step):
        f = Path(movement_dir) / f"{step}.json"
        if not f.exists():
            continue
        clock = START + timedelta(seconds=SEC_PER_STEP * step)
        day = min((clock.date() - START.date()).days + 1, 3)
        minute = clock.hour * 60 + clock.minute
        data = json.loads(f.read_text(encoding="utf-8"))["persona"]
        for name, a in schedules["agents"].items():
            entries = day_cache.setdefault((name, day), [])
            if not entries:
                t = 0
                for d, m in a[f"day_{day}"]:
                    entries.append((t, t + m, d))
                    t += m
            cur = next(((s, e, d) for s, e, d in entries if s <= minute < e), None)
            if cur is None:
                continue
            desc = str((data.get(name) or {}).get("description") or "").lower()
            want = cur[2].lower()
            out[name]["checked"] += 1
            out[name]["match"] += 1 if (desc.startswith(want) or ("sleep" in want and "sleep" in desc)) else 0
    return {n: {**v, "rate": (round(v["match"] / v["checked"], 3) if v["checked"] else None)} for n, v in out.items()}


def evaluate(run_dir: Path, sim_dir: Path, schedules: Dict[str, Any], arm: str, pinned_model: str = "gemini-3.1-flash-lite") -> Dict[str, Any]:
    run_dir, sim_dir = Path(run_dir), Path(sim_dir)
    checks: Dict[str, Dict[str, Any]] = {}
    abort: List[str] = []
    status = {}
    try:
        status = json.loads((run_dir / "run_status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        abort.append("A8: no run_status.json")
    step = int(status.get("step", 0) or 0)

    inj = _jsonl(run_dir / "injection_log.jsonl")
    passed = sum(1 for r in inj if r["result"] == "PASS")
    ok = True
    if len(inj) >= 3 and passed / len(inj) < 0.9:
        ok = False
        abort.append(f"A2: only {passed} of {len(inj)} injected events were perceived and stored")
    if any(r["type"] == "pivotal" and r["result"] == "FAIL" for r in inj):
        ok = False
        abort.append("A2: a pivotal event was not perceived")
    checks["injection"] = {"ok": ok, "resolved": len(inj), "pass": passed, "fail": [r["id"] for r in inj if r["result"] == "FAIL"]}

    adh = adherence(sim_dir / "movement", schedules, step) if step else {}
    ok = True
    for n, v in adh.items():
        if v["checked"] >= 360 and v["rate"] is not None and v["rate"] < 0.85:
            ok = False
            abort.append(f"A3: {n} follows the authored schedule in only {v['rate']:.0%} of {v['checked']} checked steps")
    checks["schedule_adherence"] = {"ok": ok, "per_agent": adh}

    windows = _jsonl(run_dir / "hourly_ledger.jsonl")
    hours_elapsed = step // 360
    ok = len([w for w in windows if w["label"].startswith("hour_ending")]) >= max(0, hours_elapsed - 1)
    if not ok:
        abort.append(f"A8: {len([w for w in windows if w['label'].startswith('hour_ending')])} hourly ledger windows for {hours_elapsed} elapsed simulated hours")
    checks["ledger_windows"] = {"ok": ok, "windows": len(windows), "hours_elapsed": hours_elapsed}

    rf = status.get("router_failures")
    calls = status.get("router_calls_total") or 0
    ok = not (rf is not None and calls and rf / calls > 0.01)
    if not ok:
        abort.append(f"A4: {rf} router failures in {calls} calls")
    checks["router_failures"] = {"ok": ok, "failures": rf, "calls": calls}

    # every ledger window counts (hourly and the partial windows a resume or a stop leaves), each weighted by its own length in steps:
    # awake agent-hours = sum over agents of (1 - sleeping fraction) * steps in window / 360 (pilot finding 2026-10-07: counting only whole
    # hourly windows gave 58 and 87 where the cumulative calls per awake agent-hour were about 160 to 210)
    awake_agent_hours, awake_calls = 0.0, 0
    for w in windows:
        hrs = sum(1 - (f or 0) for f in (w.get("sleeping_step_fraction") or {}).values()) * (w.get("steps_in_window") or 0) / 360.0
        if hrs > 0:
            awake_agent_hours += hrs
            awake_calls += w["calls"]
    rate = (awake_calls / awake_agent_hours) if awake_agent_hours else None
    ok = not (rate is not None and awake_agent_hours >= 4 and rate > 1.5 * BUDGET_CALLS_PER_AWAKE_AGENT_HOUR)
    if not ok:
        abort.append(f"A6: {rate:.0f} calls per awake agent-hour against a budget of {BUDGET_CALLS_PER_AWAKE_AGENT_HOUR}")
    checks["call_rate"] = {"ok": ok, "calls_per_awake_agent_hour": round(rate, 1) if rate else None, "awake_agent_hours": round(awake_agent_hours, 2)}

    bad_models = [r["model"] for r in _jsonl(run_dir / "raw_replies.jsonl") if r.get("model") != pinned_model]
    ok = not bad_models
    if not ok:
        abort.append(f"A7: {len(bad_models)} raw-reply records with a model other than {pinned_model}")
    checks["pinned_model_only"] = {"ok": ok, "other_model_records": len(bad_models)}

    db = run_dir / "memory.db"
    nights = []
    if db.exists():
        c = sqlite3.connect(f"file:{db.resolve().as_posix()}?mode=ro", uri=True)
        try:
            nights = c.execute("SELECT agent_id, night, sweep_time FROM consolidation_sweeps").fetchall()
        except sqlite3.Error:
            nights = []
        finally:
            c.close()
    ok = True
    for agent, night, st in nights:
        t = datetime.strptime(st, "%Y-%m-%d %H:%M:%S")
        day = (t.date() - START.date()).days + 1
        if night < 0:
            continue
        if night > 0 and not (night == day and t.hour == 14):
            ok = False
            abort.append(f"A5: {agent} night {night} marker written at {st} (expected 14:00 of day {night})")
        if night == 0 and not (t.hour < 12):
            ok = False
            abort.append(f"A5: {agent} night 0 marker written at {st}")
    checks["night_keys"] = {"ok": ok, "markers": [[a, n, s] for a, n, s in nights]}
    return {"arm": arm, "sim_step": step, "checks": checks, "abort": abort, "all_ok": not abort}


def compare_injections(run_dir_a: Path, run_dir_b: Path) -> Dict[str, Any]:
    a = {r["id"]: r for r in _jsonl(Path(run_dir_a) / "injection_log.jsonl")}
    b = {r["id"]: r for r in _jsonl(Path(run_dir_b) / "injection_log.jsonl")}
    diff = [i for i in set(a) & set(b) if a[i]["injected_step"] != b[i]["injected_step"]]
    return {"common_events": len(set(a) & set(b)), "different_step": sorted(diff), "ok": not diff}


def main():
    from devmem.eval import checks as ck
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True)
    ap.add_argument("--sim")
    a = ap.parse_args()
    sim = a.sim or f"p7_{a.arm}"
    import utils  # noqa: F401  (needs the backend path; run through the runner environment)
    out = evaluate(ROOT / "devmem" / "storage" / sim, Path(utils.fs_storage) / sim, ck.load(ck.SCHEDULES), a.arm)
    print(json.dumps(out, indent=1))
    raise SystemExit(0 if out["all_ok"] else 1)


if __name__ == "__main__":
    main()
