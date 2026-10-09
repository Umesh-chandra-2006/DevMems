"""
Offline interim analysis for a checkpoint day (E1 to E3, unique calls with replays removed, sweep marker status per agent). NO interpretation, NO API call, NO write to a run.
Reads the read-only copies (devmem/storage/interim_day<N>/<arm>/ and, for days 2 and 3, the secondary 23:45 copies in interim_day<N>_secondary/<arm>/), the router ledger and the movement
timestamps. Every number is labelled "interim, day N, step S, sim clock C" taken from the copy's own checkpoint.json.

E1 raw      = router-ledger rows of the arm from the launch (15:57:47 IST on Oct 7) to the wall time the copy was made, by purpose.
E1 unique   = raw minus the calls of each REPLAY pass: after a restart the arm re-runs the simulated steps since its last autosave; the second pass of those steps is removed (the rows between
              the restart and the moment the arm rewrote its pre-kill last step; zero when that step file was not rewritten).
E2          = mean prompt tokens per importance-scoring call over the same rows.
E3          = consolidated fraction of the copy's episodic entries (staged); 0 by construction for the baseline (no Stage 3).

    python -m devmem.eval.phase9.interim_report --day 2
"""
import argparse
import calendar
import json
import os
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from devmem.eval.phase9 import interim_day1 as I

ROOT = Path(__file__).resolve().parent.parent.parent.parent
SIM = ROOT / "reverie" / "environment" / "frontend_server" / "storage"
LAUNCH_IST = "2026-10-07 15:57:47"
DB = ROOT / "devmem" / "router" / "usage_log.db"
# restarts after which a replay pass happened: (wall time of the restart, last simulated step the killed process had reached; from the rate sampler's last sample before the kill)
RESTARTS = {"baseline": [("2026-10-08 00:53:32", 3599), ("2026-10-08 16:14:25", 13306)],
            "staged": [("2026-10-08 00:54:01", 4012), ("2026-10-08 16:15:24", 19809), ("2026-10-08 19:34:36", 20826), ("2026-10-08 20:01:52", 20826)]}
# graceful key-change and timeout restarts at an autosave have no replay pass and are not listed


