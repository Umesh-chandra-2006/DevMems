"""
Support pieces of the Phase 7 and 9 arm runner (offline-testable, no network):
  * make_checkpoint(): a COPY of the saved state at the end of an awake window (personas, reverie meta, the environment file of that step
    and a consistent copy of memory.db via SQLite's backup API). Evaluation (recall and probe interviews) runs on this copy, never on the
    live run. Only the files an evaluation needs are copied (not the thousands of per-step environment and movement files).
  * LedgerWindows: one record per simulated hour (and a step-0 record): router calls and tokens by purpose and by agent from the ONE
    ledger, the fraction of steps each agent spent asleep, the cumulative call counters and the injector summary.
  * write_status(): run_status.json, atomically replaced, so a viewer or the canary can read the run while it grows.
"""
import json
import os
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


def make_checkpoint(storage_dir: Path, sim: str, step: int, run_dir: Path, label: str, clock: str) -> Path:
    src = Path(storage_dir) / sim
    dst = Path(storage_dir) / f"{sim}__ckpt_{label}"
    shutil.rmtree(dst, ignore_errors=True)
    dst.mkdir(parents=True)
    shutil.copytree(src / "personas", dst / "personas")
    shutil.copytree(src / "reverie", dst / "reverie")
    (dst / "environment").mkdir()
    env = src / "environment" / f"{step}.json"
    if env.exists():
        shutil.copy(env, dst / "environment" / env.name)
    ck_db_dir = Path(run_dir) / "checkpoints" / label
    ck_db_dir.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(f"file:{(Path(run_dir) / 'memory.db').resolve().as_posix()}?mode=ro", uri=True)
    target = sqlite3.connect(str(ck_db_dir / "memory.db"))
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    (dst / "checkpoint.json").write_text(json.dumps({"label": label, "step": step, "sim_clock": clock, "sim": sim,
                                                      "memory_db": str(ck_db_dir / "memory.db"), "made_at": time.strftime("%Y-%m-%d %H:%M:%S")}),
                                         encoding="utf-8")
    return dst


def write_status(path: Path, status: Dict[str, Any]) -> None:
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(status, indent=1, default=str), encoding="utf-8")
    os.replace(tmp, path)


class LedgerWindows:
    def __init__(self, key_pool: Any, run_dir: Path, arm: str, personas: List[str]):
        self.kp, self.path, self.arm = key_pool, Path(run_dir) / "hourly_ledger.jsonl", arm
        self.rid = self._max_rowid()
        self.t0 = time.time()
        self.steps = 0
        self.sleep_steps = {n: 0 for n in personas}

    def _conn(self):
        return self.kp.get_db_connection()

    def _max_rowid(self) -> int:
        c = self._conn()
        try:
            return c.execute("SELECT COALESCE(MAX(rowid),0) FROM llm_call_log").fetchone()[0]
        finally:
            c.close()

    def _rows(self):
        c = self._conn()
        try:
            return c.execute("SELECT rowid AS r, purpose, agent_id, tokens_in, tokens_out, condition FROM llm_call_log WHERE rowid > ? ORDER BY rowid",
                             (self.rid,)).fetchall()
        finally:
            c.close()

    def observe_step(self, sleeping: Dict[str, bool]) -> None:
        self.steps += 1
        for n, s in sleeping.items():
            self.sleep_steps[n] = self.sleep_steps.get(n, 0) + (1 if s else 0)

    def record(self, label: str, sim_clock: str, step: int, counters: Dict[str, Any], extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        rows = [r for r in self._rows() if r["condition"] in (self.arm, None)]
        by_p: Dict[str, Dict[str, int]] = {}
        by_a: Dict[str, Dict[str, int]] = {}
        for r in rows:
            for key, d in ((r["purpose"], by_p), (r["agent_id"] or "none", by_a)):
                e = d.setdefault(key, {"calls": 0, "tokens_in": 0, "tokens_out": 0})
                e["calls"] += 1
                e["tokens_in"] += r["tokens_in"] or 0
                e["tokens_out"] += r["tokens_out"] or 0
        rec = {"label": label, "arm": self.arm, "sim_clock": sim_clock, "step": step, "wall_seconds": round(time.time() - self.t0, 1),
               "steps_in_window": self.steps,
               "sleeping_step_fraction": {n: (round(c / self.steps, 3) if self.steps else None) for n, c in self.sleep_steps.items()},
               "calls": len(rows), "tokens_in": sum(r["tokens_in"] or 0 for r in rows), "tokens_out": sum(r["tokens_out"] or 0 for r in rows),
               "by_purpose": by_p, "by_agent": by_a, **counters, **(extra or {})}
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        all_rows = self._rows()
        if all_rows:
            self.rid = all_rows[-1]["r"]
        self.steps = 0
        self.sleep_steps = {n: 0 for n in self.sleep_steps}
        return rec
