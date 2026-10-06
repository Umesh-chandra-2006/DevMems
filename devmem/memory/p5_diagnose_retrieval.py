"""
Task A (zero LLM calls, zero network): diagnose why the scripted sweep's summary nodes ranked where they did.

Rebuilds each saved scripted-sweep run (events and semantic rows from `devmem/storage/p5_scripted_sweep_<tag>/memory.db`,
vectors from the persistent embedding cache; any cache miss raises) inside a real Persona, then calls the REAL
`new_retrieve` for the same three focal points in the same call, capturing recency, importance and relevance
before and after `normalize_dict_floats`. First checks that the rebuilt ranks equal the ranks saved in the
original run's JSON artifact. Writes docs/phase5_step2_artifacts/diag_retrieval_<tag>.json.
"""
import contextlib
import datetime
import io
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND = ROOT / "reverie" / "reverie" / "backend_server"
for p in (str(BACKEND), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)
import os
os.environ["DEVMEM_EMBEDDING_MODE"] = "live"   # cache-only: the post below refuses any network call
import utils
utils.MEMORY_MODE = "staged"
from persona.persona import Persona
from persona.cognitive_modules import retrieve as R
from devmem.embeddings.vector_store import EmbeddingStore
from devmem.memory import consolidation as cons
from devmem.memory.scripted_sweep import FOCAL
import persona.prompt_template.gpt_structure as gs


def _no_network(*a, **k):
    raise RuntimeError("network call attempted during a cache-only diagnosis")


cache_store = EmbeddingStore(post=_no_network, stats_path=ROOT / "devmem/storage/diag_embedding_stats.json")
gs._EMBEDDING_STORE = cache_store        # get_embedding() inside new_retrieve now reads the cache only

FOCALS = {"neighbor_argument": FOCAL,
          "conflict_handling": "How does Isabella handle conflict with other people?",
          "baking": "What has Isabella been baking at the cafe today?"}
ART = ROOT / "docs" / "phase5_step2_artifacts"
ART.mkdir(parents=True, exist_ok=True)


def rebuild(tag):
    db = ROOT / "devmem/storage" / f"p5_scripted_sweep_{tag}" / "memory.db"
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    events = conn.execute("SELECT * FROM episodic_memory ORDER BY CAST(substr(entry_id, instr(entry_id, ':node_')+6) AS INTEGER)").fetchall()
    sems = conn.execute("SELECT * FROM semantic_memory ORDER BY CAST(substr(entry_id, instr(entry_id, ':node_')+6) AS INTEGER)").fetchall()
    sweep = conn.execute("SELECT sweep_time FROM consolidation_sweeps").fetchone()["sweep_time"]
    conn.close()
    agent = "Isabella Rodriguez"
    persona = Persona(agent, str(ROOT / "reverie/environment/frontend_server/storage/base_the_ville_isabella_maria_klaus/personas" / agent))
    from persona.memory_structures.associative_memory import AssociativeMemory
    import tempfile
    d = Path(tempfile.mkdtemp())
    (d / "nodes.json").write_text("{}"); (d / "embeddings.json").write_text("{}")
    (d / "kw_strength.json").write_text(json.dumps({"kw_strength_event": {}, "kw_strength_thought": {}}))
    persona.a_mem = AssociativeMemory(str(d))
    vecs = cache_store.embed_texts([e["content"] for e in events] + [s["summary"] for s in sems], batch=True)
    for e, v in zip(events, vecs):
        when = datetime.datetime.strptime(e["sim_timestamp"], "%Y-%m-%d %H:%M:%S")
        persona.a_mem.add_event(when, None, agent, "is", e["content"], e["content"], {e["content"].split()[0].lower()},
                                int(e["importance_score"]), (e["content"], v), None)
    sw = datetime.datetime.strptime(sweep, "%Y-%m-%d %H:%M:%S")
    for s, v in zip(sems, vecs[len(events):]):
        src = [x.split(":", 1)[1] for x in json.loads(s["source_entry_ids"])]
        persona.a_mem.add_thought(sw, sw + datetime.timedelta(days=30), agent, cons.SUMMARY_PREDICATE, cons.SUMMARY_OBJECT,
                                  s["summary"], {"consolidated memory"}, int(s["importance_score"]), (s["summary"], v), src)
    persona.scratch.curr_time = sw
    return persona, sems


