"""
Read-only ETA analysis from the movement files of the running arms (no call, writes nothing but its stdout).
The wall time of each simulated step is the difference between the modification times of consecutive movement files; a step is a CONVERSATION step when any agent
has a chat line in it. Per arm it reports, for the last N minutes of wall time and for the whole run: seconds per step for asleep steps, awake non-conversation steps and
conversation steps, the share of conversation steps among awake steps, and the projected wall clock of the day-1 checkpoint (step 5,130), the day-2 awake end and the
day-3 end, using the observed mix. Resume restarts show up as outlier gaps; gaps above 600 s are reported separately as waiting (pauses, outages, backoff).

    python -m devmem.eval.eta_analysis [--minutes 120]
"""
import argparse
import glob
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SIM = ROOT / "reverie" / "environment" / "frontend_server" / "storage"
SEC_PER_STEP = 10
DAY = 8640
CHECKPOINT_1, END_DAY2_AWAKE, END = 5130, 8640 + 5040, 3 * DAY


def awake(step: int) -> bool:
    s = (step % DAY) * SEC_PER_STEP
    return 6 * 3600 <= s < 14 * 3600


def load(arm: str, last_minutes: float):
    d = SIM / f"p7_{arm}" / "movement"
    files = sorted(((int(os.path.basename(f)[:-5]), os.path.getmtime(f), f) for f in glob.glob(str(d / "*.json"))))
    rows, prev = [], None
    for step, mt, f in files:
        chat = None
        if awake(step) and (prev is None or True):
            try:
                p = json.load(open(f, encoding="utf-8"))["persona"]
                chat = any(v.get("chat") for v in p.values())
            except Exception:
                chat = None
        if prev is not None and step == prev[0] + 1:
            rows.append({"step": step, "dt": mt - prev[1], "awake": awake(step), "chat": bool(chat), "mt": mt})
        prev = (step, mt)
    return files, rows


def stats(rows):
    out = {}
    for name, sel in (("asleep", lambda r: not r["awake"]), ("awake_plain", lambda r: r["awake"] and not r["chat"]), ("awake_conversation", lambda r: r["awake"] and r["chat"])):
        x = [r["dt"] for r in rows if sel(r) and r["dt"] < 600]
        out[name] = {"steps": len(x), "mean_s_per_step": round(sum(x) / len(x), 2) if x else None}
    waits = [r["dt"] for r in rows if r["dt"] >= 600]
    out["gaps_over_600s"] = {"count": len(waits), "total_min": round(sum(waits) / 60, 1)}
    aw = [r for r in rows if r["awake"]]
    out["conversation_share_of_awake_steps"] = round(sum(1 for r in aw if r["chat"]) / len(aw), 3) if aw else None
    return out


def project(arm: str, cur_step: int, st: dict, now: float):
    share = st["conversation_share_of_awake_steps"] or 0.12
    a = st["awake_plain"]["mean_s_per_step"]
    c = st["awake_conversation"]["mean_s_per_step"]
    s = st["asleep"]["mean_s_per_step"] or 0.2
    if not a or not c:
        return None
    per_awake = (1 - share) * a + share * c

    def eta(target):
        sec = 0.0
        for k in range(cur_step, target):
            sec += per_awake if awake(k) else s
        return datetime.fromtimestamp(now + sec).strftime("%Y-%m-%d %H:%M")
    return {"awake_s_per_step_mixed": round(per_awake, 2), "day1_checkpoint_step_5130": eta(CHECKPOINT_1), "day2_awake_end_step_13680": eta(END_DAY2_AWAKE), "day3_end_step_25920": eta(END)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=120)
    a = ap.parse_args()
    now = time.time()
    res = {}
    for arm in ("baseline", "staged"):
        files, rows = load(arm, a.minutes)
        recent = [r for r in rows if r["mt"] >= now - a.minutes * 60]
        cur = files[-1][0] if files else 0
        res[arm] = {"current_step": cur, "sim_clock": (datetime(2023, 2, 13) + timedelta(seconds=cur * SEC_PER_STEP)).strftime("%Y-%m-%d %H:%M:%S"),
                    "last_%d_min" % a.minutes: stats(recent), "whole_run": stats(rows),
                    "projection_with_recent_rates": project(arm, cur, stats(recent), now), "projection_with_whole_run_rates": project(arm, cur, stats(rows), now)}
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
