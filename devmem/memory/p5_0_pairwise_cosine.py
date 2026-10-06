"""
P5.0 / D4 evidence (offline, captured data): pairwise cosine among the real (3072-dim, gemini-embedding-001)
vectors stored in the saved Phase 2 baseline run, per agent. Writes
docs/phase5_step0_artifacts/p5_0_pairwise_cosine.json.
"""
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
SIM = ROOT / "reverie/environment/frontend_server/storage/baseline_validation_run/personas"
OUT = ROOT / "docs/phase5_step0_artifacts/p5_0_pairwise_cosine.json"

result = {"label": "captured (saved memory of baseline_validation_run) + offline compute", "agents": {}}
allpairs = []
for agent_dir in sorted(SIM.iterdir()):
    am = agent_dir / "bootstrap_memory/associative_memory"
    emb = json.load(open(am / "embeddings.json", encoding="utf-8"))
    nodes = json.load(open(am / "nodes.json", encoding="utf-8"))
    keys = [k for k, v in emb.items() if len(v) == 3072]
    M = np.array([emb[k] for k in keys])
    M = M / np.linalg.norm(M, axis=1, keepdims=True)
    S = M @ M.T
    pairs = []
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            pairs.append((float(S[i, j]), keys[i], keys[j]))
            allpairs.append(float(S[i, j]))
    pairs.sort(reverse=True)
    result["agents"][agent_dir.name] = {
        "n_vectors": len(keys),
        "n_nodes": len(nodes),
        "top_pairs": [{"cos": round(c, 4), "a": a, "b": b} for c, a, b in pairs[:5]],
    }
arr = np.array(allpairs)
result["all_pairs"] = {"n": len(arr), "min": round(float(arr.min()), 4), "median": round(float(np.median(arr)), 4),
                       "p90": round(float(np.percentile(arr, 90)), 4), "max": round(float(arr.max()), 4),
                       "count_ge_0.75": int((arr >= 0.75).sum()), "count_ge_0.80": int((arr >= 0.80).sum()),
                       "count_ge_0.70": int((arr >= 0.70).sum()), "count_ge_0.65": int((arr >= 0.65).sum())}
OUT.write_text(json.dumps(result, indent=1))
print(json.dumps(result, indent=1))
