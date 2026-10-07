"""
Standalone latency and throttle probe (diagnostic). It uses NO router, NO key pool, NO cooldown state and touches no run folder; it only sends requests
and writes its own result file. It never prints or stores a key: keys are read from the environment by NAME and only the label and the key's index or
label are recorded.

  python -m devmem.eval.latency_probe --free GEMINI_KEY_30 --n 40                          latency of one free-tier key alone (the timeout question)
  python -m devmem.eval.latency_probe --paid GEMINI_PAID_TEST_KEY --free GEMINI_KEY_30 --n 100 --embeddings 50
        100 sequential chat calls and 50 embeddings on the paid test key; every iteration also sends the SAME request on one free-tier key in the same
        minute for comparison. Prompts are real importance-scoring prompts taken from the pilot raw reply log (the baseline arm's prompt shape).

Reported per key kind: calls per minute (successful), latency percentiles of successful calls (p50, p95, p99, max), counts of 200, 429, 503, other
HTTP codes, timeouts and connection errors. Read timeout 60 s so that slow successes are measured, not cut at 15 s.
"""
import argparse
import json
import os
import statistics
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent
MODEL = "gemini-3.1-flash-lite"
EMB = "gemini-embedding-001"
BASE = "https://generativelanguage.googleapis.com/v1beta/models/"
READ_TIMEOUT = 60


def prompts(n: int):
    out = []
    raw = ROOT / "devmem" / "storage" / "p7pilot_baseline" / "raw_replies.jsonl"
    for line in raw.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("purpose") == "importance_scoring" and r.get("prompt") and r["prompt"] not in out:
            out.append(r["prompt"])
        if len(out) >= n:
            break
    return out


def texts(n: int):
    out = []
    raw = ROOT / "devmem" / "storage" / "p7pilot_baseline" / "raw_replies.jsonl"
    for line in raw.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            p = r.get("prompt", "")
            if r.get("purpose") == "importance_scoring" and "Event:" in p:
                t = p.split("Event:", 1)[1].split("\n", 1)[0].strip()
                if t and t not in out:
                    out.append(t)
        if len(out) >= n:
            break
    while len(out) < n:
        out.append(f"probe text {len(out)}")
    return out


def call(kind: str, key: str, payload: dict):
    url = BASE + (f"{MODEL}:generateContent" if kind == "chat" else f"{EMB}:embedContent")
    t0 = time.time()
    try:
        r = requests.post(url, headers={"x-goog-api-key": key}, json=payload, timeout=(10, READ_TIMEOUT))
        return r.status_code, time.time() - t0
    except requests.exceptions.Timeout:
        return "timeout", time.time() - t0
    except Exception as e:
        return type(e).__name__, time.time() - t0


def summarize(rows, wall):
    ok = sorted(l for s, l in rows if s == 200)
    codes = {}
    for s, _ in rows:
        codes[str(s)] = codes.get(str(s), 0) + 1
    pct = lambda q: round(ok[min(len(ok) - 1, int(q * len(ok)))], 2) if ok else None
    return {"requests": len(rows), "status_counts": codes, "successes": len(ok), "success_per_min": round(len(ok) / (wall / 60), 2) if wall else None,
            "latency_s": {"p50": pct(0.5), "p95": pct(0.95), "p99": pct(0.99), "max": round(ok[-1], 2) if ok else None, "mean": round(statistics.mean(ok), 2) if ok else None}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--paid", help="env var NAME of the paid test key (never printed)")
    ap.add_argument("--free", required=True, help="env var NAME of one free-tier key used for comparison")
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--embeddings", type=int, default=0)
    ap.add_argument("--label", default="probe")
    a = ap.parse_args()
    load_dotenv(ROOT / ".env")
    keys = {"free": os.environ.get(a.free)}
    if a.paid:
        keys["paid"] = os.environ.get(a.paid)
    missing = [k for k, v in keys.items() if not v]
    if missing:
        raise SystemExit(f"key not set in the environment for: {missing}")
    ps = prompts(a.n)
    res = {k: {"chat": [], "embed": []} for k in keys}
    wall = {k: {"chat": 0.0, "embed": 0.0} for k in keys}
    for i in range(a.n):
        body = {"contents": [{"parts": [{"text": ps[i % len(ps)]}]}], "generationConfig": {"maxOutputTokens": 400}}
        for k in keys:                                  # the paid call and the free call are made back to back, in the same minute
            s, lat = call("chat", keys[k], body)
            res[k]["chat"].append((s, lat))
            wall[k]["chat"] += lat
    tx = texts(a.embeddings) if a.embeddings else []
    for i in range(a.embeddings):
        body = {"content": {"parts": [{"text": tx[i]}]}}
        for k in keys:
            s, lat = call("embed", keys[k], body)
            res[k]["embed"].append((s, lat))
            wall[k]["embed"] += lat
    out = {"label": a.label, "model": MODEL, "embedding_model": EMB, "read_timeout_s": READ_TIMEOUT, "requested_chat": a.n, "requested_embeddings": a.embeddings,
           "free_key_name_is_recorded_as": a.free.split("_")[-1] if a.free.startswith("GEMINI_KEY_") else "free", "started": time.strftime("%Y-%m-%d %H:%M:%S"),
           "results": {k: {"chat": summarize(res[k]["chat"], wall[k]["chat"]), "embeddings": summarize(res[k]["embed"], wall[k]["embed"]) if res[k]["embed"] else None} for k in keys}}
    d = ROOT / "devmem" / "storage" / "probes"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{a.label}_{time.strftime('%Y%m%d_%H%M%S')}.json"
    f.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))
    print("written", f)


if __name__ == "__main__":
    main()
