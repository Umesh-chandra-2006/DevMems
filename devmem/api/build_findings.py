"""
Offline builder of the Findings, Where-it-differs and Edge-cases data (Phase 8 UI addendum, 2026-10-07).

Reads existing artifacts and logs only (pilot ledgers and injection logs, the pilot raw reply logs and movement archives, the Stop 3 and Step D
artifacts, the parser audit, the Phase 4 result files). NO LLM call, NO network, NO generated narrative: every sentence in `why` is a fixed
template filled with logged fields. Writes `devmem/api/web/data/findings.json`; the page only displays it. Standard library only.

    python devmem/api/build_findings.py
"""
import difflib
import json
import re
import sqlite3
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "devmem" / "api" / "web" / "data" / "findings.json"
ART = "docs/phase7_pilot_artifacts/"
START = datetime(2023, 2, 13, 0, 0, 0)
TAIL = re.compile(r"\s*\(duration in minutes:\s*\d+,\s*minutes left:\s*\d+\)")
NOTE = "single run per arm; differences can be model noise; PILOT is not a result"


def jl(path):
    p = ROOT / path
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


def js(path):
    p = ROOT / path
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def clock(step):
    return (START + timedelta(seconds=10 * step)).strftime("%Y-%m-%d %H:%M:%S")


def clean(text):
    return TAIL.sub("", str(text or "")).split("@")[0].strip()


# ------------------------------------------------------------------------------------------------ Findings
def injections():
    rows = {}
    for arm in ("baseline", "staged"):
        for r in jl(f"{ART}{arm}_injection_log.jsonl"):
            rows.setdefault(r["id"], {"id": r["id"], "agent": r["agent"], "type": r["type"], "text": r["stored_text"]})[arm] = {
                "step": r["injected_step"], "clock": r["injected_clock"], "perceived": r["perceived_and_stored"], "importance": r["importance"]}
    out = []
    for k, v in sorted(rows.items()):
        b, s = v.get("baseline"), v.get("staged")
        v["same_authored_step"] = bool(b and s and b["step"] == s["step"])
        v["importance_difference"] = (s["importance"] - b["importance"]) if b and s and b["importance"] is not None and s["importance"] is not None else None
        out.append(v)
    return {"rows": out, "artifact": f"{ART}baseline_injection_log.jsonl, {ART}staged_injection_log.jsonl",
            "rule": "perceived = a memory node with the rendered text exists after the injection (the injector's PASS rule); importance as stored by each arm's own scorer"}


def calls_by_purpose():
    res = {"artifact": f"{ART}baseline_hourly_ledger.jsonl, {ART}staged_hourly_ledger.jsonl", "arms": {}, "windows": {}}
    for arm in ("baseline", "staged"):
        tot, wins = {}, []
        for r in jl(f"{ART}{arm}_hourly_ledger.jsonl"):
            for k, v in r["by_purpose"].items():
                tot[k] = tot.get(k, 0) + v["calls"]
            awake = sum(1 - (f or 0) for f in (r.get("sleeping_step_fraction") or {}).values()) * (r.get("steps_in_window") or 0) / 360.0
            wins.append({"label": r["label"], "sim_clock": r["sim_clock"], "steps": r["steps_in_window"], "calls": r["calls"], "awake_agent_hours": round(awake, 2),
                         "calls_per_awake_agent_hour": round(r["calls"] / awake, 1) if awake >= 0.3 else None})
        res["arms"][arm] = {"by_purpose": tot, "total": sum(tot.values())}
        res["windows"][arm] = wins
    res["note"] = ("Totals are every ledger window of the pilot, including the replayed stretches after the kill and the crash legs, so they are not a clean "
                   "common-window count. D1: periodic reflection (focal-point and insight generation) is ON in baseline and OFF in staged; the post-conversation planning-thought and memo calls in reflect() run in both arms, so the periodic-reflection calls differ by design.")
    return res


