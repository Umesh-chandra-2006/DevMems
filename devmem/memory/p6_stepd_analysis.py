"""
Step D offline analysis (zero calls): reads docs/phase6_stepd_artifacts (raw-reply log, hourly ledger, memory.db copy, stdout log) and the
worktree router ledger (D:/DevMems_stepd/devmem/router/usage_log.db, only to attach tokens to the raw-log records in call order).
Outputs docs/phase6_stepd_artifacts/stepd_analysis.json: calls and tokens per prompt type per window per agent with awake and sleeping
agents separated, the T re-check on the population written in docs/phase6_preregistration.md section 8, 503 and timeout counts by key,
and the sleep timeline of Maria and Klaus.
"""
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
ART = ROOT / "docs" / "phase6_stepd_artifacts"
LEDGER = Path("D:/DevMems_stepd/devmem/router/usage_log.db")
sys.argv = [sys.argv[0], "phase6_stepd_artifacts"]
sys.path.insert(0, str(ROOT))


def main():
    import importlib.util
    spec = importlib.util.spec_from_file_location("sca", ROOT / "devmem" / "memory" / "p6_stepc_analysis.py")
    sca = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sca)  # re-runs the Step C analysis on the Step D artifacts (writes step_c_analysis.* there)
    rows = sca.rows
    led = sqlite3.connect(str(LEDGER))
    lrows = led.execute("SELECT rowid, purpose, tokens_in, tokens_out, agent_id FROM llm_call_log ORDER BY rowid").fetchall()
    # the Step D process wrote the ledger rows of its calls last; align from the end
    lrows = lrows[-len(rows):]
    aligned = all(r["purpose"] == l[1] and (r["agent_id"] or None) == (l[4] or None) for r, l in zip(rows, lrows))
    windows = [json.loads(l) for l in (ART / "hourly_ledger.jsonl").read_text(encoding="utf-8").splitlines()]
    i, table = 0, []
    for w in windows:
        n = w["calls"]
        seg = list(zip(rows[i:i + n], lrows[i:i + n]))
        i += n
        cell = defaultdict(lambda: {"calls": 0, "tokens_in": 0, "tokens_out": 0})
        for r, l in seg:
            k = (r["agent_id"] or "none", r["type"])
            cell[k]["calls"] += 1
            cell[k]["tokens_in"] += l[2] or 0
            cell[k]["tokens_out"] += l[3] or 0
        table.append({"window": w["label"], "sim_clock_end": w["sim_clock"], "calls": n, "sleeping_step_fraction": w["sleeping_step_fraction"],
                      "by_agent_and_prompt_type": {f"{a} | {t}": v for (a, t), v in sorted(cell.items())}})
    # awake vs sleeping: an agent-window counts as sleeping when more than half of its steps were sleeping
    agg = defaultdict(lambda: {"awake": {"calls": 0, "tokens_in": 0, "tokens_out": 0, "agent_windows": 0},
                               "sleeping": {"calls": 0, "tokens_in": 0, "tokens_out": 0, "agent_windows": 0}})
    for w, t in zip(windows, table):
        if w["label"] == "step_0_day_start_planning":
            continue  # day-start planning is reported separately
        for a, frac in w["sleeping_step_fraction"].items():
            state = "sleeping" if frac > 0.5 else "awake"
            agg[a][state]["agent_windows"] += 1
            for key, v in t["by_agent_and_prompt_type"].items():
                if key.startswith(a + " |"):
                    for f in ("calls", "tokens_in", "tokens_out"):
                        agg[a][state][f] += v[f]
    # T re-check (pre-registration section 8)
    c = sqlite3.connect(str(ART / "memory.db"))
    mir = c.execute("SELECT agent_id, content, importance_score, sim_timestamp FROM episodic_memory").fetchall()
    scored = [m for m in mir if "is idle" not in m[1]]
    n = len(scored)
    hist = Counter(int(m[2]) for m in scored)
    frac = {str(t): round(sum(1 for m in scored if m[2] >= t) / n, 4) for t in (8, 9, 10)} if n else {}
    T = None if n < 30 else next((t for t in (8, 9, 10) if sum(1 for m in scored if m[2] >= t) / n < 0.05), 10)
    scoring_calls = sum(1 for r in rows if r["type"] == "staged_importance_scoring")
    out_t = {"population": "LLM-scored events from Step D, rule-assigned 'is idle' rows excluded (section 8, committed a28a44b)",
             "mirror_rows": len(mir), "idle_rows_excluded": len(mir) - n, "llm_scored_events": n, "scoring_calls_in_raw_log": scoring_calls,
             "histogram": {str(k): hist.get(k, 0) for k in range(1, 11)}, "by_agent": dict(Counter(m[0] for m in scored)),
             "fraction_reaching": frac, "T_from_this_population": T,
             "status": "provisional (fewer than 30)" if n < 30 else "rule applied", "frozen_provisional_T": 9,
             "T_would_change": (T is not None and T != 9), "config_changed": False}
    log = (ART / "stepd_stdout.log").read_text(encoding="utf-8", errors="ignore")
    errs = Counter(re.findall(r"Provider error on gemini \((GEMINI_KEY_\d)\): Gemini returned HTTP (\d+)", log))
    tmo = Counter(re.findall(r"Timeout \(\d+s\) on provider gemini \((GEMINI_KEY_\d)\)", log))
    cons = [json.loads(l) for l in (ART / "consolidation_log.jsonl").read_text(encoding="utf-8").splitlines()]
    out = {"label": "offline analysis of live Step D artifacts", "raw_log_ledger_alignment_ok": aligned, "records": len(rows),
           "windows": table, "awake_vs_sleeping_by_agent": agg, "T_recheck": out_t,
           "provider_errors_by_key_and_status": {f"{k[0]} HTTP {k[1]}": v for k, v in sorted(errs.items())},
           "timeouts_by_key": dict(tmo), "consolidation_sweeps": [{k: s[k] for k in ("agent", "sim_time", "night", "entries_considered",
                                                                              "cluster_size_histogram", "summaries_written", "status")} for s in cons],
           "calls_by_purpose_prompt_type": dict(Counter(r["type"] for r in rows)),
           "tokens_by_prompt_type": {t: {"in": sum(l[2] or 0 for r, l in zip(rows, lrows) if r["type"] == t),
                                         "out": sum(l[3] or 0 for r, l in zip(rows, lrows) if r["type"] == t)} for t in sorted({r["type"] for r in rows})}}
    (ART / "stepd_analysis.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("raw_log_ledger_alignment_ok", "awake_vs_sleeping_by_agent", "T_recheck", "provider_errors_by_key_and_status",
                                          "timeouts_by_key", "calls_by_purpose_prompt_type", "tokens_by_prompt_type")}, indent=1, default=str))


if __name__ == "__main__":
    main()
