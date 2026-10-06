"""
P5.0b live probe (label: live). Hard cap: 3 live embedding HTTP requests.
  call 1: one batch request with the 6 Isabella priors + the Phase 3 focal point (7 texts)
  call 2: one batch request with 50 synthetic distinct texts (batch size / latency / dims)
  call 3: one single-text request for the focal point (single vs batch vector comparison)
Also reproduces the Phase 3 retrieval relevance ranking with the real vectors and with the
deterministic fallback vectors (offline), and writes raw artifacts to docs/phase5_step0_artifacts/.
"""
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from devmem.embeddings.vector_store import EmbeddingStore, deterministic_fallback_vector  # noqa: E402
from devmem.memory.priors import load_priors  # noqa: E402

ART = ROOT / "docs" / "phase5_step0_artifacts"
# Run 1 used both keys and got HTTP 403 from GEMINI_KEY_2 (see run1 stats artifact); run 2 uses key 1 only.
KEY_ENVS = ["GEMINI_KEY_1"]
FOCAL = "Isabella has a disagreement and potential confrontation with a neighbour"


def cos(a, b):
    a, b = np.asarray(a), np.asarray(b)
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))


def ranking(vecs, focal, names):
    sims = {n: cos(v, focal) for n, v in zip(names, vecs)}
    return sorted(sims, key=lambda n: -sims[n]), sims


def main():
    priors = load_priors("Isabella Rodriguez")
    texts7 = priors + [FOCAL]
    store = EmbeddingStore(
        cache_path=ROOT / "devmem" / "storage" / "p5_0b_probe_cache.db",
        stats_path=ART / "embedding_stats_p5_0b_probe.json",
        key_envs=KEY_ENVS,
    )
    log = {"label": "live", "calls": []}

    t = time.time()
    v7 = store.embed_texts(texts7, batch=True)
    log["calls"].append({"call": 1, "kind": "batch", "texts": 7, "seconds": round(time.time() - t, 2),
                         "dim": len(v7[0])})

    texts50 = [f"Synthetic probe sentence {i}: Isabella is {a} at the cafe."
               for i, a in enumerate(["baking", "cleaning", "chatting", "restocking", "greeting", "writing",
                                      "planning", "serving", "tidying", "reading"] * 5)]
    t = time.time()
    v50 = store.embed_texts(texts50, batch=True)
    log["calls"].append({"call": 2, "kind": "batch", "texts": 50, "seconds": round(time.time() - t, 2),
                         "dim": len(v50[0])})

    single_store = EmbeddingStore(
        cache_path=ROOT / "devmem" / "storage" / "p5_0b_probe_single_cache.db",
        stats_path=ART / "embedding_stats_p5_0b_probe_single.json",
        key_envs=KEY_ENVS,
    )
    t = time.time()
    s1 = single_store.embed_texts([FOCAL], batch=False)[0]
    log["calls"].append({"call": 3, "kind": "single", "texts": 1, "seconds": round(time.time() - t, 2),
                         "dim": len(s1)})
    log["single_vs_batch_cosine_for_focal"] = round(cos(s1, v7[-1]), 6)
    log["total_http_requests"] = store.stats["http_requests"] + single_store.stats["http_requests"]

    names = [f"prior{i + 1}" for i in range(6)]
    real_rank, real_sims = ranking(v7[:6], v7[6], names)
    fb = [deterministic_fallback_vector(x) for x in texts7]
    fb_rank, fb_sims = ranking(fb[:6], fb[6], names)
    # Spearman rank correlation (no ties expected)
    r_real = {n: i for i, n in enumerate(real_rank)}
    r_fb = {n: i for i, n in enumerate(fb_rank)}
    d2 = sum((r_real[n] - r_fb[n]) ** 2 for n in names)
    spearman = 1 - 6 * d2 / (6 * (36 - 1))
    log["retrieval_reproduction"] = {
        "focal": FOCAL,
        "priors": dict(zip(names, priors)),
        "gemini-embedding-001": {"ranking": real_rank, "cosine": {k: round(v, 4) for k, v in real_sims.items()}},
        "deterministic_fallback_768": {"ranking": fb_rank, "cosine": {k: round(v, 4) for k, v in fb_sims.items()},
                                       "spearman_vs_gemini": round(spearman, 3)},
        "local_model": "not measured (no local model installed; see report)",
    }
    # raw vectors for the 7 texts (rounded) so the numbers can be re-derived offline
    (ART / "p5_0b_vectors_7texts.json").write_text(json.dumps(
        {"model": store.model, "texts": texts7, "vectors": [[round(x, 6) for x in v] for v in v7]}))
    (ART / "p5_0b_probe_results.json").write_text(json.dumps(log, indent=1))
    print(json.dumps(log, indent=1))


if __name__ == "__main__":
    main()
