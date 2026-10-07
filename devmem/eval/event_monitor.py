"""Read-only event monitor: prints one line and exits on the first of: a new watchdog restart, an ABORT file, a finished arm, a day checkpoint folder appearing, or an arm
that stays DEAD for more than 8 minutes by arm_health. Used to wake the operator; writes nothing."""
import json
import sys
import time
from pathlib import Path

from devmem.eval import arm_health

ROOT = Path(__file__).resolve().parent.parent.parent
SIM = ROOT / "reverie" / "environment" / "frontend_server" / "storage"


def snapshot():
    s = {}
    for arm in ("baseline", "staged"):
        rd = ROOT / "devmem" / "storage" / f"p7_{arm}"
        log = (rd / "resume_log.jsonl").read_text(encoding="utf-8") if (rd / "resume_log.jsonl").exists() else ""
        s[arm] = {"wd": log.count("external_kill_watchdog_restart"), "abort": (rd / "ABORT").exists(), "ckpt1": (SIM / f"p7_{arm}__ckpt_day1_end_awake").exists(),
                  "ckpt3": (SIM / f"p7_{arm}__ckpt_day3_end_awake").exists()}
        try:
            st = json.loads((rd / "run_status.json").read_text(encoding="utf-8"))
            s[arm]["state"] = str(st.get("state", ""))
        except Exception:
            s[arm]["state"] = ""
    return s


def main():
    base = snapshot()
    dead_since = {}
    while True:
        time.sleep(60)
        cur = snapshot()
        for arm in cur:
            if cur[arm]["wd"] > base[arm]["wd"]:
                print(f"EVENT {arm}: watchdog restart"); return
            if cur[arm]["abort"] and not base[arm]["abort"]:
                print(f"EVENT {arm}: ABORT file"); return
            if cur[arm]["ckpt1"] and not base[arm]["ckpt1"]:
                print(f"EVENT {arm}: day-1 checkpoint exists"); return
            if cur[arm]["ckpt3"] and not base[arm]["ckpt3"]:
                print(f"EVENT {arm}: day-3 checkpoint exists"); return
            if cur[arm]["state"].startswith("finished") and not base[arm]["state"].startswith("finished"):
                print(f"EVENT {arm}: {cur[arm]['state'][:80]}"); return
        procs = arm_health._processes()
        for arm in ("baseline", "staged"):
            v = arm_health.check(arm, False, 300, procs)["verdict"]
            if v == "DEAD":
                dead_since.setdefault(arm, time.time())
                if time.time() - dead_since[arm] > 480:
                    print(f"EVENT {arm}: DEAD for more than 8 minutes (watchdog should have restarted it)"); return
            else:
                dead_since.pop(arm, None)


if __name__ == "__main__":
    main()
