"""
Day-1 interim analysis (declared in the pre-registration, section 5b): E1 to E3, R5 and the Stage 2 scoring controls on the replay sample; NOTHING else (no Stage 4 count
claims, no coherence). Everything here is labelled INTERIM with the run's clock and step. It reads a COPY of each arm's day-1 checkpoint (`copy_checkpoint`), never the live run.

Offline parts (no call): E1 calls per purpose up to the checkpoint clock from the hourly ledger; E2 mean prompt tokens per importance-scoring call from the router ledger;
E3 consolidated fraction of episodic entries in the checkpoint database (the baseline has no Stage 3, so its fraction is 0 by construction); the event stream and the
replay sample (sample_plan). Live parts, to run after the arms end (they must not take quota from the arms): R5-interim = the nine day-1 injected-event questions (3 per
agent) asked on the day-1 checkpoint copy through the answer harness (distance 0), and the replay controls on the sample (replay.py).

    python -m devmem.eval.phase9.interim_day1 --copy       copy both checkpoints to devmem/storage/interim_day1/
    python -m devmem.eval.phase9.interim_day1 --report     offline report to devmem/storage/interim_day1/report.json
"""
import argparse
import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent.parent.parent
SIM = ROOT / "reverie" / "environment" / "frontend_server" / "storage"
OUT = ROOT / "devmem" / "storage" / "interim_day1"


def copy_checkpoint(arm: str, label: str = "day1_end_awake", sim_prefix: str = "p7", dest: Path = OUT) -> Dict[str, Any]:
    """A read-only copy for analysis; the original checkpoint and the live run are not touched."""
    sim = f"{sim_prefix}_{arm}"
    src_sim = SIM / f"{sim}__ckpt_{label}"
    src_db = ROOT / "devmem" / "storage" / sim / "checkpoints" / label / "memory.db"
    if not src_sim.exists():
        return {"arm": arm, "copied": False, "reason": "checkpoint folder does not exist yet"}
    d = Path(dest) / arm
    shutil.rmtree(d, ignore_errors=True)
    shutil.copytree(src_sim, d / "sim")
    if src_db.exists():
        shutil.copy(src_db, d / "memory.db")
    meta = json.loads((src_sim / "checkpoint.json").read_text(encoding="utf-8"))
    return {"arm": arm, "copied": True, "to": str(d), "step": meta.get("step"), "sim_clock": meta.get("sim_clock"), "made_at": meta.get("made_at")}


def sweep_markers(memory_db: Path) -> Dict[str, Any]:
    """Per agent: the Stage 3 sweep markers (night, status) in the checkpoint database, to say whether the night-1 sweep was done when the copy was taken."""
    c = sqlite3.connect(f"file:{Path(memory_db).as_posix()}?mode=ro", uri=True)
    try:
        rows = c.execute("SELECT agent_id, night, status FROM consolidation_sweeps ORDER BY agent_id, night").fetchall()
    except sqlite3.OperationalError:
        rows = []
    c.close()
    out: Dict[str, List[Dict[str, Any]]] = {}
    for a, n, s in rows:
        out.setdefault(a, []).append({"night": n, "status": s})
    return out


