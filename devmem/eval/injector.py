"""
Event injection for Phase 7 (no upstream edit; the same code path as a natural event, identical in both arms).

A natural event is a tile event (subject, predicate, object, description) in `maze.tiles[y][x]["events"]`; upstream `perceive` reads the
events on the tiles within the persona's vision and arena, orders them by distance, keeps `att_bandwidth` of them, skips triples that
are among the last `retention` events, stores the text f"{subject} is {description}", embeds it and scores it (baseline: the upstream
poignancy prompt; staged: the persona-conditioned scorer).

`EventInjector.tick(rs)` runs at a step boundary BEFORE the step: it removes events whose time is up, resolves the previous injections
(was the text stored in the agent's memory?), and adds each due event to the persona's OWN current tile with upstream's
`maze.add_event_from_tile`. The tile at distance 0 sorts first, so the event is always inside the perceived bandwidth. The event
stays `remove_after_steps` steps (default 6, one simulated minute) and is removed with `maze.remove_event_from_tile`. Every event gets one
log line (injection_log.jsonl): planned time, injected clock and step, tile, whether the agent was asleep, and PASS or FAIL for
"perceived and stored", with the node id and the importance score the arm gave it. Resume: events already logged as injected are skipped.
"""
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional


class EventInjector:
    def __init__(self, events: List[Dict[str, Any]], start: datetime, log_path: Path, arm: str, remove_after_steps: int = 6):
        self.events = sorted(events, key=lambda e: (e["day"], e["time"], e["id"]))
        self.start, self.arm, self.remove_after = start, arm, remove_after_steps
        self.log_path = Path(log_path)
        self.pending: List[Dict[str, Any]] = []   # injected, waiting to be verified and removed
        self.done_ids = set()
        if self.log_path.exists():
            for line in self.log_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    self.done_ids.add(json.loads(line)["id"])
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def planned(self, e: Dict[str, Any]) -> datetime:
        hh, mm = map(int, e["time"].split(":"))
        return self.start.replace(hour=0, minute=0, second=0) + timedelta(days=e["day"] - 1, hours=hh, minutes=mm)

    @staticmethod
    def tuple_of(e: Dict[str, Any]):
        return (e["subject"], "is", f"{e['id'].lower()} event", e["desc"])

    def _write(self, rec: Dict[str, Any]) -> None:
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")

    def _resolve(self, rs, p: Dict[str, Any], final: bool) -> bool:
        persona = rs.personas[p["event"]["agent"]]
        text = p["event"]["rendered_memory_text"]
        node = next((n for n in persona.a_mem.id_to_node.values() if n.description == text and n.created >= p["clock"]), None)
        if node is None and not final:
            return False
        rec = {"id": p["event"]["id"], "agent": p["event"]["agent"], "arm": self.arm, "type": p["event"]["type"],
               "planned": self.planned(p["event"]).strftime("%Y-%m-%d %H:%M:%S"), "injected_clock": p["clock"].strftime("%Y-%m-%d %H:%M:%S"),
               "injected_step": p["step"], "tile": list(p["tile"]), "agent_asleep_at_injection": p["asleep"],
               "result": "PASS" if node is not None else "FAIL", "perceived_and_stored": node is not None,
               "node_id": node.node_id if node is not None else None, "importance": node.poignancy if node is not None else None,
               "stored_text": text}
        self._write(rec)
        self.done_ids.add(p["event"]["id"])
        return True

    def tick(self, rs) -> List[Dict[str, Any]]:
        """Call at a step boundary before the step. Returns the log records written by this call."""
        before = self._count()
        now = rs.curr_time
        keep = []
        for p in self.pending:
            if rs.step >= p["step"] + self.remove_after:
                self._resolve(rs, p, final=True)   # the event is about to be removed: this is the verdict
                rs.maze.remove_event_from_tile(p["tuple"], p["tile"])
            else:
                if not self._resolve(rs, p, final=False):
                    keep.append(p)
                else:
                    rs.maze.remove_event_from_tile(p["tuple"], p["tile"])
        self.pending = keep
        for e in self.events:
            if e["id"] in self.done_ids or any(p["event"]["id"] == e["id"] for p in self.pending):
                continue
            if self.planned(e) <= now:
                persona = rs.personas[e["agent"]]
                tile = tuple(rs.personas_tile[e["agent"]])
                tup = self.tuple_of(e)
                rs.maze.add_event_from_tile(tup, tile)
                asleep = "sleep" in str(persona.scratch.act_description or "").lower()
                self.pending.append({"event": e, "tuple": tup, "tile": tile, "clock": now, "step": rs.step, "asleep": asleep})
        return self._tail(before)

    def _count(self) -> int:
        return sum(1 for _ in self.log_path.read_text(encoding="utf-8").splitlines()) if self.log_path.exists() else 0

    def _tail(self, before: int) -> List[Dict[str, Any]]:
        lines = self.log_path.read_text(encoding="utf-8").splitlines() if self.log_path.exists() else []
        return [json.loads(l) for l in lines[before:]]

    def summary(self) -> Dict[str, Any]:
        recs = [json.loads(l) for l in self.log_path.read_text(encoding="utf-8").splitlines() if l.strip()] if self.log_path.exists() else []
        return {"events_total": len(self.events), "resolved": len(recs), "pass": sum(1 for r in recs if r["result"] == "PASS"),
                "fail": [r["id"] for r in recs if r["result"] == "FAIL"], "pending": [p["event"]["id"] for p in self.pending],
                "asleep_at_injection": [r["id"] for r in recs if r["agent_asleep_at_injection"]]}
