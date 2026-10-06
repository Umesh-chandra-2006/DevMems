"""
Live headless run with hard caps (Phase 5 tasks E and F).

  python devmem/run_live_smoke.py --sim-code S --mode staged|baseline --steps N --llm-cap L --embed-cap E
                                  [--start-time "February 13, 2023, 09:00:00"] [--out-dir DIR]

* pinned model openai/gpt-oss-20b (DEVMEM_PINNED_MODEL), fail_loud_llm on (HeadlessRunner), agent tagging on;
* LLM calls are counted at the gpt_structure boundary (one count per call_llm invocation) and embedding requests at
  the EmbeddingStore HTTP layer; reaching either cap raises CapReached (a BaseException, so upstream's
  `except Exception` retry loops cannot swallow it) and the run stops;
* writes a JSON report (counts per purpose and agent from the router ledger, ROUTER_FAILURES, schedule check,
  sweep markers, embedding stats) to --out-dir.
"""
import argparse
import json
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PINNED = "openai/gpt-oss-20b"


class CapReached(BaseException):
    pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim-code", required=True)
    ap.add_argument("--fork", default="base_the_ville_isabella_maria_klaus")
    ap.add_argument("--mode", choices=["staged", "baseline"], required=True)
    ap.add_argument("--steps", type=int, required=True)
    ap.add_argument("--llm-cap", type=int, required=True)
    ap.add_argument("--embed-cap", type=int, required=True)
    ap.add_argument("--start-time", default=None, help='e.g. "February 13, 2023, 09:00:00" (written into a fork copy)')
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    os.environ["DEVMEM_PINNED_MODEL"] = PINNED
    os.environ["DEVMEM_EMBEDDING_MODE"] = "live"
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")

    from devmem.run_headless import HeadlessRunner
    import utils
    import persona.prompt_template.gpt_structure as gs
    from devmem.embeddings.vector_store import EmbeddingStore
    from devmem.memory.episodic import get_db_path
    from devmem.router import key_pool

    storage = Path(utils.fs_storage)
    fork = args.fork
    if args.start_time:
        fork = f"{args.fork}__start_{args.sim_code}"
        shutil.rmtree(storage / fork, ignore_errors=True)
        shutil.copytree(storage / args.fork, storage / fork)
        meta_f = storage / fork / "reverie" / "meta.json"
        meta = json.loads(meta_f.read_text())
        meta["curr_time"] = args.start_time
        meta_f.write_text(json.dumps(meta, indent=2))
    shutil.rmtree(storage / args.sim_code, ignore_errors=True)
    shutil.rmtree(ROOT / "devmem" / "storage" / args.sim_code, ignore_errors=True)

    # counters (the ledger is also read afterwards; these enforce the caps live)
    counts = {"llm_calls": 0, "embed_requests": 0}
    real_call_llm = gs.call_llm

    def counted_call_llm(*a, **k):
        if counts["llm_calls"] >= args.llm_cap:
            raise CapReached(f"LLM call cap {args.llm_cap} reached")
        counts["llm_calls"] += 1
        return real_call_llm(*a, **k)
    gs.call_llm = counted_call_llm

    import requests
    os.environ["SIM_CODE"] = args.sim_code

    def counted_post(*a, **k):
        if counts["embed_requests"] >= args.embed_cap:
            raise CapReached(f"embedding request cap {args.embed_cap} reached")
        counts["embed_requests"] += 1
        return requests.post(*a, **k)
    store = EmbeddingStore(post=counted_post, stats_path=get_db_path(args.sim_code).parent / "embedding_stats.json")
    gs._EMBEDDING_STORE = store

    conn = key_pool.get_db_connection()
    ledger_start = conn.execute("SELECT COUNT(*) FROM llm_call_log").fetchone()[0]
    conn.close()

    runner = HeadlessRunner(fork, args.sim_code, memory_mode=args.mode, final_sweep=False)
    report = {"sim_code": args.sim_code, "mode": args.mode, "pinned_model": PINNED, "fork": fork,
              "start_clock": str(runner.rs.curr_time), "steps_requested": args.steps,
              "caps": {"llm_calls": args.llm_cap, "embedding_requests": args.embed_cap}, "label": "live"}
    t0 = time.time()
    stopped = "completed"
    steps_done = 0
    original_advance = runner._advance

    def advance_and_report():
        nonlocal steps_done
        original_advance()
        steps_done += 1
        print(f"step {runner.rs.step} clock {runner.rs.curr_time} llm {counts['llm_calls']} embed {counts['embed_requests']}", flush=True)
    runner._advance = advance_and_report
    try:
        runner.run(args.steps)  # autosave at the interval, plus a save on clean exit
    except CapReached as e:
        stopped = f"cap: {e}"
    except Exception as e:
        stopped = f"exception: {type(e).__name__}: {str(e)[:200]}"
    report.update({"stopped": stopped, "steps_completed": steps_done, "final_step": runner.rs.step,
                   "final_clock": str(runner.rs.curr_time), "seconds": round(time.time() - t0, 1),
                   "counted": counts, "router_failures": gs.ROUTER_FAILURES})
    try:
        runner._save()
        report["final_save"] = "ok"
    except BaseException as e:  # a mid-step stop can leave state that cannot be saved
        report["final_save"] = f"failed: {type(e).__name__}: {str(e)[:160]}"
    runner.schedule_findings = runner.schedule_findings  # populated by _save()

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    conn = key_pool.get_db_connection()
    rows = conn.execute("SELECT purpose, condition, model, agent_id, tokens_in, tokens_out FROM llm_call_log "
                        "ORDER BY rowid LIMIT -1 OFFSET ?", (ledger_start,)).fetchall()
    conn.close()
    by_purpose, by_agent = {}, {}
    for r in rows:
        for key, d in ((r["purpose"], by_purpose), (r["agent_id"] or "none", by_agent)):
            e = d.setdefault(key, {"calls": 0, "tokens_in": 0, "tokens_out": 0})
            e["calls"] += 1
            e["tokens_in"] += r["tokens_in"] or 0
            e["tokens_out"] += r["tokens_out"] or 0
    report["ledger"] = {"rows": len(rows), "by_purpose": by_purpose, "by_agent": by_agent,
                        "models": sorted({r["model"] for r in rows}), "conditions": sorted({r["condition"] for r in rows})}
    run_dir = get_db_path(args.sim_code).parent
    report["embedding_stats"] = store.stats
    sweeps = []
    if (run_dir / "memory.db").exists():
        c = sqlite3.connect(str(run_dir / "memory.db"))
        c.row_factory = sqlite3.Row
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "consolidation_sweeps" in tables:
            sweeps = [dict(r) for r in c.execute("SELECT * FROM consolidation_sweeps")]
        report["episodic_rows_by_agent"] = {r[0]: r[1] for r in c.execute(
            "SELECT agent_id, COUNT(*) FROM episodic_memory GROUP BY agent_id")}
        c.close()
    report["consolidation_sweeps_rows"] = sweeps
    report["schedule_check_findings"] = runner.schedule_findings
    for name in ("schedule_check.json", "consolidation_log.jsonl", "embedding_stats.json"):
        if (run_dir / name).exists():
            shutil.copy(run_dir / name, out / f"{args.sim_code}_{name}")
    (out / f"{args.sim_code}_report.json").write_text(json.dumps(report, indent=1, default=str))
    print(json.dumps({k: report[k] for k in ("stopped", "steps_completed", "final_clock", "counted", "router_failures",
                                              "consolidation_sweeps_rows")}, indent=1, default=str))


if __name__ == "__main__":
    main()
