"""
Offline builder of the full-run data of the viewer (Findings, Where it differs and why, Edge cases, Cost view, per-night memory views, injected-event jumps) for the seminar of 2026-10-09.

Reads only finished artifacts: the final day-3 results export (docs/phase9_results_export_day3.json), the evaluation outputs, the replay controls, the run logs, the router ledger, the staged
mirror and the saved baseline memory. NO LLM call, NO network, NO write to any run folder, NO generated narrative: every sentence is a fixed template filled with logged fields.
Writes devmem/api/web/data/full_run.json, which the page only displays.

    PYTHONPATH=<repo>;<repo>/reverie/reverie/backend_server .venv/Scripts/python.exe -m devmem.api.build_full_run
"""
import json
import re
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "devmem" / "api" / "web" / "data" / "full_run.json"
ST = ROOT / "devmem" / "storage"
EVAL = ST / "phase9_eval"
DOCS = ROOT / "docs"
SIM = ROOT / "reverie" / "environment" / "frontend_server" / "storage"
START = datetime(2023, 2, 13, 0, 0, 0)
TAIL = re.compile(r"\s*\(duration in minutes:\s*\d+,\s*minutes left:\s*\d+\)")
ARMS = ("baseline", "staged")
D1_WORDING = ("periodic reflection (focal-point and insight generation) is off in the staged arm; the post-conversation planning-thought and memo calls in reflect() run in both arms")
STANDING = "single run per arm; descriptive results; differences can be model noise"
DISTANCE_GROUPS = [("same day", lambda r: r["type"] != "theme_count" and r["distance_days"] == 0), ("1 day", lambda r: r["type"] != "theme_count" and r["distance_days"] == 1),
                   ("2 days", lambda r: r["type"] != "theme_count" and r["distance_days"] == 2), ("theme count", lambda r: r["type"] == "theme_count")]


def _read(p: Path) -> Any:
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return None


def _jsonl(p: Path) -> List[Dict[str, Any]]:
    try:
        return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]
    except Exception:
        return []


def clean_action(s: Any) -> str:
    return TAIL.sub("", str(s or "")).split("@")[0].strip()


def clock_of(step: int) -> str:
    return (START + timedelta(seconds=10 * int(step))).strftime("%Y-%m-%d %H:%M:%S")


def mean(xs: List[float]) -> Optional[float]:
    return round(sum(xs) / len(xs), 4) if xs else None


