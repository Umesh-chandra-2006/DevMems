"""
D-2 offline reproduction (PM ruling 2026-10-08): for each staged night, re-run the SAME average-linkage clustering (devmem/config/consolidation.yaml: threshold 0.82, min cluster 3,
importance floor 3, idle filter, at most 6 summaries a night, at most 12 sources a summary) on the CACHED real embeddings of the same inputs, and compare with the recorded night
(`consolidation_log.jsonl`: entries considered, cluster size histogram, entries flagged). Inputs of night k = the agent's episodic entries up to the sweep time with importance at or
above the floor, no excluded substring and not flagged by an earlier night (earlier nights are themselves reproduced, so the state is rebuilt, not read from the final flags).
If every night of an agent reproduces EXACTLY, the merge heights (mean pairwise cosine at each merge) are used as the cosines; otherwise the agent is "not reproducible" and the
mismatch is shown. An embedding missing from the cache makes the night not reproducible (it is fetched by `fetch_embeddings.py` in the chain, then this runs again).

D-2 measurement as registered: "the number of Stage 3 entries merged between 0.80 and 0.88": the entries that sit in a final cluster of at least `min_cluster_size` members and took part in
at least one merge whose height lies in [0.80, 0.88]. The variant counting final clusters of 2 or more is reported beside it.
"""
import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent.parent.parent.parent
LOW, HIGH = 0.80, 0.88


def cfg_default() -> Dict[str, Any]:
    return yaml.safe_load((ROOT / "devmem" / "config" / "consolidation.yaml").read_text(encoding="utf-8"))


def average_linkage_with_heights(vectors: Sequence[Sequence[float]], threshold: float) -> Tuple[List[List[int]], List[Dict[str, Any]]]:
    """Same loop and tie-breaking as consolidation.cluster_by_similarity(linkage='average'), recording the height of every merge."""
    n = len(vectors)
    if n == 0:
        return [], []
    m = np.asarray(vectors, dtype=float)
    nr = np.linalg.norm(m, axis=-1, keepdims=True)
    nr[nr == 0] = 1.0
    m = m / nr
    sim = m @ m.T
    clusters = [[i] for i in range(n)]
    merges: List[Dict[str, Any]] = []
    while len(clusters) > 1:
        best, best_pair = None, None
        for x in range(len(clusters)):
            for y in range(x + 1, len(clusters)):
                mean = float(sim[np.ix_(clusters[x], clusters[y])].mean())
                if mean >= threshold and (best is None or mean > best + 1e-12):
                    best, best_pair = mean, (x, y)
        if best_pair is None:
            break
        x, y = best_pair
        merges.append({"height": best, "a": list(clusters[x]), "b": list(clusters[y])})
        clusters[x] = sorted(clusters[x] + clusters[y])
        del clusters[y]
    return sorted(clusters, key=lambda c: c[0]), merges


def d2_count(clusters: List[List[int]], merges: List[Dict[str, Any]], min_size: int) -> int:
    in_range = set()
    for mg in merges:
        if LOW <= mg["height"] <= HIGH:
            in_range |= set(mg["a"]) | set(mg["b"])
    return len({i for c in clusters if len(c) >= min_size for i in c if i in in_range})


def candidate_rows(conn: sqlite3.Connection, agent: str, sweep_time: str, cfg: Dict[str, Any], flagged: set) -> List[sqlite3.Row]:
    rows = conn.execute("SELECT entry_id, content, sim_timestamp, importance_score FROM episodic_memory WHERE agent_id = ? AND sim_timestamp <= ? AND importance_score >= ? ORDER BY sim_timestamp, entry_id",
                        (agent, sweep_time, cfg["importance_floor"])).fetchall()
    ex = [s.lower() for s in cfg["exclude_description_substrings"]]
    return [r for r in rows if r["entry_id"] not in flagged and not any(s in r["content"].lower() for s in ex)]