BUGS = [
    {"bug": "Fence crash: a valid JSON reply wrapped in a markdown fence made upstream parse fail three times and a caller index None", "caught": "pilot, first conversation of the day, both arms",
     "commit": "5efbe9e", "evidence": "docs/phase7_pilot_report.md section 4; devmem/router/fixtures/fence/captured_fenced_replies.json; claims ledger H9"},
    {"bug": "Injected event subject without a colon was treated as a persona (KeyError 'A janitor' in the reaction check)", "caught": "pilot, staged arm, event K1 at 08:15",
     "commit": "fdcc7b7", "evidence": "docs/CLAIMS_LEDGER.md H14; devmem/eval/test_run_readiness.py TestInjectedSubjectsAreNotPersonas"},
    {"bug": "Resume accounting: the saved call count was written only on the hour and under-counted after a kill (33 recorded, 538 delivered)", "caught": "pilot resume after the Windows Update restart",
     "commit": "d21e0f6", "evidence": "docs/phase7_pilot_report.md section 3"},
    {"bug": "Canary A6 call rate counted only whole hourly windows (printed 58 and 87 instead of about 160)", "caught": "pilot canary", "commit": "025c8f3",
     "evidence": "docs/phase7_pilot_report.md section 6; devmem/eval/canary.py"},
    {"bug": "Operator ABORT raised inside a call was swallowed by upstream's bare except and surfaced as an upstream exception; the supervisor could have resumed over it",
     "caught": "pilot baseline stop at 12:19", "commit": "503dc08", "evidence": "devmem/eval/test_supervisor.py test_abort_file_after_an_exception_exit_is_never_resumed"},
    {"bug": "Outage handling: a connection failure longer than about 40 minutes would have let a fail-safe reach the simulation (provider 503s and timeouts were seen in the pilot logs)",
     "caught": "launch gate review after the pilot", "commit": "503dc08", "evidence": "devmem/eval/test_outage.py; claims ledger H15"},
    {"bug": "Viewer: the memory panel blocked the thoughts for a run without a memory database (baseline arm)", "caught": "viewer check on the pilot recordings", "commit": "4496e46",
     "evidence": "devmem/api/web/town.js"},
]


# ------------------------------------------------------------------------------------------------ Edge cases
def edge_cases():
    audit = js("docs/phase7_parser_echo_audit.json") or {"results": []}
    stepd = next((r for r in audit["results"] if r["artifact"].startswith("step D")), {})
    rd = jl("docs/phase6_stop3_artifacts/reinforcement_decisions.jsonl")
    cos = [(r["night"], r["cosine"]) for r in rd if r.get("kind") == "reinforcement" and r.get("cosine") is not None]
    lk = js("docs/phase6_stop3_artifacts/linkage_check.json") or {"nights": {}}
    n2 = lk["nights"].get("2", {})
    single = n2.get("settings", {}).get("single_0.78 (what Stop 3 used)", {})
    avg = n2.get("settings", {}).get("average_0.82", {})
    return [
        {"title": "Fence crash", "what": "A reply wrapped in a markdown fence ended both pilot arms with TypeError at the first conversation.", "status": "fixed (router fence rule)",
         "numbers": "fenced raw replies in the pilot: 7 of 991 (baseline), 7 of 992 (staged)", "evidence": "docs/phase7_pilot_artifacts/raw_reply_summary.json; docs/phase7_pilot_report.md"},
        {"title": "Injector subject", "what": "Injected events with a subject lacking ':' were treated as persona events and raised KeyError.", "status": "fixed (subject prefix)",
         "numbers": "1 event (K1) crashed the staged pilot arm; 27 authored events share the shape", "evidence": "docs/CLAIMS_LEDGER.md H14"},
        {"title": "Importance parser misread", "what": "The staged scorer read the echoed 'Rate (return a number between 1 to 10): N' as 1.", "status": "fixed (commit f25a10b); past artifacts not rewritten",
         "numbers": f"Step D: {stepd.get('old_vs_corrected_differ')} of {stepd.get('importance_replies')} importance replies scored differently; {stepd.get('echo_format_replies')} used the echo format",
         "evidence": "docs/phase7_parser_echo_audit.json; docs/CLAIMS_LEDGER.md H10"},
        {"title": "Reinforcement threshold 0.88", "what": "Summaries of different scripted themes reinforced one entry above the frozen 0.88 (the cake summary at 0.9134 reinforced the baking entry).",
         "status": "open weakness (threshold frozen, tuned on a hand-written fixture)", "numbers": "Stop 3 reinforcement cosines: " + ", ".join(f"night {n}: {c}" for n, c in cos),
         "evidence": "docs/phase6_stop3_artifacts/reinforcement_decisions.jsonl; docs/CLAIMS_LEDGER.md D9, H5"},
        {"title": "Single linkage merged different themes (Stop 3 night 2)", "what": "With the setting Stop 3 used (single linkage 0.78) seven entries of three themes formed one cluster.",
         "status": "frozen setting changed to average 0.82 before the full runs", "numbers": f"single 0.78: {single.get('cross_theme_pairs_merged')} cross-theme pairs merged; average 0.82: {avg.get('cross_theme_pairs_merged')} (same-theme pairs together {avg.get('same_theme_pairs_together')})",
         "evidence": "docs/phase6_stop3_artifacts/linkage_check.json; docs/prelaunch_p1_p3_report.md"},
        {"title": "Trait with content absent from its source", "what": "Stop 3 trait_2 (pivotal path) states a tendency not present in the one event it was built from.",
         "status": "open weakness (no grounding check)", "numbers": "1 of 3 Stop 3 traits flagged; n is tiny", "evidence": "docs/phase6_stop3_report.md (open question 2); docs/phase6_stop3_artifacts/identity_log.jsonl"},
    ]


