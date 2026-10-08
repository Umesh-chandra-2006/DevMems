"""
Read-only analysis of calls per awake step (no call, no write to a run): the router ledger rows of an arm are mapped to simulated steps through the modification times of the
movement files (a step's file is written when the step ends, so a call belongs to the first step file written after it), then counted by purpose per window; prompt tokens per
purpose per window come from the same rows; repeated or near-identical prompts are counted in the delivered-reply log (`raw_replies.jsonl`, which keeps prompts, in call order) for the
calls of a recent wall-clock window. Embedding requests are not in the router ledger and have no time stamps (only run totals from embedding_stats.json are available).

    python -m devmem.eval.step_cost_analysis
"""
import bisect
import collections
import glob
import hashlib
import json
import os
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SIM = ROOT / "reverie" / "environment" / "frontend_server" / "storage"
DB = ROOT / "devmem" / "router" / "usage_log.db"
LAUNCH_UTC = "2026-10-07 10:27:00"
WINDOWS = {"day1_morning_06_to_10": (2160, 3600), "day1_afternoon_10_to_14": (3600, 5040), "day2_06_to_08": (10800, 11520)}


def step_times(arm):
    d = SIM / f"p7_{arm}" / "movement"
    pairs = sorted((os.path.getmtime(f), int(os.path.basename(f)[:-5])) for f in glob.glob(str(d / "*.json")))
    return [p[0] for p in pairs], [p[1] for p in pairs]


def rows(arm):
    c = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    r = c.execute("SELECT created_at, purpose, tokens_in, tokens_out FROM llm_call_log WHERE condition=? AND created_at>=? ORDER BY created_at", (arm, LAUNCH_UTC)).fetchall()
    c.close()
    out = []
    for ts, p, ti, to in r:
        epoch = datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S").timestamp() - (time.timezone * -1 if False else 0)
        out.append((ts, p, ti or 0, to or 0))
    return out


def analyse(arm, last_minutes=60, dup_minutes=120):
    mt, st = step_times(arm)
    rs = rows(arm)
    # ledger created_at is UTC text: convert to a local epoch comparable with file mtimes
    import calendar
    ep = [calendar.timegm(time.strptime(r[0][:19], "%Y-%m-%d %H:%M:%S")) for r in rs]
    step_of = []
    for e in ep:
        i = bisect.bisect_left(mt, e)
        step_of.append(st[i] if i < len(st) else st[-1])
    now = time.time()
    res = {"arm": arm, "windows": {}}
    for name, a, b in [(n, w[0], w[1]) for n, w in WINDOWS.items()] + [("last_60_min_wall", None, None)]:
        if b is None:
            sel = [k for k, e in enumerate(ep) if e >= now - last_minutes * 60]
            steps = len([1 for t in mt if t >= now - last_minutes * 60])
        else:
            sel = [k for k, s in enumerate(step_of) if a <= s < b]
            steps = b - a
            top = max(st)
            if top < b:
                steps = max(0, top - a + 1)
        by = collections.defaultdict(lambda: [0, 0, 0])
        for k in sel:
            e = by[rs[k][1]]
            e[0] += 1
            e[1] += rs[k][2]
            e[2] += rs[k][3]
        res["windows"][name] = {"steps": steps, "calls_total": len(sel), "calls_per_step_total": round(len(sel) / steps, 3) if steps else None,
                                "by_purpose": {p: {"calls": v[0], "calls_per_step": round(v[0] / steps, 3) if steps else None, "mean_tokens_in": round(v[1] / v[0], 1) if v[0] else None,
                                                   "mean_tokens_out": round(v[2] / v[0], 1) if v[0] else None} for p, v in sorted(by.items())}}
    # repeated prompts in the calls of the last dup_minutes (delivered replies, in call order; the count of recent ledger rows gives how many of the log's tail to look at)
    n_recent = sum(1 for e in ep if e >= now - dup_minutes * 60)
    raw = [json.loads(l) for l in open(ROOT / "devmem" / "storage" / f"p7_{arm}" / "raw_replies.jsonl", encoding="utf-8") if l.strip()]
    tail = raw[-n_recent:] if n_recent else []
    norm = lambda p: re.sub(r"\d+", "#", p)
    exact = collections.Counter(hashlib.md5(r["prompt"].encode()).hexdigest() for r in tail if r.get("prompt"))
    nearm = collections.Counter(hashlib.md5(norm(r["prompt"]).encode()).hexdigest() for r in tail if r.get("prompt"))
    by_purpose = collections.Counter()
    for r in tail:
        by_purpose[r["purpose"]] += 1
    dup_exact = sum(v - 1 for v in exact.values() if v > 1)
    dup_near = sum(v - 1 for v in nearm.values() if v > 1)
    ex = None
    for k, v in exact.most_common(1):
        if v > 1:
            r0 = next(r for r in tail if r.get("prompt") and hashlib.md5(r["prompt"].encode()).hexdigest() == k)
            ex = {"times": v, "purpose": r0["purpose"], "agent": r0.get("agent_id"), "prompt_start": r0["prompt"][:160].replace("\n", " ")}
    res["repeats_last_%d_min" % dup_minutes] = {"calls_looked_at": len(tail), "by_purpose": dict(by_purpose), "repeated_with_identical_prompt": dup_exact,
                                                 "repeated_when_digits_are_ignored": dup_near, "most_repeated_identical_prompt": ex}
    emb = ROOT / "devmem" / "storage" / f"p7_{arm}" / "embedding_stats.json"
    try:
        e = json.loads(emb.read_text(encoding="utf-8"))
        res["embedding_stats_first_process_only"] = {k: e.get(k) for k in ("http_requests", "cache_hits", "cache_misses") if k in e}
    except Exception:
        pass
    return res


if __name__ == "__main__":
    print(json.dumps({arm: analyse(arm) for arm in ("baseline", "staged")}, indent=1))
