"""
Documented MANUAL repair of the stale "night 1" marker in the saved Step D state (follow-up A3). Works only on a COPY of a run database
that the caller names; the original is never touched. Dry run by default.

What it removes: `consolidation_sweeps` rows that are EMPTY sweeps written at or after the night boundary hour on the first simulated
day while the agent was in a sleep action that began before the boundary (the Step D 12:00 rows of Maria and Klaus, night 1). A row is
removable only if (a) night == 1, (b) its sweep_time hour is at or after the boundary hour, (c) status is done, (d) the run's
consolidation log shows entries_considered == 0 for that agent and sweep time, (e) no semantic_memory row and no consolidated episodic
flag exists for that agent. Anything else is left alone and reported. It also writes a one-line JSON record of what it did next to the copy.
Resume then behaves as if the noon tick had not happened (the in-memory per-night guard is not persisted).
Usage: python devmem/memory/p6_repair_night_marker.py --db <COPY of memory.db> --log <consolidation_log.jsonl> [--apply]
"""
import argparse
import json
import sqlite3
from pathlib import Path

BOUNDARY_HOUR = 12


def repair(db_path, log_path, apply=False):
    db_path = Path(db_path)
    log = [json.loads(l) for l in Path(log_path).read_text(encoding="utf-8").splitlines() if l.strip()]
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    report = {"db": str(db_path), "applied": apply, "removed": [], "kept": []}
    try:
        rows = conn.execute("SELECT * FROM consolidation_sweeps ORDER BY agent_id, night").fetchall()
        for r in rows:
            hour = int(r["sweep_time"][11:13])
            empty_in_log = any(l["agent"] == r["agent_id"] and l["sim_time"] == r["sweep_time"] and l["entries_considered"] == 0 for l in log)
            sem = conn.execute("SELECT COUNT(*) FROM semantic_memory WHERE agent_id = ?", (r["agent_id"],)).fetchone()[0]
            flagged = conn.execute("SELECT COUNT(*) FROM episodic_memory WHERE agent_id = ? AND consolidated = 1", (r["agent_id"],)).fetchone()[0]
            ok = r["night"] == 1 and hour >= BOUNDARY_HOUR and r["status"] == "done" and empty_in_log and sem == 0 and flagged == 0
            entry = {"agent": r["agent_id"], "night": r["night"], "sweep_time": r["sweep_time"]}
            (report["removed"] if ok else report["kept"]).append(entry)
        if apply:
            conn.execute("BEGIN")
            for e in report["removed"]:
                conn.execute("DELETE FROM consolidation_sweeps WHERE agent_id = ? AND night = ?", (e["agent"], e["night"]))
            conn.commit()
    finally:
        conn.close()
    if apply:
        (db_path.parent / (db_path.name + ".repair.json")).write_text(json.dumps(report), encoding="utf-8")
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    print(json.dumps(repair(a.db, a.log, a.apply), indent=1))
