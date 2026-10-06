"""
Offline analysis of the Phase 6 Stop 3 live run (reads docs/phase6_stop3_artifacts only; no network).
Calls and tokens by purpose are taken from the router ledger rows of the run AND from the run's memory.db llm_call_log: the five
new-event scoring calls passed db_path=<run db> to the scorer, which forwards it to call_llm as the LEDGER path (existing Phase 3
behavior), so their rows are in memory.db and not in the main ledger. Raw replies are the per-call cross-check.
"""
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
ART = ROOT / "docs" / "phase6_stop3_artifacts"


def main():
    rep = json.loads((ART / "stop3_report.json").read_text(encoding="utf-8"))
    raw = [json.loads(l) for l in (ART / "raw_replies.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    c = sqlite3.connect(str(ART / "memory.db"))
    rows = c.execute("SELECT purpose, tokens_in, tokens_out FROM llm_call_log").fetchall()
    c.close()
    by = {k: dict(v) for k, v in rep["tokens_by_purpose"].items()}
    for purpose, ti, to in rows:
        e = by.setdefault(purpose, {"calls": 0, "tokens_in": 0, "tokens_out": 0})
        e["calls"] += 1
        e["tokens_in"] += ti or 0
        e["tokens_out"] += to or 0
    raw_by = {}
    for r in raw:
        raw_by[r["purpose"]] = raw_by.get(r["purpose"], 0) + 1
    traits = {t["trait_id"]: t for t in rep["tables"]["identity_traits"]}
    renders = []
    for s in rep["new_event_scoring"]:
        included = [tid for tid, t in traits.items() if t["text"] in s["prompt"]]
        renders.append({"text": s["text"], "score": s["score"], "prompt_contains_header": s["prompt_contains_header"],
                        "traits_in_prompt": included, "active_traits_not_in_prompt": [t for t, v in traits.items() if v["active"] and t not in included]})
    retry = [r for r in raw if r["purpose"] == "identity_trait" and len(r["raw"].split()) > 35]
    out = {"label": "offline analysis of live artifacts", "calls_by_purpose_router_counter": rep["router_counter"]["by_purpose"],
           "raw_reply_count_by_purpose": raw_by, "tokens_by_purpose_main_ledger": rep["tokens_by_purpose"],
           "tokens_by_purpose_main_plus_run_db_ledger": by, "new_event_prompts": renders,
           "trait_raw_replies_over_35_words": [{"words": len(r["raw"].split()), "raw": r["raw"]} for r in retry],
           "all_trait_texts": [{"trait_id": k, "path": v["path"], "active": v["active"], "night": v["created_night"], "words": len(v["text"].split()),
                                "text": v["text"]} for k, v in traits.items()]}
    (ART / "stop3_analysis.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("calls_by_purpose_router_counter", "raw_reply_count_by_purpose",
                                          "tokens_by_purpose_main_plus_run_db_ledger", "trait_raw_replies_over_35_words")}, indent=1))
    for r in renders:
        print(r)


if __name__ == "__main__":
    main()
