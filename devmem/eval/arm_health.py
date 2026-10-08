"""
Dead-arm detector (read-only). Usage: python -m devmem.eval.arm_health [--pilot] [--stale-seconds 300]

For each arm it reports: whether a run_arm process for that arm exists, the age of the newest movement file (written every simulated step, so
a live arm refreshes it every few seconds, awake or asleep), the age of the newest raw reply, the saved simulation clock, the last line of
resume_log.jsonl, and a verdict: RUNNING, DEAD (no process or a stale heartbeat while the run is not finished), FINISHED or ABORTED.
Exit code 0 when every arm is RUNNING or FINISHED, 1 otherwise, so a scheduler or a shell loop can act on it. It never writes anything.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SIM_STORAGE = ROOT / "reverie" / "environment" / "frontend_server" / "storage"


def _processes() -> str:
    try:
        out = subprocess.check_output(["powershell", "-NoProfile", "-Command",
                                       "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*devmem.eval.run_arm*' } | "
                                       "ForEach-Object { $_.CommandLine }"], text=True, timeout=60)
        return out
    except Exception:
        return ""


def _age(path: Path) -> float:
    return time.time() - path.stat().st_mtime if path.exists() else float("inf")


def _last(path: Path):
    if not path.exists():
        return None
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    return json.loads(lines[-1]) if lines else None


def _waiting(run_dir: Path):
    """PAUSED_QUOTA when the last quota event is a pause whose wake time is in the future (UTC), WAITING_NETWORK when an outage is open."""
    from datetime import datetime
    o = _last(run_dir / "outage_log.jsonl")
    if o and o.get("event") == "outage_start":
        return "WAITING_NETWORK"
    rl = _last(run_dir / "rate_limit_log.jsonl")
    if rl and rl.get("event") in ("rate_limit_start", "rate_limit_backoff"):
        return "WAITING_RATE_LIMIT"
    pz = _last(run_dir / "pause_log.jsonl")
    if pz and pz.get("event") == "pause_start":
        return "PAUSED_BY_OPERATOR"
    q = _last(run_dir / "quota_pauses.jsonl")
    if q and q.get("event") == "pause":
        try:
            if datetime.fromisoformat(q["wake"]) > datetime.utcnow():
                return "PAUSED_QUOTA"
        except Exception:
            pass
    return None


def check(arm: str, pilot: bool, stale: float, procs: str) -> dict:
    sim = f"p7pilot_{arm}" if pilot else f"p7_{arm}"
    run_dir = ROOT / "devmem" / "storage" / sim
    mov = SIM_STORAGE / sim / "movement"
    newest = max((p.stat().st_mtime for p in mov.glob("*.json")), default=0) if mov.is_dir() else 0
    st = json.loads((run_dir / "run_status.json").read_text(encoding="utf-8")) if (run_dir / "run_status.json").exists() else {}
    alive = any(f"--arm {arm}" in l and (("--pilot" in l) == pilot) for l in procs.splitlines())
    hb = time.time() - newest if newest else float("inf")
    state = str(st.get("state", ""))
    waiting = _waiting(run_dir) if alive else None
    if (run_dir / "ABORT").exists() and not alive:
        verdict = "ABORTED"
    elif alive and waiting:
        verdict = waiting                      # PAUSED_QUOTA or WAITING_NETWORK: the process is alive and deliberately idle
    elif state.startswith("finished") and not alive:
        verdict = "FINISHED"
    elif alive and hb < stale:
        verdict = "RUNNING"
    else:
        verdict = "DEAD"
    log = run_dir / "resume_log.jsonl"
    last = log.read_text(encoding="utf-8").splitlines()[-1] if log.exists() and log.read_text(encoding="utf-8").strip() else None
    return {"arm": arm, "sim": sim, "verdict": verdict, "process": alive, "heartbeat_age_s": round(hb) if hb != float("inf") else None,
            "raw_reply_age_s": round(_age(run_dir / "raw_replies.jsonl")) if (run_dir / "raw_replies.jsonl").exists() else None,
            "status_clock": st.get("sim_clock"), "status_state": state[:80], "calls": st.get("router_calls_total"), "last_resume_log": last}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", action="store_true")
    ap.add_argument("--stale-seconds", type=float, default=300)
    a = ap.parse_args(argv)
    procs = _processes()
    rows = [check(arm, a.pilot, a.stale_seconds, procs) for arm in ("baseline", "staged")]
    print(json.dumps(rows, indent=1))
    return 0 if all(r["verdict"] in ("RUNNING", "FINISHED", "PAUSED_QUOTA", "WAITING_NETWORK", "PAUSED_BY_OPERATOR", "WAITING_RATE_LIMIT") for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
