"""
Ledger splitter: from the ONE router ledger (llm_call_log) calls and tokens per arm (condition), simulated day and purpose, with every evaluation purpose
(`eval_*`) reported separately and never included in the per-day efficiency figures. Read-only. The ledger is the router's SQLite database (default
devmem/router/usage_log.db). A time window (created_at, UTC text) can limit the rows to one run.
"""
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional


def split(db_path: Path, since: Optional[str] = None, until: Optional[str] = None) -> Dict[str, Any]:
    c = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    q = "SELECT condition, sim_day, purpose, COUNT(*), COALESCE(SUM(tokens_in),0), COALESCE(SUM(tokens_out),0) FROM llm_call_log WHERE 1=1"
    args = []
    if since:
        q += " AND created_at >= ?"
        args.append(since)
    if until:
        q += " AND created_at <= ?"
        args.append(until)
    q += " GROUP BY condition, sim_day, purpose"
    efficiency: Dict[str, Dict[str, Dict[str, Dict[str, int]]]] = {}
    evaluation: Dict[str, Dict[str, Dict[str, int]]] = {}
    for cond, day, purpose, n, tin, tout in c.execute(q, args):
        cond = cond or "none"
        rec = {"calls": n, "tokens_in": tin, "tokens_out": tout}
        if str(purpose).startswith("eval_"):
            e = evaluation.setdefault(cond, {}).setdefault(purpose, {"calls": 0, "tokens_in": 0, "tokens_out": 0})
            for k, v in rec.items():
                e[k] += v
        else:
            efficiency.setdefault(cond, {}).setdefault(str(day), {})[purpose] = rec
    c.close()
    totals = {cond: {"calls": sum(p["calls"] for d in days.values() for p in d.values()), "tokens_in": sum(p["tokens_in"] for d in days.values() for p in d.values())}
              for cond, days in efficiency.items()}
    return {"efficiency_per_condition_day_purpose": efficiency, "efficiency_totals_excluding_evaluation": totals, "evaluation_reported_separately": evaluation,
            "rule": "purposes starting with eval_ are excluded from the efficiency figures and listed under evaluation_reported_separately"}
