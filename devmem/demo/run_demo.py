"""
Stage 3 demo (label: SCRIPTED events: a day written by hand for Isabella Rodriguez, not a simulation run).

  python devmem/demo/run_demo.py                 replay from saved artifacts (no network, no keys needed)
  python devmem/demo/run_demo.py --run 0.82      replay only one threshold run
  python devmem/demo/run_demo.py --live          live mode: real embeddings (cached) and at most 4 LLM calls, pinned
                                                 openai/gpt-oss-20b, one sweep at the approved default threshold 0.78

Prints: the scripted day's episodic entries, the clusters, each summary with its sources, and the retrieval ranking with
consolidated_weight 0.5 versus 1.0 for three focal points.
"""
import argparse
import json
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252; model text contains e.g. U+2011
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
REPLAY = ROOT / "docs" / "phase5_step3_artifacts" / "demo_replay_data.json"
FOCAL_NAMES = {"neighbor_argument": "neighbor argument", "conflict_handling": "conflict handling", "baking": "baking"}


def hr(title):
    print("\n" + "=" * 100 + f"\n{title}\n" + "=" * 100)


def reason_unconsolidated(text, importance, floor=3):
    if "idle" in text.lower():
        return "idle event (excluded by the idle filter)"
    if importance < floor:
        return f"importance {importance} below the floor {floor}"
    return "not clustered (isolated, or its cluster was smaller than 3)"


def show_events(rows, label):
    hr(f"1. EPISODIC ENTRIES AFTER THE SWEEP ({label})")
    print(f"{'time':<6} {'imp':>3}  {'consolidated':<12} text")
    for r in rows:
        print(f"{r['time']:<6} {int(r['importance']):>3}  {'yes' if r['consolidated'] else 'no':<12} {r['text']}")


def show_clusters(run, events_by_text):
    hr(f"2. CLUSTERS  (threshold {run['threshold']}, single linkage; entries considered {run['entries_considered']}, "
       f"flagged {run['entries_flagged']})")
    print("cluster-size histogram (size: count of clusters):", run["cluster_size_histogram"])
    for i, s in enumerate(run["summaries"], 1):
        print(f"\n  cluster {i}: {len(s['sources'])} entries")
        for t in s["source_texts"]:
            print(f"    - {t}")
    left = [r for r in run["episodic_final"] if not r["consolidated"]]
    print("\n  left as raw episodic entries:")
    for r in left:
        print(f"    - {r['text']}   [{reason_unconsolidated(r['text'], r['importance'])}]")


def show_summaries(run):
    hr("3. SEMANTIC MEMORIES (summary and the source entries it references)")
    for s in run["summaries"]:
        print(f"\n  {s['entry_id']}  importance {s['importance']}")
        print(f"  SUMMARY: {s['summary']}")
        print(f"  sources ({len(s['sources'])}): {', '.join(x.split(':', 1)[1] for x in s['sources'])}")
        for t in s["source_texts"]:
            print(f"    - {t}")
    print("\n  second sweep the same night:", run.get("second_sweep"))


def show_ranking(ranking, weights, with_scores):
    hr("4. RETRIEVAL RANKING (real new_retrieve; '*' = summary thought, 'c' = consolidated source entry)")
    for fname, entry in ranking.items():
        print(f"\n  focal point [{FOCAL_NAMES.get(fname, fname)}]: {entry['focal_text']}")
        w05, w10 = entry["weight_0.5"], entry["weight_1.0"]
        print(f"    {'rank':>4}  {'consolidated_weight 0.5':<62} | consolidated_weight 1.0")
        for a, b in zip(w05, w10):
            def cell(r):
                mark = "*" if r["type"] == "thought" else ("c" if r.get("consolidated_source") else " ")
                sc = f" {r['score']:.2f}" if with_scores else ""
                return f"{mark} {r['text'][:46]:<46}{sc}"
            print(f"    {a['rank']:>4}  {cell(a):<62} | {cell(b)}")


