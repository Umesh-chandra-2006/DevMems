"""
Offline clustering-threshold scan on a saved live run (the calibration dataset). Zero network, zero LLM. Reads the saved
associative memories (nodes.json + embeddings.json) under devmem/storage/calibration/<name>/reverie_storage, and for each
agent clusters (a) the entries the sweep would consider (event/chat nodes, poignancy >= floor, no 'idle') and (b) ALL
nodes with embeddings, with single and average linkage at thresholds 0.70 to 0.90. Does NOT choose or freeze a threshold.

  python devmem/memory/p5_calibration_scan.py <calibration_dir_name> [<more names>]
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from devmem.memory.consolidation import cluster_by_similarity, load_config

THRESHOLDS = [round(0.70 + 0.02 * i, 2) for i in range(11)]
OUT = ROOT / "docs" / "phase5_step3_artifacts"


def load_agent(am_dir):
    nodes = json.load(open(am_dir / "nodes.json", encoding="utf-8"))
    emb = json.load(open(am_dir / "embeddings.json", encoding="utf-8"))
    rows = []
    for nid, n in nodes.items():
        v = emb.get(n["embedding_key"])
        rows.append({"node_id": nid, "type": n["type"], "text": n["description"], "poignancy": n["poignancy"],
                     "created": n["created"], "vec": v})
    return rows


def histogram(clusters):
    h = {}
    for c in clusters:
        h[len(c)] = h.get(len(c), 0) + 1
    return {str(k): v for k, v in sorted(h.items())}


def scan(rows):
    out = {"n": len(rows), "dims": sorted({len(r["vec"]) for r in rows}) if rows else [], "settings": {}}
    if len(rows) < 2 or len(out["dims"]) != 1:
        return out
    vecs = [r["vec"] for r in rows]
    m = np.array(vecs, dtype=float)
    m = m / np.linalg.norm(m, axis=1, keepdims=True)
    sim = (m @ m.T)[np.triu_indices(len(rows), 1)]
    out["pairwise_cosine"] = {"min": round(float(sim.min()), 4), "median": round(float(np.median(sim)), 4),
                              "p90": round(float(np.percentile(sim, 90)), 4), "max": round(float(sim.max()), 4)}
    for linkage in ("single", "average"):
        for th in THRESHOLDS:
            cl = cluster_by_similarity(vecs, th, linkage)
            multi = [c for c in cl if len(c) >= 3]
            out["settings"][f"{linkage}@{th}"] = {
                "histogram": histogram(cl), "clusters_ge_3": len(multi),
                "largest": max(len(c) for c in cl), "entries_in_clusters_ge_3": sum(len(c) for c in multi)}
    return out


def main(names):
    cfg = load_config()
    result = {"label": "offline scan of a saved live run; no threshold chosen or frozen", "floor": cfg["importance_floor"],
              "datasets": {}}
    for name in names:
        base = ROOT / "devmem" / "storage" / "calibration" / name / "reverie_storage" / "personas"
        ds = {}
        for agent_dir in sorted(base.iterdir()):
            rows = load_agent(agent_dir / "bootstrap_memory" / "associative_memory")
            kinds = {}
            for r in rows:
                kinds[r["type"]] = kinds.get(r["type"], 0) + 1
            eligible = [r for r in rows if r["type"] in ("event", "chat") and r["poignancy"] >= cfg["importance_floor"]
                        and "idle" not in r["text"].lower() and r["vec"]]
            allrows = [r for r in rows if r["vec"]]
            ds[agent_dir.name] = {"nodes_by_type": kinds, "poignancy_histogram": {
                str(k): sum(1 for r in rows if r["poignancy"] == k) for k in sorted({r["poignancy"] for r in rows})},
                "eligible_for_sweep": scan(eligible), "all_nodes": scan(allrows),
                "eligible_texts": [r["text"] for r in eligible][:40]}
        result["datasets"][name] = ds
    (OUT / "calibration_scan.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    for name, ds in result["datasets"].items():
        for agent, d in ds.items():
            for key in ("eligible_for_sweep", "all_nodes"):
                s = d[key]
                print(f"\n{name} | {agent} | {key}: n={s['n']} dims={s.get('dims')} cos={s.get('pairwise_cosine')}")
                for k, v in s["settings"].items():
                    print(f"  {k:<14} hist={v['histogram']}  clusters>=3: {v['clusters_ge_3']}  largest {v['largest']}")


if __name__ == "__main__":
    main(sys.argv[1:])
