"""
P5.0d: ledger analysis for the Stage 3 cost estimate. Reads devmem/router/usage_log.db (read-only),
writes docs/phase5_step0_artifacts/p5_0d_ledger_analysis.json. Label: derived from captured ledger rows.
"""
import json
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DB = ROOT / "devmem" / "router" / "usage_log.db"
OUT = ROOT / "docs" / "phase5_step0_artifacts" / "p5_0d_ledger_analysis.json"

conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
rows = [dict(r) for r in conn.execute(
    "SELECT purpose, condition, model, tokens_in, tokens_out, created_at FROM llm_call_log "
    "WHERE condition='baseline' AND purpose IN ('planning','dialogue','reflection') ORDER BY created_at")]

# 1) mean tokens per call by (purpose, condition), all models and gpt-oss-20b only
def stats(sel):
    g = defaultdict(lambda: [0, 0, 0])
    for r in sel:
        k = (r["purpose"], r["condition"])
        g[k][0] += 1
        g[k][1] += r["tokens_in"] or 0
        g[k][2] += r["tokens_out"] or 0
    return {f"{k[0]}|{k[1]}": {"calls": v[0], "mean_in": round(v[1] / v[0], 1), "mean_out": round(v[2] / v[0], 1)}
            for k, v in g.items()}

all_rows = [dict(r) for r in conn.execute(
    "SELECT purpose, condition, model, tokens_in, tokens_out, created_at FROM llm_call_log "
    "WHERE purpose IN ('planning','dialogue','reflection','importance_scoring')")]
per_purpose_all = stats(all_rows)
per_purpose_20b = stats([r for r in all_rows if r["model"] == "openai/gpt-oss-20b"])

# 2) split baseline simulation calls into bursts (gap > 5 min = a new run)
bursts, cur, last = [], [], None
for r in rows:
    t = datetime.strptime(r["created_at"], "%Y-%m-%d %H:%M:%S")
    if last and (t - last).total_seconds() > 300:
        bursts.append(cur)
        cur = []
    cur.append(r)
    last = t
if cur:
    bursts.append(cur)
burst_summary = []
for b in bursts:
    t0 = datetime.strptime(b[0]["created_at"], "%Y-%m-%d %H:%M:%S")
    t1 = datetime.strptime(b[-1]["created_at"], "%Y-%m-%d %H:%M:%S")
    burst_summary.append({
        "start": b[0]["created_at"], "span_s": int((t1 - t0).total_seconds()), "calls": len(b),
        "tokens_in": sum(r["tokens_in"] or 0 for r in b), "tokens_out": sum(r["tokens_out"] or 0 for r in b),
        "by_purpose": {p: sum(1 for r in b if r["purpose"] == p) for p in sorted({r["purpose"] for r in b})},
    })

result = {
    "label": "derived from captured ledger rows (devmem/router/usage_log.db)",
    "per_purpose_mean_tokens_all_models": per_purpose_all,
    "per_purpose_mean_tokens_gpt_oss_20b": per_purpose_20b,
    "baseline_sim_bursts": burst_summary,
    "note": "agent_id is NULL on most baseline sim rows, so per-agent splits are not possible from the ledger",
}
OUT.write_text(json.dumps(result, indent=1))
print(json.dumps(result, indent=1))
