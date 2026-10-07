"""
Arm supervisor (operational measure, disclosed): keeps one arm running through crashes and kills.

It starts `python -m devmem.eval.run_arm --arm <arm> [--pilot]` and watches the child.
  * A clean end (outcome "reached ...", "soft stop ...", "HARD CAP ...", "ABORT ...", "aborted by the operator ...", or "completed"): stop.
  * An A1 exit (outcome "upstream exception ...") or a child that died without writing a fresh report (killed, reboot of the child only):
    resume with `--resume` from the last autosave, at most MAX_RESUMES_PER_SIM_DAY resumes per simulated day. Every start, exit, resume and
    abort is appended to `<run dir>/resume_log.jsonl`.
  * If the same step crashes twice in a row, or the per-day limit is exceeded, the supervisor creates the ABORT file and stops.
It resumes only what upstream's own autosave allows; it patches nothing and retries no call. If the machine itself reboots the supervisor dies
with the child: relaunch it (it resumes by itself when the run folder already holds state).
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent.parent
MAX_RESUMES_PER_SIM_DAY = 3
FINAL_PREFIXES = ("reached ", "soft stop", "HARD CAP", "ABORT", "aborted by the operator", "completed", "wall-clock stop", "a key reached")


def _log(run_dir: Path, rec: Dict) -> None:
    rec = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), **rec}
    with open(run_dir / "resume_log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def _fresh_report(run_dir: Path, since: float) -> Optional[Dict]:
    best = None
    for f in run_dir.glob("arm_report_*.json"):
        if f.stat().st_mtime >= since and (best is None or f.stat().st_mtime > best[0]):
            best = (f.stat().st_mtime, f)
    return json.loads(best[1].read_text(encoding="utf-8")) if best else None


def _status(run_dir: Path) -> Dict:
    try:
        return json.loads((run_dir / "run_status.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def supervise(run_dir: Path, build_cmd: Callable[[bool], List[str]], max_resumes: int = MAX_RESUMES_PER_SIM_DAY, pause_s: float = 20.0) -> str:
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    resume = (run_dir / "arm_state.json").exists()
    per_day: Dict[str, int] = {}
    last_crash_step = None
    while True:
        t0 = time.time()
        _log(run_dir, {"event": "start", "resume": resume})
        rc = subprocess.call(build_cmd(resume), cwd=str(ROOT))
        report = _fresh_report(run_dir, t0)
        outcome = (report or {}).get("outcome")
        st = _status(run_dir)
        clock = (report or {}).get("final_clock") or st.get("sim_clock") or ""
        step = (report or {}).get("final_step", st.get("step"))
        _log(run_dir, {"event": "exit", "returncode": rc, "outcome": outcome, "sim_clock": clock, "step": step, "report": report is not None})
        if outcome and outcome.startswith(FINAL_PREFIXES):
            _log(run_dir, {"event": "final", "outcome": outcome})
            return "final"
        if (run_dir / "ABORT").exists():
            # an operator ABORT raised mid-call can surface as an upstream exception (upstream's bare `except:` swallows the gate's RunAborted three
            # times and the caller indexes None; seen on the pilot baseline, 2026-10-07): never resume over an ABORT file
            _log(run_dir, {"event": "final", "outcome": "ABORT file present after the exit"})
            return "final"
        day = str(clock)[:10] or "unknown"
        per_day[day] = per_day.get(day, 0) + 1
        crashed_here = step if report else None   # a kill has no crash step to compare
        if crashed_here is not None and crashed_here == last_crash_step:
            (run_dir / "ABORT").write_text("same step crashed twice in a row\n", encoding="utf-8")
            _log(run_dir, {"event": "abort", "reason": "same step crashed twice", "step": step})
            return "abort_same_step"
        if per_day[day] > max_resumes:
            (run_dir / "ABORT").write_text(f"more than {max_resumes} resumes on sim day {day}\n", encoding="utf-8")
            _log(run_dir, {"event": "abort", "reason": f"more than {max_resumes} resumes on sim day {day}"})
            return "abort_per_day_limit"
        last_crash_step = crashed_here
        _log(run_dir, {"event": "resume", "sim_day": day, "resumes_on_this_day": per_day[day], "from": "last autosave"})
        resume = True
        time.sleep(pause_s)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True, choices=["baseline", "staged"])
    ap.add_argument("--pilot", action="store_true")
    ap.add_argument("--sim")
    ap.add_argument("--pause", type=float, default=20.0)
    a = ap.parse_args(argv)
    sim = a.sim or (f"p7pilot_{a.arm}" if a.pilot else f"p7_{a.arm}")

    def build(resume: bool) -> List[str]:
        cmd = [sys.executable, "-m", "devmem.eval.run_arm", "--arm", a.arm, "--sim", sim]
        return cmd + (["--pilot"] if a.pilot else []) + (["--resume"] if resume else [])
    print(supervise(ROOT / "devmem" / "storage" / sim, build, pause_s=a.pause))


if __name__ == "__main__":
    main()