# ------------------------------------------------------------------------------------------------ Where it differs
def card_scoring():
    inj = {r["id"]: r for r in injections()["rows"]}
    ex = []
    for eid in ("K1", "I1", "M1"):
        r = inj.get(eid)
        if not r or "baseline" not in r or "staged" not in r:
            ex.append({"id": eid, "available": False})
            continue
        prompts = {}
        for arm in ("baseline", "staged"):
            for rec in jl(f"devmem/storage/p7pilot_{arm}/raw_replies.jsonl"):
                if rec["purpose"] == "importance_scoring" and rec.get("agent_id") == r["agent"] and r["text"].split(" is ", 1)[-1][:40] in rec.get("prompt", ""):
                    prompts[arm] = {"prompt": rec["prompt"], "reply": rec["delivered"][:120]}
                    break
        if len(prompts) < 2:
            ex.append({"id": eid, "available": False, "reason": "a scoring prompt for this event was not found in both raw logs"})
            continue
        b, s = prompts["baseline"]["prompt"].splitlines(), prompts["staged"]["prompt"].splitlines()
        only_b = [l for l in b if l not in s and l.strip()]
        only_s = [l for l in s if l not in b and l.strip()]
        ex.append({"id": eid, "available": True, "agent": r["agent"], "event": r["text"], "baseline": r["baseline"], "staged": r["staged"], "run": "p7pilot_baseline and p7pilot_staged (PILOT, live)",
                   "baseline_reply": prompts["baseline"]["reply"], "staged_reply": prompts["staged"]["reply"],
                   "lines_only_in_staged_prompt": only_s[:40], "lines_only_in_baseline_prompt": only_b[:12], "n_only_staged": len(only_s), "n_only_baseline": len(only_b),
                   "why": f"Rule: staged prompt = upstream scoring prompt plus the Stage 1 priors block. Logged: {len(only_s)} lines occur only in the staged prompt and {len(only_b)} only in the baseline prompt; "
                          f"scores {r['baseline']['importance']} (baseline) and {r['staged']['importance']} (staged). The spread of repeated scores for the same prompt is not measured on the Phase 7 model; the Phase 4 means below are from another model."})
    t7, t4 = js("devmem/memory/task7b_differential_results.json"), js("devmem/memory/task4_1_control_results.json")
    table = []
    mean = lambda lst: round(sum(x["score"] for x in lst) / len(lst), 2) if lst else None
    if t7 and t4:
        for eid, v in t7["event_results"].items():
            c = t4["event_results"].get(eid, {})
            table.append({"id": eid, "baseline": mean(v.get("baseline", [])), "staged": mean(v.get("staged", [])), "mismatch": mean(c.get("control_mismatch", [])), "filler": mean(c.get("control_filler", []))})
    return {"examples": ex, "phase4": {"rows": table, "run": "Phase 4 replay controls, model openai/gpt-oss-20b on Groq (recorded, not the Phase 7 model); mean of 3 repeats per event",
            "artifact": "devmem/memory/task7b_differential_results.json, devmem/memory/task4_1_control_results.json"}}


