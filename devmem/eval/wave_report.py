"""Read-only report of the 429 waves (rate-limit backoffs) of each arm in a wall-clock window (IST): each wave (start, end, length, attempts), per clock hour the number of waves
and the seconds waited as a share of the hour, mean and maximum wave length, the waves of the two arms that overlap in time, and the first-half against second-half comparison
(whether the waves fade). Reads rate_limit_log.jsonl (UTC timestamps); no call, no write.
    python -m devmem.eval.wave_report [--since "2026-10-08 16:14:00"] [--until "2026-10-08 18:15:00"]"""
import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
FMT = "%Y-%m-%d %H:%M:%S"
IST = timedelta(hours=5, minutes=30)


def waves(arm: str, since_ist: str, until_ist: str = None):
    """Waves that START inside [since, until). Each has start/end as IST datetimes (end is None while open)."""
    f = ROOT / "devmem" / "storage" / f"p7_{arm}" / "rate_limit_log.jsonl"
    since = datetime.strptime(since_ist, FMT)
    until = datetime.strptime(until_ist, FMT) if until_ist else None
    out, cur = [], None
    for line in f.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        at = datetime.fromisoformat(r["at"]) + IST
        if r["event"] == "rate_limit_start":
            cur = {"start": at} if at >= since and (until is None or at < until) else None
        elif r["event"] == "rate_limit_end" and cur is not None:
            cur.update({"seconds": r["seconds"], "attempts": r["attempts"], "end": at})
            out.append(cur)
            cur = None
    if cur is not None:
        cur.update({"open": True, "end": None})
        out.append(cur)
    for w in out:
        w["start_ist"] = w["start"].strftime("%H:%M:%S")
    return out


def per_hour(ws, since: datetime, until: datetime):
    """Clock-hour buckets inside the window: waves started, seconds waited (clipped to the bucket), share of the bucket's wall time."""
    rows, t = [], since.replace(minute=0, second=0, microsecond=0)
    while t < until:
        a, b = max(t, since), min(t + timedelta(hours=1), until)
        started = [w for w in ws if a <= w["start"] < b]
        waited = 0.0
        for w in ws:
            e = w["end"] or until
            lo, hi = max(w["start"], a), min(e, b)
            if hi > lo:
                waited += (hi - lo).total_seconds()
        span = (b - a).total_seconds()
        rows.append({"hour": t.strftime("%m-%d %H:00"), "window_minutes": round(span / 60, 1), "waves_started": len(started), "waited_seconds": round(waited), "share_of_wall_time": round(waited / span, 4) if span else None})
        t += timedelta(hours=1)
    return rows


def overlaps(wa, wb, until: datetime):
    """Pairs (baseline wave, staged wave) whose time spans overlap, with the overlap length."""
    out = []
    for x in wa:
        for y in wb:
            lo, hi = max(x["start"], y["start"]), min(x["end"] or until, y["end"] or until)
            if hi > lo:
                out.append({"baseline_start": x["start"].strftime("%H:%M:%S"), "staged_start": y["start"].strftime("%H:%M:%S"), "overlap_seconds": round((hi - lo).total_seconds())})
    return out


def summarize(arm_waves, since: datetime, until: datetime):
    done = [w for w in arm_waves if w.get("seconds") is not None]
    mid = since + (until - since) / 2

    def half(a, b):
        sel = [w for w in arm_waves if a <= w["start"] < b]
        return {"waves": len(sel), "waited_seconds": round(sum(w.get("seconds") or 0 for w in sel))}
    return {"waves": len(arm_waves), "waited_seconds_total": round(sum(w["seconds"] for w in done)), "share_of_wall_time": round(sum(w["seconds"] for w in done) / (until - since).total_seconds(), 4),
            "mean_wave_seconds": round(sum(w["seconds"] for w in done) / len(done), 1) if done else None, "max_wave_seconds": round(max((w["seconds"] for w in done), default=0), 1),
            "first_half": half(since, mid), "second_half": half(mid, until), "per_hour": per_hour(arm_waves, since, until),
            "list": [{"start": w["start_ist"], "seconds": w.get("seconds"), "attempts": w.get("attempts"), "open": w.get("open", False)} for w in arm_waves]}


def report(since_ist: str, until_ist: str = None):
    until = datetime.strptime(until_ist, FMT) if until_ist else datetime.now()
    since = datetime.strptime(since_ist, FMT)
    ws = {arm: waves(arm, since_ist, until_ist) for arm in ("baseline", "staged")}
    res = {"since": since_ist, "until": until.strftime(FMT), "hours": round((until - since).total_seconds() / 3600, 2)}
    for arm in ws:
        res[arm] = summarize(ws[arm], since, until)
    res["overlapping_waves_between_arms"] = overlaps(ws["baseline"], ws["staged"], until)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-10-08 16:14:00")
    ap.add_argument("--until")
    a = ap.parse_args()
    print(json.dumps(report(a.since, a.until), indent=1))


if __name__ == "__main__":
    main()
