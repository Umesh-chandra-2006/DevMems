"""
PHASE 6 STOP 3 (live confirmation, one persona). Label: live LLM (pinned gemini-3.1-flash-lite, normalizer on), live embeddings
(gemini-embedding-001, cache first, fail loud), scripted events and scripted importance for the fixture events.

Isabella Rodriguez, the scripted four-night fixture (devmem/memory/fixtures/scripted_four_nights_isabella.json), then five new events
scored by the real Stage 2 scorer with the Stage 4 identity_context filled. Real Stage 3 summaries and real Stage 4 trait generation
run through the real sleep hook. Production Stage 3 settings (consolidation.yaml) and Stage 4 settings (identity.yaml, frozen).

Caps: HARD 40 router-counted LLM calls (CapReached ends the step), at most 60 real embedding requests (the 61st raises, fail loud).
Chat calls rotate over GEMINI_KEY_4, _5, _6 through temporary provider configs. The raw-reply log keeps every prompt, raw reply and
delivered text. No prompt is tuned: a third-person failure after the corrective retry is reported with its raw reply.
"""
import copy
import datetime
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "reverie" / "reverie" / "backend_server"
for p in (str(BACKEND), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)
FIXTURE = ROOT / "devmem" / "memory" / "fixtures" / "scripted_four_nights_isabella.json"
ART = ROOT / "docs" / "phase6_stop3_artifacts"
SIM = "p6_stop3_isabella"
MODEL = "gemini-3.1-flash-lite"
KEYS = ["GEMINI_KEY_4", "GEMINI_KEY_5", "GEMINI_KEY_6"]
CAP, EMBED_CAP = 40, 60
NEW_EVENTS = [
    "Isabella Rodriguez is greeting regular customers at the cafe counter",
    "Isabella Rodriguez is carefully shaping a new batch of baguettes",
    "A neighbor complained again about the noise from the cafe",
    "Isabella Rodriguez received a notice that the cafe lease ends next month",
    "Isabella Rodriguez is wiping down the tables after closing",
]


