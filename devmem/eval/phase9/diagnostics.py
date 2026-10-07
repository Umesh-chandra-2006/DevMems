"""
Provenance and cluster diagnostics (offline, no call). Provenance reuses the inspector's cached-embedding diagnostic (a trait's cosine to its sources and to the agent's priors;
unavailable when a vector is not in the embedding cache, never estimated). Cluster quality summarizes consolidation_log.jsonl: sweeps, entries considered, cluster size
histogram, summaries written and reinforced, flags. Both are diagnostics, not outcomes.
"""
import json
from pathlib import Path
from typing import Any, Dict, List

from devmem.api import store


def provenance_rows(traits: List[Dict[str, Any]], source_texts_by_trait: Dict[str, List[str]], priors_text: str) -> List[Dict[str, Any]]:
    rows = []
    for t in traits:
        rows.append({"trait_id": t["trait_id"], "path": t.get("path"), **store.provenance(t["text"], source_texts_by_trait.get(t["trait_id"], []), priors_text)})
    flagged = sum(1 for r in rows if r.get("available") and r.get("closer_to_priors_than_to_best_source"))
    return [{"summary": {"traits": len(rows), "available": sum(1 for r in rows if r.get("available")), "closer_to_priors_than_to_best_source": flagged}}] + rows


def cluster_quality(consolidation_log: Path) -> Dict[str, Any]:
    rows = [json.loads(l) for l in Path(consolidation_log).read_text(encoding="utf-8").splitlines() if l.strip()]
    hist: Dict[str, int] = {}
    for r in rows:
        for size, n in (r.get("cluster_size_histogram") or {}).items():
            hist[size] = hist.get(size, 0) + n
    done = [r for r in rows if r.get("status") == "done"]
    settings = sorted({str(r.get("linkage")) + "@" + str(r.get("threshold")) for r in rows})
    return {"sweeps": len(rows), "sweeps_done": len(done), "entries_considered": sum(r.get("entries_considered", 0) for r in done),
            "summaries_written": sum(r.get("summaries_written", 0) for r in done), "summaries_reinforced": sum(r.get("summaries_reinforced", 0) for r in done),
            "entries_flagged": sum(r.get("entries_flagged", 0) for r in done), "cluster_size_histogram": dict(sorted(hist.items(), key=lambda x: int(x[0]))),
            "settings_seen": settings, "failures": sum(len(r.get("failures") or []) for r in rows), "fallbacks": sum(r.get("fallbacks", 0) for r in rows)}
