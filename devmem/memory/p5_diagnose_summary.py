"""Prints/writes a readable table of the Task A diagnosis from docs/phase5_step2_artifacts/diag_retrieval_*.json
(for the conflict summary node and the top 3 nodes per focal point: recency, importance, relevance before/after
normalization). No network, no LLM."""
import json
from pathlib import Path

ART = Path(__file__).resolve().parent.parent.parent / "docs" / "phase5_step2_artifacts"
lines = []
for tag in ("threshold_0_78_default", "threshold_0_82_calibrated"):
    d = json.loads((ART / f"diag_retrieval_{tag}.json").read_text(encoding="utf-8"))
    lines.append(f"## {tag}  (reproduces saved ranks: {d['reproduces_saved_summary_ranks']}, nodes {d['nodes_total']})")
    for nid, text in d["summary_nodes"].items():
        lines.append(f"- {nid}: {text}")
    for focal, v in d["runs"]["weight_configured"].items():
        lines.append(f"\n### focal: {focal}   summary ranks {v['summary_ranks']} (weight {d['consolidated_weight']})")
        lines.append("| rank | node | type | recency raw -> norm | importance raw -> norm | relevance cos -> norm | weighted rec/rel/imp | text |")
        lines.append("|---|---|---|---|---|---|---|---|")
        shown = []
        for nid, r in list(v["rows_top3"].items()) + [(k, x) for k, x in v["rows_summaries"].items() if k == "node_18"]:
            if nid in shown:
                continue
            shown.append(nid)
            w = r["weighted"]
            lines.append(f"| {r['rank']} | {nid} | {r['type']} | {r['recency_raw']} -> {r['recency_norm']} | "
                         f"{r['importance_raw']} -> {r['importance_norm']} | {r['relevance_raw_cos']} -> {r['relevance_norm']} | "
                         f"{w['recency']} / {w['relevance']} / {w['importance']} | {r['text']} |")
    lines.append("")
(ART / "diag_retrieval_tables.md").write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines))
