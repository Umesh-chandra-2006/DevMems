"""
External checkpoint copier (read-only toward the run). The runner makes only the day-1 and day-3 primary checkpoints; the day-2 interim copy (step 13,770) and the secondary
sensitivity copies (day 2 step 17,190, day 3 step 25,830; pre-registration 7g) are taken from OUTSIDE the run by this script, which never writes to a run folder.

How a copy is made: wait until the saved simulation folder's reverie/meta.json shows an autosave at or after the target step; copy `personas/`, `reverie/` and the environment file
of that step; make a consistent SQLite backup of the arm's mirror (`memory.db`, opened read-only) and then TRIM the copy to the autosave clock (rows of episodic_memory,
semantic_memory, identity_traits, consolidation_sweeps and identity_sweeps stamped later than the autosave clock are deleted from the COPY), because the live mirror is written
immediately while the saved folders change only at autosaves; re-read meta.json afterwards and, if an autosave happened during the copy, discard and retry. The actual step and
clock are recorded in checkpoint.json; if the first autosave at or after the target was missed (the observed step is above the target), `exact_first_autosave` is false.

    python -m devmem.eval.phase9.external_checkpoint --arm staged --target-step 13770 --label day2_primary_interim --dest devmem/storage/interim_day2
"""
import argparse
import json
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parent.parent.parent.parent
SIM = ROOT / "reverie" / "environment" / "frontend_server" / "storage"
TRIM = {"episodic_memory": "sim_timestamp", "semantic_memory": "created_at", "identity_traits": "created_sim_time", "consolidation_sweeps": "sweep_time", "identity_sweeps": "sweep_time"}


def _meta(sim_dir: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads((sim_dir / "reverie" / "meta.json").read_text(encoding="utf-8"))
    except Exception:
        return None


def _clock(meta: Dict[str, Any]) -> str:
    from datetime import datetime
    return datetime.strptime(meta["curr_time"], "%B %d, %Y, %H:%M:%S").strftime("%Y-%m-%d %H:%M:%S")


def copy_once(arm: str, target_step: int, label: str, dest: Path, storage: Path = SIM, run_root: Optional[Path] = None, sim_prefix: str = "p7") -> Optional[Dict[str, Any]]:
    """One attempt. Returns the checkpoint record, or None when no autosave at or after the target exists yet (or an autosave happened during the copy)."""
    sim = f"{sim_prefix}_{arm}"
    sim_dir = Path(storage) / sim
    run_dir = Path(run_root) / sim if run_root else ROOT / "devmem" / "storage" / sim
    m1 = _meta(sim_dir)
    if not m1 or int(m1["step"]) < target_step:
        return None
    step = int(m1["step"])
    d = Path(dest) / arm
    tmp = Path(str(d) + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    (tmp / "sim").mkdir(parents=True)
    shutil.copytree(sim_dir / "personas", tmp / "sim" / "personas")
    shutil.copytree(sim_dir / "reverie", tmp / "sim" / "reverie")
    env = sim_dir / "environment" / f"{step}.json"
    if env.exists():
        (tmp / "sim" / "environment").mkdir()
        shutil.copy(env, tmp / "sim" / "environment" / env.name)
    clock = _clock(m1)
    trimmed: Dict[str, int] = {}
    mdb = run_dir / "memory.db"
    if mdb.exists():
        src = sqlite3.connect(f"file:{mdb.resolve().as_posix()}?mode=ro", uri=True)
        dst = sqlite3.connect(str(tmp / "memory.db"))
        try:
            src.backup(dst)
        finally:
            src.close()
        for table, col in TRIM.items():
            try:
                cur = dst.execute(f"DELETE FROM {table} WHERE {col} > ?", (clock,))
                trimmed[table] = cur.rowcount
            except sqlite3.OperationalError:
                pass
        dst.commit()
        dst.execute("VACUUM")
        dst.close()
    m2 = _meta(sim_dir)
    if not m2 or int(m2["step"]) != step:           # an autosave happened while copying: the copy may mix two saves
        shutil.rmtree(tmp, ignore_errors=True)
        return None
    rec = {"label": label, "arm": arm, "step": step, "sim_clock": clock, "target_step": target_step, "exact_first_autosave": step == target_step,
           "made_at": time.strftime("%Y-%m-%d %H:%M:%S"), "source": "external copy of the saved simulation folder and a trimmed SQLite backup (run untouched)",
           "rows_trimmed_from_the_copy_because_they_are_later_than_the_autosave_clock": trimmed}
    (tmp / "checkpoint.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
    shutil.rmtree(d, ignore_errors=True)
    tmp.rename(d)
    return rec


def wait_and_copy(arm: str, target_step: int, label: str, dest: Path, poll: float = 1.0, timeout: Optional[float] = None, **kw) -> Dict[str, Any]:
    t0 = time.time()
    while True:
        rec = copy_once(arm, target_step, label, dest, **kw)
        if rec:
            return rec
        if timeout is not None and time.time() - t0 > timeout:
            raise TimeoutError(f"no autosave at or after step {target_step} within {timeout} s")
        time.sleep(poll)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True, choices=["baseline", "staged"])
    ap.add_argument("--target-step", type=int, required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--dest", required=True)
    ap.add_argument("--poll", type=float, default=1.0)
    a = ap.parse_args()
    rec = wait_and_copy(a.arm, a.target_step, a.label, Path(a.dest), poll=a.poll)
    from devmem.eval.phase9 import interim_day1
    mdb = Path(a.dest) / a.arm / "memory.db"
    rec["sweep_markers"] = interim_day1.sweep_markers(mdb) if (a.arm == "staged" and mdb.exists()) else {}
    (Path(a.dest) / a.arm / "checkpoint.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
    print(json.dumps(rec, indent=1))


if __name__ == "__main__":
    main()
