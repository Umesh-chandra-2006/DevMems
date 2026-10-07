"""
Watchdog for the FULL arms (PM-approved 2026-10-08; run every 5 minutes by the Windows task "DevMem-FullRun-Watchdog" and at logon by "DevMem-FullRun-Restart").

For each arm it restarts the SUPERVISOR (which resumes the arm from its last autosave) only when ALL of these hold:
  * the arm's run_label.json mode starts with "FULL";
  * there is no ABORT file and no operator pause (no PAUSE_FOR file, and the last pause_log event is not an open pause_start);
  * the run has not ended cleanly (status state "finished: <final outcome>");
  * no supervisor process for the arm exists (a live supervisor restarts its own arm), and the heartbeat (newest movement file) is stale for more than 300 s;
  * the arm's lock can be taken (an exclusive lock file, so two watchdogs never start two supervisors for one arm);
  * fewer than 6 watchdog restarts of that arm happened in the last hour; the 7th is NOT done: a flag is raised instead (watchdog_flag.json in the run folder and the key
    "watchdog_flag" in run_status.json) and nothing else is touched.
A restart is logged in resume_log.jsonl as event "external_kill_watchdog_restart" (an external kill, not a crash: the supervisor never counts it toward its 3 resumes per
simulated day) and in devmem/storage/watchdog.log. The supervisor is started through WMI (Win32_Process.Create), so it is not a child of the caller and survives the
Claude app restarting. Nothing is written to a run folder except resume_log.jsonl and, on the cap, the flag.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, List, Optional

from devmem.eval import supervisor

ROOT = Path(__file__).resolve().parent.parent.parent
STALE_SECONDS = 300
MAX_RESTARTS_PER_HOUR = 6
LOCK_STALE_SECONDS = 120
LOG = ROOT / "devmem" / "storage" / "watchdog.log"
ARMS = ("baseline", "staged")


def _log(msg: str, log: Path = LOG) -> None:
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")


def list_processes() -> List[str]:
    """Command lines of the python processes of the project (read-only)."""
    try:
        out = subprocess.check_output(["powershell", "-NoProfile", "-Command",
                                       "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*devmem.eval.*' } | ForEach-Object { $_.CommandLine }"],
                                      text=True, timeout=60)
        return [l for l in out.splitlines() if l.strip()]
    except Exception:
        return []


def start_supervisor_via_wmi(arm: str, root: Path = ROOT) -> bool:
    py = str(root / ".venv" / "Scripts" / "python.exe")
    cmd = (f'cmd /c "cd /d {root} && set PYTHONIOENCODING=utf-8 && {py} -m devmem.eval.supervisor --arm {arm} '
           f'>> devmem\\storage\\full_{arm}_supervisor_wd.log 2>> devmem\\storage\\full_{arm}_supervisor_wd.err"')
    ps = ("$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = '" + cmd.replace("'", "''") + "'; CurrentDirectory = '" + str(root) + "' }; $r.ReturnValue")
    out = subprocess.check_output(["powershell", "-NoProfile", "-Command", ps], text=True, timeout=60).strip()
    return out.endswith("0")


def heartbeat_age(arm: str, root: Path, now: float) -> float:
    mov = root / "reverie" / "environment" / "frontend_server" / "storage" / f"p7_{arm}" / "movement"
    newest = max((p.stat().st_mtime for p in mov.glob("*.json")), default=0) if mov.is_dir() else 0
    return now - newest if newest else float("inf")


def _recent_restarts(run_dir: Path, now: float) -> int:
    f = run_dir / "resume_log.jsonl"
    n = 0
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            if '"external_kill_watchdog_restart"' in line:
                try:
                    r = json.loads(line)
                    if now - time.mktime(time.strptime(r["ts"], "%Y-%m-%d %H:%M:%S")) < 3600:
                        n += 1
                except Exception:
                    pass
    return n


def _take_lock(path: Path, now: float) -> bool:
    try:
        if path.exists() and now - path.stat().st_mtime > LOCK_STALE_SECONDS:
            path.unlink()
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, f"{os.getpid()} {time.strftime('%H:%M:%S')}".encode())
        os.close(fd)
        return True
    except FileExistsError:
        return False


def decide(arm: str, root: Path, procs: List[str], now: float) -> str:
    """Returns "restart" or the reason to leave the arm alone (pure function of the files and the process list)."""
    run_dir = root / "devmem" / "storage" / f"p7_{arm}"
    try:
        label = json.loads((run_dir / "run_label.json").read_text(encoding="utf-8"))
    except Exception:
        return "skip: no readable run_label.json"
    if not str(label.get("mode", "")).startswith("FULL"):
        return "skip: label is not FULL"
    if (run_dir / "ABORT").exists():
        return "skip: ABORT file present"
    if (run_dir / "PAUSE_FOR").exists():
        return "skip: operator pause file present"
    pz = run_dir / "pause_log.jsonl"
    if pz.exists():
        lines = [l for l in pz.read_text(encoding="utf-8").splitlines() if l.strip()]
        if lines and json.loads(lines[-1]).get("event") == "pause_start":
            return "skip: operator pause in progress"
    try:
        state = str(json.loads((run_dir / "run_status.json").read_text(encoding="utf-8")).get("state", ""))
    except Exception:
        state = ""
    if state.startswith("finished: ") and state[len("finished: "):].startswith(supervisor.FINAL_PREFIXES):
        return "skip: the run ended cleanly"
    if any(f"supervisor --arm {arm}" in l for l in procs):
        return "skip: a supervisor for this arm is running"
    age = heartbeat_age(arm, root, now)
    if age <= STALE_SECONDS:
        return "skip: heartbeat is fresh"
    return "restart"


def check_arm(arm: str, root: Path = ROOT, procs_fn: Callable[[], List[str]] = list_processes, start_fn: Callable[[str], bool] = start_supervisor_via_wmi,
              now_fn: Callable[[], float] = time.time, log: Path = LOG) -> str:
    now = now_fn()
    run_dir = root / "devmem" / "storage" / f"p7_{arm}"
    d = decide(arm, root, procs_fn(), now)
    if d != "restart":
        _log(f"{arm}: {d}", log)
        return d
    lock = root / "devmem" / "storage" / f"p7_{arm}.watchdog.lock"
    if not _take_lock(lock, now):
        _log(f"{arm}: skip: lock held by another watchdog", log)
        return "skip: lock held"
    try:
        if _recent_restarts(run_dir, now) >= MAX_RESTARTS_PER_HOUR:
            flag = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "arm": arm, "reason": f"{MAX_RESTARTS_PER_HOUR} watchdog restarts in the last hour; no further restart until an operator looks"}
            (run_dir / "watchdog_flag.json").write_text(json.dumps(flag, indent=1), encoding="utf-8")
            try:
                sf = run_dir / "run_status.json"
                st = json.loads(sf.read_text(encoding="utf-8"))
                st["watchdog_flag"] = flag
                sf.write_text(json.dumps(st, indent=1), encoding="utf-8")
            except Exception:
                pass
            _log(f"{arm}: FLAG raised, restart cap reached", log)
            return "flag: cap reached"
        if any(f"supervisor --arm {arm}" in l for l in procs_fn()):          # re-check under the lock: never two supervisors for one arm
            _log(f"{arm}: skip: a supervisor appeared while taking the lock", log)
            return "skip: supervisor appeared"
        ok = start_fn(arm)
        with open(run_dir / "resume_log.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "event": "external_kill_watchdog_restart", "started": bool(ok),
                                "heartbeat_age_s": round(heartbeat_age(arm, root, now)), "note": "external kill, not a crash; not counted toward the supervisor's resumes per sim day"}) + "\n")
        _log(f"{arm}: supervisor restarted by the watchdog (started={ok})", log)
        return "restarted" if ok else "restart failed"
    finally:
        try:
            lock.unlink()
        except OSError:
            pass


def main(argv: Optional[List[str]] = None) -> int:
    for arm in ARMS:
        try:
            check_arm(arm)
        except Exception as e:                      # the watchdog must never raise into the scheduler
            _log(f"{arm}: watchdog error {type(e).__name__}: {str(e)[:120]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
