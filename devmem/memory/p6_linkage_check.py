"""
Pre-launch P3 (offline, ZERO LLM calls, ZERO embedding requests): how do Stage 3's clustering settings split Stop 3's real entries?
Stop 3 used the production config recorded in its own consolidation log: single linkage at cluster_similarity 0.78, minimum cluster 3,
importance floor 3. This script re-clusters the SAME entries, with the SAME real embeddings read from the on-disk embedding cache,
under (a) single 0.78 (what Stop 3 used) and (b) average 0.82, and compares both with the scripted theme labels of the fixture
(devmem/memory/fixtures/scripted_four_nights_isabella.json). The theme labels are the author's; they are not a measurement.
Nights 2 and 3 are the informative ones (night 2 mixes baking, letters and the lease event; night 3 mixes the conflict theme and the
cake theme); nights 1 and 4 are listed for completeness.
"""
import itertools
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "docs" / "phase6_stop3_artifacts" / "linkage_check.json"
SETTINGS = [("single_0.78 (what Stop 3 used)", "single", 0.78), ("average_0.82", "average", 0.82)]


def main():
    from devmem.api import store
    from devmem.memory.consolidation import cluster_by_similarity
    fx = json.loads((ROOT / "devmem/memory/fixtures/scripted_four_nights_isabella.json").read_text(encoding="utf-8"))
    theme_of = {e["text"]: e["theme"] for n in fx["nights"] for e in n["events"]}
    night_of = {e["text"]: n["night"] for n in fx["nights"] for e in n["events"]}
    c = sqlite3.connect(str(ROOT / "docs/phase6_stop3_artifacts/memory.db"))
    rows = c.execute("SELECT entry_id, content, importance_score FROM episodic_memory WHERE agent_id LIKE 'Isabella%' ORDER BY rowid").fetchall()
    result = {"label": "offline: cached real embeddings, scripted theme labels, zero calls", "settings": [s[0] for s in SETTINGS], "nights": {}}
    for night in (1, 2, 3, 4):
        ents = [(e, t, i) for e, t, i in rows if night_of.get(t) == night and (i or 0) >= 3 and "idle" not in t.lower()]
        vecs, missing = [], 0
        for e, t, i in ents:
            v = store._cached_vec(t)
            if v is None:
                missing += 1
            vecs.append(v)
        if missing:
            result["nights"][str(night)] = {"error": f"{missing} entry vectors are not in the embedding cache"}
            continue
        themes = [theme_of[t] for _, t, _ in ents]
        pair_cos = [{"a": themes[i], "b": themes[j], "same_theme": themes[i] == themes[j],
                     "cosine": round(sum(x * y for x, y in zip(vecs[i], vecs[j])) / ((sum(x * x for x in vecs[i]) ** .5) * (sum(y * y for y in vecs[j]) ** .5)), 4)}
                    for i, j in itertools.combinations(range(len(ents)), 2)]
        same = [p["cosine"] for p in pair_cos if p["same_theme"]]
        diff = [p["cosine"] for p in pair_cos if not p["same_theme"]]
        entry = {"entries": len(ents), "themes": dict((t, themes.count(t)) for t in sorted(set(themes))),
                 "min_same_theme_cosine": min(same) if same else None, "max_cross_theme_cosine": max(diff) if diff else None, "settings": {}}
        for name, linkage, thr in SETTINGS:
            groups = cluster_by_similarity(vecs, thr, linkage)
            desc = [{"size": len(g), "themes": dict((t, [themes[i] for i in g].count(t)) for t in sorted({themes[i] for i in g}))} for g in groups]
            summarized = [d for d in desc if d["size"] >= 3]
            pure = [d for d in summarized if len(d["themes"]) == 1]
            # pairs of same-theme entries that ended in the same cluster / cross-theme pairs wrongly merged
            lab = {}
            for gi, g in enumerate(groups):
                for i in g:
                    lab[i] = gi
            tp = sum(1 for i, j in itertools.combinations(range(len(ents)), 2) if themes[i] == themes[j] and lab[i] == lab[j])
            fp = sum(1 for i, j in itertools.combinations(range(len(ents)), 2) if themes[i] != themes[j] and lab[i] == lab[j])
            n_same = sum(1 for i, j in itertools.combinations(range(len(ents)), 2) if themes[i] == themes[j])
            entry["settings"][name] = {"clusters": desc, "clusters_that_would_be_summarized": len(summarized),
                                       "summarized_clusters_with_a_single_theme": len(pure), "same_theme_pairs_together": f"{tp} of {n_same}",
                                       "cross_theme_pairs_merged": fp}
        result["nights"][str(night)] = entry
    OUT.write_text(json.dumps(result, indent=1), encoding="utf-8")
    for n, e in result["nights"].items():
        print("night", n, {k: v for k, v in e.items() if k != "settings"} if "error" not in e else e)
        for s, d in e.get("settings", {}).items():
            print("   ", s, "clusters", [x["size"] for x in d["clusters"]], "summarized", d["clusters_that_would_be_summarized"], "pure", d["summarized_clusters_with_a_single_theme"], "same-theme pairs together", d["same_theme_pairs_together"], "cross-theme merged", d["cross_theme_pairs_merged"])


if __name__ == "__main__":
    main()
