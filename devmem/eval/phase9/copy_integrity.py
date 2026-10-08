"""
Integrity tests for a checkpoint copy (PM rule 2026-10-08, after the torn day-2 copies): for a simulation folder (personas/ and reverie/meta.json) and, when given, the mirror database
of the copy:
  T1  every persona's scratch.json (the last file of a persona's save) is at least as new as reverie/meta.json (the first file of the save);
  T2  every JSON file parses (no truncation);
  T3  every mirror episodic row of the agent has its node in the persona's nodes.json (a persona file older than the mirror fails this).
`check` returns a report with the three results per persona and `passes`. `choose_day3(arm)` picks the day-3 checkpoint an evaluation uses: the runner's OWN checkpoint folder when it
passes T1 and T2 (the runner writes it after its save finished), otherwise the external copy when that passes, otherwise nothing.

    python -m devmem.eval.phase9.copy_integrity            checks every copy under devmem/storage and writes docs/phase9_copy_integrity.json
"""
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parent.parent.parent.parent
SIM = ROOT / "reverie" / "environment" / "frontend_server" / "storage"
ST = ROOT / "devmem" / "storage"


def _parses(f: Path) -> bool:
    try:
        with open(f, encoding="utf-8") as fh:
            json.load(fh)
        return True
    except Exception:
        return False


def check(sim_dir: Path, memory_db: Optional[Path] = None) -> Dict[str, Any]:
    sim_dir = Path(sim_dir)
    meta_f = sim_dir / "reverie" / "meta.json"
    out: Dict[str, Any] = {"sim_dir": str(sim_dir), "personas": {}, "json_not_parsing": []}
    if not meta_f.exists() or not _parses(meta_f):
        out.update({"passes": False, "reason": "reverie/meta.json missing or not parsing"})
        return out
    t_meta = meta_f.stat().st_mtime
    mirror = sqlite3.connect(f"file:{Path(memory_db).as_posix()}?mode=ro", uri=True) if memory_db and Path(memory_db).exists() else None
    for pdir in sorted((sim_dir / "personas").iterdir()):
        b = pdir / "bootstrap_memory"
        sc = b / "scratch.json"
        item: Dict[str, Any] = {"T1_scratch_at_least_as_new_as_meta": sc.exists() and sc.stat().st_mtime >= t_meta - 0.001}
        nodes = None
        if _parses(b / "associative_memory" / "nodes.json"):
            nodes = json.loads((b / "associative_memory" / "nodes.json").read_text(encoding="utf-8"))
        if mirror is not None and nodes is not None:
            rows = {r[0].split(":", 1)[1] for r in mirror.execute("SELECT entry_id FROM episodic_memory WHERE agent_id = ?", (pdir.name,))}
            item["T3_mirror_rows_without_a_node"] = len(rows - set(nodes))
        out["personas"][pdir.name] = item
    if mirror is not None:
        mirror.close()
    for f in sim_dir.rglob("*.json"):
        if not _parses(f):
            out["json_not_parsing"].append(f.relative_to(sim_dir).as_posix())
    out["T2_all_json_parse"] = not out["json_not_parsing"]
    out["passes"] = out["T2_all_json_parse"] and all(v["T1_scratch_at_least_as_new_as_meta"] and v.get("T3_mirror_rows_without_a_node", 0) == 0 for v in out["personas"].values())
    return out


def check_copy_folder(copy_dir: Path) -> Dict[str, Any]:
    """A copy folder made by the external copier or the day-1 copier: <dir>/sim, <dir>/memory.db, <dir>/checkpoint.json."""
    copy_dir = Path(copy_dir)
    sim = copy_dir / "sim"
    if not sim.exists():
        return {"passes": False, "reason": "no sim folder"}
    r = check(sim, copy_dir / "memory.db")
    cj = copy_dir / "checkpoint.json"
    if cj.exists() and _parses(cj):
        m = json.loads(cj.read_text(encoding="utf-8"))
        r["checkpoint"] = {k: m.get(k) for k in ("label", "step", "sim_clock", "made_at", "repaired_copy")}
    return r


def choose_day3(arm: str, sim_root: Path = None, storage: Path = None) -> Dict[str, Any]:
    sim_root, storage = sim_root or SIM, storage or ST
    own = sim_root / f"p7_{arm}__ckpt_day3_end_awake"
    ext = storage / "interim_day3" / arm
    res: Dict[str, Any] = {"arm": arm, "runner_checkpoint": str(own), "external_copy": str(ext)}
    if own.exists():
        r = check(own)
        res["runner_checkpoint_tests"] = {k: r.get(k) for k in ("passes", "T2_all_json_parse", "json_not_parsing")}
        res["runner_checkpoint_T1"] = {n: v["T1_scratch_at_least_as_new_as_meta"] for n, v in r["personas"].items()} if r.get("personas") else None
        if r.get("passes"):
            res.update({"chosen": "runner", "path": str(own)})
            return res
    if (ext / "sim").exists():
        r = check_copy_folder(ext)
        res["external_copy_tests"] = {k: r.get(k) for k in ("passes", "T2_all_json_parse", "json_not_parsing")}
        if r.get("passes"):
            res.update({"chosen": "external", "path": str(ext / "sim")})
            return res
    res.update({"chosen": None, "path": None})
    return res


def main():
    out = {}
    for d in sorted(ST.glob("interim_day*/*")):
        if (d / "sim").exists():
            out[d.relative_to(ST).as_posix()] = check_copy_folder(d)
    for d in sorted(SIM.glob("p7_*__ckpt_*")):
        r = check(d)
        out["runner:" + d.name] = r
    (ROOT / "docs" / "phase9_copy_integrity.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    for k, v in out.items():
        bad = {n: x for n, x in (v.get("personas") or {}).items() if not x["T1_scratch_at_least_as_new_as_meta"] or x.get("T3_mirror_rows_without_a_node", 0)}
        print(f"{k:55} passes={v.get('passes')} json_bad={v.get('json_not_parsing')} personas_failing={ {n: (x['T1_scratch_at_least_as_new_as_meta'], x.get('T3_mirror_rows_without_a_node')) for n, x in bad.items()} }")


if __name__ == "__main__":
    main()
