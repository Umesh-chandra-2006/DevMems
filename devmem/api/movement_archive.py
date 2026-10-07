"""
Movement data for the town replay (Phase 8 Stop 2). Standard library only; read-only.

A run's movement is what upstream already writes during a simulation: `movement/{step}.json` in the saved simulation folder, one file per
step with each persona's tile, pronunciatio emoji, description and chat lines. This module reads it from either place:
  * a SINGLE COMPRESSED ARCHIVE `movement.zip` placed in the run's folder (what a recording ships with), made by `export()` from a
    simulation folder (CLI: python -m devmem.api.movement_archive export <sim folder> <out.zip>);
  * or, for a run that is still executing, directly from the simulation folder `reverie/environment/frontend_server/storage/<run>/`
    (so the viewer can replay the part already recorded while the run grows).
Archive layout: `meta.json` (start time of step 0, seconds per step, persona names, step range, source), `frames.jsonl` (one line per step:
{"s": step, "p": {name: [x, y, pronunciatio, description, chat]}}) and `thoughts.json` (the thought nodes of the saved persona memory:
{name: [{"created", "description", "kind"}]}). Nothing is invented: a step without a file is simply absent.
"""
import io
import json
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent.parent
SIM_STORAGE = ROOT / "reverie" / "environment" / "frontend_server" / "storage"
_CACHE: Dict[str, Any] = {}


def _parse_clock(s: str) -> datetime:
    return datetime.strptime(s, "%B %d, %Y, %H:%M:%S")


def _frame_line(step: int, data: Dict[str, Any]) -> Dict[str, Any]:
    p = {}
    for name, v in data.get("persona", {}).items():
        mv = v.get("movement") or [None, None]
        p[name] = [mv[0], mv[1], v.get("pronunciatio"), v.get("description"), v.get("chat")]
    return {"s": step, "p": p}


def _thoughts_from_sim(sim: Path) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    for pdir in sorted((sim / "personas").glob("*")):
        f = pdir / "bootstrap_memory" / "associative_memory" / "nodes.json"
        if not f.is_file():
            continue
        nodes = json.loads(f.read_text(encoding="utf-8"))
        out[pdir.name] = sorted(
            ({"created": n["created"], "description": n["description"], "kind": n.get("type")} for n in nodes.values()
             if n.get("type") in ("thought",)), key=lambda x: x["created"])
    return out


def export(sim_folder: Path, out_zip: Path) -> Dict[str, Any]:
    sim = Path(sim_folder)
    meta_src = json.loads((sim / "reverie" / "meta.json").read_text(encoding="utf-8"))
    files = sorted((sim / "movement").glob("*.json"), key=lambda p: int(p.stem))
    if not files:
        raise ValueError(f"no movement files in {sim}")
    curr = _parse_clock(meta_src["curr_time"])
    from datetime import timedelta
    start = curr - timedelta(seconds=int(meta_src["sec_per_step"]) * int(meta_src["step"]))
    steps = [int(p.stem) for p in files]
    meta = {"label": "movement archive exported from a saved simulation folder", "start_time": start.strftime("%Y-%m-%d %H:%M:%S"),
            "sec_per_step": int(meta_src["sec_per_step"]), "persona_names": meta_src["persona_names"], "maze_name": meta_src.get("maze_name", "the_ville"),
            "first_step": steps[0], "last_step": steps[-1], "frames": len(steps), "saved_step": meta_src["step"],
            "saved_clock": meta_src["curr_time"], "source_sim_code": sim.name,
            "missing_steps": sorted(set(range(steps[0], steps[-1] + 1)) - set(steps))[:50]}
    out_zip = Path(out_zip)
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr("meta.json", json.dumps(meta, indent=1))
        lines = (json.dumps(_frame_line(int(p.stem), json.loads(p.read_text(encoding="utf-8"))), separators=(",", ":")) for p in files)
        z.writestr("frames.jsonl", "\n".join(lines) + "\n")
        z.writestr("thoughts.json", json.dumps(_thoughts_from_sim(sim), separators=(",", ":")))
    return meta