def _utc(ist: str) -> str:
    return (datetime.strptime(ist, "%Y-%m-%d %H:%M:%S") - timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d %H:%M:%S")


def _by(c, arm, a, b) -> Dict[str, int]:
    return dict(c.execute("SELECT purpose, COUNT(*) FROM llm_call_log WHERE condition=? AND created_at>=? AND created_at<=? GROUP BY purpose", (arm, a, b)).fetchall())


def e1_raw_unique(arm: str, until_ist: str) -> Dict[str, Any]:
    c = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    a, b = _utc(LAUNCH_IST), _utc(until_ist)
    raw = _by(c, arm, a, b)
    removed: Dict[str, int] = {}
    detail = []
    for restart_ist, prekill in RESTARTS[arm]:
        if restart_ist >= until_ist:
            continue
        f = SIM / f"p7_{arm}" / "movement" / f"{prekill}.json"
        mt = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S") if f.exists() else None
        r0 = _utc(restart_ist)
        if mt is None or mt < restart_ist:
            detail.append({"restart_ist": restart_ist, "prekill_step": prekill, "replayed_second_pass_calls": 0, "note": "the pre-kill last step was not rewritten: no replay pass"})
            continue
        dup = _by(c, arm, r0, min(_utc(mt), b))
        for k, v in dup.items():
            removed[k] = removed.get(k, 0) + v
        detail.append({"restart_ist": restart_ist, "prekill_step": prekill, "rewritten_until_ist": mt, "replayed_second_pass_calls": sum(dup.values())})
    c.close()
    uniq = {k: raw.get(k, 0) - removed.get(k, 0) for k in raw}
    return {"raw_by_purpose": raw, "raw_total": sum(raw.values()), "replay_pass_removed_by_purpose": removed, "removed_total": sum(removed.values()),
            "unique_by_purpose": uniq, "unique_total": sum(uniq.values()), "restarts_with_a_replay_pass": detail}


def e2_tokens(arm: str, until_ist: str) -> Dict[str, Any]:
    return I.e2_prompt_tokens(DB, arm, _utc(LAUNCH_IST), _utc(until_ist))


def analyse_copy(arm: str, cdir: Path) -> Optional[Dict[str, Any]]:
    cj = cdir / "checkpoint.json"
    if not cj.exists():
        sim_cj = cdir / "sim" / "checkpoint.json"
        cj = sim_cj if sim_cj.exists() else cj
    if not cj.exists():
        return None
    meta = json.loads(cj.read_text(encoding="utf-8"))
    mdb = cdir / "memory.db"
    markers = I.sweep_markers(mdb) if (arm == "staged" and mdb.exists()) else {}
    names = json.loads(((cdir / "sim" / "reverie" / "meta.json") if (cdir / "sim" / "reverie" / "meta.json").exists() else (cdir / "reverie" / "meta.json")).read_text(encoding="utf-8"))["persona_names"]
    nights_done = {n: sorted(m["night"] for m in markers.get(n, []) if m["status"] == "done") for n in names} if arm == "staged" else {}
    out = {"label": f"interim, step {meta['step']}, sim clock {meta['sim_clock']}", "checkpoint": {k: meta.get(k) for k in ("label", "step", "sim_clock", "made_at", "exact_first_autosave")},
           "E1": e1_raw_unique(arm, meta["made_at"]), "E2_prompt_tokens": e2_tokens(arm, meta["made_at"]),
           "E3_consolidated_fraction": I.e3_consolidated_fraction(mdb if arm == "staged" else None),
           "sweep_markers_done_nights_per_agent": nights_done}
    if arm == "staged" and mdb.exists():
        c = sqlite3.connect(f"file:{mdb.as_posix()}?mode=ro", uri=True)
        out["summaries_and_traits"] = {"semantic_summaries": c.execute("SELECT COUNT(*) FROM semantic_memory").fetchone()[0], "identity_traits": c.execute("SELECT COUNT(*) FROM identity_traits").fetchone()[0]}
        c.close()
    return out


def build(day: int) -> Dict[str, Any]:
    st = ROOT / "devmem" / "storage"
    roots = {"primary": st / f"interim_day{day}", "secondary_2345": st / f"interim_day{day}_secondary"}
    rep: Dict[str, Any] = {"day": day, "arms": {}, "built_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    for arm in ("baseline", "staged"):
        rep["arms"][arm] = {}
        for kind, r in roots.items():
            a = analyse_copy(arm, r / arm)
            rep["arms"][arm][kind] = a if a else {"status": "copy does not exist yet"}
    return rep


def markdown(rep: Dict[str, Any]) -> str:
    L = [f"# Interim analysis, day {rep['day']} (offline, no interpretation)", "",
         "Every number is interim and labelled with the copy's own step and sim clock. Single run per arm; this is not a result. Source: read-only checkpoint copies, the router ledger and the movement timestamps (`devmem/eval/phase9/interim_report.py`). E1 raw counts every router row of the arm up to the wall time the copy was made; E1 unique removes the second pass of each replayed stretch after a restart.", ""]
    for kind in ("primary", "secondary_2345"):
        L += [f"## {'Primary checkpoint' if kind == 'primary' else 'Secondary copy at the first autosave at or after 23:45 (sensitivity analysis)'}", ""]
        have = {arm: rep["arms"][arm][kind] for arm in ("baseline", "staged")}
        if not any("E1" in v for v in have.values()):
            L += ["Neither copy exists yet.", ""]
            continue
        L += ["| item | baseline | staged |", "|---|---|---|"]
        g = lambda arm, f, d="not available": (f(have[arm]) if "E1" in have[arm] else d)
        L.append("| checkpoint | " + " | ".join(g(a, lambda v: f"step {v['checkpoint']['step']}, sim {v['checkpoint']['sim_clock']}, made {v['checkpoint']['made_at']}, exact first autosave {v['checkpoint'].get('exact_first_autosave')}") for a in ("baseline", "staged")) + " |")
        purposes = sorted({p for a in ("baseline", "staged") if "E1" in have[a] for p in have[a]["E1"]["raw_by_purpose"]})
        for p in purposes:
            L.append(f"| E1 {p}: raw / unique | " + " | ".join(g(a, lambda v: f"{v['E1']['raw_by_purpose'].get(p, 0)} / {v['E1']['unique_by_purpose'].get(p, 0)}") for a in ("baseline", "staged")) + " |")
        L.append("| E1 total: raw / unique | " + " | ".join(g(a, lambda v: f"{v['E1']['raw_total']} / {v['E1']['unique_total']}") for a in ("baseline", "staged")) + " |")
        L.append("| E2 mean tokens in per importance-scoring call (calls) | " + " | ".join(g(a, lambda v: f"{v['E2_prompt_tokens']['mean_tokens_in']} ({v['E2_prompt_tokens']['calls']})") for a in ("baseline", "staged")) + " |")
        L.append("| E3 consolidated fraction | " + " | ".join(g(a, lambda v: f"{v['E3_consolidated_fraction']['fraction']} ({v['E3_consolidated_fraction']['consolidated']} of {v['E3_consolidated_fraction']['entries']})" if v['E3_consolidated_fraction']['entries'] else "0 by construction (no Stage 3)") for a in ("baseline", "staged")) + " |")
        L.append("| sweeps done per agent (nights) | not applicable | " + (", ".join(f"{n}: {v}" for n, v in have["staged"]["sweep_markers_done_nights_per_agent"].items()) if "E1" in have["staged"] else "not available") + " |")
        if "E1" in have["staged"]:
            L.append(f"| summaries and traits | not applicable | {have['staged']['summaries_and_traits']['semantic_summaries']} summaries, {have['staged']['summaries_and_traits']['identity_traits']} traits |")
        L += ["", "Replay passes removed from E1 unique: " + "; ".join(f"{a}: " + (", ".join(f"restart {d['restart_ist']} removed {d['replayed_second_pass_calls']} calls" for d in have[a]["E1"]["restarts_with_a_replay_pass"]) or "none") for a in ("baseline", "staged") if "E1" in have[a]), ""]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", type=int, required=True)
    ap.add_argument("--write-docs", action="store_true")
    a = ap.parse_args()
    rep = build(a.day)
    out = ROOT / "devmem" / "storage" / f"interim_day{a.day}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")
    md = markdown(rep)
    if a.write_docs:
        (ROOT / "docs" / f"phase9_interim_day{a.day}.md").write_text(md, encoding="utf-8")
        (ROOT / "docs" / f"phase9_interim_day{a.day}_report.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