def card_consolidation():
    rows = [r for r in jl("docs/phase6_stop3_artifacts/consolidation_log.jsonl") if r["night"] == 2]
    lk = (js("docs/phase6_stop3_artifacts/linkage_check.json") or {"nights": {}})["nights"].get("2")
    if not rows or not lk:
        return {"available": False}
    r = rows[0]
    db = ROOT / "docs/phase6_stop3_artifacts/memory.db"
    sem = []
    if db.exists():
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            cols = [x[1] for x in c.execute("PRAGMA table_info(semantic_memory)")]
            sem = [dict(zip(cols, row)) for row in c.execute("SELECT * FROM semantic_memory LIMIT 3")]
        except Exception:
            sem = []
        c.close()
    keep = ("semantic_id", "summary", "agent_id", "created_at", "source_entry_ids", "importance")
    sem = [{k: (str(v)[:300] if v is not None else None) for k, v in s.items() if k in keep or k.startswith("sum") or k.startswith("source")} for s in sem]
    st = lk["settings"]
    return {"available": True, "run": "p6_stop3_isabella (recorded, live, one persona, scripted fixture)", "night": 2, "entries_considered": r["entries_considered"],
            "log": {k: r[k] for k in ("sim_time", "threshold", "linkage", "min_cluster_size", "cluster_size_histogram", "summaries_written", "summaries_reinforced", "entries_flagged")},
            "offline_relabel": {"min_same_theme_cosine": lk["min_same_theme_cosine"], "max_cross_theme_cosine": lk["max_cross_theme_cosine"], "themes": lk["themes"], "settings": st},
            "semantic_rows": sem,
            "why": (f"Rule: cluster entries by cosine; Stage 3 used {r['linkage']} linkage at {r['threshold']} on night {r['night']}, "
                    f"giving {r['cluster_size_histogram']} and {r['summaries_written']} summary written, {r['entries_flagged']} sources flagged consolidated (retrieval weight 0.5 on the sources). "
                    f"Offline relabel with the frozen setting (average linkage 0.82): {st.get('average_0.82', {}).get('cross_theme_pairs_merged')} cross-theme pairs merged against "
                    f"{st.get('single_0.78 (what Stop 3 used)', {}).get('cross_theme_pairs_merged')} under the setting Stop 3 used. Lowest same-theme cosine {lk['min_same_theme_cosine']}, highest cross-theme cosine {lk['max_cross_theme_cosine']}. "
                    "Pairwise cosines per entry are not stored in the artifacts; only these bounds are."),
            "evidence": "docs/phase6_stop3_artifacts/consolidation_log.jsonl; docs/phase6_stop3_artifacts/linkage_check.json; docs/phase6_stop3_artifacts/memory.db"}


def card_identity():
    ilog = jl("docs/phase6_stop3_artifacts/identity_log.jsonl")
    dec = jl("docs/phase6_stop3_artifacts/reinforcement_decisions.jsonl")
    traits = [(r["night"], t) for r in ilog for t in r.get("traits_created", [])]
    if not traits:
        return {"available": False}
    out = []
    renders = jl("docs/phase6_stop3_artifacts/identity_prompt_renders.jsonl")
    db = ROOT / "docs/phase6_stop3_artifacts/memory.db"
    for night, t in traits[:3]:
        tid = t["trait_id"]
        path = t["path"]
        line = None
        for r in renders:
            if tid in r["trait_ids"]:
                p = r["prompt"]
                i = p.find(t["text"][:60])
                line = {"night": r["night"], "sim_time": r["sim_time"], "line": ("- " + p[i:i + len(t["text"])]) if i >= 0 else None}
                break
        src_text = None
        if path == "pivotal" and db.exists():
            ev = (t.get("source_event_ids") or [None])[0]
            c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            try:
                row = c.execute("SELECT content FROM episodic_memory WHERE entry_id=?", (ev,)).fetchone()
                src_text = row[0] if row else None
            except Exception:
                src_text = None
            c.close()
        rel = [d for d in dec if d.get("kind") == "reinforcement" and d["night"] <= night]
        piv = [d for d in dec if d.get("kind") == "pivotal" and d["night"] == night]
        why = (f"Rule: path {path}. " + (
            "Path A same_day: 4 or more new source events attached to one entry in one night; reinforcement rows up to this night: "
            + "; ".join(f"night {d['night']} {d['decision']} cosine {d['cosine']} (threshold {d['threshold']}), new sources {d['new_sources']}" for d in rel) + "." if path == "same_day" else
            "Path B pivotal: importance at or above T=9 graduates one event; logged: " + "; ".join(f"{d['event_id']} importance {d['importance']} threshold {d['threshold']} {d['decision']}" for d in piv) + "."))
        out.append({"trait_id": tid, "night": night, "path": path, "text": t["text"], "source_event_text": src_text, "later_prompt_line": line, "why": why,
                    "flag": ("EDGE CASE: this trait states content that its one source event does not contain (Stop 3 open question 2); the source event text is shown above." if path == "pivotal" else None)})
    return {"available": True, "run": "p6_stop3_isabella (recorded, live, one persona, scripted fixture; T=9 was provisional then)", "traits": out,
            "evidence": "docs/phase6_stop3_artifacts/identity_log.jsonl; reinforcement_decisions.jsonl; identity_prompt_renders.jsonl; memory.db"}