def replay(which):
    if not REPLAY.exists():
        sys.exit(f"missing {REPLAY}; run devmem/demo/export_demo_data.py first")
    data = json.loads(REPLAY.read_text(encoding="utf-8"))
    hr("STAGE 3 DEMO, REPLAY MODE: scripted day for " + data["agent"] + f" ({data['day']})")
    print("Label: SCRIPTED events (hand-written). Embeddings and summaries are saved live outputs; the ranking is recomputed\n"
          "offline with the real new_retrieve. No network, no LLM calls in this mode.")
    times = {e["text"]: e["t"] for e in data["events"]}
    for label, run in data["runs"].items():
        if which and which not in label:
            continue
        print("\n\n" + "#" * 100 + f"\n# RUN: threshold {label}\n" + "#" * 100)
        rows = sorted(({"time": times.get(r["text"], "?"), **r} for r in run["episodic_final"]), key=lambda r: r["time"])
        show_events(rows, label)
        show_clusters(run, times)
        show_summaries(run)
        show_ranking(run["ranking"], (0.5, 1.0), with_scores=True)
    print("\nLimits: one scripted day, one persona; the ranking combines recency, importance and relevance, and upstream's\n"
          "recency favors older nodes (see the report). This demo shows the mechanism, not recall quality.")


def live():
    import os
    os.environ["DEVMEM_PINNED_MODEL"] = "openai/gpt-oss-20b"
    from devmem.memory import consolidation as cons, episodic, scripted_sweep

    class CapReached(BaseException):
        pass
    used = {"n": 0}

    def guard(fn):
        def wrapped(*a, **k):
            if used["n"] >= 4:
                raise CapReached("live demo cap of 4 LLM calls reached")
            used["n"] += 1
            return fn(*a, **k)
        return wrapped
    cons.call_llm = guard(cons.call_llm)
    episodic.call_llm = guard(episodic.call_llm)
    hr("STAGE 3 DEMO, LIVE MODE (at most 4 LLM calls; real embeddings; scripted events)")
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):  # upstream prints very verbose debug lines during retrieval
        out = scripted_sweep.run_scripted_sweep("demo_live", threshold=None, artifacts_dir=None)
    print(f"LLM calls made: {used['n']} (cap 4); ledger rows: {out['llm_calls_made']}")
    first = out["first_sweep"]
    rows = [{"time": "", "text": r["content"], "importance": r["importance_score"], "consolidated": bool(r["consolidated"])}
            for r in out["episodic_rows"]]
    show_events(rows, "live")
    run = {"threshold": out["threshold"], "entries_considered": first["entries_considered"],
           "entries_flagged": first["entries_flagged"], "cluster_size_histogram": first["cluster_size_histogram"],
           "summaries": [{"entry_id": r["entry_id"], "summary": r["summary"], "importance": r["importance"],
                          "sources": r["sources"], "source_texts": r["source_contents"]} for r in first["results"]],
           "episodic_final": rows, "second_sweep": out["second_sweep_direct"]}
    show_clusters(run, {})
    show_summaries(run)
    ranking = {}
    for fname, focal in out["retrieval"]["focal_points"].items():
        e = {"focal_text": focal}
        for lab, key in (("weight_0.5", "weight_configured"), ("weight_1.0", "weight_1.0")):
            order = out["retrieval"]["runs"][key][fname]["order"]
            cons_ids = set(out["live_consolidated_node_ids"])
            e[lab] = [{"rank": i + 1, "node": o["node_id"], "type": o["type"], "text": o["description"],
                       "consolidated_source": o["node_id"] in cons_ids} for i, o in enumerate(order)]
        ranking[fname] = e
    show_ranking(ranking, (0.5, 1.0), with_scores=False)
    import shutil
    shutil.rmtree(ROOT / "devmem" / "storage" / "p5_scripted_sweep_demo_live", ignore_errors=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--run", default=None, help='replay only runs whose label contains this text, e.g. "0.82"')
    a = ap.parse_args()
    if a.live:
        live()
    else:
        replay(a.run)
