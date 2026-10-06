"""
Step C RERUN (live): end-to-end smoke on Gemini with the REVISED output normalizer ON (strip the exact annotation on every prompt except the
decomposition veto set), to decide whether Gemini can drive full runs. Changes from the first run (devmem/run_step_c.py): hard cap 400
router-counted calls with a soft stop at a step boundary after 300; on an upstream exception the run STOPS, tries to save state, and records
the traceback and the prompt that caused it (no exception handling is added around upstream; the single catch below is only the reporter).

  3 agents (Isabella Rodriguez, Maria Lopez, Klaus Mueller), from 06:00, 2 simulated hours (stops at 08:00), staged mode,
  Stage 4 off (not built yet), pinned gemini-3.1-flash-lite, DEVMEM_OUTPUT_NORMALIZER=on for the run (applies identically to
  any condition), fail_loud_llm on, agent tagging on. HARD CAP 150 calls counted at the ROUTER (CapReached ends the run; no save is
  attempted after a mid-step stop). The raw-reply log is on and keeps the full prompt, raw reply and delivered text of every call.

Keys: calls rotate round-robin over GEMINI_KEY_4, _5, _6 through temporary provider configs (never written into the repo's
providers.yaml), applied to every caller (gpt_structure, episodic scoring, consolidation) by patching the call_llm names in memory;
the router's own per-key RPM pacing (15 RPM for this model) then applies per key.

Embeddings: DEVMEM_EMBEDDING_MODE=offline for the whole run: deterministic vectors, no embedding request of any kind (the cache is
not read, so real and fallback vectors can never mix inside the run's memory). Retrieval relevance is therefore meaningless in this
run; Step C measures output validity and cost only.
"""
import copy
import json
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
SIM = "p5_step_c2_gemini"
MODEL = "gemini-3.1-flash-lite"
KEYS = ["GEMINI_KEY_4", "GEMINI_KEY_5", "GEMINI_KEY_6"]
CAP = 400
SOFT = 300
START = "February 13, 2023, 06:00:00"
UNTIL = datetime(2023, 2, 13, 8, 0, 0)
ART = ROOT / "docs" / "phase6_stepc2_artifacts"