def load_zip_frames(arm):
    z = ROOT / "devmem" / "storage" / f"p7pilot_{arm}" / "movement.zip"
    if not z.exists():
        return {}
    with zipfile.ZipFile(z) as zf:
        return {json.loads(l)["s"]: json.loads(l)["p"] for l in zf.read("frames.jsonl").decode("utf-8").splitlines() if l.strip()}


def nodes_before(arm, agent, clk, n=3):
    f = ROOT / "reverie" / "environment" / "frontend_server" / "storage" / f"p7pilot_{arm}" / "personas" / agent / "bootstrap_memory" / "associative_memory" / "nodes.json"
    if not f.exists():
        return []
    nodes = json.loads(f.read_text(encoding="utf-8")).values()
    cand = [x for x in nodes if x["created"] <= clk and x.get("type") in ("event", "thought")]
    cand.sort(key=lambda x: x["created"])
    return [{"created": x["created"], "type": x["type"], "text": clean(x["description"])[:200]} for x in cand[-n:]]


def card_divergence():
    fb, fs = load_zip_frames("baseline"), load_zip_frames("staged")
    if not fb or not fs:
        return {"available": False}
    agents = sorted({a for p in fb.values() for a in p})
    out = []
    for a in agents:
        first = None
        for s in sorted(set(fb) & set(fs)):
            tb, ts = clean((fb[s].get(a) or [None] * 4)[3]), clean((fs[s].get(a) or [None] * 4)[3])
            if tb != ts:
                first = (s, tb, ts)
                break
        if first is None:
            out.append({"agent": a, "differs": False})
            continue
        s, tb, ts = first
        out.append({"agent": a, "differs": True, "step": s, "clock": clock(s), "baseline_action": tb, "staged_action": ts,
                    "stored_before_baseline": nodes_before("baseline", a, clock(s)), "stored_before_staged": nodes_before("staged", a, clock(s))})
    refl = {arm: sum(1 for r in jl(f"devmem/storage/p7pilot_{arm}/raw_replies.jsonl") if r["purpose"] == "reflection") for arm in ("baseline", "staged")}
    return {"available": True, "run": "p7pilot_baseline vs p7pilot_staged (PILOT, live)", "rule": "first step (common to both recordings) at which the agent's recorded action text, with the duration annotation removed and the address part after '@' dropped, is not identical",
            "agents": out, "retrieval_note": "Which memory items were retrieved is not logged in these runs. The lists show the last three event or thought nodes each arm had STORED before that clock (read from each arm's node file); stored is not retrieved.",
            "candidate_causes_mechanically_present": [
                f"Stage 1 priors block in the staged scoring prompt (see card 1); it changes importance scores, not the action text directly",
                f"periodic reflection (focal-point and insight generation) is on in baseline and off in staged; the post-conversation planning-thought and memo calls in reflect() run in both arms (reflection-tagged replies in the raw logs, keyword tag: baseline {refl['baseline']}, staged {refl['staged']})",
                "sampling variation of the model on identical prompts (a single run per arm)"],
            "notice": "single run per arm; this difference may be model noise; the candidate causes are not tested",
            "evidence": "devmem/storage/p7pilot_baseline/movement.zip, devmem/storage/p7pilot_staged/movement.zip, the personas node files, raw_replies.jsonl"}


def main():
    data = {"note": NOTE, "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "findings": {"injections": injections(), "calls": calls_by_purpose(), "bugs": BUGS},
            "edge_cases": edge_cases(),
            "differs": {"scoring": card_scoring(), "consolidation": card_consolidation(), "identity": card_identity(), "divergence": card_divergence()}}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=1), encoding="utf-8")
    d = data["differs"]
    print("written", OUT, OUT.stat().st_size, "bytes; scoring examples available:", [e.get("available") for e in d["scoring"]["examples"]],
          "consolidation", d["consolidation"].get("available"), "identity", d["identity"].get("available"), "divergence", d["divergence"].get("available"))


if __name__ == "__main__":
    main()
