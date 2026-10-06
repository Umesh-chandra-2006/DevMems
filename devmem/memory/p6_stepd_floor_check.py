"""
Follow-up A2 (offline, zero calls, zero embedding requests): per agent, how many Step D mirror entries pass Stage 3's selection
(importance >= 3, description without "idle"), and what a night sweep would have had to work with: the cluster size histogram of those
entries with the run's own saved embeddings at the production clustering setting (0.78, single linkage, min size 3, at most 6 summaries).
Reads docs/phase6_stepd_artifacts/memory.db (copy of the run mirror) and the saved associative memory in the Step D worktree.
Nothing is summarized or written to a run.
"""
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
SAVED = Path("D:/DevMems_stepd/reverie/environment/frontend_server/storage/p6_step_d_gemini/personas")
OUT = ROOT / "docs" / "phase6_stepd_artifacts" / "stepd_floor_check.json"


def main():
    import yaml
    from devmem.memory.consolidation import cluster_by_similarity
    cfg = yaml.safe_load(open(ROOT / "devmem/config/consolidation.yaml", encoding="utf-8"))
    c = sqlite3.connect(str(ROOT / "docs/phase6_stepd_artifacts/memory.db"))
    rows = c.execute("SELECT agent_id, entry_id, content, importance_score, sim_timestamp FROM episodic_memory").fetchall()
    report = {"label": "offline-captured; zero calls", "floor": cfg["importance_floor"], "min_cluster_size": cfg["min_cluster_size"],
              "cluster_similarity": cfg["cluster_similarity"], "linkage": cfg["linkage"], "agents": {}}
    for agent in sorted({r[0] for r in rows}):
        mine = [r for r in rows if r[0] == agent]
        idle = [r for r in mine if "idle" in r[2].lower()]
        below = [r for r in mine if r not in idle and (r[3] or 0) < cfg["importance_floor"]]
        passing = [r for r in mine if r not in idle and (r[3] or 0) >= cfg["importance_floor"]]
        nodes = json.load(open(SAVED / agent / "bootstrap_memory/associative_memory/nodes.json", encoding="utf-8"))
        emb = json.load(open(SAVED / agent / "bootstrap_memory/associative_memory/embeddings.json", encoding="utf-8"))
        vecs, usable = [], []
        for r in passing:
            n = nodes.get(r[1].split(":", 1)[1])
            v = emb.get(n["embedding_key"]) if n else None
            if v is not None:
                vecs.append(v)
                usable.append(r)
        clusters = cluster_by_similarity(vecs, cfg["cluster_similarity"], cfg["linkage"]) if vecs else []
        hist = Counter(len(g) for g in clusters)
        multi = sorted([g for g in clusters if len(g) >= cfg["min_cluster_size"]], key=lambda g: -len(g))[: cfg["max_summaries_per_night"]]
        report["agents"][agent] = {
            "mirror_rows": len(mine), "idle_rows": len(idle), "non_idle_below_floor": len(below), "passing_floor": len(passing),
            "distinct_texts_all_rows": len({r[2] for r in mine}), "distinct_texts_passing": len({r[2] for r in passing}),
            "passing_text_counts": dict(Counter(r[2] for r in passing).most_common()),
            "importance_of_passing": dict(sorted(Counter(int(r[3]) for r in passing).items())),
            "passing_with_saved_embedding": len(usable), "cluster_size_histogram": {str(k): v for k, v in sorted(hist.items())},
            "clusters_that_would_be_summarized": [{"size": len(g), "entries": [usable[i][2] for i in g][:6]} for g in multi],
            "first_and_last_passing_sim_time": [min((r[4] for r in passing), default=None), max((r[4] for r in passing), default=None)]}
    OUT.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps({a: {k: v for k, v in d.items() if k != "clusters_that_would_be_summarized"} for a, d in report["agents"].items()}, indent=1))
    for a, d in report["agents"].items():
        for g in d["clusters_that_would_be_summarized"]:
            print(a, g["size"], g["entries"][:3])


if __name__ == "__main__":
    main()
