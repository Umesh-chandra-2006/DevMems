"""Task B (offline, cached vectors only; zero network/LLM): single vs average linkage on the scripted day, with the same
filters as the sweep (importance >= 3, no 'idle'). Writes docs/phase5_step2_artifacts/linkage_comparison.json."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from devmem.embeddings.vector_store import EmbeddingStore
from devmem.memory.consolidation import cluster_by_similarity

def refuse(*a, **k): raise RuntimeError("network call attempted")
day = json.loads((ROOT / "devmem/memory/fixtures/scripted_day_isabella.json").read_text(encoding="utf-8"))
store = EmbeddingStore(post=refuse)
vecs = store.embed_texts([e["text"] for e in day["events"]])
idx = [i for i, e in enumerate(day["events"]) if e["importance"] >= 3 and "idle" not in e["text"]]
out = {"label": "offline, cached live vectors of scripted events", "network_requests": store.stats["http_requests"],
       "eligible_events": len(idx), "results": {}}
for linkage in ("single", "average"):
    for th in (0.70, 0.72, 0.74, 0.76, 0.78, 0.80, 0.82, 0.83, 0.84):
        cl = cluster_by_similarity([vecs[i] for i in idx], th, linkage)
        hist = {}
        for c in cl: hist[len(c)] = hist.get(len(c), 0) + 1
        out["results"][f"{linkage}@{th}"] = {
            "histogram": {str(k): v for k, v in sorted(hist.items())},
            "clusters": [[f"{day['events'][idx[j]]['group']}:{idx[j]}" for j in c] for c in cl if len(c) > 1]}
(ROOT / "docs/phase5_step2_artifacts/linkage_comparison.json").write_text(json.dumps(out, indent=1))
for k, v in out["results"].items():
    print(k, v["histogram"], [[x.split(":")[0][:4] + x.split(":")[1] for x in c] for c in v["clusters"]])
print("network requests:", out["network_requests"])
