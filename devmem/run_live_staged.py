"""
Live staged run in two phases (Phase 5, merged tasks E and F).

  phase soft:     fresh run from the fork at 00:00, runs ONE step (step 0, day-start planning for all 3 agents) and saves.
                  soft cap 250 LLM calls (hard cap = 1.5 x soft = 375: raises, no save).
  phase continue: resumes the SAME run from that save (HeadlessRunner(resume=True)) until the sim clock reaches --until
                  (default 10:00). hard cap 400 LLM calls / 150 embedding requests; soft caps = hard / 1.5, checked
                  at step boundaries only (graceful stop and clean save).

Common: staged mode, pinned openai/gpt-oss-20b, fail_loud_llm on, agent tagging on. Before starting, prints the
remaining Groq token budget per key (router ledger) and ABORTS if the projected need (soft LLM cap x mean tokens per call
measured in the earlier smoke run) exceeds it. At every simulated hour boundary the ledger deltas (calls and tokens by
purpose and agent) are appended to hourly_ledger.jsonl. A hard-cap stop never attempts a save (crash semantics).
The saved memory is copied to devmem/storage/calibration/<sim_code>_<phase>/ as the calibration dataset.
"""
import argparse
import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
PINNED = "openai/gpt-oss-20b"
ART = ROOT / "docs" / "phase5_step3_artifacts"


from devmem.router.call_counter import CapReached  # router-level; BaseException so upstream retry loops cannot swallow it


def ledger_rows_since(rowid):
    from devmem.router import key_pool
    conn = key_pool.get_db_connection()
    try:
        return conn.execute("SELECT rowid AS rid, purpose, agent_id, tokens_in, tokens_out FROM llm_call_log "
                            "WHERE rowid > ? ORDER BY rowid", (rowid,)).fetchall()
    finally:
        conn.close()


def max_rowid():
    from devmem.router import key_pool
    conn = key_pool.get_db_connection()
    try:
        return conn.execute("SELECT COALESCE(MAX(rowid), 0) FROM llm_call_log").fetchone()[0]
    finally:
        conn.close()


def summarize(rows):
    by_purpose, by_agent = {}, {}
    for r in rows:
        for key, d in ((r["purpose"], by_purpose), (r["agent_id"] or "none", by_agent)):
            e = d.setdefault(key, {"calls": 0, "tokens_in": 0, "tokens_out": 0})
            e["calls"] += 1
            e["tokens_in"] += r["tokens_in"] or 0
            e["tokens_out"] += r["tokens_out"] or 0
    return {"calls": len(rows), "tokens_in": sum(r["tokens_in"] or 0 for r in rows),
            "tokens_out": sum(r["tokens_out"] or 0 for r in rows), "by_purpose": by_purpose, "by_agent": by_agent}


