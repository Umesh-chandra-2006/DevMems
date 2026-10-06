"""
REINFORCE_THRESHOLD tuning, executed once at Phase 6 Stop 2 by the protocol committed in docs/phase6_preregistration.md section 2.

Label: live embeddings (gemini-embedding-001, cache first, fail loud), scripted text. NO LLM call is made. At most 40 real embedding
requests (counted at the HTTP layer; the 41st raises). The texts are the scripted summary sentences of
devmem/memory/fixtures/scripted_four_nights_isabella.json, written by the Senior Developer, so the margin is a property of an
author-chosen negative and is reported as such.

Protocol (verbatim from the pre-registration):
  1. cosine of every same-theme pair across nights (positives) and every different-theme pair, including the deliberate
     topically similar negative (negatives);
  2. if min(positives) > max(negatives): choose 0.01 below min(positives) rounded down to two decimals, not below 0.80 and not
     above 0.90, and require max(negatives) < chosen; record both extremes and the margin;
  3. if the groups overlap (or step 2's requirement fails): keep 0.85, report it, and state that the fixture cannot separate them;
  4. record the chosen value, the reason and every cosine; then freeze.
"""
import itertools
import json
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
FIXTURE = ROOT / "devmem" / "memory" / "fixtures" / "scripted_four_nights_isabella.json"
ART = ROOT / "docs" / "phase6_stop2_artifacts"
START_VALUE = 0.85
MAX_REQUESTS = 40


def cosine(a, b):
    d = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b)) / d


def decide(positives, negatives):
    min_pos, max_neg = min(p["cosine"] for p in positives), max(n["cosine"] for n in negatives)
    out = {"min_positive": round(min_pos, 4), "max_negative": round(max_neg, 4), "margin": round(min_pos - max_neg, 4)}
    if min_pos > max_neg:
        chosen = math.floor((min_pos - 0.01) * 100 + 1e-9) / 100
        clipped = min(0.90, max(0.80, chosen))
        out["unclipped_candidate"] = round(chosen, 2)
        if max_neg < clipped:
            out.update(chosen=round(clipped, 2), rule="groups separate and max(negatives) < chosen: protocol step 2",
                       clipped=clipped != chosen)
        else:
            out.update(chosen=START_VALUE, rule="groups separate but max(negatives) is not below the clipped candidate: protocol step 3 "
                                                "(keep the starting value); the fixture cannot place a threshold between them",
                       clipped=clipped != chosen)
    else:
        out.update(chosen=START_VALUE, rule="groups overlap: protocol step 3 (keep the starting value); the fixture cannot separate them",
                   clipped=False)
    return out


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    os.environ["DEVMEM_EMBEDDING_MODE"] = "live"
    import requests
    from devmem.embeddings.vector_store import EmbeddingStore

    fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
    sentences = [{"theme": theme, "night": int(n), "text": text}
                 for theme, d in fx["themes"].items() for n, text in d["summaries"].items()]
    counts = {"requests": 0}

    def counted_post(*a, **k):
        if counts["requests"] >= MAX_REQUESTS:
            raise RuntimeError(f"embedding request cap {MAX_REQUESTS} reached")
        counts["requests"] += 1
        return requests.post(*a, **k)

    ART.mkdir(parents=True, exist_ok=True)
    store = EmbeddingStore(post=counted_post, stats_path=ART / "reinforce_tuning_embedding_stats.json")
    vecs = store.embed_texts([s["text"] for s in sentences], batch=True)
    pairs = []
    for (i, a), (j, b) in itertools.combinations(list(enumerate(sentences)), 2):
        pairs.append({"a": f"{a['theme']} n{a['night']}", "b": f"{b['theme']} n{b['night']}", "same_theme": a["theme"] == b["theme"],
                      "cosine": round(cosine(vecs[i], vecs[j]), 4), "a_text": a["text"], "b_text": b["text"]})
    positives = [p for p in pairs if p["same_theme"]]
    negatives = [p for p in pairs if not p["same_theme"]]
    decision = decide(positives, negatives)
    result = {"label": "live embeddings (cache first), scripted text, no LLM calls", "embedding_model": store.model,
              "embedding_requests_made": counts["requests"], "embedding_request_cap": MAX_REQUESTS,
              "embedding_stats": store.stats, "dimension": len(vecs[0]), "starting_value": START_VALUE,
              "positives": sorted(positives, key=lambda p: p["cosine"]), "negatives": sorted(negatives, key=lambda p: -p["cosine"]),
              "decision": decision,
              "stage3_match_threshold": 0.80,
              "note": "Positives are only the three baking pairs (the fixture has one recurring theme); the negative set contains the "
                      "author-chosen topically similar 'cake_negative'. The margin is a property of those choices, not a measurement of "
                      "how Stage 3 summaries from a natural run will behave."}
    (ART / "reinforce_tuning.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    lines = ["# REINFORCE_THRESHOLD tuning (Phase 6 Stop 2)", "", "Label: live embeddings (cache first), scripted text, no LLM calls.",
             f"Model: {store.model}; dimension {len(vecs[0])}; real embedding requests made: {counts['requests']} (cap {MAX_REQUESTS}).", "",
             "## Positives (same theme, different nights)", "", "| pair | cosine |", "|---|---|"]
    lines += [f"| {p['a']} vs {p['b']} | {p['cosine']} |" for p in result["positives"]]
    lines += ["", "## Negatives (different themes)", "", "| pair | cosine |", "|---|---|"]
    lines += [f"| {p['a']} vs {p['b']} | {p['cosine']} |" for p in result["negatives"]]
    lines += ["", "## Decision", "", f"- min positive {decision['min_positive']}, max negative {decision['max_negative']}, margin {decision['margin']}",
              f"- chosen REINFORCE_THRESHOLD: **{decision['chosen']}**", f"- rule applied: {decision['rule']}", "",
              result["note"]]
    (ART / "reinforce_tuning.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"requests": counts["requests"], "stats": {k: store.stats[k] for k in ("http_requests", "cache_hits", "cache_misses", "http_status_counts")},
                      "decision": decision}, indent=1))


if __name__ == "__main__":
    main()
