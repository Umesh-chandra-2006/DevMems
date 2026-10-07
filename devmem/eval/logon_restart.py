"""
At-logon restarter (operational measure, disclosed; approved by the PM on 2026-10-07 with these limits).

Run by the Windows scheduled task "DevMem-FullRun-Restart" when the user logs on (for example after an update restart). For each arm it starts the
supervisor with the same arguments as the launch (which resumes from the last autosave when the run folder holds state) ONLY IF
  * the arm's `run_label.json` mode starts with "FULL" (a PILOT or a missing label is never restarted),
  * there is no ABORT file in the run folder,
  * the run has not ended cleanly (status state "finished: <outcome>" with a final outcome, see supervisor.FINAL_PREFIXES), and
  * no run_arm process for that arm is already running.
It touches nothing else and appends every decision to `devmem/storage/logon_restart.log`. The task is removed when the runs end (README of the run).
"""
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Optional

from devmem.eval import arm_health, supervisor

ROOT = Path(__file__).resolve().parent.parent.parent
LOG = ROOT / "devmem" / "storage" / "logon_restart.log"


def _log(msg: str, log: Path = LOG) -> None:
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")


def decide(run_dir: Path, arm: str, procs: str) -> str:
    """Returns "restart" or the reason not to."""
    try:
        label = json.loads((run_dir / "run_label.json").read_text(encoding="utf-8"))
    except Exception:
        return "skip: no readable run_label.json"
    if not str(label.get("mode", "")).startswith("FULL"):
        return "skip: label is not FULL"
    if (run_dir / "ABORT").exists():
        return "skip: ABORT file present"
    try:
        state = str(json.loads((run_dir / "run_status.json").read_text(encoding="utf-8")).get("state", ""))
    except Exception:
        state = ""
    if state.startswith("finished: ") and state[len("finished: "):].startswith(supervisor.FINAL_PREFIXES):
        return "skip: the run ended cleanly"
    if any(f"--arm {arm}" in l and "--pilot" not in l for l in procs.splitlines()):
        return "skip: an arm process is already running"
    return "restart"


def main(argv=None, popen: Callable = subprocess.Popen, procs: Optional[str] = None, root: Path = ROOT, log: Path = LOG) -> int:
    procs = arm_health._processes() if procs is None else procs
    started = 0
    for arm in ("baseline", "staged"):
        run_dir = root / "devmem" / "storage" / f"p7_{arm}"
        d = decide(run_dir, arm, procs)
        _log(f"{arm}: {d}", log)
        if d == "restart":
            popen([sys.executable, "-m", "devmem.eval.supervisor", "--arm", arm], cwd=str(root), creationflags=0x00000008 | 0x00000200)   # DETACHED_PROCESS | NEW_PROCESS_GROUP
            _log(f"{arm}: supervisor started", log)
            started += 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