def budget_table():
    import yaml
    from devmem.router import key_pool
    cfg = yaml.safe_load(open(ROOT / "devmem/config/providers.yaml", encoding="utf-8"))
    groq = next(p for p in cfg["providers"] if p["name"] == "groq")
    tpd = groq["tpd"]
    rows = {}
    for k in groq["keys"]:
        used = key_pool.get_token_usage("groq", k["env"], model=PINNED)
        rows[k["env"]] = {"used_today": used, "limit": tpd, "remaining": max(0, tpd - used)}
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["soft", "continue"], required=True)
    ap.add_argument("--sim-code", default="p5_staged_live")
    ap.add_argument("--fork", default="base_the_ville_isabella_maria_klaus")
    ap.add_argument("--soft-llm", type=int, default=250)
    ap.add_argument("--hard-llm", type=int, default=400)
    ap.add_argument("--hard-embed", type=int, default=150)
    ap.add_argument("--until", default="February 13, 2023, 10:00:00")
    ap.add_argument("--mean-tokens-per-call", type=float, default=2192.0,
                    help="measured in the earlier smoke run: 218,521 tokens over 100 calls")
    args = ap.parse_args()
    ART.mkdir(parents=True, exist_ok=True)

    if args.phase == "soft":
        soft_llm, hard_llm = args.soft_llm, int(args.soft_llm * 1.5)
        hard_embed = 60
        steps = 1
    else:
        hard_llm, hard_embed = args.hard_llm, args.hard_embed
        soft_llm = int(hard_llm / 1.5)
        steps = 10 ** 6
    soft_embed = int(hard_embed / 1.5)
    until = datetime.strptime(args.until, "%B %d, %Y, %H:%M:%S")

    os.environ["DEVMEM_PINNED_MODEL"] = PINNED
    os.environ["DEVMEM_EMBEDDING_MODE"] = "live"
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")

    # ---- token budget check (before anything else touches the network) -----------------------------
    table = budget_table()
    remaining = sum(v["remaining"] for v in table.values())
    projected = soft_llm * args.mean_tokens_per_call
    print("Groq gpt-oss-20b token budget today (router ledger):")
    for k, v in table.items():
        print(f"  {k}: used {v['used_today']:>7}  remaining {v['remaining']:>7}")
    print(f"  total remaining {remaining}; projected need for phase '{args.phase}' = soft cap {soft_llm} calls x "
          f"{args.mean_tokens_per_call:.0f} tokens = {projected:.0f}")
    budget_report = {"phase": args.phase, "per_key": table, "remaining_total": remaining, "projected_need": projected,
                     "soft_llm": soft_llm, "hard_llm": hard_llm}
    (ART / f"{args.sim_code}_{args.phase}_budget.json").write_text(json.dumps(budget_report, indent=1))
    if projected > remaining:
        print(f"ABORT: projected need {projected:.0f} exceeds remaining token budget {remaining}. Nothing was run.")
        sys.exit(2)

    from devmem.run_headless import HeadlessRunner
    import utils
    import persona.prompt_template.gpt_structure as gs
    from devmem.embeddings.vector_store import EmbeddingStore
    from devmem.memory.episodic import get_db_path
    import requests

    storage = Path(utils.fs_storage)
    resume = args.phase == "continue"
    if not resume:
        shutil.rmtree(storage / args.sim_code, ignore_errors=True)
        shutil.rmtree(ROOT / "devmem" / "storage" / args.sim_code, ignore_errors=True)
    os.environ["SIM_CODE"] = args.sim_code
    run_dir = get_db_path(args.sim_code).parent

    counts = {"llm_calls": 0, "embed_requests": 0}
    # LLM calls are counted by the ROUTER itself (every call_llm attempt, whatever the import path, including
    # episodic.py's scoring calls); the hard cap raises CapReached from inside call_llm.
    from devmem.router import call_counter
    call_counter.reset()
    call_counter.set_cap(hard_llm)

    def counted_post(*a, **k):
        if counts["embed_requests"] >= hard_embed:
            raise CapReached(f"hard embedding cap {hard_embed} reached")
        counts["embed_requests"] += 1
        return requests.post(*a, **k)
    store = EmbeddingStore(post=counted_post, stats_path=run_dir / "embedding_stats.json")
    gs._EMBEDDING_STORE = store

    runner = HeadlessRunner(args.fork, args.sim_code, memory_mode="staged", resume=resume, final_sweep=False)
    start_clock, start_step = runner.rs.curr_time, runner.rs.step
    hourly_f = run_dir / "hourly_ledger.jsonl"
    state = {"last_rowid": max_rowid(), "last_embed": 0, "last_hour": start_clock.replace(minute=0, second=0),
             "first_boundary_label": f"start {start_clock}"}

    def record(label, partial=False):
        rows = ledger_rows_since(state["last_rowid"])
        rec = {"label": label, "phase": args.phase, "sim_clock": str(runner.rs.curr_time), "step": runner.rs.step,
               "partial": partial, "embedding_requests_delta": counts["embed_requests"] - state["last_embed"],
               "wall_seconds": round(time.time() - t0, 1), **summarize(rows)}
        with open(hourly_f, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        if rows:
            state["last_rowid"] = rows[-1]["rid"]
        state["last_embed"] = counts["embed_requests"]

    original_advance = runner._advance
    t0 = time.time()

    def advance():
        original_advance()
        counts["llm_calls"] = call_counter.snapshot()["count"]
        clock = runner.rs.curr_time
        if args.phase == "soft":
            record("day_start_planning_step_0")
        elif clock.minute == 0 and clock.second == 0:
            record(f"hour_ending_{clock:%H:%M}")
        if runner.rs.step % 90 == 0:
            print(f"step {runner.rs.step} clock {clock} llm {counts['llm_calls']} embed {counts['embed_requests']}", flush=True)
    runner._advance = advance

    def should_stop():
        if counts["llm_calls"] >= soft_llm:
            state["why"] = f"soft LLM cap {soft_llm} reached at a step boundary"
            return True
        if counts["embed_requests"] >= soft_embed:
            state["why"] = f"soft embedding cap {soft_embed} reached at a step boundary"
            return True
        if args.phase == "continue" and runner.rs.curr_time >= until:
            state["why"] = f"reached target clock {until}"
            return True
        return False
    runner.should_stop = should_stop

    report = {"label": "live", "phase": args.phase, "sim_code": args.sim_code, "pinned_model": PINNED,
              "start_clock": str(start_clock), "start_step": start_step, "resumed": resume,
              "caps": {"soft_llm": soft_llm, "hard_llm": hard_llm, "soft_embed": soft_embed, "hard_embed": hard_embed},
              "budget": budget_report}
    outcome = "completed"
    try:
        runner.run(steps)
        outcome = state.get("why", "completed requested steps")
        saved = True
    except CapReached as e:
        outcome = f"HARD CAP, no save attempted (crash semantics): {e}"
        saved = False
    except Exception as e:
        outcome = f"exception: {type(e).__name__}: {str(e)[:200]}"
        saved = False
    if saved and args.phase == "continue":
        record(f"final_partial_hour_to_{runner.rs.curr_time:%H:%M:%S}", partial=True)

    counts["llm_calls"] = call_counter.snapshot()["count"]
    report.update({"outcome": outcome, "saved": saved, "final_step": runner.rs.step, "final_clock": str(runner.rs.curr_time),
                   "steps_run": runner.rs.step - start_step, "wall_seconds": round(time.time() - t0, 1),
                   "counted": counts, "router_counter": call_counter.snapshot(), "router_failures": gs.ROUTER_FAILURES,
                   "autosave_steps": runner.autosave_steps, "embedding_stats": store.stats,
                   "schedule_check": json.loads((run_dir / "schedule_check.json").read_text())})
    import sqlite3
    sweeps, eps = [], {}
    if (run_dir / "memory.db").exists():
        c = sqlite3.connect(str(run_dir / "memory.db"))
        c.row_factory = sqlite3.Row
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "consolidation_sweeps" in tables:
            sweeps = [dict(r) for r in c.execute("SELECT * FROM consolidation_sweeps")]
        eps = {r[0]: r[1] for r in c.execute("SELECT agent_id, COUNT(*) FROM episodic_memory GROUP BY agent_id")}
        c.close()
    report["consolidation_sweeps_rows"] = sweeps
    report["episodic_rows_by_agent_in_mirror"] = eps
    (ART / f"{args.sim_code}_{args.phase}_report.json").write_text(json.dumps(report, indent=1, default=str))
    for name in ("hourly_ledger.jsonl", "schedule_check.json", "embedding_stats.json", "consolidation_log.jsonl"):
        if (run_dir / name).exists():
            shutil.copy(run_dir / name, ART / f"{args.sim_code}_{args.phase}_{name}")
    if saved:  # calibration dataset: the saved memory (and the mirror DB) of this run
        dest = ROOT / "devmem" / "storage" / "calibration" / f"{args.sim_code}_{args.phase}"
        shutil.rmtree(dest, ignore_errors=True)
        shutil.copytree(storage / args.sim_code, dest / "reverie_storage", ignore=shutil.ignore_patterns("movement", "environment"))
        if (run_dir / "memory.db").exists():
            shutil.copy(run_dir / "memory.db", dest / "memory.db")
    print(json.dumps({k: report[k] for k in ("outcome", "saved", "final_clock", "steps_run", "counted", "router_failures",
                                              "consolidation_sweeps_rows")}, indent=1, default=str))


if __name__ == "__main__":
    main()