def persona_vec_fn(personas_dir: Path, tries: int = 6) -> Callable[[str, str, str], Optional[Sequence[float]]]:
    """The vectors the sweep itself used: node embedding_key from nodes.json, vector from embeddings.json of the agent's saved associative memory (read only; a file caught
    mid-save is re-read). The live folder holds a superset of every earlier save and vectors never change, so the latest files serve any earlier night."""
    import time
    cache: Dict[str, Any] = {}

    def load(agent: str):
        if agent in cache:
            return cache[agent]
        b = Path(personas_dir) / agent / "bootstrap_memory" / "associative_memory"
        for k in range(tries):
            try:
                nodes = json.loads((b / "nodes.json").read_text(encoding="utf-8"))
                emb = json.loads((b / "embeddings.json").read_text(encoding="utf-8"))
                cache[agent] = (nodes, emb)
                return cache[agent]
            except (ValueError, OSError):
                time.sleep(2)
        cache[agent] = ({}, {})
        return cache[agent]

    def fn(agent: str, entry_id: str, content: str):
        nodes, emb = load(agent)
        nd = nodes.get(entry_id.split(":", 1)[1])
        return emb.get(nd["embedding_key"]) if nd else None
    return fn


def reproduce(memory_db: Path, log_rows: List[Dict[str, Any]], vec_fn: Callable[[str, str, str], Optional[Sequence[float]]], cfg: Dict[str, Any] = None) -> Dict[str, Any]:
    cfg = cfg or cfg_default()
    conn = sqlite3.connect(f"file:{Path(memory_db).as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    out: Dict[str, Any] = {"agents": {}, "missing_texts": []}
    agents = sorted({r["agent"] for r in log_rows})
    for agent in agents:
        flagged: set = set()
        nights = sorted((r for r in log_rows if r["agent"] == agent and r.get("status") == "done"), key=lambda r: r["night"])
        res: List[Dict[str, Any]] = []
        ok_all = True
        for rec in nights:
            rows = candidate_rows(conn, agent, rec["sim_time"], cfg, flagged)
            vecs, usable, missing = [], [], []
            for r in rows:
                v = vec_fn(agent, r["entry_id"], r["content"])
                if v is None:
                    missing.append(r["content"])
                else:
                    vecs.append(v)
                    usable.append(r)
            item: Dict[str, Any] = {"night": rec["night"], "sim_time": rec["sim_time"], "recorded_entries_considered": rec["entries_considered"], "recorded_histogram": rec["cluster_size_histogram"],
                                    "recorded_entries_flagged": rec["entries_flagged"], "reconstructed_entries": len(rows), "embeddings_missing": len(missing)}
            if rec["entries_considered"] == 0 and not rows:
                item.update({"reproduced": True, "note": "no entries"})
                res.append(item)
                continue
            if missing:
                out["missing_texts"] += missing
                item.update({"reproduced": False, "reason": f"{len(missing)} embeddings missing from the cache"})
                res.append(item)
                ok_all = False
                break
            clusters, merges = average_linkage_with_heights(vecs, cfg["cluster_similarity"])
            hist: Dict[str, int] = {}
            for c in clusters:
                hist[str(len(c))] = hist.get(str(len(c)), 0) + 1
            hist = {k: hist[k] for k in sorted(hist, key=int)}
            multi = [c for c in clusters if len(c) >= cfg["min_cluster_size"]]
            multi.sort(key=lambda c: (-len(c), -sum(usable[i]["importance_score"] or 0 for i in c), c[0]))
            multi = multi[: cfg["max_summaries_per_night"]]
            fl = set()
            for c in multi:
                members = sorted(c, key=lambda i: (-(usable[i]["importance_score"] or 0), usable[i]["sim_timestamp"]))
                fl |= {usable[i]["entry_id"] for i in sorted(members[: cfg["max_entries_per_prompt"]])}
            same = (len(usable) == rec["entries_considered"] and hist == rec["cluster_size_histogram"] and len(fl) == rec["entries_flagged"])
            item.update({"reproduced": same, "reproduced_histogram": hist, "reproduced_entries_flagged": len(fl)})
            if same:
                item["d2_entries_in_range_min_cluster"] = d2_count(clusters, merges, cfg["min_cluster_size"])
                item["d2_entries_in_range_clusters_of_2_or_more"] = d2_count(clusters, merges, 2)
                item["merge_heights_in_range"] = sorted(round(m["height"], 4) for m in merges if LOW <= m["height"] <= HIGH)
                item["merge_height_summary"] = {"merges": len(merges), "min": round(min((m["height"] for m in merges), default=0), 4), "max": round(max((m["height"] for m in merges), default=0), 4)}
            else:
                ok_all = False
                item["reason"] = "recorded night not reproduced (entries considered, cluster histogram or flagged count differ)"
            res.append(item)
            if not same:
                break
            flagged |= fl
        out["agents"][agent] = {"nights": res, "all_nights_reproduced": ok_all and len(res) == len(nights)}
    conn.close()
    out["missing_texts"] = sorted(set(out["missing_texts"]))
    return out


def score(rep: Dict[str, Any]) -> Dict[str, Any]:
    """D-2 verdict. Decidable only if every agent that consolidated reproduces on every night. Right if each such agent has a count above 0 over its nights."""
    per = {}
    for a, v in rep["agents"].items():
        if not v["all_nights_reproduced"]:
            return {"outcome": "undecidable", "reason": f"{a}: the recorded clustering is not reproduced from the cached embeddings (see the night table)", "numbers": {"missing_embeddings": len(rep["missing_texts"])}}
        per[a] = sum(n.get("d2_entries_in_range_min_cluster", 0) for n in v["nights"])
    if not per:
        return {"outcome": "undecidable", "reason": "no staged night in the copy", "numbers": {}}
    ok = all(c > 0 for c in per.values())
    return {"outcome": "right" if ok else "wrong", "reason": "entries in final clusters of at least min_cluster_size that took part in a merge at height 0.80 to 0.88, summed over the nights of the copy", "numbers": per}


def d1_texts(memory_db: Path) -> List[str]:
    """Texts whose embeddings the D-1 provenance diagnostic needs: each Stage 4 trait, its source summaries and source events, and each agent's priors text."""
    from devmem.api import store
    conn = sqlite3.connect(f"file:{Path(memory_db).as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    sem = {r["entry_id"]: r["summary"] for r in conn.execute("SELECT entry_id, summary FROM semantic_memory")}
    t = set()
    for r in conn.execute("SELECT * FROM identity_traits"):
        t.add(r["text"])
        for s in json.loads(r["source_semantic_ids_json"]):
            if sem.get(s):
                t.add(sem[s])
        for e in json.loads(r["source_event_ids_json"]):
            row = conn.execute("SELECT content FROM episodic_memory WHERE entry_id=?", (e,)).fetchone()
            if row:
                t.add(row[0])
    for (a,) in conn.execute("SELECT DISTINCT agent_id FROM identity_traits"):
        t.add(" ".join(p["statement"] for p in store.priors_for(a)))
    conn.close()
    return sorted(x for x in t if x)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--memory-db", required=True)
    ap.add_argument("--log", default=str(ROOT / "devmem" / "storage" / "p7_staged" / "consolidation_log.jsonl"))
    ap.add_argument("--personas-dir", default=str(ROOT / "reverie" / "environment" / "frontend_server" / "storage" / "p7_staged" / "personas"))
    ap.add_argument("--out")
    a = ap.parse_args()
    conn = sqlite3.connect(f"file:{Path(a.memory_db).as_posix()}?mode=ro", uri=True)
    present = {(r[0], r[1]) for r in conn.execute("SELECT agent_id, night FROM consolidation_sweeps WHERE status='done'")}
    conn.close()
    rows = [json.loads(l) for l in Path(a.log).read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = [r for r in rows if (r["agent"], r["night"]) in present]
    rep = reproduce(Path(a.memory_db), rows, persona_vec_fn(Path(a.personas_dir)))
    rep["verdict"] = score(rep)
    if a.out:
        Path(a.out).write_text(json.dumps(rep, indent=1), encoding="utf-8")
    print(json.dumps({"verdict": rep["verdict"], "missing": len(rep["missing_texts"]), "agents": {k: [(n["night"], n.get("reproduced")) for n in v["nights"]] for k, v in rep["agents"].items()}}))


if __name__ == "__main__":
    main()
