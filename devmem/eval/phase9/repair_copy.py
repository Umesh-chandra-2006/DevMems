"""
Repair of a TORN external checkpoint copy (found 2026-10-08: the day-2 copies made before the copier waited for the end of the autosave have a truncated `embeddings.json` for some
personas, because upstream `Reverie.save()` writes meta.json first and the personas afterwards). The original copy is never modified: the repair writes a NEW folder.

For every persona whose embeddings.json does not parse, the file is rebuilt from that persona's nodes.json: each node's `embedding_key` is looked up in the on-disk embedding cache
(the same gemini-embedding-001 vectors the run used; the cache stores float32, so a rebuilt vector can differ from the original float64 in the 7th decimal, which does not change a
cosine ranking in practice but is NOT bit-identical and is disclosed in repair.json). If any key is missing from the cache the persona is listed as not repairable and the copy is
not usable. Other files are checked for parsing; the mirror rows are checked against nodes.json (rows whose node is absent mean the persona files come from an earlier save).

    python -m devmem.eval.phase9.repair_copy --src devmem/storage/interim_day2/baseline --dst devmem/storage/interim_day2_repaired/baseline
"""
import argparse
import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Sequence


def _parses(f: Path) -> bool:
    try:
        with open(f, encoding="utf-8") as fh:
            json.load(fh)
        return True
    except Exception:
        return False


def repair(src: Path, dst: Path, cached_fn: Callable[[str], Optional[Sequence[float]]]) -> Dict[str, Any]:
    src, dst = Path(src), Path(dst)
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst)
    report: Dict[str, Any] = {"source": str(src), "personas": {}, "usable": True,
                              "note": "embeddings.json rebuilt from nodes.json embedding keys and the on-disk embedding cache (float32 precision); original copy untouched"}
    mdb = dst / "memory.db"
    mirror = None
    if mdb.exists():
        mirror = sqlite3.connect(f"file:{mdb.as_posix()}?mode=ro", uri=True)
    for pdir in sorted((dst / "sim" / "personas").iterdir()):
        a = pdir / "bootstrap_memory" / "associative_memory"
        nodes = json.loads((a / "nodes.json").read_text(encoding="utf-8")) if _parses(a / "nodes.json") else None
        item: Dict[str, Any] = {"nodes_json_parses": nodes is not None, "embeddings_json_parsed_before": _parses(a / "embeddings.json")}
        if nodes is None:
            item["repairable"] = False
            report["usable"] = False
        elif not item["embeddings_json_parsed_before"]:
            emb, missing = {}, 0
            for nd in nodes.values():
                k = nd["embedding_key"]
                if k in emb:
                    continue
                v = cached_fn(k)
                if v is None:
                    missing += 1
                else:
                    emb[k] = [float(x) for x in v]
            item.update({"rebuilt_keys": len(emb), "keys_missing_from_cache": missing, "repairable": missing == 0})
            if missing == 0:
                (a / "embeddings.json").write_text(json.dumps(emb), encoding="utf-8")
            else:
                report["usable"] = False
        if mirror is not None and nodes is not None:
            rows = {r[0].split(":", 1)[1] for r in mirror.execute("SELECT entry_id FROM episodic_memory WHERE agent_id = ?", (pdir.name,))}
            item["mirror_rows_without_a_node_in_nodes_json"] = len(rows - set(nodes))
        report["personas"][pdir.name] = item
    if mirror is not None:
        mirror.close()
    bad = [str(f.relative_to(dst)) for f in (dst / "sim").rglob("*.json") if not _parses(f)]
    report["json_files_still_not_parsing"] = bad
    if bad:
        report["usable"] = False
    cj = dst / "checkpoint.json"
    if cj.exists():
        meta = json.loads(cj.read_text(encoding="utf-8"))
        meta["repaired_copy"] = "embeddings.json rebuilt from the embedding cache (see repair.json); do not present as an untouched checkpoint"
        cj.write_text(json.dumps(meta, indent=1), encoding="utf-8")
    (dst / "repair.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--dst", required=True)
    a = ap.parse_args()
    from devmem.api import store
    rep = repair(Path(a.src), Path(a.dst), store._cached_vec)
    print(json.dumps({"usable": rep["usable"], "personas": {k: {x: v[x] for x in v if x in ("embeddings_json_parsed_before", "rebuilt_keys", "keys_missing_from_cache", "mirror_rows_without_a_node_in_nodes_json")} for k, v in rep["personas"].items()}, "still_bad": rep["json_files_still_not_parsing"]}))


if __name__ == "__main__":
    main()
