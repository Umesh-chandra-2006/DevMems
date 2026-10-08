"""Read-only report of the 429 waves (rate-limit backoffs) of each arm since a given wall time (IST): number, start, length and attempts of each wave, and waves and waited minutes per
hour, so fading can be judged. Reads rate_limit_log.jsonl (UTC timestamps).   python -m devmem.eval.wave_report [--since "2026-10-08 16:14:00"]"""
import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def waves(arm: str, since_ist: str):
    since_utc = (datetime.strptime(since_ist, "%Y-%m-%d %H:%M:%S") - timedelta(hours=5, minutes=30)).strftime("%Y-%m-%dT%H:%M:%S")
    f = ROOT / "devmem" / "storage" / f"p7_{arm}" / "rate_limit_log.jsonl"
    out, cur = [], None
    for line in f.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r["at"] < since_utc:
            continue
        if r["event"] == "rate_limit_start":
            cur = {"start_ist": (datetime.fromisoformat(r["at"]) + timedelta(hours=5, minutes=30)).strftime("%H:%M:%S")}
        elif r["event"] == "rate_limit_end" and cur is not None:
            cur.update({"seconds": r["seconds"], "attempts": r["attempts"]})
            out.append(cur)
            cur = None
    if cur is not None:
        cur["open"] = True
        out.append(cur)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-10-08 16:14:00")
    a = ap.parse_args()
    now = datetime.now()
    hours = max((now - datetime.strptime(a.since, "%Y-%m-%d %H:%M:%S")).total_seconds() / 3600, 0.01)
    res = {}
    for arm in ("baseline", "staged"):
        w = waves(arm, a.since)
        done = [x for x in w if "seconds" in x]
        res[arm] = {"waves": len(w), "waited_seconds_total": round(sum(x["seconds"] for x in done)), "mean_wave_seconds": round(sum(x["seconds"] for x in done) / len(done), 1) if done else None,
                    "waves_per_hour": round(len(w) / hours, 2), "list": w}
    print(json.dumps({"since": a.since, "hours": round(hours, 2), **res}, indent=1))


if __name__ == "__main__":
    main()