class MovementSource:
    """Read access to one run's movement, from movement.zip or a live simulation folder."""

    def __init__(self, kind: str, path: Path, meta: Dict[str, Any], frames: Optional[Dict[int, Any]] = None, thoughts: Optional[Dict[str, Any]] = None):
        self.kind, self.path, self.meta, self._frames, self._thoughts = kind, path, meta, frames, thoughts

    # ---- construction
    @staticmethod
    def open(run_dir: Path, run_id: str) -> Optional["MovementSource"]:
        run_dir = Path(run_dir)
        z = run_dir / "movement.zip"
        key = f"{z.resolve()}:{z.stat().st_mtime_ns}" if z.is_file() else None
        if z.is_file():
            if key in _CACHE:
                return _CACHE[key]
            with zipfile.ZipFile(z) as zf:
                meta = json.loads(zf.read("meta.json"))
                frames = {}
                for line in io.TextIOWrapper(zf.open("frames.jsonl"), encoding="utf-8"):
                    if line.strip():
                        d = json.loads(line)
                        frames[d["s"]] = d["p"]
                thoughts = json.loads(zf.read("thoughts.json")) if "thoughts.json" in zf.namelist() else {}
            src = MovementSource("zip", z, meta, frames, thoughts)
            _CACHE.clear()
            _CACHE[key] = src
            return src
        sim = SIM_STORAGE / run_id
        if (sim / "movement").is_dir() and (sim / "reverie" / "meta.json").is_file():
            return MovementSource("folder", sim, {})
        return None

    # ---- folder mode reads meta and frames lazily so a growing run can be replayed
    def _folder_meta(self) -> Dict[str, Any]:
        sim = self.path
        m = json.loads((sim / "reverie" / "meta.json").read_text(encoding="utf-8"))
        from datetime import timedelta
        start = _parse_clock(m["curr_time"]) - timedelta(seconds=int(m["sec_per_step"]) * int(m["step"]))
        steps = [int(p.stem) for p in (sim / "movement").glob("*.json") if p.stem.isdigit()]
        return {"label": "live simulation folder (read while it may still be growing)", "start_time": start.strftime("%Y-%m-%d %H:%M:%S"),
                "sec_per_step": int(m["sec_per_step"]), "persona_names": m["persona_names"], "maze_name": m.get("maze_name", "the_ville"),
                "first_step": min(steps) if steps else None, "last_step": max(steps) if steps else None, "frames": len(steps),
                "saved_step": m["step"], "saved_clock": m["curr_time"], "source_sim_code": sim.name, "missing_steps": []}

    def describe(self) -> Dict[str, Any]:
        meta = dict(self.meta) if self.kind == "zip" else self._folder_meta()
        meta["source"] = self.kind
        if meta.get("first_step") is not None:
            from datetime import timedelta
            start = datetime.strptime(meta["start_time"], "%Y-%m-%d %H:%M:%S")
            meta["t_min"] = (start + timedelta(seconds=meta["sec_per_step"] * meta["first_step"])).strftime("%Y-%m-%d %H:%M:%S")
            meta["t_max"] = (start + timedelta(seconds=meta["sec_per_step"] * meta["last_step"])).strftime("%Y-%m-%d %H:%M:%S")
        return meta

    def frames(self, from_step: int, to_step: int, stride: int = 1, limit: int = 3000) -> Dict[str, Any]:
        stride = max(1, int(stride))
        out = []
        for s in range(from_step, to_step + 1, stride):
            if len(out) >= limit:
                break
            if self.kind == "zip":
                p = self._frames.get(s)
            else:
                f = self.path / "movement" / f"{s}.json"
                p = _frame_line(s, json.loads(f.read_text(encoding="utf-8")))["p"] if f.is_file() else None
            if p is not None:
                out.append({"s": s, "p": p})
        return {"from_step": from_step, "to_step": to_step, "stride": stride, "frames": out, "truncated": len(out) >= limit}

    def thoughts(self, agent: str, t: Optional[str]) -> Dict[str, Any]:
        if self.kind == "zip":
            all_t = (self._thoughts or {}).get(agent, [])
            src = "thoughts.json in movement.zip (thought nodes of the saved memory)"
        else:
            all_t = _thoughts_from_sim(self.path).get(agent, [])
            src = "nodes.json of the live simulation folder (as of its last autosave)"
        cut = (t or "9999-12-31 23:59:59").replace("T", " ")
        shown = [x for x in all_t if x["created"] <= cut]
        return {"agent": agent, "source": src, "total_in_record": len(all_t), "up_to_t": len(shown), "thoughts": shown[-8:]}


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "export":
        print(json.dumps(export(Path(sys.argv[2]), Path(sys.argv[3])), indent=1))
    else:
        print("usage: python -m devmem.api.movement_archive export <simulation folder> <out.zip>")


class MovementExporter:
    """Incremental, atomic `movement.zip` writer for a run that is still executing (the viewer reads the zip while the run grows).
    `export()` reads only the movement files written since the last call, keeps the frame lines in memory, rewrites the whole zip to a temporary
    file and replaces the real one in a single step (so a reader never sees a partial archive). Called by the arm runner at every autosave and
    at the end of the run."""

    def __init__(self, sim_folder: Path, out_zip: Path):
        self.sim, self.out = Path(sim_folder), Path(out_zip)
        self.lines: List[str] = []
        self.next_step = 0

    def export(self) -> Dict[str, Any]:
        movement = self.sim / "movement"
        last = max([int(p.stem) for p in movement.glob("*.json") if p.stem.isdigit()] or [-1])
        for s in range(self.next_step, last + 1):
            f = movement / f"{s}.json"
            if f.is_file():
                self.lines.append(json.dumps(_frame_line(s, json.loads(f.read_text(encoding="utf-8"))), separators=(",", ":")))
        self.next_step = max(self.next_step, last + 1)
        meta_src = json.loads((self.sim / "reverie" / "meta.json").read_text(encoding="utf-8"))
        from datetime import timedelta
        start = _parse_clock(meta_src["curr_time"]) - timedelta(seconds=int(meta_src["sec_per_step"]) * int(meta_src["step"]))
        steps = [json.loads(l)["s"] for l in (self.lines[:1] + self.lines[-1:])]
        meta = {"label": "movement archive written incrementally by the arm runner", "start_time": start.strftime("%Y-%m-%d %H:%M:%S"),
                "sec_per_step": int(meta_src["sec_per_step"]), "persona_names": meta_src["persona_names"], "maze_name": meta_src.get("maze_name", "the_ville"),
                "first_step": steps[0] if steps else None, "last_step": steps[-1] if steps else None, "frames": len(self.lines),
                "saved_step": meta_src["step"], "saved_clock": meta_src["curr_time"], "source_sim_code": self.sim.name, "missing_steps": []}
        self.out.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(str(self.out) + ".tmp")
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            z.writestr("meta.json", json.dumps(meta, indent=1))
            z.writestr("frames.jsonl", "\n".join(self.lines) + "\n")
            z.writestr("thoughts.json", json.dumps(_thoughts_from_sim(self.sim), separators=(",", ":")))
        import os
        os.replace(tmp, self.out)
        return meta
