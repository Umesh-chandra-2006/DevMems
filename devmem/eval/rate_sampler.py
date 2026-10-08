"""Read-only rate sampler (diagnostic, writes only its own log). Every 60 s it appends, per arm, the movement step, delivered replies, and the counts of 429, 503 and
timeout lines in the supervisor error log, to devmem/storage/rate_samples.jsonl. Used to compare success and 429 rates across two time windows (for example
the home or college network against the phone hotspot). It touches no run folder and makes no call.

    python -m devmem.eval.rate_sampler            (runs until stopped)
    python -m devmem.eval.rate_sampler --report <minutes> <end_epoch_or_now>   prints the rates over the window of that length ending then
"""
import argparse
import glob
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "devmem" / "storage" / "rate_samples.jsonl"
SIM = ROOT / "reverie" / "environment" / "frontend_server" / "storage"


def sample() -> dict:
    out = {"t": time.time()}
    for arm in ("baseline", "staged"):
        d = SIM / f"p7_{arm}" / "movement"
        steps = [int(os.path.basename(f)[:-5]) for f in glob.glob(str(d / "*.json"))]
        raw = ROOT / "devmem" / "storage" / f"p7_{arm}" / "raw_replies.jsonl"
        # every supervisor error log of the arm (the first supervisor, the WMI relaunch, the watchdog relaunch): the sums are monotonic, so differences stay valid
        txt = "".join(f.read_text(encoding="utf-8", errors="ignore") for f in sorted((ROOT / "devmem" / "storage").glob(f"full_{arm}_supervisor*.err")))
        out[arm] = {"step": max(steps) if steps else None, "replies": sum(1 for _ in open(raw, encoding="utf-8")) if raw.exists() else 0,
                    "n429": len(re.findall(r"429 RateLimit", txt)), "n503": len(re.findall(r"HTTP 503", txt)), "ntimeout": len(re.findall(r"Timeout \(", txt))}
    return out


def report(minutes: float, end: float) -> dict:
    rows = [json.loads(l) for l in OUT.read_text(encoding="utf-8").splitlines() if l.strip()]
    lo = [r for r in rows if r["t"] <= end - minutes * 60]
    hi = [r for r in rows if r["t"] <= end]
    if not lo or not hi:
        return {"error": "not enough samples for that window"}
    a, b = lo[-1], hi[-1]
    dt = (b["t"] - a["t"]) / 60
    return {arm: {"window_min": round(dt, 1), "successes_per_min": round((b[arm]["replies"] - a[arm]["replies"]) / dt, 2), "429_per_min": round((b[arm]["n429"] - a[arm]["n429"]) / dt, 2),
                  "503_per_min": round((b[arm]["n503"] - a[arm]["n503"]) / dt, 2), "timeouts_per_min": round((b[arm]["ntimeout"] - a[arm]["ntimeout"]) / dt, 2),
                  "sim_steps_per_min": round((b[arm]["step"] - a[arm]["step"]) / dt, 2)} for arm in ("baseline", "staged")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", nargs=2, metavar=("MINUTES", "END"))
    a = ap.parse_args()
    if a.report:
        end = time.time() if a.report[1] == "now" else float(a.report[1])
        print(json.dumps(report(float(a.report[0]), end), indent=1))
        return
    while True:
        with open(OUT, "a", encoding="utf-8") as f:
            f.write(json.dumps(sample()) + "\n")
        time.sleep(60)


if __name__ == "__main__":
    main()