def main():
    ART.mkdir(parents=True, exist_ok=True)
    run_dir = ROOT / "devmem" / "storage" / SIM
    shutil.rmtree(run_dir, ignore_errors=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    raw_log = run_dir / "raw_replies.jsonl"
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    for k, v in (("DEVMEM_PINNED_MODEL", MODEL), ("DEVMEM_OUTPUT_NORMALIZER", "on"), ("DEVMEM_EMBEDDING_MODE", "live"),
                 ("DEVMEM_RAW_REPLY_LOG", str(raw_log)), ("SIM_CODE", SIM), ("STAGE4_ENABLED", "on"), ("IDENTITY_FEEDBACK", "true")):
        os.environ[k] = v

    import requests
    import utils
    import yaml
    utils.MEMORY_MODE = "staged"
    import persona.prompt_template.gpt_structure as gs
    from persona.persona import Persona
    from devmem.embeddings.vector_store import EmbeddingStore
    from devmem.memory import consolidation as cons
    from devmem.memory import episodic, identity
    from devmem.router import call_counter, key_pool, llm_router, output_normalizer

    fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
    agent = fx["agent"]
    db = cons.init_consolidation_db(run_dir / "memory.db")
    identity.init_identity_db(db)

    emb = {"requests": 0}

    def counted_post(*a, **k):
        if emb["requests"] >= EMBED_CAP:
            raise RuntimeError(f"embedding request cap {EMBED_CAP} reached")
        emb["requests"] += 1
        return requests.post(*a, **k)
    store = EmbeddingStore(post=counted_post, stats_path=run_dir / "embedding_stats.json")
    gs._EMBEDDING_STORE = store

    base = yaml.safe_load(open(ROOT / "devmem/config/providers.yaml", encoding="utf-8"))
    gem = next(p for p in base["providers"] if p["name"] == "gemini")
    tmp = Path(tempfile.mkdtemp(prefix="p6_stop3_"))
    cfgs = []
    for i in range(len(KEYS)):
        p = copy.deepcopy(gem)
        p["keys"] = [{"env": k} for k in KEYS[i:] + KEYS[:i]]
        f = tmp / f"gemini_rot{i}.yaml"
        f.write_text(yaml.dump({"providers": [p]}), encoding="utf-8")
        cfgs.append(str(f))
    rot = {"i": 0, "first_key": {k: 0 for k in KEYS}}
    real_call = llm_router.call_llm

    def rotating(*a, **k):
        idx = rot["i"] % len(KEYS)
        rot["i"] += 1
        rot["first_key"][KEYS[idx]] += 1
        k.setdefault("config_path", cfgs[idx])
        return real_call(*a, **k)
    for mod in (cons, identity, episodic):
        mod.call_llm = rotating

    conn = key_pool.get_db_connection()
    rid0 = conn.execute("SELECT COALESCE(MAX(rowid),0) FROM llm_call_log").fetchone()[0]
    conn.close()
    call_counter.reset()
    call_counter.set_cap(CAP)

    persona_dir = ROOT / "reverie/environment/frontend_server/storage/base_the_ville_isabella_maria_klaus/personas" / agent
    persona = Persona(agent, str(persona_dir))
    assert len(persona.a_mem.id_to_node) == 0
    t0 = time.time()
    outcome, nights, new_scores = "completed", [], []
    try:
        for night in fx["nights"]:
            n = night["night"]
            day = datetime.datetime.strptime(night["sleep"], "%Y-%m-%d %H:%M:%S").date()
            vecs = store.embed_texts([e["text"] for e in night["events"]], batch=True)
            for ev, vec in zip(night["events"], vecs):
                hh, mm = map(int, ev["t"].split(":"))
                when = datetime.datetime.combine(day, datetime.time(hh, mm))
                node = persona.a_mem.add_event(when, None, agent, "is", ev["text"], ev["text"], {"scripted"}, ev["importance"],
                                               (ev["text"], vec), None)
                # scripted importance: no scoring call, so no traits were in a scoring context (recorded as ok with no traits)
                identity.note_scoring_context(agent, when, ev["text"], [], True)
                episodic.log_episodic_node(agent, node, sim_time=when, importance_score=ev["importance"], db_path=db)
            persona.scratch.curr_time = datetime.datetime.strptime(night["sleep"], "%Y-%m-%d %H:%M:%S")
            persona.scratch.act_description = "sleeping"
            res = cons.maybe_sweep_on_sleep(persona, db_path=db, pinned_model=MODEL)
            nights.append({"night": n, "result": json.loads(json.dumps(res, default=str)),
                           "router_calls_so_far": call_counter.snapshot()["count"], "embedding_requests_so_far": emb["requests"]})
        # five new events on day 5, scored by the real scorer with identity_context filled, then mirrored
        day5 = datetime.date(2023, 2, 17)
        vecs = store.embed_texts(NEW_EVENTS, batch=True)
        for i, (text, vec) in enumerate(zip(NEW_EVENTS, vecs)):
            when = datetime.datetime.combine(day5, datetime.time(9 + i, 0))
            persona.scratch.curr_time = when
            persona.scratch.act_description = "working"
            score = episodic.score_importance_persona_conditioned(agent, text, kind="event", persona=persona, db_path=db)
            node = persona.a_mem.add_event(when, None, agent, "is", text, text, {"new"}, score, (text, vec), None)
            episodic.log_episodic_node(agent, node, sim_time=when, importance_score=score, db_path=db)
            new_scores.append({"text": text, "score": score, "entry_id": f"{agent}:{node.node_id}"})
    except call_counter.CapReached as e:
        outcome = f"HARD CAP: {e}"
    except Exception as e:  # reporter only; nothing is wrapped around the code under test
        import traceback
        outcome = f"exception: {type(e).__name__}: {str(e)[:200]}"
        (ART / "exception_traceback.txt").write_text(traceback.format_exc(), encoding="utf-8")

    import sqlite3
    c = sqlite3.connect(str(db))
    c.row_factory = sqlite3.Row
    tables = {t: [dict(r) for r in c.execute(f"SELECT * FROM {t}")] for t in
              ("semantic_memory", "semantic_reinforcement", "identity_traits", "identity_sweeps", "consolidation_events",
               "event_scoring_context", "consolidation_sweeps")}
    c.close()
    conn = key_pool.get_db_connection()
    rows = conn.execute("SELECT purpose, tokens_in, tokens_out FROM llm_call_log WHERE rowid > ?", (rid0,)).fetchall()
    kusage = [dict(r) for r in conn.execute("SELECT key_id, SUM(requests_used) n FROM key_usage WHERE provider='gemini' GROUP BY key_id")]
    conn.close()
    by_purpose = {}
    for r in rows:
        e = by_purpose.setdefault(r["purpose"], {"calls": 0, "tokens_in": 0, "tokens_out": 0})
        e["calls"] += 1
        e["tokens_in"] += r["tokens_in"] or 0
        e["tokens_out"] += r["tokens_out"] or 0
    band = [e for e in tables["consolidation_events"] if e["action"] == "reinforced" and 0.80 <= (e["match_similarity"] or 0) < 0.88]
    thr = identity.load_config()["reinforce_threshold"]
    log_lines = [json.loads(l) for l in (run_dir / "identity_log.jsonl").read_text(encoding="utf-8").splitlines()] \
        if (run_dir / "identity_log.jsonl").exists() else []
    raw = [json.loads(l) for l in raw_log.read_text(encoding="utf-8").splitlines() if l.strip()] if raw_log.exists() else []
    ctx_header = identity.load_config()["identity_header"]
    new_prompts = []
    for ns in new_scores:
        rec = next((r for r in raw if r.get("purpose") == "importance_scoring" and ns["text"] in r.get("prompt", "")), None)
        traits = [t["text"] for t in tables["identity_traits"] if t["active"]]
        new_prompts.append({"text": ns["text"], "score": ns["score"], "raw_reply": rec["raw"] if rec else None,
                            "prompt_contains_header": bool(rec and ctx_header in rec["prompt"]),
                            "prompt_contains_active_traits": bool(rec) and all(t in rec["prompt"] for t in traits),
                            "prompt": rec["prompt"] if rec else None})
    report = {"label": "live LLM and live embeddings; scripted events and scripted fixture importance", "sim": SIM, "model": MODEL,
              "outcome": outcome, "wall_seconds": round(time.time() - t0, 1), "cap": CAP, "router_counter": call_counter.snapshot(),
              "calls_by_first_key": rot["first_key"], "embedding_requests": emb["requests"], "embedding_cap": EMBED_CAP,
              "embedding_stats": store.stats, "tokens_by_purpose": by_purpose, "reinforce_threshold": thr,
              "merge_band_0_80_to_0_88_count": len(band), "merge_band_rows": band,
              "unknown_scoring_context_rows": sum(1 for e in tables["event_scoring_context"] if e["status"] == "unknown"),
              "scoring_context_status_counts": {s: sum(1 for e in tables["event_scoring_context"] if e["status"] == s)
                                                for s in sorted({e["status"] for e in tables["event_scoring_context"]})},
              "pivotal_lost": sum(l.get("pivotal_lost", 0) for l in log_lines),
              "self_reinforced_pivotal": sum(l.get("self_reinforced_pivotal", 0) for l in log_lines),
              "nights": nights, "new_event_scoring": new_prompts, "normalizer_stats": output_normalizer.STATS,
              "router_failures": gs.ROUTER_FAILURES, "key_usage_ledger_gemini_all_models": kusage, "tables": tables}
    (ART / "stop3_report.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    for name in ("raw_replies.jsonl", "identity_log.jsonl", "reinforcement_decisions.jsonl", "consolidation_log.jsonl",
                 "identity_prompt_renders.jsonl", "memory.db", "embedding_stats.json"):
        if (run_dir / name).exists():
            shutil.copy(run_dir / name, ART / name)
    print(json.dumps({k: report[k] for k in ("outcome", "router_counter", "embedding_requests", "tokens_by_purpose",
                                              "merge_band_0_80_to_0_88_count", "unknown_scoring_context_rows", "pivotal_lost")},
                     indent=1, default=str))


if __name__ == "__main__":
    main()
