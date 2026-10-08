"""
Results export for the paper: ONE readable file and ONE JSON with every number the paper needs, and the pre-registered predictions scored right, wrong or undecidable (with the reason).
Offline: reads the checkpoint copies, the router ledger, the run logs and the evaluation outputs; makes no call and writes nothing into a run. Anything that does not exist yet is
listed as "not available yet" and the prediction that needs it is "undecidable" with that reason, so the same code serves the interim dry run and the final export.

    python -m devmem.eval.phase9.results_export --day 2     INTERIM day 2 (labelled so; dry run of the final export)
    python -m devmem.eval.phase9.results_export --day 3     day-3 primary checkpoint (FINAL only if both arms finished and every part exists)

Rules for the verdicts (fixed here BEFORE any day-3 answer exists; they apply the pre-registration, docs/phase7_preregistration.md sections 4 to 6, literally):
  * a prediction is undecidable when the grader or the judge fails its validation (below 80 percent), when the relevant n is below 3 questions, when the data needed is missing,
    or when the registered definition matches no question; the literal reading is the verdict and any other reading is shown beside it as "observed", never as the verdict;
  * an injected event that failed its injection check in either arm is excluded from both arms (section 4); the number excluded is reported;
  * the calls of a replayed stretch after a restart are counted once in every "unique" figure (interim_report.RESTARTS).
"""
import argparse
import calendar
import glob
import json
import os
import random
import sqlite3
import time
from bisect import bisect_left
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from devmem.eval import wave_report
from devmem.eval.phase9 import d2_reproduction, grader, interim_day1, interim_report, purpose_audit, purpose_classes

ROOT = Path(__file__).resolve().parent.parent.parent.parent
ST = ROOT / "devmem" / "storage"
SIM = interim_report.SIM
DB = interim_report.DB
LAUNCH_IST = interim_report.LAUNCH_IST
EVAL = ST / "phase9_eval"
QFILE = ROOT / "docs" / "phase7_stop1_events_questions.json"
LABELS = ROOT / "docs" / "phase9_grader_validation_labels.json"
ARMS = ("baseline", "staged")
PIVOTAL = ("I5", "M5", "K5")
FRICTION = ("I3", "I9", "M3", "M9", "K3", "K9")


def _read(p: Path) -> Optional[Any]:
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return None


def _jsonl(p: Path) -> List[Dict[str, Any]]:
    try:
        return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]
    except Exception:
        return []


def _mean(xs: List[float]) -> Optional[float]:
    return round(sum(xs) / len(xs), 4) if xs else None


# ---------------------------------------------------------------- E1 per sim day and per agent
def _day_mapper(arm: str, sim: Path = None):
    d = (sim or SIM) / f"p7_{arm}" / "movement"
    pairs = sorted((os.path.getmtime(f), int(os.path.basename(f)[:-5])) for f in glob.glob(str(d / "*.json")))
    mt, st = [p[0] for p in pairs], [p[1] for p in pairs]

    def day(created_at_utc: str) -> Optional[int]:
        if not mt:
            return None
        e = calendar.timegm(time.strptime(created_at_utc[:19], "%Y-%m-%d %H:%M:%S"))
        i = bisect_left(mt, e)
        return st[i if i < len(st) else -1] // 8640 + 1
    return day


def e1_grouped(arm: str, until_ist: str, db: Path = None, restarts=None, sim: Path = None) -> Dict[str, Any]:
    """Router-ledger rows of the arm up to the copy time, by (simulated day, agent, purpose): raw and unique (second pass of each replayed stretch removed). The simulated day of a call
    is the day of the first step file written after it (the same method as step_cost_analysis); it is approximate only within a step of a day boundary."""
    db = db or DB
    restarts = interim_report.RESTARTS if restarts is None else restarts
    c = sqlite3.connect(f"file:{Path(db).as_posix()}?mode=ro", uri=True)
    a, b = interim_report._utc(LAUNCH_IST), interim_report._utc(until_ist)
    day = _day_mapper(arm, sim)

    def rows(lo, hi):
        return c.execute("SELECT created_at, COALESCE(agent_id,'none'), purpose FROM llm_call_log WHERE condition=? AND created_at>=? AND created_at<=? AND purpose NOT LIKE 'eval_%'", (arm, lo, hi)).fetchall()
    raw: Dict[Any, int] = {}
    for ts, ag, pu in rows(a, b):
        raw[(day(ts), ag, pu)] = raw.get((day(ts), ag, pu), 0) + 1
    rem: Dict[Any, int] = {}
    for restart_ist, prekill in restarts.get(arm, []):
        if restart_ist >= until_ist:
            continue
        f = (sim or SIM) / f"p7_{arm}" / "movement" / f"{prekill}.json"
        mt = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S") if f.exists() else None
        if mt is None or mt < restart_ist:
            continue
        for ts, ag, pu in rows(interim_report._utc(restart_ist), min(interim_report._utc(mt), b)):
            rem[(day(ts), ag, pu)] = rem.get((day(ts), ag, pu), 0) + 1
    c.close()
    table = [{"sim_day": k[0], "agent": k[1], "purpose": k[2], "raw": v, "unique": v - rem.get(k, 0)} for k, v in sorted(raw.items(), key=lambda kv: (str(kv[0][0]), kv[0][1], kv[0][2]))]
    by_day: Dict[str, Dict[str, int]] = {}
    for r in table:
        d = by_day.setdefault(str(r["sim_day"]), {})
        d[r["purpose"]] = d.get(r["purpose"], 0) + r["unique"]
    return {"by_day_agent_purpose": table, "unique_by_day_purpose": by_day, "raw_total": sum(r["raw"] for r in table), "unique_total": sum(r["unique"] for r in table),
            "method": "sim day = day of the first step file written after the call; replayed second passes removed"}


