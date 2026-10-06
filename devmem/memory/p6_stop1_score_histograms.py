"""
Phase 6 Stop 1 analysis (ANALYSIS ONLY, offline, zero live calls, no Stage 4 code): importance-score histograms and the pivotal
threshold T, applying docs/phase6_preregistration.md exactly as committed (commit 2e5e49b, before this script was run).

Reference population (pre-registered): LLM-assigned event/chat importance scores under the staged condition, from
  * devmem/memory/task7b_differential_results.json, key "staged" (friction experiment), and
  * the mirror databases of the saved live staged runs p5_staged_smoke and p5_staged_live (rows whose text lacks "is idle").
Reported separately, not pooled into T: control conditions, baseline, rule-assigned idle scores, summary scores, and any score source
found after the pre-registration (devmem/storage/staged_mini_run, a Phase 4 mini run).
"""
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "docs" / "phase6_stop1_artifacts"
OUT.mkdir(parents=True, exist_ok=True)


def hist(scores):
    c = Counter(int(round(s)) for s in scores)
    return {str(k): c.get(k, 0) for k in range(1, 11)}


def apply_rule(scores):
    n = len(scores)
    out = {"n": n, "fraction_reaching": {}}
    for t in (8, 9, 10):
        out["fraction_reaching"][str(t)] = round(sum(1 for s in scores if s >= t) / n, 4) if n else None
    if n < 30:
        out["T"], out["status"] = None, "provisional (fewer than 30 scored events)"
        return out
    chosen = next((t for t in (8, 9, 10) if sum(1 for s in scores if s >= t) / n < 0.05), None)
    if chosen is None:
        out["T"], out["status"] = 10, "no integer from 8 to 10 gives < 5 percent; T = 10 (Path B rare by design)"
    else:
        out["T"], out["status"] = chosen, f"smallest integer in 8..10 with fewer than 5 percent reaching it"
    return out


def db_rows(name):
    p = ROOT / "devmem" / "storage" / name / "memory.db"
    if not p.exists():
        return []
    c = sqlite3.connect(str(p))
    c.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in c.execute("SELECT agent_id, content, importance_score FROM episodic_memory")]
    finally:
        c.close()


sources = {}  # (source, condition, agent) -> list of scores
rule_assigned = Counter()

t7b = json.loads((ROOT / "devmem/memory/task7b_differential_results.json").read_text(encoding="utf-8"))
t41 = json.loads((ROOT / "devmem/memory/task4_1_control_results.json").read_text(encoding="utf-8"))
for ev in t7b["event_results"].values():
    for cond in ("baseline", "staged"):
        sources.setdefault(("friction_experiment_7b", cond, "Isabella Rodriguez"), []).extend(r["score"] for r in ev[cond])
for ev in t41["event_results"].values():
    for cond in ("control_mismatch", "control_filler"):
        sources.setdefault(("friction_experiment_4_1", cond, "Isabella Rodriguez"), []).extend(r["score"] for r in ev[cond])

for run in ("p5_staged_smoke", "p5_staged_live"):
    for r in db_rows(run):
        if "is idle" in r["content"]:
            rule_assigned[(run, r["agent_id"])] += 1
            continue
        sources.setdefault((f"live_{run}", "staged", r["agent_id"]), []).append(r["importance_score"])
late = {}
for r in db_rows("staged_mini_run"):  # found after the pre-registration; reported, not in the reference population
    if "is idle" not in r["content"]:
        late.setdefault(r["agent_id"], []).append(r["importance_score"])

# summary scores (different object): scripted sweep artifacts, results[].importance
summary_scores = []
for f in sorted((ROOT / "docs").glob("phase5_step*_artifacts/scripted_sweep_*.json")):
    d = json.loads(f.read_text(encoding="utf-8"))
    for r in d.get("first_sweep", {}).get("results", []):
        summary_scores.append({"artifact": f.name, "importance": r["importance"]})

per_source = {f"{k[0]} | {k[1]} | {k[2]}": {"n": len(v), "histogram": hist(v), "mean": round(sum(v) / len(v), 3)}
              for k, v in sorted(sources.items())}

primary = [s for (src, cond, agent), v in sources.items()
           if cond == "staged" and (src == "friction_experiment_7b" or src.startswith("live_")) for s in v]
s1 = [s for (src, cond, agent), v in sources.items() if cond == "staged" and src.startswith("live_") for s in v]
s2 = [s for (src, cond, agent), v in sources.items() if cond == "staged" and src == "friction_experiment_7b" for s in v]
s3 = [s for v in sources.values() for s in v] + [s for v in late.values() for s in v]

result = {
    "label": "offline analysis of saved artifacts; applies docs/phase6_preregistration.md (commit 2e5e49b)",
    "per_source_condition_agent": per_source,
    "reference_population_primary": {"definition": "friction_experiment_7b|staged + live staged runs (non-idle rows)",
                                     "histogram": hist(primary), **apply_rule(primary)},
    "sensitivity": {"S1_live_runs_only": {"histogram": hist(s1), **apply_rule(s1)},
                    "S2_friction_experiment_only": {"histogram": hist(s2), **apply_rule(s2)},
                    "S3_all_conditions_pooled_incl_controls_baseline_and_late_source": {"histogram": hist(s3), **apply_rule(s3)}},
    "rule_assigned_idle_rows_excluded": {f"{k[0]} | {k[1]}": v for k, v in sorted(rule_assigned.items())},
    "late_source_staged_mini_run_not_in_reference": {a: {"n": len(v), "histogram": hist(v)} for a, v in late.items()},
    "summary_scores_separate_object": summary_scores,
    "summary_scores_histogram": hist([x["importance"] for x in summary_scores]),
}
(OUT / "score_histograms.json").write_text(json.dumps(result, indent=1), encoding="utf-8")

lines = ["| source | condition | agent | n | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
for k, v in per_source.items():
    s, c, a = k.split(" | ")
    lines.append(f"| {s} | {c} | {a} | {v['n']} | " + " | ".join(str(v["histogram"][str(i)]) for i in range(1, 11)) + " |")
(OUT / "score_histograms.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines))
for name in ("reference_population_primary",):
    r = result[name]
    print("\nPRIMARY:", {k: r[k] for k in ("n", "histogram", "fraction_reaching", "T", "status")})
for k, r in result["sensitivity"].items():
    print(k, {x: r[x] for x in ("n", "histogram", "fraction_reaching", "T", "status")})
print("rule-assigned idle rows excluded:", result["rule_assigned_idle_rows_excluded"])
print("late source (not in reference):", result["late_source_staged_mini_run_not_in_reference"])
print("summary scores histogram:", result["summary_scores_histogram"], "n", len(summary_scores))
