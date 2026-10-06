"""
Scripted Stage 3 scenario (label: scripted events, live embeddings, live LLM).

A hand-written day of events for Isabella Rodriguez (fixtures/scripted_day_isabella.json) is placed into a real
upstream Persona/AssociativeMemory with real gemini-embedding-001 vectors and mirrored into a real SQLite
database. The sleep hook then runs the nightly sweep through the real router, pinned to
openai/gpt-oss-20b. The result is checked for: a semantic memory with correct source references, flipped
consolidated flags, a retrievable thought node (real new_retrieve), and an idempotent second sweep.
"""
import datetime
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND = ROOT / "reverie" / "reverie" / "backend_server"
FIXTURE = ROOT / "devmem" / "memory" / "fixtures" / "scripted_day_isabella.json"
PINNED = "openai/gpt-oss-20b"
FOCAL = "Isabella had an argument with a neighbor about the noise"


def _mean_rank(order, ids):
    ranks = [order.index(i) + 1 for i in ids if i in order]
    return round(sum(ranks) / len(ranks), 2) if ranks else None


def run_scripted_sweep(tag: str, threshold: Optional[float] = None, artifacts_dir: Optional[Path] = None) -> Dict[str, Any]:
    for p in (str(BACKEND), str(ROOT)):
        if p not in sys.path:
            sys.path.insert(0, p)
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    prev_mode = os.environ.get("DEVMEM_EMBEDDING_MODE")
    os.environ["DEVMEM_EMBEDDING_MODE"] = "live"
    os.environ["DEVMEM_PINNED_MODEL"] = PINNED
    import utils
    utils.MEMORY_MODE = "staged"
    from persona.persona import Persona
    from persona.cognitive_modules.retrieve import new_retrieve
    from devmem.embeddings.vector_store import EmbeddingStore
    from devmem.memory import consolidation as cons
    from devmem.memory import episodic
    from devmem.router import key_pool

    day = json.loads(FIXTURE.read_text(encoding="utf-8"))
    agent = day["agent"]
    sim_dir = ROOT / "devmem" / "storage" / f"p5_scripted_sweep_{tag}"
    shutil.rmtree(sim_dir, ignore_errors=True)
    db = cons.init_consolidation_db(sim_dir / "memory.db")
    persona_dir = ROOT / "reverie/environment/frontend_server/storage/base_the_ville_isabella_maria_klaus/personas" / agent
    persona = Persona(agent, str(persona_dir))
    assert len(persona.a_mem.id_to_node) == 0, "staged persona must start with an empty memory"

    store = EmbeddingStore(stats_path=sim_dir / "embedding_stats.json")
    vecs = store.embed_texts([e["text"] for e in day["events"]], batch=True)
    date = datetime.date(2023, 2, 13)
    node_of = {}
    for ev, vec in zip(day["events"], vecs):
        hh, mm = map(int, ev["t"].split(":"))
        when = datetime.datetime.combine(date, datetime.time(hh, mm))
        node = persona.a_mem.add_event(when, None, agent, "is", ev["text"], ev["text"], {ev["text"].split()[0].lower()},
                                       ev["importance"], (ev["text"], vec), None)
        episodic.log_episodic_node(agent, node, sim_time=when, importance_score=ev["importance"], db_path=db)
        node_of[ev["text"]] = f"{agent}:{node.node_id}"

    cfg = cons.load_config()
    if threshold is not None:
        cfg["cluster_similarity"] = threshold
    sweep_time = datetime.datetime.combine(date, datetime.time(22, 0))
    persona.scratch.curr_time = sweep_time
    persona.scratch.act_description = "sleeping"
    ledger_before = key_pool.get_db_connection()
    n_before = ledger_before.execute("SELECT COUNT(*) FROM llm_call_log").fetchone()[0]
    ledger_before.close()

    out: Dict[str, Any] = {"label": "scripted events, live embeddings, live LLM (pinned %s)" % PINNED, "tag": tag,
                           "threshold": cfg["cluster_similarity"], "events": len(day["events"])}
    first = cons.maybe_sweep_on_sleep(persona, db_path=db, config=cfg, pinned_model=PINNED)       # the sleep hook
    again_hook = cons.maybe_sweep_on_sleep(persona, db_path=db, config=cfg, pinned_model=PINNED)  # same night
    again_direct = cons.run_nightly_sweep(persona, sweep_time, db_path=db, config=cfg, pinned_model=PINNED)
    out["first_sweep"] = first
    out["second_sweep_via_hook"] = again_hook
    out["second_sweep_direct"] = again_direct

    import sqlite3
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    out["semantic_rows"] = [dict(r) for r in conn.execute("SELECT * FROM semantic_memory")]
    out["episodic_rows"] = [dict(r) for r in conn.execute(
        "SELECT entry_id, content, importance_score, consolidated FROM episodic_memory ORDER BY entry_id")]
    out["markers"] = [dict(r) for r in conn.execute("SELECT * FROM consolidation_sweeps")]
    conn.close()
    out["event_groups"] = {node_of[e["text"]]: e["group"] for e in day["events"]}
    out["live_consolidated_node_ids"] = sorted(cons.consolidated_node_ids(persona.a_mem))
    out["summary_nodes"] = [{"node_id": n.node_id, "description": n.description, "poignancy": n.poignancy,
                             "filling": n.filling, "depth": n.depth}
                            for n in persona.a_mem.id_to_node.values() if cons._is_summary_node(n)]

    # Real new_retrieve over the whole memory for three focal points, with the D2 weight at its configured
    # value and at 1.0 (no down-weighting). last_accessed is restored between runs so recency is comparable.
    focals = {"neighbor_argument": FOCAL,
              "conflict_handling": "How does Isabella handle conflict with other people?",
              "baking": "What has Isabella been baking at the cafe today?"}
    n_all = len(persona.a_mem.id_to_node)
    summary_ids = [n["node_id"] for n in out["summary_nodes"]]
    consolidated = {nid for nid in cons.consolidated_node_ids(persona.a_mem)}
    saved_access = {k: n.last_accessed for k, n in persona.a_mem.id_to_node.items()}
    configured_weight = cons._CONFIG_CACHE.get("consolidated_weight", cons.load_config()["consolidated_weight"])
    out["retrieval"] = {"consolidated_weight_configured": configured_weight, "focal_points": focals, "runs": {}}
    for label, weight in (("weight_configured", configured_weight), ("weight_1.0", 1.0)):
        cons._CONFIG_CACHE["consolidated_weight"] = weight
        for k, n in persona.a_mem.id_to_node.items():
            n.last_accessed = saved_access[k]
        res = new_retrieve(persona, list(focals.values()), n_count=n_all)
        run = {}
        for fname, ftext in focals.items():
            order = [n.node_id for n in res[ftext]]
            run[fname] = {
                "order": [{"node_id": n.node_id, "type": n.type, "description": n.description} for n in res[ftext]],
                "top5": [{"node_id": n.node_id, "type": n.type, "description": n.description} for n in res[ftext][:5]],
                "summary_ranks": {sid: order.index(sid) + 1 for sid in summary_ids},
                "mean_rank_of_consolidated_sources": _mean_rank(order, consolidated),
                "mean_rank_of_unconsolidated_events": _mean_rank(
                    order, {k for k, n in persona.a_mem.id_to_node.items() if n.type == "event" and k not in consolidated}),
                "not_ranked_idle_nodes_excluded_by_upstream": n_all - len(order)}
        out["retrieval"]["runs"][label] = run
    cons._CONFIG_CACHE["consolidated_weight"] = configured_weight
    out["retrieval"]["nodes_total"] = n_all
    out["embedding_stats"] = store.stats
    ledger = key_pool.get_db_connection()
    out["llm_calls_made"] = ledger.execute("SELECT COUNT(*) FROM llm_call_log").fetchone()[0] - n_before
    out["llm_ledger_rows"] = [dict(r) for r in ledger.execute(
        "SELECT purpose, model, tokens_in, tokens_out, agent_id FROM llm_call_log ORDER BY created_at DESC LIMIT ?",
        (out["llm_calls_made"],))]
    ledger.close()
    out["persona"] = persona
    out["db"] = db
    if prev_mode is None:
        os.environ.pop("DEVMEM_EMBEDDING_MODE", None)
    else:
        os.environ["DEVMEM_EMBEDDING_MODE"] = prev_mode
    if artifacts_dir:
        Path(artifacts_dir).mkdir(parents=True, exist_ok=True)
        slim = {k: v for k, v in out.items() if k not in ("persona", "db")}
        (Path(artifacts_dir) / f"scripted_sweep_{tag}.json").write_text(json.dumps(slim, indent=1, default=str))
    return out


if __name__ == "__main__":
    # Usage: scripted_sweep.py <artifact_subdir> <tag_suffix>   (default: Step 2 third-person re-run; cap 20 LLM calls)
    sub = sys.argv[1] if len(sys.argv) > 1 else "phase5_step2_artifacts"
    suffix = sys.argv[2] if len(sys.argv) > 2 else "third_person"
    art = ROOT / "docs" / sub
    for tag, th in ((f"threshold_0_78_default_{suffix}", None), (f"threshold_0_82_calibrated_{suffix}", 0.82)):
        r = run_scripted_sweep(tag, th, art)
        print(tag, "llm_calls", r["llm_calls_made"], "summaries", [s["description"] for s in r["summary_nodes"]])