def by_distance(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for name, pick in DISTANCE_GROUPS:
        sel = [r for r in rows if "excluded" not in r and r.get("baseline") and r.get("staged") and pick(r)]
        out.append({"group": name, "n": len(sel), "baseline_mean": mean([r["baseline"]["score"] for r in sel]), "staged_mean": mean([r["staged"]["score"] for r in sel])})
    return out


def first_divergence(frames_a: List[Dict[str, Any]], frames_b: List[Dict[str, Any]], agent: str) -> Optional[Dict[str, Any]]:
    """First step at which the cleaned action text of the agent differs between two runs (frames: [{"s": step, "p": {agent: [x, y, emoji, text, chat]}}])."""
    mb = {f["s"]: f for f in frames_b}
    for f in sorted(frames_a, key=lambda x: x["s"]):
        g = mb.get(f["s"])
        if g and f["p"].get(agent) and g["p"].get(agent):
            a, b = clean_action(f["p"][agent][3]), clean_action(g["p"][agent][3])
            if a != b:
                return {"step": f["s"], "clock": clock_of(f["s"]), "left_action": a, "right_action": b}
    return None


def scorecard(exp: Dict[str, Any], replay: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    has_new = bool(replay and "staged_replayed" in ((replay.get("summary") or {}).get("by_condition") or {}))
    out = []
    for p in exp["predictions"]:
        nums = {k: v for k, v in (p.get("numbers") or {}).items() if not isinstance(v, (dict, list))}
        row = {"id": p["id"], "prediction": p["prediction"], "outcome": p["outcome"], "reason": p["reason"], "numbers": nums, "being_re_run": False}
        if p["id"] in ("S-Isabella", "S-Maria", "S-Klaus", "S-filler") and not has_new:
            row.update({"outcome": "being re-run", "reason": "the staged condition is being replayed (PM correction 2026-10-09); the earlier verdict used the recorded in-run scores", "being_re_run": True})
        out.append(row)
    return out


def replay_section(replay: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not replay:
        return {"available": False}
    bc = (replay.get("summary") or {}).get("by_condition") or {}
    fr = replay.get("friction_events_staged_minus_baseline_inputs") or {}
    return {"available": True, "label": replay.get("label"), "seed": replay.get("seed"), "n_injected": replay.get("n_injected"), "n_natural": replay.get("n_natural"),
            "conditions_present": sorted(bc), "staged_replayed_present": "staged_replayed" in bc, "whole_sample_means": bc, "friction_by_agent": fr,
            "note": replay.get("conditions_note", "")}


def questions() -> Dict[str, Any]:
    return {q["id"]: q for q in _read(DOCS / "phase7_stop1_events_questions.json")["questions"]}


def recall_section(exp: Dict[str, Any]) -> Dict[str, Any]:
    qs = questions()
    ev = {a: _read(EVAL / a / "evaluation.json") for a in ARMS}
    ans = {a: {x["question_id"]: x for x in (ev[a] or {}).get("recall", [])} for a in ARMS}
    rows = []
    for r in exp["recall"]["rows"]:
        q = qs.get(r["question_id"], {})
        row = dict(r)
        row["question"] = q.get("question")
        row["checklist"] = [c["item"] for c in q.get("checklist", [])]
        for a in ARMS:
            x = ans[a].get(r["question_id"])
            row[a + "_answer"] = x["answer"] if x else None
            row[a + "_items"] = (x.get("grade") or {}).get("items") if x else None
        rows.append(row)
    differing = [r for r in rows if "excluded" not in r and r.get("baseline") and r.get("staged") and r["baseline"]["score"] != r["staged"]["score"]]
    return {"rows": rows, "by_distance": by_distance(rows), "differing_question_ids": [r["question_id"] for r in differing], "excluded": exp["recall"]["excluded_question_ids"],
            "grader": exp["recall"]["grader_validation"], "bootstrap": exp["recall"]["bootstrap_staged_minus_baseline"], "notes": exp["recall"]["definition_notes"],
            "retrieval_note": "Which memory items were retrieved is not logged (the answer harness logged the number retrieved, not the items)."}


def class_calls() -> Dict[str, Any]:
    from devmem.eval.phase9 import results_export as RE
    out = {}
    until = time.strftime("%Y-%m-%d %H:%M:%S")
    for a in ARMS:
        try:
            r = RE.e1_classes(a, until)
            out[a] = {"unique_by_day_class": r["unique_by_day_class"], "unique_total": r["unique_total"], "raw_total": r["raw_total"], "other_share_of_unique": r["other_share_of_unique"],
                      "keyword_tag_to_class": r["keyword_tag_to_class_whole_log"], "classes": r["classes"], "pairing": r["pairing"]}
        except Exception as exc:
            out[a] = {"available": False, "note": f"{type(exc).__name__}: {str(exc)[:160]}"}
    return out


def injections() -> List[Dict[str, Any]]:
    rows: Dict[str, Dict[str, Any]] = {}
    for a in ARMS:
        for r in _jsonl(ST / f"p7_{a}" / "injection_log.jsonl"):
            d = rows.setdefault(r["id"], {"id": r["id"], "agent": r["agent"], "type": r["type"], "planned": r["planned"]})
            d[a] = {"step": r["injected_step"], "clock": r["injected_clock"], "result": r["result"], "importance": r.get("importance"), "node_id": r.get("node_id"), "stored_text": r.get("stored_text")}
    out = []
    for k, d in sorted(rows.items(), key=lambda kv: kv[1].get("baseline", kv[1].get("staged", {})).get("step", 0)):
        d["step"] = (d.get("staged") or d.get("baseline") or {}).get("step")
        d["both_perceived"] = all((d.get(a) or {}).get("result") == "PASS" for a in ARMS)
        d["importance_difference"] = (d["staged"]["importance"] - d["baseline"]["importance"]) if d["both_perceived"] and d["staged"].get("importance") is not None and d["baseline"].get("importance") is not None else None
        out.append(d)
    return out


def nights_section() -> Dict[str, Any]:
    mdb = ST / "interim_day3" / "staged" / "memory.db"
    if not mdb.exists():
        return {"available": False}
    c = sqlite3.connect(f"file:{mdb.as_posix()}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    epi = {r["entry_id"]: dict(r) for r in c.execute("SELECT entry_id, content, sim_timestamp, importance_score FROM episodic_memory")}
    sem = {r["entry_id"]: dict(r) for r in c.execute("SELECT entry_id, summary, importance_score, created_at FROM semantic_memory")}
    ev: Dict[Any, List[Dict[str, Any]]] = {}
    for r in c.execute("SELECT * FROM consolidation_events ORDER BY night, semantic_id"):
        src = json.loads(r["new_source_ids_json"])
        ev.setdefault((r["agent_id"], r["night"]), []).append({"semantic_id": r["semantic_id"], "action": r["action"], "match_similarity": r["match_similarity"],
                                                               "summary": (sem.get(r["semantic_id"]) or {}).get("summary"),
                                                               "sources": [{"id": s, "time": (epi.get(s) or {}).get("sim_timestamp"), "text": (epi.get(s) or {}).get("content"), "importance": (epi.get(s) or {}).get("importance_score")} for s in src]})
    log = _jsonl(ST / "p7_staged" / "consolidation_log.jsonl")
    idlog = {(r["agent"], r["night"]): r for r in _jsonl(ST / "p7_staged" / "identity_log.jsonl")}
    nights = []
    for r in log:
        i = idlog.get((r["agent"], r["night"])) or {}
        nights.append({"agent": r["agent"], "night": r["night"], "sim_time": r["sim_time"], "entries_considered": r["entries_considered"], "threshold": r["threshold"], "linkage": r["linkage"],
                       "cluster_size_histogram": r["cluster_size_histogram"], "summaries_written": r["summaries_written"], "summaries_reinforced": r["summaries_reinforced"],
                       "entries_flagged": r["entries_flagged"], "status": r["status"], "failures": r["failures"], "summaries": ev.get((r["agent"], r["night"]), []),
                       "identity_step": {"traits_created": [t.get("trait_id") for t in i.get("traits_created", [])], "decision_counts": i.get("decision_counts"), "evicted": i.get("evicted"), "status": i.get("status")}})
    # traits with sources, the D-1 provenance cosine and the identity context as fed into scoring
    from devmem.eval.phase9 import results_export as RE
    from devmem.memory import identity
    prov = {r["trait_id"]: r for r in RE.d1_provenance(mdb).get("rows", [])}
    traits = []
    for r in c.execute("SELECT * FROM identity_traits ORDER BY agent_id, created_night, trait_id"):
        p = prov.get(r["trait_id"], {})
        traits.append({"trait_id": r["trait_id"], "agent": r["agent_id"], "text": r["text"], "path": r["path"], "night": r["created_night"], "sim_time": r["created_sim_time"], "active": bool(r["active"]),
                       "semantic_sources": [{"id": s, "summary": (sem.get(s) or {}).get("summary")} for s in json.loads(r["source_semantic_ids_json"])],
                       "event_sources": [{"id": e, "time": (epi.get(e) or {}).get("sim_timestamp"), "text": (epi.get(e) or {}).get("content")} for e in json.loads(r["source_event_ids_json"])],
                       "provenance_cosine_to_priors": p.get("cosine_to_priors"), "provenance_best_source_cosine": p.get("best_source_cosine"), "closer_to_priors_than_to_best_source": p.get("closer_to_priors")})
    ctx = {}
    for a in sorted({t["agent"] for t in traits}):
        act = [t["text"] for t in sorted([t for t in traits if t["agent"] == a and t["active"]], key=lambda t: (-t["night"], t["trait_id"]))]
        ctx[a] = identity.render_identity_context(act)[0]
    c.close()
    return {"available": True, "nights": nights, "traits": traits, "identity_context_final_active_traits": ctx, "provenance_flagged": sum(1 for t in traits if t["closer_to_priors_than_to_best_source"]), "provenance_n": len(traits)}


def baseline_reflections() -> Dict[str, Any]:
    out = {}
    for a in ("Isabella Rodriguez", "Klaus Mueller", "Maria Lopez"):
        f = SIM / "p7_baseline" / "personas" / a / "bootstrap_memory" / "associative_memory" / "nodes.json"
        n = _read(f) or {}
        th = sorted([v for v in n.values() if v.get("type") == "thought"], key=lambda v: v["created"])
        post = [v for v in th if str(v["description"]).startswith("For ") and "planning" in str(v["description"])[:40]]
        out[a] = {"thought_nodes": len(th), "post_conversation_planning_thoughts": len(post), "stream_nodes": len(n),
                  "thoughts": [{"created": v["created"], "text": v["description"], "evidence_nodes": len(v.get("filling") or [])} for v in th if v not in post][:60]}
    return out


def scoring_card(inj: List[Dict[str, Any]]) -> Dict[str, Any]:
    from devmem.memory import identity
    from devmem.memory.priors import get_prompt_context
    mdb = ST / "interim_day3" / "staged" / "memory.db"
    c = sqlite3.connect(f"file:{mdb.as_posix()}?mode=ro", uri=True)
    texts = {r[0]: r[1] for r in c.execute("SELECT trait_id, text FROM identity_traits")}
    rows = []
    for d in inj:
        if not d["both_perceived"]:
            continue
        ctx = ""
        nid = (d.get("staged") or {}).get("node_id")
        if nid:
            r = c.execute("SELECT trait_ids_json FROM event_scoring_context WHERE agent_id=? AND entry_id=?", (d["agent"], f"{d['agent']}:{nid}")).fetchone()
            ids = json.loads(r[0]) if r else []
            ctx = identity.render_identity_context([texts[i] for i in ids if i in texts])[0] if ids else ""
        rows.append({"id": d["id"], "agent": d["agent"], "type": d["type"], "step": d["step"], "text": (d.get("staged") or {}).get("stored_text"), "baseline_importance": d["baseline"]["importance"],
                     "staged_importance": d["staged"]["importance"], "identity_context_in_staged_prompt": ctx})
    priors = {a: get_prompt_context(a) for a in sorted({r["agent"] for r in rows})}
    c.close()
    return {"rows": rows, "priors_block_by_agent": priors, "note": "The staged prompt is the upstream prompt plus the priors block, plus the identity context when the agent had traits at that clock. The baseline scores with the upstream prompt alone."}


def divergence() -> Dict[str, Any]:
    from devmem.api import store
    res = {}
    for agent in ("Isabella Rodriguez", "Maria Lopez", "Klaus Mueller"):
        res[agent] = None
    found = {a: None for a in res}
    for lo in range(0, 25920, 1440):
        fl = store.movement_frames("p7_staged", lo, lo + 1439)["frames"]
        fr = store.movement_frames("p7_baseline", lo, lo + 1439)["frames"]
        for a in res:
            if found[a] is None:
                found[a] = first_divergence(fl, fr, a)
        if all(found.values()):
            break
    return {"left": "p7_staged", "right": "p7_baseline", "rule": "the first step at which the action text of the agent (duration annotation removed, part after '@' dropped) differs between the two runs",
            "retrieval_note": "Which memory items were retrieved is not logged.", "agents": found}


INCIDENTS = [
    {"title": "Arena parser crash and fix", "ledger": "H27, H28", "what": "The staged arm stopped at step 20,826: upstream rejected a run-on area reply five times (identical replies at temperature 0) and returned its own fail-safe area \"kitchen\", which does not exist in the cafe sector. The same step crashed twice and ABORT was written. A validator change (upstream touch point 6) was applied to both arms.",
     "numbers": "staged resumed at step 20,790 (20:01 IST Oct 8), baseline restarted at step 19,980 (20:10); the replay of the recorded calls shows 5 area calls parsed differently (2 staged, 3 baseline)", "evidence": "docs/CLAIMS_LEDGER.md H27, H28; docs/phase9_arena_validator_replay.json"},
    {"title": "Upstream fail-safes reached the simulation", "ledger": "H29", "what": "decide_to_talk fell back to upstream's fail-safe \"yes\" in 14 of 14 calls in both arms, so conversation starts were not decided by the model in this setup; schedule revision fell back in 38 to 39 percent of calls in both arms.",
     "numbers": "certain fail-safe calls: baseline 49 of 7,532 upstream function calls (0.65 percent), staged 30 of 6,863 (0.44 percent)", "evidence": "docs/phase9_failsafe_count.json"},
    {"title": "Injected event I6 not perceived (staged)", "ledger": "H24", "what": "I6 was injected on Isabella's tile [78,19] at step 13,140 and was not stored in the staged arm (passed in the baseline). Attention crowding is plausible and unverified.", "numbers": "26 of 27 injected events evaluated; Q_I6 excluded from both arms", "evidence": "devmem/storage/p7_staged/injection_log.jsonl"},
    {"title": "Importance-scoring timeout 15 s to 30 s mid-run", "ledger": "H20 (7f)", "what": "Before the change up to 31 percent (baseline) and 28 percent (staged) of scoring calls had a timeout retry.", "numbers": "changed at sim 10:30 (baseline) and 11:15 (staged) on day 1", "evidence": "docs/CLAIMS_LEDGER.md H20"},
    {"title": "Torn interim checkpoint copies", "ledger": "H23", "what": "Some day-2 copies were taken while upstream was still saving: truncated embedding files and persona files one save old. Repaired copies are used and labelled.", "numbers": "fixed copier in `cc7123d`", "evidence": "docs/phase9_copy_integrity.json"},
    {"title": "App restart and laptop power-off", "ledger": "H19, H22", "what": "Both arms were killed at about 00:10 IST on Oct 8 (cause not established) and by a critical-battery power-off at 14:56:53; the watchdog restarted them from the last autosave. Replayed steps are counted once in unique figures.", "numbers": "restarts at 00:53 and 16:14 IST", "evidence": "docs/CLAIMS_LEDGER.md H19, H22"},
    {"title": "Purpose tags are a keyword heuristic", "ledger": "H25, H26", "what": "The router's purpose tag for upstream calls comes from words in the prompt: the dialogue tag has 73 to 78 percent false matches. Per-call classes are assigned from the prompts instead. Periodic reflection is off in the staged arm; the post-conversation memo calls run in both arms.", "numbers": "unclassified: 0.1 to 0.15 percent of calls", "evidence": "docs/phase9_purpose_tag_audit.json"},
    {"title": "Replay controls: staged condition corrected", "ledger": "H30", "what": "The first replay run used the recorded in-run scores as the staged condition; the registered condition is a fresh replay (staged_replayed). The recorded scores are kept as a sensitivity line.", "numbers": "299 events, 26 injected + 273 natural", "evidence": "docs/CLAIMS_LEDGER.md H30"},
]


def build() -> Dict[str, Any]:
    exp = _read(DOCS / "phase9_results_export_day3.json")
    replay = _read(EVAL / "replay_controls.json")
    inj = injections()
    status = {a: (_read(ST / f"p7_{a}" / "run_status.json") or {}).get("state") for a in ARMS}
    return {"built_at": time.strftime("%Y-%m-%d %H:%M:%S"), "standing_line": STANDING, "d1_wording": D1_WORDING, "export_label": exp["label"], "arm_states": status,
            "scorecard": scorecard(exp, replay), "recall": recall_section(exp),
            "tiles": {a: {"E1_raw": exp["arms"][a]["E1"]["raw_total"], "E1_unique": exp["arms"][a]["E1"]["unique_total"], "E2_mean_tokens_in": exp["arms"][a]["E2_prompt_tokens"]["mean_tokens_in"],
                          "E3_consolidated_fraction": exp["arms"][a]["E3_consolidated_fraction"]["fraction"]} for a in ARMS},
            "calls_by_class": class_calls(), "replay": replay_section(replay), "m2": exp["coherence_M2"], "injections": inj, "nights": nights_section(),
            "baseline_reflections": baseline_reflections(), "scoring_card": scoring_card(inj), "divergence": divergence(), "incidents": INCIDENTS}


def main():
    sys.path.insert(0, str(ROOT))
    d = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(d, indent=1, default=str), encoding="utf-8")
    print("written", OUT, OUT.stat().st_size, "bytes; scorecard rows", len(d["scorecard"]), "recall rows", len(d["recall"]["rows"]), "injections", len(d["injections"]),
          "nights", len(d["nights"].get("nights", [])), "traits", len(d["nights"].get("traits", [])), "divergence", {a: bool(v) for a, v in d["divergence"]["agents"].items()})


if __name__ == "__main__":
    main()