def run(tag):
    saved = json.load(open(ROOT / "docs/phase5_step1_artifacts" / f"scripted_sweep_{tag}.json", encoding="utf-8"))
    persona, sems = rebuild(tag)
    cons._CONFIG_CACHE.clear(); cons._CONFIG_CACHE.update(cons.load_config())
    weight = cons._CONFIG_CACHE["consolidated_weight"]
    n_all = len(persona.a_mem.id_to_node)
    summary_ids = [f"node_{s['entry_id'].split('node_')[1]}" for s in sems]
    out = {"label": "offline reconstruction from saved run DB + cached vectors; real new_retrieve; zero network/LLM",
           "tag": tag, "summary_nodes": {nid: s["summary"] for nid, s in zip(summary_ids, sems)},
           "consolidated_weight": weight, "runs": {}}

    for label, w in (("weight_configured", weight), ("weight_1.0", 1.0)):
        cons._CONFIG_CACHE["consolidated_weight"] = w
        saved_access = {k: n.last_accessed for k, n in persona.a_mem.id_to_node.items()}
        # capture components per focal point
        captured = []
        orig = {"rec": R.extract_recency, "imp": R.extract_importance, "rel": R.extract_relevance,
                "norm": R.normalize_dict_floats}
        calls = {"i": 0, "cur": {}}

        def wrap(name):
            def f(*a, **k):
                r = orig[name](*a, **k)
                calls["cur"][name] = dict(r)
                return r
            return f

        def norm(d, lo, hi):
            before = dict(d)
            after = orig["norm"](d, lo, hi)
            kind = ("rec", "imp", "rel")[calls["i"] % 3]
            calls["cur"][kind + "_norm"] = dict(after)
            calls["cur"][kind + "_raw"] = before
            calls["i"] += 1
            if calls["i"] % 3 == 0:
                captured.append(calls["cur"]); calls["cur"] = {}
            return after
        R.normalize_dict_floats = norm
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                res = R.new_retrieve(persona, list(FOCALS.values()), n_count=n_all)
        finally:
            R.normalize_dict_floats = orig["norm"]
        for k, n in persona.a_mem.id_to_node.items():
            n.last_accessed = saved_access[k]
        gw = [0.5, 3, 2]
        run_out = {}
        for (fname, ftext), comp in zip(FOCALS.items(), captured):
            order = [n.node_id for n in res[ftext]]
            rows = {}
            for nid in order:
                node = persona.a_mem.id_to_node[nid]
                rec_n, imp_n, rel_n = comp["rec_norm"][nid], comp["imp_norm"][nid], comp["rel_norm"][nid]
                rows[nid] = {"rank": order.index(nid) + 1, "type": node.type, "text": node.description[:70],
                             "recency_raw": round(comp["rec_raw"][nid], 5), "recency_norm": round(rec_n, 4),
                             "importance_raw": comp["imp_raw"][nid], "importance_norm": round(imp_n, 4),
                             "relevance_raw_cos": round(comp["rel_raw"][nid], 4), "relevance_norm": round(rel_n, 4),
                             "weighted": {"recency": round(0.5 * rec_n, 4), "relevance": round(3 * rel_n, 4),
                                          "importance": round(2 * imp_n, 4)},
                             "final_score_after_D2": None}
            run_out[fname] = {"order": order, "summary_ranks": {s: order.index(s) + 1 for s in summary_ids},
                              "rows_top3": {nid: rows[nid] for nid in order[:3]},
                              "rows_summaries": {s: rows[s] for s in summary_ids}}
        out["runs"][label] = run_out
    cons._CONFIG_CACHE["consolidated_weight"] = weight
    # reproduction check against the original run's artifact
    ok = {}
    for fname in FOCALS:
        ok[fname] = (out["runs"]["weight_configured"][fname]["summary_ranks"]
                     == saved["retrieval"]["runs"]["weight_configured"][fname]["summary_ranks"]
                     and out["runs"]["weight_1.0"][fname]["summary_ranks"]
                     == saved["retrieval"]["runs"]["weight_1.0"][fname]["summary_ranks"])
    out["reproduces_saved_summary_ranks"] = ok
    out["nodes_total"] = n_all
    (ART / f"diag_retrieval_{tag}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    for tag in ("threshold_0_78_default", "threshold_0_82_calibrated"):
        o = run(tag)
        print(tag, "reproduces saved ranks:", o["reproduces_saved_summary_ranks"], "| network http requests:",
              cache_store.stats["http_requests"], "| cache hits:", cache_store.stats["cache_hits"])