def e1_classes(arm: str, until_ist: str, restarts=None, sim: Path = None, aligned: Dict[str, Any] = None) -> Dict[str, Any]:
    """E1 by the rule-based CLASS of each call (purpose_classes), same window and same replay removal as e1_grouped; the primary per-purpose breakdown. The ledger keyword tag is kept as the
    ledger record beside it. `aligned` is injectable for tests."""
    restarts = interim_report.RESTARTS if restarts is None else restarts
    al = aligned or purpose_classes.aligned(arm)
    a, b = interim_report._utc(LAUNCH_IST), interim_report._utc(until_ist)
    day = _day_mapper(arm, sim)
    sel = [r for r in al["rows"] if a <= r["created_at"] <= b]
    raw: Dict[Any, int] = {}
    for r in sel:
        k = (day(r["created_at"]), r["agent"], r["class"])
        raw[k] = raw.get(k, 0) + 1
    rem: Dict[Any, int] = {}
    for restart_ist, prekill in restarts.get(arm, []):
        if restart_ist >= until_ist:
            continue
        f = (sim or SIM) / f"p7_{arm}" / "movement" / f"{prekill}.json"
        mt = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S") if f.exists() else None
        if mt is None or mt < restart_ist:
            continue
        lo, hi = interim_report._utc(restart_ist), min(interim_report._utc(mt), b)
        for r in sel:
            if lo <= r["created_at"] <= hi:
                k = (day(r["created_at"]), r["agent"], r["class"])
                rem[k] = rem.get(k, 0) + 1
    table = [{"sim_day": k[0], "agent": k[1], "class": k[2], "raw": v, "unique": v - rem.get(k, 0)} for k, v in sorted(raw.items(), key=lambda kv: (str(kv[0][0]), kv[0][1], kv[0][2]))]
    by_day: Dict[str, Dict[str, int]] = {}
    for r in table:
        d = by_day.setdefault(str(r["sim_day"]), {})
        d[r["class"]] = d.get(r["class"], 0) + r["unique"]
    tot_raw, tot_unique = sum(r["raw"] for r in table), sum(r["unique"] for r in table)
    other = sum(r["unique"] for r in table if r["class"] == "other")
    return {"by_day_agent_class": table, "unique_by_day_class": by_day, "raw_total": tot_raw, "unique_total": tot_unique, "other_share_of_unique": round(other / tot_unique, 4) if tot_unique else None,
            "pairing": {k: al[k] for k in ("ledger_rows", "log_rows", "paired", "positions_disagreeing")},
            "keyword_tag_to_class_whole_log": purpose_classes.keyword_vs_class(al["rows"]), "classes": purpose_classes.CLASSES,
            "method": "each call classified from its prompt by the rules of purpose_classes; the delivered-reply log is paired with the ledger by position (disagreement guard 0.1 percent) to give each call its time and agent"}


# ---------------------------------------------------------------- run conditions
def run_conditions(arm: str, upto_step: Optional[int] = None) -> Dict[str, Any]:
    d = ST / f"p7_{arm}"
    res = _jsonl(d / "resume_log.jsonl")
    kinds: Dict[str, int] = {}
    for r in res:
        kinds[r["event"]] = kinds.get(r["event"], 0) + 1
    outage = sum(r.get("seconds", 0) for r in _jsonl(d / "outage_log.jsonl") if r.get("event") == "outage_end") / 60
    waves = wave_report.waves(arm, LAUNCH_IST)
    done = [w for w in waves if w.get("seconds") is not None]
    hl = [h for h in _jsonl(d / "hourly_ledger.jsonl") if upto_step is None or h["step"] <= upto_step]
    st = _read(d / "run_status.json") or {}
    wall_h = (datetime.now() - datetime.strptime(LAUNCH_IST, "%Y-%m-%d %H:%M:%S")).total_seconds()
    return {"restart_log_events": kinds, "restarts_detail": [{k: r.get(k) for k in ("ts", "event", "outcome", "step", "sim_clock")} for r in res if r["event"] in ("exit", "external_kill_watchdog_restart")],
            "replayed_spans": interim_report.RESTARTS.get(arm, []), "outage_minutes_from_outage_log": round(outage, 1),
            "counters_at_last_hourly_row": {k: hl[-1].get(k) for k in ("outage_minutes_total", "rate_limit_wait_minutes_total", "quota_pauses", "step", "sim_clock")} if hl else None,
            "429_waves_whole_run_to_now": {"waves": len(waves), "waited_seconds": round(sum(w["seconds"] for w in done)), "mean_wave_seconds": round(sum(w["seconds"] for w in done) / len(done), 1) if done else None,
                                          "max_wave_seconds": round(max((w["seconds"] for w in done), default=0), 1), "share_of_wall_time_since_launch": round(sum(w["seconds"] for w in done) / wall_h, 4),
                                          "note": "wall time includes a stoppage (power off) in which no wave could occur; see the per-hour tables of devmem.eval.wave_report for windows"},
            "router_failures_in_run_status": st.get("router_failures"), "fail_safe_scores": "not logged as a separate counter (the scorer returns 4 and the call counts as a router success); router_failures counts calls that raised",
            "injection_check": st.get("injection"), "state": st.get("state")}


