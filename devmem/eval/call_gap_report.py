"""
Per-call time of successful router calls per arm, from the router ledger, for a recent window against the overnight window (PM request 2026-10-08 night). Read-only; no call, no write to a run.

The router does not store a latency per call. Each arm drives its model calls from ONE process, one call at a time, and the ledger row of a call is written when the call completes. The gap between
two consecutive ledger rows of the same arm is therefore the time of the later call PLUS whatever happened between the calls (simulation compute, a retry on another key after a 429 or a timeout,
a backoff wait). The gap is an UPPER BOUND of the call time. Two views are reported: all gaps (median, 90th and 99th percentile, share above 60 s) and the gaps of at most 120 s (a call that was not
caught in a backoff or an outage), whose median and 90th percentile are the nearest figure to a successful call's time. The call rate is rows per minute of the window. The rate sampler's counters
(429, 503 and timeouts seen by the arms) give the error rate per minute over the same window.

    python -m devmem.eval.call_gap_report [--recent-minutes 120] [--overnight "2026-10-08 01:10:00" "2026-10-08 08:00:00"] [--window NAME START END]
"""
import argparse
import calendar
import json
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent.parent
DB = ROOT / "devmem" / "router" / "usage_log.db"
SAMPLES = ROOT / "devmem" / "storage" / "rate_samples.jsonl"
IST = timedelta(hours=5, minutes=30)


def pct(xs: List[float], q: float) -> Optional[float]:
    if not xs:
        return None
    xs = sorted(xs)
    k = (len(xs) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return round(xs[lo] + (xs[hi] - xs[lo]) * (k - lo), 2)


def _epoch_utc(text: str) -> float:
    return calendar.timegm(time.strptime(text[:19], "%Y-%m-%d %H:%M:%S"))


def window_stats(arm: str, start_ist: datetime, end_ist: datetime, db: Path = None, samples: Path = None) -> Dict[str, Any]:
    c = sqlite3.connect(f"file:{Path(db or DB).as_posix()}?mode=ro", uri=True)
    a, b = (start_ist - IST).strftime("%Y-%m-%d %H:%M:%S"), (end_ist - IST).strftime("%Y-%m-%d %H:%M:%S")
    rows = c.execute("SELECT created_at FROM llm_call_log WHERE condition=? AND created_at>=? AND created_at<=? AND purpose NOT LIKE 'eval_%' ORDER BY created_at, rowid", (arm, a, b)).fetchall()
    c.close()
    t = [_epoch_utc(r[0]) for r in rows]
    gaps = [t[i] - t[i - 1] for i in range(1, len(t))]
    short = [g for g in gaps if g <= 120]
    minutes = max((end_ist - start_ist).total_seconds() / 60, 1e-9)
    out: Dict[str, Any] = {"calls": len(t), "calls_per_minute": round(len(t) / minutes, 2), "gaps": len(gaps),
                           "all_gaps_s": {"median": pct(gaps, 0.5), "p90": pct(gaps, 0.9), "p99": pct(gaps, 0.99), "share_above_60s": round(sum(1 for g in gaps if g > 60) / len(gaps), 4) if gaps else None},
                           "gaps_up_to_120s": {"n": len(short), "median": pct(short, 0.5), "p90": pct(short, 0.9)}}
    # error counters of the rate sampler over the window (deltas between the first and last sample inside it)
    try:
        s = [json.loads(l) for l in Path(samples or SAMPLES).read_text(encoding="utf-8").splitlines() if l.strip()]
        lo, hi = start_ist.timestamp(), end_ist.timestamp()
        inside = [x for x in s if lo <= x["t"] <= hi and arm in x]
        if len(inside) >= 2:
            d = {k: inside[-1][arm].get(k, 0) - inside[0][arm].get(k, 0) for k in ("n429", "n503", "ntimeout")}
            mins = (inside[-1]["t"] - inside[0]["t"]) / 60
            out["errors_seen_per_minute"] = {k: round(v / mins, 2) for k, v in d.items()} if mins > 0 else None
            out["errors_seen_counts"] = d
    except Exception:
        pass
    return out


def report(recent_minutes: int, overnight, now: datetime = None, db: Path = None, samples: Path = None, extra=None) -> Dict[str, Any]:
    now = now or datetime.now()
    wins = {f"last_{recent_minutes}_min": (now - timedelta(minutes=recent_minutes), now),
            "overnight": (datetime.strptime(overnight[0], "%Y-%m-%d %H:%M:%S"), datetime.strptime(overnight[1], "%Y-%m-%d %H:%M:%S"))}
    for name, s0, s1 in (extra or []):
        wins[name] = (datetime.strptime(s0, "%Y-%m-%d %H:%M:%S"), datetime.strptime(s1, "%Y-%m-%d %H:%M:%S"))
    res: Dict[str, Any] = {"method": __doc__.strip().split("\n\n")[1].replace("\n", " "), "windows_ist": {k: [v[0].strftime("%Y-%m-%d %H:%M:%S"), v[1].strftime("%Y-%m-%d %H:%M:%S")] for k, v in wins.items()}, "arms": {}}
    for arm in ("baseline", "staged"):
        res["arms"][arm] = {k: window_stats(arm, v[0], v[1], db, samples) for k, v in wins.items()}
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recent-minutes", type=int, default=120)
    ap.add_argument("--overnight", nargs=2, default=["2026-10-08 01:10:00", "2026-10-08 08:00:00"])
    ap.add_argument("--window", nargs=3, action="append", metavar=("NAME", "START_IST", "END_IST"), help="an extra window, for example an awake stretch of day 1")
    a = ap.parse_args()
    r = report(a.recent_minutes, a.overnight, extra=a.window)
    (ROOT / "docs" / "phase9_call_latency.json").write_text(json.dumps(r, indent=1), encoding="utf-8")
    for arm, v in r["arms"].items():
        for k, x in v.items():
            print(arm, k, "calls", x["calls"], "per min", x["calls_per_minute"], "| all gaps", x["all_gaps_s"], "| gaps<=120s", x["gaps_up_to_120s"], "| errors/min", x.get("errors_seen_per_minute"))


if __name__ == "__main__":
    main()
