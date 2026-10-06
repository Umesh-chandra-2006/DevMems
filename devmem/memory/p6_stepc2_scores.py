"""T re-check on the Step C rerun (offline, zero calls), applying the population written BEFORE the run (docs/phase6_preregistration.md
section 7, commit 06c733c): every importance score returned by the scoring model during Step C (staged, Gemini, event and chat texts)
whose text does not contain "is idle". Rule unchanged; provisional if fewer than 30 scores; reported next to, not pooled with, the frozen
provisional T = 9."""
import json
import sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
db = ROOT / "devmem" / "storage" / "p5_step_c2_gemini" / "memory.db"
c = sqlite3.connect(str(db))
rows = [dict(zip(("agent", "content", "score"), r)) for r in c.execute("SELECT agent_id, content, importance_score FROM episodic_memory")]
scored = [r for r in rows if "is idle" not in r["content"]]
hist = Counter(int(r["score"]) for r in scored)
n = len(scored)
frac = {str(t): round(sum(1 for r in scored if r["score"] >= t) / n, 4) if n else None for t in (8, 9, 10)}
raw = [json.loads(l) for l in (ROOT / "docs/phase6_stepc2_artifacts/raw_replies.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
scoring_calls = sum(1 for r in raw if r["purpose"] == "importance_scoring")
if n < 30:
    status, T = "provisional again (fewer than 30 scored events)", None
else:
    T = next((t for t in (8, 9, 10) if sum(1 for r in scored if r["score"] >= t) / n < 0.05), 10)
    status = "rule applied"
out = {"label": "offline analysis of the Step C rerun mirror database", "mirror_rows": len(rows),
       "rule_assigned_idle_rows_excluded": len(rows) - n, "llm_scored_events": n, "scoring_calls_in_router_log": scoring_calls,
       "cross_check_scored_events_equal_scoring_calls": n == scoring_calls, "histogram": {str(k): hist.get(k, 0) for k in range(1, 11)},
       "by_agent": dict(Counter(r["agent"] for r in scored)), "fraction_reaching": frac, "T_from_this_population": T, "status": status,
       "frozen_provisional_T_unchanged": 9}
(ROOT / "docs/phase6_stepc2_artifacts/step_c2_score_check.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