def e1_calls(run_dir: Path, until_clock: str) -> Dict[str, Any]:
    tot: Dict[str, int] = {}
    n = 0
    for line in (Path(run_dir) / "hourly_ledger.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r["sim_clock"] <= until_clock:
            n += 1
            for k, v in r["by_purpose"].items():
                tot[k] = tot.get(k, 0) + v["calls"]
    return {"windows": n, "by_purpose": tot, "total": sum(tot.values()),
            "caveat": "windows include replayed stretches after restarts, so the totals count replayed calls twice; evaluation calls are not in this ledger"}


def e2_prompt_tokens(ledger_db: Path, condition: str, since: str, until: str, purpose: str = "importance_scoring") -> Dict[str, Any]:
    c = sqlite3.connect(f"file:{Path(ledger_db).as_posix()}?mode=ro", uri=True)
    n, tin = c.execute("SELECT COUNT(*), COALESCE(SUM(tokens_in),0) FROM llm_call_log WHERE condition=? AND purpose=? AND created_at>=? AND created_at<=?",
                       (condition, purpose, since, until)).fetchone()
    c.close()
    return {"condition": condition, "purpose": purpose, "calls": n, "mean_tokens_in": round(tin / n, 1) if n else None, "window_utc": [since, until]}


def e3_consolidated_fraction(memory_db: Optional[Path]) -> Dict[str, Any]:
    if memory_db is None or not Path(memory_db).exists():
        return {"entries": 0, "consolidated": 0, "fraction": 0.0, "note": "no memory database: the baseline has no Stage 3, so the fraction is 0 by construction"}
    c = sqlite3.connect(f"file:{Path(memory_db).as_posix()}?mode=ro", uri=True)
    n, k = c.execute("SELECT COUNT(*), COALESCE(SUM(consolidated),0) FROM episodic_memory").fetchone()
    c.close()
    return {"entries": n, "consolidated": k, "fraction": round(k / n, 4) if n else 0.0}


def event_stream(memory_db: Path, injected_texts: List[str], until: str) -> Tuple[List[Tuple[str, str, str]], List[Tuple[str, str, str]]]:
    """(natural, injected) scoring events of the staged arm up to the checkpoint clock, from its mirror: (agent, sim time, text)."""
    c = sqlite3.connect(f"file:{Path(memory_db).as_posix()}?mode=ro", uri=True)
    rows = c.execute("SELECT agent_id, sim_timestamp, content FROM episodic_memory WHERE sim_timestamp <= ? ORDER BY sim_timestamp", (until,)).fetchall()
    c.close()
    inj = set(injected_texts)
    nat = [(a, t, x) for a, t, x in rows if x not in inj and "idle" not in x.lower()]
    ij = [(a, t, x) for a, t, x in rows if x in inj]
    return nat, ij


def day1_questions() -> List[Dict[str, Any]]:
    qs = json.loads((ROOT / "docs" / "phase7_stop1_events_questions.json").read_text(encoding="utf-8"))["questions"]
    return [q for q in qs if q.get("type") == "injected" and q.get("event_day") == 1]


def _utc(local_ist: str) -> str:
    from datetime import datetime, timedelta
    return (datetime.strptime(local_ist, "%Y-%m-%d %H:%M:%S") - timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d %H:%M:%S")


def report(until_clock: str, since: str, ledger_db: Path, copy_root: Path = OUT, root: Path = ROOT, sim_prefix: str = "p7") -> Dict[str, Any]:
    """Offline day-1 interim numbers from the READ-ONLY COPIES in copy_root (E3 and the sweep markers) and from the hourly ledger and the router ledger (E1, E2).
    Every number is interim, day 1, step 5,130, sim 14:15; the router-ledger window of each arm ends when its checkpoint copy was made."""
    out: Dict[str, Any] = {"label": f"interim, day 1, step 5,130, sim {until_clock[11:16]}; offline parts only; single run per arm; not a result", "arms": {}}
    for arm in ("baseline", "staged"):
        run_dir = root / "devmem" / "storage" / f"{sim_prefix}_{arm}"
        cdir = Path(copy_root) / arm
        meta = json.loads((cdir / "sim" / "checkpoint.json").read_text(encoding="utf-8"))
        ck_db = cdir / "memory.db"
        markers = sweep_markers(ck_db) if (arm == "staged" and ck_db.exists()) else {}
        names = json.loads((cdir / "sim" / "reverie" / "meta.json").read_text(encoding="utf-8"))["persona_names"]
        missing = [n for n in names if arm == "staged" and not any(m["night"] == 1 and m["status"] == "done" for m in markers.get(n, []))]
        out["arms"][arm] = {"checkpoint": {"step": meta["step"], "sim_clock": meta["sim_clock"], "made_at_ist": meta["made_at"]},
                            "E1_calls_up_to_checkpoint": e1_calls(run_dir, until_clock),
                            "E2_prompt_tokens": e2_prompt_tokens(ledger_db, arm, since, _utc(meta["made_at"])),
                            "E3_consolidated_fraction": e3_consolidated_fraction(ck_db if arm == "staged" else None),
                            "sweep_markers_in_checkpoint": markers, "agents_without_a_done_night1_marker": missing}
        if arm == "staged" and ck_db.exists():
            c = sqlite3.connect(f"file:{ck_db.as_posix()}?mode=ro", uri=True)
            out["arms"][arm]["summaries_and_traits_in_checkpoint"] = {"semantic_summaries": c.execute("SELECT COUNT(*) FROM semantic_memory").fetchone()[0],
                                                                       "identity_traits": c.execute("SELECT COUNT(*) FROM identity_traits").fetchone()[0]}
            c.close()
    out["R5_interim_questions"] = [q["id"] for q in day1_questions()]
    out["not_run_yet"] = ["R5-interim answers (live calls, after the arms end)", "Stage 2 replay controls on the fixed sample (live calls, after the arms end)"]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--copy", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--until-clock", default="2023-02-13 14:15:00")
    ap.add_argument("--since", default="2026-10-07 10:27:00", help="UTC; the launch of the full arms (15:57 IST)")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if a.copy:
        res = [copy_checkpoint(arm) for arm in ("baseline", "staged")]
        print(json.dumps(res, indent=1))
    if a.report:
        r = report(a.until_clock, a.since, ROOT / "devmem" / "router" / "usage_log.db")
        (OUT / "report.json").write_text(json.dumps(r, indent=1), encoding="utf-8")
        print(json.dumps(r, indent=1))


if __name__ == "__main__":
    main()
