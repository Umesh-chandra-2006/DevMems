"""
Builds docs/phase5_step3_artifacts/demo_replay_data.json: everything the demo replay prints, from saved scripted-sweep
artifacts (events, clusters, summaries and sources, flags) plus an offline rebuild of the retrieval ranking with
consolidated_weight 0.5 and 1.0 (cached vectors, network disabled, real new_retrieve). Zero network, zero LLM.
Label: scripted events; the vectors and the summaries are live outputs saved earlier.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from devmem.memory import p5_diagnose_retrieval as D

OUT = ROOT / "docs" / "phase5_step3_artifacts" / "demo_replay_data.json"
RUNS = {"0.78 (approved default)": "threshold_0_78_default_third_person",
        "0.82 (calibrated on this one day)": "threshold_0_82_calibrated_third_person"}
fixture = json.loads((ROOT / "devmem/memory/fixtures/scripted_day_isabella.json").read_text(encoding="utf-8"))
data = {"label": "scripted events; saved live embeddings and summaries; ranking recomputed offline", "agent": fixture["agent"],
        "day": fixture["day"], "fixture_note": fixture["note"], "events": fixture["events"], "runs": {}}
for label, tag in RUNS.items():
    saved = json.loads((ROOT / "docs/phase5_step2_artifacts" / f"scripted_sweep_{tag}.json").read_text(encoding="utf-8"))
    diag = D.run(tag, saved_dir="phase5_step2_artifacts", out_dir=ROOT / "docs/phase5_step3_artifacts", full=True)
    assert all(diag["reproduces_saved_summary_ranks"].values()), "offline rebuild must reproduce the saved ranks"
    first = saved["first_sweep"]
    run = {"tag": tag, "threshold": saved["threshold"], "cluster_size_histogram": first["cluster_size_histogram"],
           "entries_considered": first["entries_considered"], "entries_flagged": first["entries_flagged"],
           "episodic_final": [{"entry_id": r["entry_id"], "text": r["content"], "importance": r["importance_score"],
                               "consolidated": bool(r["consolidated"])} for r in saved["episodic_rows"]],
           "event_groups": saved["event_groups"],
           "summaries": [{"entry_id": r["entry_id"], "summary": r["summary"], "importance": r["importance"],
                          "sources": r["sources"], "source_texts": r["source_contents"]} for r in first["results"]],
           "second_sweep": saved["second_sweep_direct"],
           "ranking": {}}
    consolidated = set(diag["consolidated_node_ids"])
    for fname in D.FOCALS:
        entry = {"focal_text": D.FOCALS[fname]}
        for wlabel, wkey in (("weight_0.5", "weight_configured"), ("weight_1.0", "weight_1.0")):
            v = diag["runs"][wkey][fname]
            w = diag["consolidated_weight"] if wkey == "weight_configured" else 1.0
            rows = []
            for nid in v["order"]:
                r = v["rows_all"][nid]
                base = r["weighted"]["recency"] + r["weighted"]["relevance"] + r["weighted"]["importance"]
                score = base * (w if nid in consolidated else 1.0)
                rows.append({"rank": r["rank"], "node": nid, "type": r["type"], "text": r["text"],
                             "consolidated_source": nid in consolidated, "score": round(score, 3),
                             "recency": r["weighted"]["recency"], "relevance": r["weighted"]["relevance"],
                             "importance": r["weighted"]["importance"]})
            entry[wlabel] = rows
        run["ranking"][fname] = entry
    data["runs"][label] = run
OUT.write_text(json.dumps(data, indent=1), encoding="utf-8")
print("wrote", OUT, "| network requests:", D.cache_store.stats["http_requests"])