# ---------------------------------------------------------------- recall tables and predictions
def _events() -> Dict[str, Any]:
    return _read(QFILE)


def _dist(q: Dict[str, Any], day: int) -> Optional[int]:
    return None if q["type"] == "theme_count" else day - q["event_day"]


def recall_table(day: int, ev: Dict[str, Optional[dict]], failed: set) -> Dict[str, Any]:
    qs = _events()
    etype = {e["id"]: e["type"] for e in qs["events"]}
    rows, excluded = [], []
    for q in qs["questions"]:
        if q.get("event_day", 3) > day or (day != 3 and q["type"] == "theme_count"):
            continue
        r = {"question_id": q["id"], "agent": q["agent"], "type": q["type"], "event_id": q.get("event_id"), "event_type": etype.get(q.get("event_id")), "distance_days": _dist(q, day)}
        if q["type"] == "injected" and q["event_id"] in failed:
            r["excluded"] = f"injection of {q['event_id']} failed its check in an arm; excluded from both arms (pre-registration section 4)"
            excluded.append(q["id"])
        for arm in ARMS:
            a = next((x for x in (ev[arm] or {}).get("recall", []) if x["question_id"] == q["id"]), None)
            r[arm] = {"score": a["grade"]["score"], "strict": a["grade"]["strict"], "failure": a["grade"]["failure"]} if a and a.get("grade") else None
        rows.append(r)
    return {"rows": rows, "excluded_question_ids": excluded}


def _pool(rows: List[Dict[str, Any]], pick) -> Dict[str, Any]:
    sel = [r for r in rows if pick(r) and "excluded" not in r and r["baseline"] and r["staged"]]
    d = [r["staged"]["score"] - r["baseline"]["score"] for r in sel]
    return {"n": len(sel), "question_ids": [r["question_id"] for r in sel], "baseline_mean": _mean([r["baseline"]["score"] for r in sel]), "staged_mean": _mean([r["staged"]["score"] for r in sel]),
            "staged_minus_baseline_mean": _mean(d), "per_question_diff": {r["question_id"]: round(r["staged"]["score"] - r["baseline"]["score"], 4) for r in sel}}


def bootstrap(rows: List[Dict[str, Any]], n: int = 2000, seed: int = 20261008) -> Dict[str, Any]:
    """Mean staged-minus-baseline checklist score; resampling questions within agent, then averaging over agents; 95 percent percentile interval. Descriptive only (3 agents, one run per arm)."""
    by: Dict[str, List[float]] = {}
    for r in rows:
        if "excluded" not in r and r["baseline"] and r["staged"]:
            by.setdefault(r["agent"], []).append(r["staged"]["score"] - r["baseline"]["score"])
    if not by:
        return {"available": False}
    rng = random.Random(seed)
    means = []
    for _ in range(n):
        means.append(sum(sum(rng.choice(v) for _ in v) / len(v) for v in by.values()) / len(by))
    means.sort()
    return {"available": True, "mean": _mean([sum(v) / len(v) for v in by.values()]), "ci95": [round(means[int(0.025 * n)], 4), round(means[int(0.975 * n)], 4)], "resamples": n, "agents": len(by), "questions": sum(len(v) for v in by.values())}


def verdict(outcome: str, reason: str, **numbers) -> Dict[str, Any]:
    return {"outcome": outcome, "reason": reason, "numbers": numbers}


