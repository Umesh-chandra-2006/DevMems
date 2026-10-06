"""
Embeds the scripted day (live, through EmbeddingStore, cached on disk) and writes the pairwise cosine matrix
and the cluster result at several thresholds, so the threshold used in the scripted sweep is chosen from data
(non-evaluation data) and not guessed. Writes docs/phase5_step1_artifacts/scripted_day_cosines.json.
"""
import json, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")
from devmem.embeddings.vector_store import EmbeddingStore
from devmem.memory.consolidation import cluster_by_similarity

day = json.loads((ROOT / "devmem/memory/fixtures/scripted_day_isabella.json").read_text())
texts = [e["text"] for e in day["events"]]
store = EmbeddingStore(stats_path=ROOT / "docs/phase5_step1_artifacts/scripted_day_embedding_stats.json")
vecs = store.embed_texts(texts, batch=True)
m = np.array(vecs); m = m / np.linalg.norm(m, axis=1, keepdims=True)
sim = m @ m.T
out = {"label": "live embeddings (gemini-embedding-001) of scripted events", "dim": len(vecs[0]),
       "http_requests": store.stats["http_requests"], "cache_hits": store.stats["cache_hits"], "thresholds": {}}
idx = [i for i, e in enumerate(day["events"]) if e["importance"] >= 3 and "idle" not in e["text"]]
for th in (0.60, 0.65, 0.68, 0.70, 0.72, 0.75, 0.78, 0.80):
    cl = cluster_by_similarity([vecs[i] for i in idx], th)
    out["thresholds"][str(th)] = [[day["events"][idx[j]]["group"] + ":" + str(idx[j]) for j in c] for c in cl]
groups = {}
for i, e in enumerate(day["events"]):
    groups.setdefault(e["group"], []).append(i)
def stats(pairs):
    a = np.array(pairs); return {"n": len(a), "min": round(float(a.min()), 4), "mean": round(float(a.mean()), 4), "max": round(float(a.max()), 4)}
within = {g: stats([sim[i, j] for a, i in enumerate(ix) for j in ix[a + 1:]]) for g, ix in groups.items() if len(ix) > 1}
cross = stats([sim[i, j] for g1 in ("baking",) for g2 in ("neighbor_conflict", "isolated") for i in groups[g1] for j in groups[g2]]
              + [sim[i, j] for i in groups["neighbor_conflict"] for j in groups["isolated"]])
out["within_group_cosine"] = within
out["cross_group_cosine_baking_conflict_isolated"] = cross
out["idle_vs_idle"] = stats([sim[i, j] for a, i in enumerate(groups["idle"]) for j in groups["idle"][a + 1:]])
(ROOT / "docs/phase5_step1_artifacts/scripted_day_cosines.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