def main():
    ART.mkdir(parents=True, exist_ok=True)
    run_dir_pre = ROOT / "devmem" / "storage" / SIM
    shutil.rmtree(run_dir_pre, ignore_errors=True)
    run_dir_pre.mkdir(parents=True, exist_ok=True)
    raw_log = run_dir_pre / "raw_replies.jsonl"
    os.environ.update({"DEVMEM_PINNED_MODEL": MODEL, "DEVMEM_OUTPUT_NORMALIZER": "on", "DEVMEM_EMBEDDING_MODE": "offline",
                       "DEVMEM_RAW_REPLY_LOG": str(raw_log), "SIM_CODE": SIM})
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    for k, v in (("DEVMEM_PINNED_MODEL", MODEL), ("DEVMEM_OUTPUT_NORMALIZER", "on"), ("DEVMEM_EMBEDDING_MODE", "offline"),
                 ("DEVMEM_RAW_REPLY_LOG", str(raw_log))):
        os.environ[k] = v  # .env must not override the run's settings

    from devmem.run_headless import HeadlessRunner
    import utils
    import yaml
    import persona.prompt_template.gpt_structure as gs
    from devmem.memory import consolidation, episodic
    from devmem.router import call_counter, key_pool, llm_router, output_normalizer

    storage = Path(utils.fs_storage)
    fork_src = "base_the_ville_isabella_maria_klaus"
    fork = f"{fork_src}__start_{SIM}"
    shutil.rmtree(storage / fork, ignore_errors=True)
    shutil.copytree(storage / fork_src, storage / fork)
    meta_f = storage / fork / "reverie" / "meta.json"
    meta = json.loads(meta_f.read_text())
    meta["curr_time"] = START
    meta_f.write_text(json.dumps(meta, indent=2))
    shutil.rmtree(storage / SIM, ignore_errors=True)

    # temporary provider configs: only the Gemini provider, only the chosen keys, rotated
    base = yaml.safe_load(open(ROOT / "devmem/config/providers.yaml", encoding="utf-8"))
    gem = next(p for p in base["providers"] if p["name"] == "gemini")
    tmp = Path(tempfile.mkdtemp(prefix="p5_step_c_"))
    cfgs = []
    for i in range(len(KEYS)):
        p = copy.deepcopy(gem)
        p["keys"] = [{"env": k} for k in KEYS[i:] + KEYS[:i]]
        f = tmp / f"gemini_rot{i}.yaml"
        f.write_text(yaml.dump({"providers": [p]}), encoding="utf-8")
        cfgs.append(str(f))
    rot = {"i": 0, "per_first_key": {k: 0 for k in KEYS}}
    real_call = llm_router.call_llm

    def rotating(*a, **k):
        idx = rot["i"] % len(KEYS)
        rot["i"] += 1
        rot["per_first_key"][KEYS[idx]] += 1
        k.setdefault("config_path", cfgs[idx])
        return real_call(*a, **k)
    for mod in (gs, episodic, consolidation):
        mod.call_llm = rotating

    call_counter.reset()
    call_counter.set_cap(CAP)

    def max_rowid():
        c = key_pool.get_db_connection()
        try:
            return c.execute("SELECT COALESCE(MAX(rowid),0) FROM llm_call_log").fetchone()[0]
        finally:
            c.close()

    def rows_since(rid):
        c = key_pool.get_db_connection()
        try:
            return c.execute("SELECT rowid AS r, purpose, agent_id, tokens_in, tokens_out FROM llm_call_log WHERE rowid > ? ORDER BY rowid",
                             (rid,)).fetchall()
        finally:
            c.close()

    def summarize(rows):
        bp, ba = {}, {}
        for r in rows:
            for key, d in ((r["purpose"], bp), (r["agent_id"] or "none", ba)):
                e = d.setdefault(key, {"calls": 0, "tokens_in": 0, "tokens_out": 0})
                e["calls"] += 1
                e["tokens_in"] += r["tokens_in"] or 0
                e["tokens_out"] += r["tokens_out"] or 0
        return {"calls": len(rows), "tokens_in": sum(r["tokens_in"] or 0 for r in rows),
                "tokens_out": sum(r["tokens_out"] or 0 for r in rows), "by_purpose": bp, "by_agent": ba}

    runner = HeadlessRunner(fork, SIM, memory_mode="staged", final_sweep=False)
    run_dir = runner.db_path.parent
    start_clock = runner.rs.curr_time
    state = {"rid": max_rowid(), "t0": time.time()}
    hourly = run_dir / "hourly_ledger.jsonl"

    def record(label, partial=False):
        rows = rows_since(state["rid"])
        rec = {"label": label, "sim_clock": str(runner.rs.curr_time), "step": runner.rs.step, "partial": partial,
               "wall_seconds": round(time.time() - state["t0"], 1), "router_calls_so_far": call_counter.snapshot()["count"],
               **summarize(rows)}
        with open(hourly, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        if rows:
            state["rid"] = rows[-1]["r"]

    orig = runner._advance

    def advance():
        orig()
        clock = runner.rs.curr_time
        if runner.rs.step == 1:
            record("step_0_day_start_planning")
        elif clock.minute == 0 and clock.second == 0:
            record(f"hour_ending_{clock:%H:%M}")
        if runner.rs.step % 90 == 0:
            print(f"step {runner.rs.step} clock {clock} router_calls {call_counter.snapshot()['count']}", flush=True)
    runner._advance = advance
    why_stop = {}

    def should_stop():
        if call_counter.snapshot()["count"] >= SOFT:
            why_stop["why"] = f"soft stop: {SOFT} router calls reached at a step boundary"
            return True
        if runner.rs.curr_time >= UNTIL:
            why_stop["why"] = "reached 08:00:00 (2 simulated hours)"
            return True
        return False
    runner.should_stop = should_stop

    outcome, saved, exc_info = "completed", True, None
    try:
        runner.run(10 ** 6)
        outcome = why_stop.get("why", "completed")
    except call_counter.CapReached as e:
        outcome, saved = f"HARD CAP, no save attempted: {e}", False
    except Exception as e:  # reporter only: the run stops here; nothing upstream is wrapped or retried
        import traceback
        last_prompt = None
        if raw_log.exists():
            lines = [l for l in raw_log.read_text(encoding="utf-8").splitlines() if l.strip()]
            last_prompt = json.loads(lines[-1]) if lines else None
        exc_info = {"type": type(e).__name__, "message": str(e)[:300], "traceback": traceback.format_exc(),
                    "last_router_call_before_the_exception": last_prompt}
        outcome, saved = f"upstream exception: {type(e).__name__}: {str(e)[:200]}", False
        try:  # per instruction: stop, save state, report (a mid-step save can fail; the result is recorded either way)
            runner._save()
            exc_info["state_saved"] = True
            saved = True
        except BaseException as save_err:
            exc_info["state_saved"] = False
            exc_info["save_error"] = f"{type(save_err).__name__}: {str(save_err)[:200]}"
    record("final_partial_hour" if saved else "interrupted_mid_step", partial=True)

    report = {"label": "live", "sim_code": SIM, "model": MODEL, "start_clock": str(start_clock), "final_clock": str(runner.rs.curr_time),
              "final_step": runner.rs.step, "outcome": outcome, "saved": saved, "cap": CAP, "soft_stop_at": SOFT, "exception": exc_info,
              "per_agent_progress": {n: {"act_description_at_stop": str(p.scratch.act_description), "scratch_clock": str(p.scratch.curr_time),
                                         "memory_nodes": len(p.a_mem.id_to_node)} for n, p in runner.rs.personas.items()},
              "router_counter": call_counter.snapshot(),
              "wall_seconds": round(time.time() - state["t0"], 1), "calls_by_first_key": rot["per_first_key"],
              "normalizer_stats": output_normalizer.STATS, "router_failures": gs.ROUTER_FAILURES,
              "autosave_steps": runner.autosave_steps, "schedule_check": json.loads((run_dir / "schedule_check.json").read_text()),
              "embedding_mode": "offline (deterministic vectors, zero embedding requests)"}
    (ART / "step_c_report.json").write_text(json.dumps(report, indent=1, default=str))
    for name in ("hourly_ledger.jsonl", "raw_replies.jsonl", "schedule_check.json", "consolidation_log.jsonl"):
        src = run_dir / name
        if src.exists():
            shutil.copy(src, ART / name)
    print(json.dumps({k: report[k] for k in ("outcome", "final_clock", "router_counter", "calls_by_first_key", "normalizer_stats",
                                              "router_failures")}, indent=1, default=str))


if __name__ == "__main__":
    main()
