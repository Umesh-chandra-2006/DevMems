"""
Embedding fetch for D-1 and D-2 (PM ruling 2026-10-08): on the FINISHED staged arm's embedding keys (eval_keys guard), model gemini-embedding-001 (the run's model), embed every text
the D-1 provenance diagnostic needs (each Stage 4 trait, its source summaries and events, each agent's priors text) and every entry text the D-2 reproduction found missing, that is not
already in the on-disk embedding cache. Cached texts cost nothing. Output: devmem/storage/phase9_eval/fetch_embeddings.json (counts, no key). `--dry-run` lists the missing texts only.

    python -m devmem.eval.phase9.fetch_embeddings [--memory-db PATH] [--dry-run]
"""
import argparse
import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from devmem.eval.phase9 import d2_reproduction

ROOT = Path(__file__).resolve().parent.parent.parent.parent
BATCH = 50


def plan(memory_db: Path, personas_dir: Path, cached_fn: Callable[[str], Optional[Sequence[float]]], log_path: Path) -> Dict[str, Any]:
    d1 = d2_reproduction.d1_texts(memory_db)
    conn = sqlite3.connect(f"file:{Path(memory_db).as_posix()}?mode=ro", uri=True)
    present = {(r[0], r[1]) for r in conn.execute("SELECT agent_id, night FROM consolidation_sweeps WHERE status='done'")}
    conn.close()
    rows = [json.loads(l) for l in Path(log_path).read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = [r for r in rows if (r["agent"], r["night"]) in present]
    d2 = d2_reproduction.reproduce(memory_db, rows, d2_reproduction.persona_vec_fn(personas_dir))
    miss_d1 = [t for t in d1 if cached_fn(t) is None]
    miss_d2 = d2["missing_texts"]
    return {"d1_texts": len(d1), "d1_missing_from_cache": len(miss_d1), "d2_missing_entry_vectors": len(miss_d2), "to_fetch": sorted(set(miss_d1) | set(miss_d2))}


def fetch(texts: List[str], embed_fn: Callable[[List[str]], List[List[float]]]) -> int:
    n = 0
    for i in range(0, len(texts), BATCH):
        chunk = texts[i:i + BATCH]
        n += len(embed_fn(chunk))
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--memory-db", default=str(ROOT / "devmem" / "storage" / "interim_day3" / "staged" / "memory.db"))
    ap.add_argument("--personas-dir", default=str(ROOT / "reverie" / "environment" / "frontend_server" / "storage" / "p7_staged" / "personas"))
    ap.add_argument("--log", default=str(ROOT / "devmem" / "storage" / "p7_staged" / "consolidation_log.jsonl"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    sys.path.insert(0, str(ROOT))
    from devmem.api import store
    p = plan(Path(a.memory_db), Path(a.personas_dir), store._cached_vec, Path(a.log))
    out = ROOT / "devmem" / "storage" / "phase9_eval"
    out.mkdir(parents=True, exist_ok=True)
    summary = {k: v for k, v in p.items() if k != "to_fetch"}
    summary["to_fetch"] = len(p["to_fetch"])
    if a.dry_run:
        print(json.dumps(summary))
        return
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    from devmem.embeddings.vector_store import EmbeddingStore
    from devmem.eval import run_arm
    from devmem.eval.phase9 import eval_keys
    eval_keys.pool("staged")                                   # raises ArmStillRunning unless the staged arm has finished
    es = EmbeddingStore(stats_path=Path(tempfile.mkdtemp()) / "s.json", key_envs=list(run_arm.EMBED_KEYS["staged"]), model="gemini-embedding-001")
    fetched = fetch(p["to_fetch"], lambda chunk: es.embed_texts(chunk, batch=True))
    summary.update({"fetched": fetched, "model": "gemini-embedding-001", "http_requests": es.stats.get("http_requests")})
    (out / "fetch_embeddings.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