def predictions(day: int, label: str, arms: Dict[str, Any], recall: Dict[str, Any], grader_val: Dict[str, Any], m2: Dict[str, Any], replay: Optional[dict], d1: Dict[str, Any], d2: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    P = []
    b, s = arms["baseline"], arms["staged"]
    # E1, E2, E3 (always decidable from the copies)
    if b and s:
        bu, su = b["E1"]["unique_total"], s["E1"]["unique_total"]
        rel = (su - bu) / bu if bu else None
        ok = su > bu and rel < 0.10
        why = "S more than B by less than 10 percent" if ok else ("S made fewer calls than B; the cause is named in the purpose breakdown (E1 table)" if su <= bu else "S more than B by 10 percent or more")
        P.append({"id": "E1", "prediction": "S makes more calls than B by less than 10 percent of B's calls (unique calls, same checkpoint step)", **verdict("right" if ok else "wrong", why, baseline_unique=bu, staged_unique=su, relative_difference=round(rel, 4) if rel is not None else None)})
        e2b, e2s = b["E2_prompt_tokens"]["mean_tokens_in"], s["E2_prompt_tokens"]["mean_tokens_in"]
        P.append({"id": "E2", "prediction": "mean prompt tokens per scoring call higher in S than in B", **verdict("right" if e2s > e2b else "wrong", "direction only; the size of the priors and trait blocks is not separately checked here", baseline=e2b, staged=e2s)})
        e3b, e3s = b["E3_consolidated_fraction"]["fraction"], s["E3_consolidated_fraction"]["fraction"]
        P.append({"id": "E3", "prediction": "consolidated fraction above 0 in S and exactly 0 in B", **verdict("right" if e3s > 0 and e3b == 0 else "wrong", "B has no Stage 3 by construction", baseline=e3b, staged=e3s)})
    else:
        for i in ("E1", "E2", "E3"):
            P.append({"id": i, "prediction": i, **verdict("undecidable", "a checkpoint copy is missing for an arm")})
    rows = recall["rows"]
    grader_ok = bool(grader_val.get("interpretable"))
    answers = all(rows and any(r[a] for r in rows) for a in ARMS)

    def recall_pred(pid, text, pick, rule, need_day3=True, n_min=3):
        if need_day3 and day != 3:
            return {"id": pid, "prediction": text, **verdict("undecidable", f"interim day {day}: this prediction needs the day-3 checkpoint (pre-registration section 5b)")}
        if not grader_ok:
            return {"id": pid, "prediction": text, **verdict("undecidable", "the grader agreement is below 80 percent")}
        if not answers:
            return {"id": pid, "prediction": text, **verdict("undecidable", "recall answers are not available yet for both arms")}
        pool = _pool(rows, pick)
        if pool["n"] == 0:
            return {"id": pid, "prediction": text, **verdict("undecidable", "the registered definition matches no question (see the note below the table)")}
        if pool["n"] < n_min:
            return {"id": pid, "prediction": text, **verdict("undecidable", f"n = {pool['n']} question(s), below the 3 required by pre-registration section 6; the observed difference is shown, not scored", **pool)}
        ok = rule(pool)
        return {"id": pid, "prediction": text, **verdict("right" if ok else "wrong", "applied literally", **pool)}
    P.append(recall_pred("R1", "S answers Isabella's theme-count question no worse than B", lambda r: r["question_id"] == "Q_I_theme", lambda p: p["staged_mean"] >= p["baseline_mean"]))
    P.append(recall_pred("R2", "S answers Klaus's theme-count question no worse than B", lambda r: r["question_id"] == "Q_K_theme", lambda p: p["staged_mean"] >= p["baseline_mean"]))
    P.append(recall_pred("R3", "pivotal events I5, M5, K5 at distance 2: no checklist difference larger than 0.2",
                         lambda r: r["event_id"] in PIVOTAL and r["distance_days"] == 2, lambda p: abs(p["staged_minus_baseline_mean"]) <= 0.2))
    P.append(recall_pred("R4", "mundane events at distance 2: S at or below B", lambda r: r["event_type"] == "mundane" and r["distance_days"] == 2, lambda p: p["staged_minus_baseline_mean"] <= 0))
    P.append(recall_pred("R5", "same-day questions (distance 0): no difference larger than 0.1", lambda r: r["distance_days"] == 0, lambda p: abs(p["staged_minus_baseline_mean"]) <= 0.1, need_day3=False))
    # scoring directions from the replay controls
    for pid, agent, sign in (("S-Isabella", "Isabella Rodriguez", 1), ("S-Maria", "Maria Lopez", 1), ("S-Klaus", "Klaus Mueller", -1)):
        text = f"staged minus baseline mean importance on the persona's friction events is {'above' if sign > 0 else 'below'} 0"
        fr = (replay or {}).get("friction_events_staged_minus_baseline_inputs", {}).get(agent) if replay else None
        if not fr or "staged_own" not in fr or "baseline" not in fr:
            P.append({"id": pid, "prediction": text, **verdict("undecidable", "replay controls have not been run yet (they run on the staged pool after the staged arm finishes)")})
            continue
        diff = round(fr["staged_own"]["mean"] - fr["baseline"]["mean"], 3)
        P.append({"id": pid, "prediction": text, **verdict("right" if diff * sign > 0 else "wrong", f"n = {fr['staged_own']['n']} friction events for this persona (a small n; the sign is the verdict, no more)", staged_minus_baseline=diff, detail=fr)})
    # mismatch and filler (registered text: "move toward that persona's direction" / "toward the baseline")
    if replay and replay.get("summary", {}).get("by_condition"):
        bc = replay["summary"]["by_condition"]
        if all(k in bc for k in ("staged_own", "filler", "baseline")):
            dist = lambda k: abs(bc[k]["mean"] - bc["baseline"]["mean"])
            P.append({"id": "S-filler", "prediction": "neutral filler moves scores toward the baseline (closer to baseline than staged is)", **verdict("right" if dist("filler") < dist("staged_own") else "wrong", "over the whole sample, all personas pooled", filler_mean=bc["filler"]["mean"], baseline_mean=bc["baseline"]["mean"], staged_mean=bc["staged_own"]["mean"])})
    mm = ((replay or {}).get("summary", {}).get("by_condition") or {}).get("mismatch")
    P.append({"id": "S-mismatch", "prediction": "mismatch priors move scores toward that persona's direction", **verdict("undecidable", "PM ruling 2026-10-08: the registered text gives no sign for Wolfgang Schulz's direction; observed value only", observed_mismatch_mean=(mm or {}).get("mean"))})
    # coherence: no directional prediction
    P.append({"id": "M2", "prediction": "no directional prediction (two-sided, only if the judge calibration is at least 80 percent)", **verdict("undecidable" if not m2.get("available") else "no prediction", m2.get("note", "reported two-sided"), **({k: m2[k] for k in ("calibration_accuracy", "coherence_interpretable")} if m2.get("available") else {}))})
    # diagnostics
    tr = d1.get("traits", 0)
    if d1.get("available", 0) >= 3:
        frac = d1["flagged"] / d1["available"]
        P.append({"id": "D-1", "prediction": "at least one third of Stage 4 traits closer to the priors text than to their sources", **verdict("right" if frac >= 1 / 3 else "wrong", "cached-embedding cosines; a diagnostic", traits=tr, available=d1["available"], flagged=d1["flagged"], fraction=round(frac, 3))})
    else:
        P.append({"id": "D-1", "prediction": "at least one third of Stage 4 traits closer to the priors text than to their sources", **verdict("undecidable", f"fewer than 3 traits with cached embeddings (traits {tr}, available {d1.get('available', 0)})", **d1)})
    if d2 and d2.get("agents"):
        sc = d2_reproduction.score(d2)
        P.append({"id": "D-2", "prediction": "Stage 3 entries merged between cosine 0.80 and 0.88 above 0 over the nights, per agent (merge heights recovered offline by re-running the recorded clustering); WEAK BY DESIGN: at threshold 0.82 nearly every merge falls in this band", **verdict(sc["outcome"], sc["reason"], **sc["numbers"])})
    else:
        P.append({"id": "D-2", "prediction": "Stage 3 entries merged between cosine 0.80 and 0.88 above 0", **verdict("undecidable", "the offline reproduction of the recorded clustering is not available")})
    return P


# ---------------------------------------------------------------- M2, D-1, replay
def m2_section(ev: Dict[str, Optional[dict]]) -> Dict[str, Any]:
    cal = _read(EVAL / "judge_calibration.json")
    if not all(ev.get(a) for a in ARMS) or not cal:
        return {"available": False, "note": "day-1 against day-3 judge results or the judge calibration are not available yet", "calibration_available": bool(cal)}
    out: Dict[str, Any] = {"available": True, "calibration_accuracy": cal.get("accuracy"), "coherence_interpretable": cal.get("coherence_interpretable"), "confusion_matrix_true_by_judged": cal.get("confusion_matrix_true_by_judged"),
                           "calibration_pairs": cal.get("pairs"), "calibration_parse_failures": cal.get("parse_failures"), "arms": {}}
    for arm in ARMS:
        js = ev[arm]["judge"]
        per: Dict[str, Dict[str, int]] = {}
        for j in js:
            p = per.setdefault(j["agent"], {"consistent": 0, "contradictory": 0, "unrelated": 0, "parse_failure": 0, "n": 0})
            p[j["judge_label"] or "parse_failure"] += 1
            p["n"] += 1
        out["arms"][arm] = {"pairs": len(js), "contradiction_rate": round(sum(1 for j in js if j["judge_label"] == "contradictory") / len(js), 4) if js else None, "per_agent": per}
    return out


def d1_provenance(memory_db: Path) -> Dict[str, Any]:
    from devmem.api import store
    if not Path(memory_db).exists():
        return {"traits": 0, "available": 0, "flagged": 0, "note": "no memory database"}
    c = sqlite3.connect(f"file:{Path(memory_db).as_posix()}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    sem = {r["entry_id"]: r["summary"] for r in c.execute("SELECT entry_id, summary FROM semantic_memory")}
    rows, avail, flagged = [], 0, 0
    for t in c.execute("SELECT * FROM identity_traits"):
        src = [sem.get(s, "") for s in json.loads(t["source_semantic_ids_json"])]
        for e in json.loads(t["source_event_ids_json"]):
            r = c.execute("SELECT content FROM episodic_memory WHERE entry_id=?", (e,)).fetchone()
            src.append(r[0] if r else "")
        pr = store.provenance(t["text"], [x for x in src if x], " ".join(p["statement"] for p in store.priors_for(t["agent_id"])))
        if pr.get("available"):
            avail += 1
            flagged += 1 if pr["closer_to_priors_than_to_best_source"] else 0
        rows.append({"trait_id": t["trait_id"], "agent": t["agent_id"], "available": pr.get("available"), "cosine_to_priors": pr.get("cosine_to_priors_text"),
                     "best_source_cosine": max((x["cosine"] for x in pr.get("cosine_to_sources", [])), default=None), "closer_to_priors": pr.get("closer_to_priors_than_to_best_source")})
    n = len(rows)
    c.close()
    return {"traits": n, "available": avail, "flagged": flagged, "rows": rows}


def purpose_tag_audit() -> Dict[str, Any]:
    """The router ledger's `purpose` of the upstream calls is a keyword heuristic on the prompt text. Audit of the tags planning, dialogue, reflection and importance_scoring against the
    upstream prompt family (devmem/eval/phase9/purpose_audit.py; sample of 200 rows per tag per arm with seed 20261008 for the large tags). The tags are NOT changed in the live arms."""
    return purpose_audit.audit()


def sweeps_per_night(memory_db: Path) -> Dict[str, Any]:
    if not Path(memory_db).exists():
        return {}
    return interim_day1.sweep_markers(memory_db)


# ---------------------------------------------------------------- build
def build(day: int, interim_root: Path = None) -> Dict[str, Any]:
    root = interim_root or (ST / ("interim_day2" if day == 2 else "interim_day3"))
    ev = {a: _read(EVAL / (a if day == 3 else f"{a}_day2") / "evaluation.json") for a in ARMS}
    arms: Dict[str, Any] = {}
    for a in ARMS:
        cdir = root / a
        arms[a] = interim_report.analyse_copy(a, cdir)
        if arms[a]:
            arms[a]["E1"]["per_day_agent_purpose"] = e1_grouped(a, arms[a]["checkpoint"]["made_at"])
            try:
                arms[a]["E1"]["per_day_agent_class"] = e1_classes(a, arms[a]["checkpoint"]["made_at"])
                if arms[a]["E1"]["per_day_agent_class"]["unique_total"] != arms[a]["E1"]["per_day_agent_purpose"]["unique_total"]:
                    arms[a]["E1"]["per_day_agent_class"]["total_check"] = f"class unique total {arms[a]['E1']['per_day_agent_class']['unique_total']} differs from the ledger unique total {arms[a]['E1']['per_day_agent_purpose']['unique_total']} (the log and the ledger are read at slightly different moments)"
            except Exception as exc:
                arms[a]["E1"]["per_day_agent_class"] = {"available": False, "note": f"{type(exc).__name__}: {str(exc)[:160]}"}
    status = {a: (_read(ST / f"p7_{a}" / "run_status.json") or {}).get("state") for a in ARMS}
    failed = set()
    for a in ARMS:
        failed |= set(((_read(ST / f"p7_{a}" / "run_status.json") or {}).get("injection") or {}).get("fail", []))
    recall = recall_table(day, ev, failed)
    gv = grader.validate(_read(LABELS), _events())
    d1 = d1_provenance(root / "staged" / "memory.db")
    rep = _read(EVAL / "replay_controls.json")
    m2 = m2_section(ev)
    finished = all(str(status[a] or "").startswith("finished") for a in ARMS)
    complete = day == 3 and finished and all(ev[a] for a in ARMS) and bool(rep) and m2.get("available")
    lab = f"INTERIM day {day} (dry run of the final export)" if day == 2 else ("FINAL day-3 export" if complete else "day-3 export, PARTIAL: " + "; ".join(x for x in (
        "an arm has not finished" if not finished else "", "evaluation answers missing" if not all(ev[a] for a in ARMS) else "", "replay controls missing" if not rep else "", "judge results or calibration missing" if not m2.get("available") else "") if x))
    try:
        sdb = root / "staged" / "memory.db"
        conn = sqlite3.connect(f"file:{sdb.as_posix()}?mode=ro", uri=True)
        present = {(r[0], r[1]) for r in conn.execute("SELECT agent_id, night FROM consolidation_sweeps WHERE status='done'")}
        conn.close()
        logrows = [x for x in _jsonl(ST / "p7_staged" / "consolidation_log.jsonl") if (x["agent"], x["night"]) in present]
        d2 = d2_reproduction.reproduce(sdb, logrows, d2_reproduction.persona_vec_fn(SIM / "p7_staged" / "personas"))
        d2["verdict"] = d2_reproduction.score(d2)
    except Exception as exc:
        d2 = {"available": False, "note": f"{type(exc).__name__}: {str(exc)[:120]}"}
    out = {"label": lab, "day": day, "built_at": time.strftime("%Y-%m-%d %H:%M:%S"), "arm_states": status, "single_run_per_arm": True, "agents": 3,
           "arms": arms, "run_conditions": {a: run_conditions(a, (arms[a] or {}).get("checkpoint", {}).get("step")) for a in ARMS},
           "sweep_markers_per_agent_and_night": {"staged": sweeps_per_night(root / "staged" / "memory.db"), "baseline": "none by design (no Stage 3)"},
           "recall": {"rows": recall["rows"], "excluded_question_ids": recall["excluded_question_ids"], "grader_validation": {k: gv[k] for k in ("items_checked", "item_agreement", "answers", "answer_agreement", "interpretable")},
                      "grader_disagreements": gv["disagreements"], "bootstrap_staged_minus_baseline": bootstrap(recall["rows"]),
                      "pivotal_observed_not_pre_registered": _pool(recall["rows"], lambda r: r["event_id"] in PIVOTAL), "definition_notes": [
                          "R3 as registered says distance 2, but I5, M5 and K5 are day-2 events: at the day-3 checkpoint their distance is 1; the literal registered definition matches no question. The observed pivotal pool is shown separately.",
                          "R1 and R2 each rest on one question (n = 1 < 3): undecidable under pre-registration section 6; the observed values are shown."]},
           "coherence_M2": m2, "stage2_replay_controls": rep if rep else {"available": False, "note": "not run yet"}, "D1_provenance": d1,
           "D2_reproduction": d2, "purpose_tag_audit": purpose_tag_audit(),
           "consolidation_log_per_agent_and_night": _jsonl(ST / "p7_staged" / "consolidation_log.jsonl"), "evaluation_calls": {a: (ev[a] or {}).get("counts") for a in ARMS}}
    out["predictions"] = predictions(day, lab, arms, recall, gv, m2, rep, d1, d2)
    return out


def markdown(r: Dict[str, Any]) -> str:
    L = [f"# Results export: {r['label']}", "", f"Built {r['built_at']}. Single run per arm, 3 agents: descriptive only, no significance claims, no causal attribution to one stage (periodic reflection (focal-point and insight generation) is off in the staged arm by decision D1; the post-conversation planning-thought and memo calls in reflect() run in both arms). Arm states: {r['arm_states']}.", ""]
    L += ["## Predictions (pre-registration section 5, scored by the rules in the module header)", "", "| id | prediction | outcome | reason | numbers |", "|---|---|---|---|---|"]
    for p in r["predictions"]:
        nums = ", ".join(f"{k}={v}" for k, v in p["numbers"].items() if not isinstance(v, (dict, list))) if p.get("numbers") else ""
        L.append(f"| {p['id']} | {p['prediction']} | **{p['outcome']}** | {p['reason']} | {nums} |")
    L += ["", "## E1 to E3 (checkpoint copies)", "", "| item | baseline | staged |", "|---|---|---|"]
    A = r["arms"]
    g = lambda arm, f: f(A[arm]) if A[arm] else "not available"
    L.append("| checkpoint | " + " | ".join(g(a, lambda v: f"step {v['checkpoint']['step']}, sim {v['checkpoint']['sim_clock']}") for a in ARMS) + " |")
    L.append("| E1 calls raw / unique | " + " | ".join(g(a, lambda v: f"{v['E1']['raw_total']} / {v['E1']['unique_total']}") for a in ARMS) + " |")
    L.append("| E2 mean tokens in per importance call | " + " | ".join(g(a, lambda v: f"{v['E2_prompt_tokens']['mean_tokens_in']} ({v['E2_prompt_tokens']['calls']} calls)") for a in ARMS) + " |")
    L.append("| E3 consolidated fraction | " + " | ".join(g(a, lambda v: f"{v['E3_consolidated_fraction']['fraction']} ({v['E3_consolidated_fraction']['consolidated']} of {v['E3_consolidated_fraction']['entries']})") for a in ARMS) + " |")
    L += ["", "### E1 unique calls by CLASS per simulated day (primary breakdown; rule-based classes from the prompts, devmem/eval/phase9/purpose_classes.py)", "", "| arm | sim day | class | unique calls |", "|---|---|---|---|"]
    for a in ARMS:
        pc = (A[a] or {}).get("E1", {}).get("per_day_agent_class") if A[a] else None
        if pc and pc.get("unique_by_day_class"):
            for d, cl in pc["unique_by_day_class"].items():
                for c_, n in sorted(cl.items()):
                    L.append(f"| {a} | {d} | {c_} | {n} |")
            L.append(f"| {a} | all | other (share of unique) | {pc['other_share_of_unique']} |")
            if pc.get("total_check"):
                L.append(f"| {a} | note | {pc['total_check']} | |")
    L += ["", "Where each ledger keyword tag's calls go in the classes (whole log, both arms):", ""]
    for a in ARMS:
        pc = (A[a] or {}).get("E1", {}).get("per_day_agent_class") if A[a] else None
        if pc and pc.get("keyword_tag_to_class_whole_log"):
            L.append(f"- {a}: {json.dumps(pc['keyword_tag_to_class_whole_log'])}")
    L += ["", "### E1 unique calls by the ledger KEYWORD tag per simulated day (the ledger record, not a classification); the last column is the purpose-tag audit (false-match rate of the keyword tag, sampled)", "", "| arm | sim day | purpose | unique calls | tag audit |", "|---|---|---|---|---|"]
    aud = r.get("purpose_tag_audit", {}).get("arms", {})

    def audit_cell(a, p):
        x = aud.get(a, {}).get("tags", {}).get(p)
        return "not audited (set by the code, not by the keyword rule)" if x is None else f"{x['false_match_rate_of_classified']} false-match rate ({x['false_match']} of {x['true_family'] + x['false_match']} classified, {x['audited']} audited)"
    for a in ARMS:
        if A[a]:
            for d, pu in A[a]["E1"]["per_day_agent_purpose"]["unique_by_day_purpose"].items():
                for p, n in sorted(pu.items()):
                    L.append(f"| {a} | {d} | {p} | {n} | {audit_cell(a, p)} |")
    L += ["", "### E1 unique calls per agent (simulated day, purpose)", "", "| arm | agent | sim day | purpose | raw | unique |", "|---|---|---|---|---|---|"]
    for a in ARMS:
        if A[a]:
            for x in A[a]["E1"]["per_day_agent_purpose"]["by_day_agent_purpose"]:
                L.append(f"| {a} | {x['agent']} | {x['sim_day']} | {x['purpose']} | {x['raw']} | {x['unique']} |")
    L += ["", "## Sweep markers per agent and night (staged)", ""]
    for ag, ms in (r["sweep_markers_per_agent_and_night"]["staged"] or {}).items():
        L.append(f"- {ag}: " + ", ".join(f"night {m['night']} {m['status']}" for m in ms))
    L += ["", "## Recall (R1 to R5): per question", "", f"Grader validation: {r['recall']['grader_validation']}. Excluded questions: {r['recall']['excluded_question_ids'] or 'none'}.", "", "| question | agent | type | event | distance | baseline score | staged score | note |", "|---|---|---|---|---|---|---|---|"]
    for q in r["recall"]["rows"]:
        L.append(f"| {q['question_id']} | {q['agent']} | {q['type']} | {q['event_id']} | {q['distance_days']} | {q['baseline']['score'] if q['baseline'] else 'n/a'} | {q['staged']['score'] if q['staged'] else 'n/a'} | {q.get('excluded', '')} |")
    L += ["", f"Bootstrap of the mean staged-minus-baseline difference: {r['recall']['bootstrap_staged_minus_baseline']}", ""]
    L += [f"- {n}" for n in r["recall"]["definition_notes"]]
    L += ["", "## Purpose-tag audit (planning, dialogue, reflection, importance_scoring)", "", json.dumps({k: v for k, v in r["purpose_tag_audit"].items() if k != "family_table"}, indent=1), ""]
    L += ["", "## Coherence (M2)", "", json.dumps(r["coherence_M2"], indent=1), "", "## Stage 2 replay controls", "", json.dumps({k: v for k, v in (r["stage2_replay_controls"] or {}).items() if k != "rows"}, indent=1), "",
          "## D-1 provenance and D-2", "", f"D-1: {r['D1_provenance'].get('traits')} traits, {r['D1_provenance'].get('available')} with cached embeddings, {r['D1_provenance'].get('flagged')} closer to the priors than to the best source.", "", "D-2 NOTE: right, but weak by design: with the clustering threshold at 0.82 nearly every merge falls in the 0.80 to 0.88 band, so a count above 0 was close to certain. D-2 reproduction (nights, reproduced, count): " + json.dumps({a: [(n['night'], n.get('reproduced'), n.get('d2_entries_in_range_min_cluster')) for n in v['nights']] for a, v in (r['D2_reproduction'].get('agents') or {}).items()}) + f"; verdict {r['D2_reproduction'].get('verdict')}", "",
          "## Run conditions per arm (failures, restarts, replayed spans, outage minutes, 429 wave shares)", ""]
    for a in ARMS:
        c = r["run_conditions"][a]
        L += [f"### {a}", "", f"- state {c['state']}; router failures {c['router_failures_in_run_status']}; fail-safe: {c['fail_safe_scores']}", f"- restart log events {c['restart_log_events']}; replayed spans (restart wall time, pre-kill step): {c['replayed_spans']}",
              f"- outage minutes (outage log) {c['outage_minutes_from_outage_log']}; counters at the last hourly row {c['counters_at_last_hourly_row']}", f"- 429 waves, whole run to now: {c['429_waves_whole_run_to_now']}", f"- injection check {c['injection_check']}", ""]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", type=int, choices=[2, 3], required=True)
    a = ap.parse_args()
    r = build(a.day)
    tag = "interim_day2" if a.day == 2 else "day3"
    (ROOT / "docs" / f"phase9_results_export_{tag}.json").write_text(json.dumps(r, indent=1, default=str), encoding="utf-8")
    (ROOT / "docs" / f"phase9_results_export_{tag}.md").write_text(markdown(r), encoding="utf-8")
    print(r["label"])
    for p in r["predictions"]:
        print(f"{p['id']:12} {p['outcome']:12} {p['reason'][:110]}")


if __name__ == "__main__":
    main()
