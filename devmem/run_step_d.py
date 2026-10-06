"""
STEP D (live, background): natural multi-day-boundary run on Gemini, run from an isolated git worktree at a committed HEAD.

  3 agents (Isabella Rodriguez, Maria Lopez, Klaus Mueller), staged mode, Stage 4 not built into this run (STAGE4_ENABLED off), Stage 3
  consolidation ON (the sleep hook fires from persona.move), normalizer ON, raw-reply log ON, pinned gemini-3.1-flash-lite,
  start 2023-02-13 06:00, stop at 2023-02-14 08:00 or at a cap.

Caps: HARD 1200 router-counted LLM calls (CapReached ends the run), SOFT 900 (graceful stop at a step boundary), no chat key above 400
HTTP requests (checked from the router ledger at step boundaries with a margin: stop at 380), embeddings: real model through the existing
cache, fail loud, HARD 150 real embedding requests (counted at the HTTP layer; the 151st raises), soft stop at 130. Autosave every 15 sim minutes.

Crash policy: an upstream exception is NOT wrapped or patched. The run records the traceback and the last router call, snapshots the sim
folder as it stands (no mid-step save, so the last autosave stays intact), and stops. A second invocation with --resume re-opens the last
autosave in place (allowed once; the counters continue from stepd_state.json).

Keys: chat calls rotate round-robin over GEMINI_KEY_4, _5, _6 through temporary provider configs (never written into providers.yaml).
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
SIM = "p6_step_d_gemini"
MODEL = "gemini-3.1-flash-lite"
KEYS = ["GEMINI_KEY_4", "GEMINI_KEY_5", "GEMINI_KEY_6"]
CAP, SOFT = 1200, 900
KEY_LIMIT, KEY_STOP = 400, 380
EMBED_HARD, EMBED_SOFT = 150, 130
START = "February 13, 2023, 06:00:00"
UNTIL = datetime(2023, 2, 14, 8, 0, 0)
ART = ROOT / "docs" / "phase6_stepd_artifacts"


def main():
    resume = "--resume" in sys.argv
    ART.mkdir(parents=True, exist_ok=True)
    run_dir_pre = ROOT / "devmem" / "storage" / SIM
    if not resume:
        shutil.rmtree(run_dir_pre, ignore_errors=True)
    run_dir_pre.mkdir(parents=True, exist_ok=True)
    raw_log = run_dir_pre / "raw_replies.jsonl"
    state_f = run_dir_pre / "stepd_state.json"
    prior = json.loads(state_f.read_text()) if (resume and state_f.exists()) else {"calls": 0, "embed": 0, "runs": 0}
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    for k, v in (("DEVMEM_PINNED_MODEL", MODEL), ("DEVMEM_OUTPUT_NORMALIZER", "on"), ("DEVMEM_EMBEDDING_MODE", "live"),
                 ("DEVMEM_RAW_REPLY_LOG", str(raw_log)), ("SIM_CODE", SIM)):
        os.environ[k] = v  # .env must not override the run's settings

    from devmem.run_headless import HeadlessRunner
    import utils
    import yaml
    import requests
    import persona.prompt_template.gpt_structure as gs
    from devmem.embeddings.vector_store import EmbeddingStore
    from devmem.memory import consolidation, episodic
    from devmem.router import call_counter, key_pool, llm_router, output_normalizer

    storage = Path(utils.fs_storage)
    fork_src = "base_the_ville_isabella_maria_klaus"
    fork = f"{fork_src}__start_{SIM}"
    if not resume:
        shutil.rmtree(storage / fork, ignore_errors=True)
        shutil.copytree(storage / fork_src, storage / fork)
        meta_f = storage / fork / "reverie" / "meta.json"
        meta = json.loads(meta_f.read_text())
        meta["curr_time"] = START
        meta_f.write_text(json.dumps(meta, indent=2))
        shutil.rmtree(storage / SIM, ignore_errors=True)

    base = yaml.safe_load(open(ROOT / "devmem/config/providers.yaml", encoding="utf-8"))
    gem = next(p for p in base["providers"] if p["name"] == "gemini")
    tmp = Path(tempfile.mkdtemp(prefix="p6_step_d_"))
    cfgs = []
    for i in range(len(KEYS)):
        p = copy.deepcopy(gem)
        p["keys"] = [{"env": k} for k in KEYS[i:] + KEYS[:i]]
        f = tmp / f"gemini_rot{i}.yaml"
        f.write_text(yaml.dump({"providers": [p]}), encoding="utf-8")
        cfgs.append(str(f))
    rot = {"i": prior["calls"], "per_first_key": {k: 0 for k in KEYS}}
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
    call_counter.set_cap(CAP - prior["calls"])
    soft_left = SOFT - prior["calls"]

    embed = {"requests": 0}

    def counted_post(*a, **k):
        if prior["embed"] + embed["requests"] >= EMBED_HARD:
            raise RuntimeError(f"hard embedding cap {EMBED_HARD} reached")
        embed["requests"] += 1
        return requests.post(*a, **k)
    from devmem.memory.episodic import get_db_path
    store = EmbeddingStore(post=counted_post, stats_path=get_db_path(SIM).parent / f"embedding_stats{'_resume' if resume else ''}.json")
    gs._EMBEDDING_STORE = store

    def key_requests():
        c = key_pool.get_db_connection()
        try:
            rows = c.execute("SELECT key_id, SUM(requests_used) AS n FROM key_usage WHERE provider='gemini' GROUP BY key_id").fetchall()
        finally:
            c.close()
        return {r["key_id"]: r["n"] for r in rows if r["key_id"].endswith("#" + MODEL)}

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

    runner = HeadlessRunner(fork, SIM, memory_mode="staged", resume=resume, final_sweep=False)
    run_dir = runner.db_path.parent
    start_clock = runner.rs.curr_time
    state = {"rid": max_rowid(), "t0": time.time(), "sleep_steps": {n: 0 for n in runner.rs.personas}, "steps_in_hour": 0}
    hourly = run_dir / "hourly_ledger.jsonl"
    markers = consolidation.load_config()["sleep_markers"]

    def record(label, partial=False):
        rows = rows_since(state["rid"])
        frac = {n: (round(state["sleep_steps"][n] / state["steps_in_hour"], 3) if state["steps_in_hour"] else None)
                for n in state["sleep_steps"]}
        rec = {"label": label, "sim_clock": str(runner.rs.curr_time), "step": runner.rs.step, "partial": partial,
               "resumed_run": resume, "wall_seconds": round(time.time() - state["t0"], 1),
               "router_calls_this_process": call_counter.snapshot()["count"], "embedding_requests_this_process": embed["requests"],
               "steps_in_window": state["steps_in_hour"], "sleeping_step_fraction": frac, **summarize(rows)}
        with open(hourly, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        if rows:
            state["rid"] = rows[-1]["r"]
        state["sleep_steps"] = {n: 0 for n in state["sleep_steps"]}
        state["steps_in_hour"] = 0
        state_f.write_text(json.dumps({"calls": prior["calls"] + call_counter.snapshot()["count"],
                                       "embed": prior["embed"] + embed["requests"], "runs": prior["runs"] + 1}))

    orig = runner._advance

    def advance():
        orig()
        clock = runner.rs.curr_time
        state["steps_in_hour"] += 1
        for n, p in runner.rs.personas.items():
            if consolidation.is_sleeping(p.scratch.act_description, markers):
                state["sleep_steps"][n] += 1
        if runner.rs.step == 1 and not resume:
            record("step_0_day_start_planning")
        elif clock.minute == 0 and clock.second == 0:
            record(f"hour_ending_{clock:%Y-%m-%d_%H:%M}")
        if runner.rs.step % 90 == 0:
            print(f"step {runner.rs.step} clock {clock} router_calls {prior['calls'] + call_counter.snapshot()['count']} "
                  f"embed {prior['embed'] + embed['requests']}", flush=True)
    runner._advance = advance
    why_stop = {}

    def should_stop():
        n = call_counter.snapshot()["count"]
        if n >= soft_left:
            why_stop["why"] = f"soft stop: {SOFT} router calls reached at a step boundary"
            return True
        if prior["embed"] + embed["requests"] >= EMBED_SOFT:
            why_stop["why"] = f"soft stop: {EMBED_SOFT} real embedding requests reached"
            return True
        kr = key_requests()
        if kr and max(kr.values()) >= KEY_STOP:
            why_stop["why"] = f"per-key stop: a chat key reached {max(kr.values())} requests (limit {KEY_LIMIT}, stop at {KEY_STOP})"
            return True
        if runner.rs.curr_time >= UNTIL:
            why_stop["why"] = "reached 2023-02-14 08:00:00"
            return True
        return False
    runner.should_stop = should_stop

    outcome, saved, exc_info = "completed", True, None
    try:
        runner.run(10 ** 6)
        outcome = why_stop.get("why", "completed")
    except call_counter.CapReached as e:
        outcome, saved = f"HARD CAP, no save attempted: {e}", False
    except Exception as e:  # reporter only: nothing upstream is wrapped, patched or retried
        import traceback
        last = None
        if raw_log.exists():
            lines = [l for l in raw_log.read_text(encoding="utf-8").splitlines() if l.strip()]
            last = json.loads(lines[-1]) if lines else None
        exc_info = {"type": type(e).__name__, "message": str(e)[:300], "traceback": traceback.format_exc(),
                    "last_router_call_before_the_exception": last, "autosave_steps": runner.autosave_steps}
        outcome, saved = f"upstream exception: {type(e).__name__}: {str(e)[:200]}", False
        snap = storage / f"{SIM}__crash_snapshot_{prior['runs'] + 1}"
        shutil.rmtree(snap, ignore_errors=True)
        shutil.copytree(storage / SIM, snap)
        exc_info["crash_snapshot"] = snap.name
    record("final_partial_hour" if saved else "interrupted_mid_step", partial=True)

    tag = "resume" if resume else "first"
    report = {"label": "live", "sim_code": SIM, "invocation": tag, "model": MODEL, "start_clock": str(start_clock),
              "final_clock": str(runner.rs.curr_time), "final_step": runner.rs.step, "outcome": outcome, "saved": saved,
              "cap": CAP, "soft_stop_at": SOFT, "embedding_caps": [EMBED_SOFT, EMBED_HARD], "exception": exc_info,
              "per_agent_progress": {n: {"act_description_at_stop": str(p.scratch.act_description),
                                         "scratch_clock": str(p.scratch.curr_time), "memory_nodes": len(p.a_mem.id_to_node)}
                                     for n, p in runner.rs.personas.items()},
              "router_counter_this_process": call_counter.snapshot(), "router_calls_total": prior["calls"] + call_counter.snapshot()["count"],
              "embedding_requests_this_process": embed["requests"], "embedding_requests_total": prior["embed"] + embed["requests"],
              "chat_key_requests_ledger": key_requests(), "calls_by_first_key": rot["per_first_key"],
              "wall_seconds": round(time.time() - state["t0"], 1), "normalizer_stats": output_normalizer.STATS,
              "router_failures": gs.ROUTER_FAILURES, "autosave_steps": runner.autosave_steps,
              "schedule_check": json.loads((run_dir / "schedule_check.json").read_text())}
    (ART / f"step_d_report_{tag}.json").write_text(json.dumps(report, indent=1, default=str))
    for name in ("hourly_ledger.jsonl", "raw_replies.jsonl", "schedule_check.json", "consolidation_log.jsonl", "memory.db",
                 "embedding_stats.json", "embedding_stats_resume.json", "stepd_state.json"):
        src = run_dir / name
        if src.exists():
            shutil.copy(src, ART / name)
    print(json.dumps({k: report[k] for k in ("outcome", "final_clock", "router_calls_total", "embedding_requests_total",
                                              "chat_key_requests_ledger", "normalizer_stats", "router_failures")}, indent=1, default=str),
          flush=True)


if __name__ == "__main__":
    main()
