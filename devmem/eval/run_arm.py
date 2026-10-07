"""
ONE ARM of the Phase 7 / Phase 9 comparison (baseline or staged), as its own process. NOT launched by this stop; `--dry-run` prints the plan
and runs every offline check without a network call or a simulation step.

  python -m devmem.eval.run_arm --arm baseline --dry-run
  python -m devmem.eval.run_arm --arm staged   --dry-run
(the real runs are two such processes in parallel on DISJOINT chat-key sets, started only after the PM approves the launch).

Settings (all from the PM's launch spec):
  * pinned model gemini-3.1-flash-lite for both arms, normalizer ON, raw-reply log ON, real embeddings (cache first, fail loud);
  * authored schedules through the plan-function replacement (devmem.eval.authored_plan), start 2023-02-13 00:00, 3 compressed days;
  * the event injector (devmem.eval.injector) with a PASS or FAIL line per event;
  * Arm S: STAGE4_ENABLED on, IDENTITY_FEEDBACK on, Stage 3 on with the frozen clustering config; Arm B: baseline memory (priors as atomic nodes);
  * chat keys: a DISJOINT set per arm (7 and 7 of the 14 verified Gemini chat keys), per-key daily cap 450 (set as the `rpd` of the arm's
    temporary provider config; the quota day starts at DEVMEM_QUOTA_RESET_UTC_HOUR=7, i.e. the provider reset, about 12:30 IST);
  * per-arm hard cap 16,500 router calls (CapReached), soft stop at a step boundary after 15,500, autosave every 15 simulated minutes;
  * quota exhaustion PAUSES the process until the reset (devmem.eval.quota_gate) and never crashes or switches model;
  * checkpoint copies at the end of the day 1 and day 3 awake windows (14:00), the simulation folder and the movement files are kept;
  * an upstream exception is not patched around: the run stops, snapshots the folder (no mid-step save) and can be resumed ONCE with --resume;
  * the operator can stop a run by creating a file named ABORT in the run folder.
"""
import argparse
import copy
import json
import os
import shutil
import sys
import tempfile
import time
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

MODEL = "gemini-3.1-flash-lite"
START = datetime(2023, 2, 13, 0, 0, 0)
START_STR = "February 13, 2023, 00:00:00"
DAYS = 3
UNTIL = START + timedelta(days=DAYS)               # end of day 3 (everyone asleep since 14:00)
# Taken at the first autosave at or after 14:15, i.e. 15 simulated minutes AFTER the 14:00 sleep begins: the sleep hook (and so the night sweep) fires on
# the first sleeping step, which is the step after the autosave at 14:00:00 (step 5,040), so a 14:00 checkpoint would precede the night-1 sweep.
# Steps 5,130 and 22,410. Pre-registration section 5b (PM asked for the order to be specified, 2026-10-07).
CHECKPOINTS = {"day1_end_awake": START + timedelta(hours=14, minutes=15), "day3_end_awake": START + timedelta(days=2, hours=14, minutes=15)}
PER_KEY_CAP = 450
HARD_CAP, SOFT_STOP = 16500, 15500   # amended before launch (PM 2026-10-07, claims ledger H12); was 9500 and 8500
RESET_UTC_HOUR = "7"
# Chat-capable Gemini keys verified for the pinned model (docs/key_verification_2026_10_07.md; the 30 keys GEMINI_KEY_18 to 47 verified on 2026-10-07
# afternoon, one chat and one embedding call each, statuses in docs/phase5_step2_artifacts/key_verification.json: chat 200 for 24, 403 for 26, 35, 40,
# 41, 46, 47; GEMINI_KEY_21 chat 503 once and 200 on one retry). GEMINI_KEY_48 and 49 verified (200 and 200) at launch; 50 and 51 returned 403. The eight PILOT keys (8, 10 to 16) are NOT in the full-arm pool.
_PILOT_ONLY = ["GEMINI_KEY_8", "GEMINI_KEY_10", "GEMINI_KEY_11", "GEMINI_KEY_12", "GEMINI_KEY_13", "GEMINI_KEY_14", "GEMINI_KEY_15", "GEMINI_KEY_16"]
_NEW_OK = [n for n in range(18, 52) if n not in (26, 35, 40, 41, 46, 47, 50, 51)]   # 48 and 49 verified later the same day; 50 and 51 returned 403 on chat and embedding
FULL_POOL = [f"GEMINI_KEY_{n}" for n in [1, 2, 3, 4, 5, 6, 17] + _NEW_OK]                       # 31 chat-verified keys
VERIFIED_CHAT_KEYS = FULL_POOL + _PILOT_ONLY
# Embedding: GEMINI_KEY_2 has no embedding verification; the other 30 alternate between the arms (15 and 15), GEMINI_KEY_2 goes to baseline as the odd key
_EMBED_POOL = [k for k in FULL_POOL if k != "GEMINI_KEY_2"]
_EMBED_VERIFIED_EXTRA = list(_PILOT_ONLY)   # the eight pilot keys are embedding-verified as well (HTTP 200 on 2026-10-07)
EMBED_KEYS = {"baseline": _EMBED_POOL[0::2], "staged": _EMBED_POOL[1::2]}
ARM_KEYS = {"baseline": sorted(EMBED_KEYS["baseline"] + ["GEMINI_KEY_2"], key=lambda k: int(k.split("_")[-1])), "staged": EMBED_KEYS["staged"]}   # 16 and 15, disjoint
# PILOT (mechanism and readiness check, never a result): only the NEW keys verified on 2026-10-07, disjoint per arm; stop at 09:00 simulated
PILOT_KEYS = {"baseline": ["GEMINI_KEY_8", "GEMINI_KEY_10", "GEMINI_KEY_11", "GEMINI_KEY_12"],
              "staged": ["GEMINI_KEY_13", "GEMINI_KEY_14", "GEMINI_KEY_15", "GEMINI_KEY_16"]}
NEW_KEYS_2026_10_07 = ["GEMINI_KEY_8", "GEMINI_KEY_10", "GEMINI_KEY_11", "GEMINI_KEY_12", "GEMINI_KEY_13", "GEMINI_KEY_14", "GEMINI_KEY_15",
                       "GEMINI_KEY_16", "GEMINI_KEY_17"]
PILOT_UNTIL = START + timedelta(hours=9)
PILOT_HARD_CAP, PILOT_SOFT_STOP = 1100, 1000
PILOT_CHECKPOINTS = {"pilot_end_0900": START + timedelta(hours=9)}
FORK_SRC = "base_the_ville_isabella_maria_klaus"


def plan(arm: str, sim: str, pilot: bool = False) -> dict:
    other = "staged" if arm == "baseline" else "baseline"
    ks = PILOT_KEYS if pilot else ARM_KEYS
    return {"arm": arm, "sim_code": sim, "PILOT": pilot, "pinned_model": MODEL, "normalizer": "on", "raw_reply_log": "on",
            "memory_mode": arm, "stage4": arm == "staged", "identity_feedback": arm == "staged",
            "chat_keys": ks[arm], "other_arm_keys": ks[other], "keys_disjoint": not set(ks[arm]) & set(ks[other]),
            "per_key_daily_cap": PER_KEY_CAP, "quota_reset_utc_hour": RESET_UTC_HOUR,
            "hard_cap_calls": PILOT_HARD_CAP if pilot else HARD_CAP, "soft_stop_calls": PILOT_SOFT_STOP if pilot else SOFT_STOP,
            "autosave_sim_minutes": 15, "start": START_STR, "until": str(PILOT_UNTIL if pilot else UNTIL), "days": DAYS,
            "checkpoints": {k: str(v) for k, v in (PILOT_CHECKPOINTS if pilot else CHECKPOINTS).items()},
            "embeddings": "real gemini-embedding-001, cache first, fail loud", "movement_zip_export": "at every autosave and at run end",
            "groq_or_nim_used": False}


def load_extra_keys(run_dir: Path, arm: str) -> list:
    """Keys added to a running arm by an operator (disclosed key change): `extra_keys.json` in the run folder, {"keys": [names]}. Only names that are
    verified for chat, not already in the arm, and not in the other arm are accepted; anything else is ignored and reported."""
    f = Path(run_dir) / "extra_keys.json"
    if not f.exists():
        return []
    want = json.loads(f.read_text(encoding="utf-8")).get("keys", [])
    other = ARM_KEYS["staged" if arm == "baseline" else "baseline"]
    return [k for k in want if k in VERIFIED_CHAT_KEYS and k not in ARM_KEYS[arm] and k not in other]


def preflight(arm: str, pilot: bool = False) -> list:
    """Offline checks that must be clean before any run: schedules, events, key sets, env names (never values)."""
    from devmem.eval import checks
    bad = [f"schedule: {x}" for x in checks.check_schedules()] + [f"events: {x}" for x in checks.check_events()]
    ks = PILOT_KEYS if pilot else ARM_KEYS
    a, b = set(ks["baseline"]), set(ks["staged"])
    if a & b:
        bad.append(f"arm key sets overlap: {sorted(a & b)}")
    if not (a | b) <= set(VERIFIED_CHAT_KEYS):
        bad.append("an arm uses a key that is not in the verified chat list")
    if pilot and not (a | b) <= set(NEW_KEYS_2026_10_07):
        bad.append("the pilot must use only the new keys verified on 2026-10-07")
    if any(not k.startswith("GEMINI_KEY_") for k in ks[arm]):
        bad.append("a non-Gemini key is assigned to an arm")
    return bad


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=["baseline", "staged"], required=True)
    ap.add_argument("--sim")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--pilot", action="store_true", help="mechanism and readiness pilot (new keys only, stop at 09:00, caps 1100 and 1000); never a result")
    ap.add_argument("--wall-stop", help="HH:MM local (IST) wall clock: stop at the first step boundary at or after it (absolute)")
    ap.add_argument("--key-stop", type=int, help="stop at a step boundary when any chat key of this arm has reached this many requests today")
    ap.add_argument("--hard-cap", type=int)
    ap.add_argument("--soft-stop", type=int)
    a = ap.parse_args(argv)
    arm, pilot = a.arm, a.pilot
    sim = a.sim or (f"p7pilot_{arm}" if pilot else f"p7_{arm}")
    hard_cap = a.hard_cap or (PILOT_HARD_CAP if pilot else HARD_CAP)
    soft_stop = a.soft_stop or (PILOT_SOFT_STOP if pilot else SOFT_STOP)
    arm_keys = (PILOT_KEYS if pilot else ARM_KEYS)[arm]
    until = PILOT_UNTIL if pilot else UNTIL
    checkpoints = PILOT_CHECKPOINTS if pilot else CHECKPOINTS
    problems = preflight(arm, pilot)
    extra = [] if pilot else load_extra_keys(ROOT / "devmem" / "storage" / sim, arm)
    if extra:
        arm_keys = arm_keys + extra                      # disclosed key change (supervisor resume at an autosave); names only in the log below
        with open(ROOT / "devmem" / "storage" / sim / "key_changes.jsonl", "a", encoding="utf-8") as kc:
            kc.write(json.dumps({"at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "arm": arm, "added_chat_keys": extra}) + "\n")
    print(json.dumps(plan(arm, sim, pilot), indent=1))
    if problems:
        print("PREFLIGHT FAILED:", *problems, sep="\n  ")
        raise SystemExit(2)
    print("preflight: clean (schedules, events, disjoint verified key sets)")
    if a.dry_run:
        return

    run_dir = ROOT / "devmem" / "storage" / sim
    if not a.resume:
        shutil.rmtree(run_dir, ignore_errors=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    raw_log = run_dir / "raw_replies.jsonl"
    state_f = run_dir / "arm_state.json"
    prior = json.loads(state_f.read_text()) if (a.resume and state_f.exists()) else {"calls": 0, "runs": 0}
    if a.resume:
        # arm_state.json is only written on the hour, so after a crash or a kill it under-counts. The raw reply log has one line per delivered
        # reply of every process of this arm (pilot finding 2026-10-07: 33 recorded vs 538 delivered), so the cumulative spend is the larger.
        prior["calls"] = max(prior["calls"], sum(1 for l in raw_log.read_text(encoding="utf-8").splitlines() if l.strip())) if raw_log.exists() else prior["calls"]
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    stage4 = "on" if arm == "staged" else "off"
    for k, v in (("DEVMEM_PINNED_MODEL", MODEL), ("DEVMEM_OUTPUT_NORMALIZER", "on"), ("DEVMEM_EMBEDDING_MODE", "live"),
                 ("DEVMEM_RAW_REPLY_LOG", str(raw_log)), ("SIM_CODE", sim), ("STAGE4_ENABLED", stage4), ("IDENTITY_FEEDBACK", stage4),
                 ("DEVMEM_QUOTA_RESET_UTC_HOUR", RESET_UTC_HOUR)):
        os.environ[k] = v
    missing = [k for k in arm_keys if not os.environ.get(k)]
    if missing:
        raise SystemExit(f"keys not set in the environment: {missing}")

    from devmem.run_headless import HeadlessRunner
    import utils
    import yaml
    import persona.prompt_template.gpt_structure as gs
    from devmem.embeddings.vector_store import EmbeddingStore
    from devmem.eval import authored_plan, checks
    from devmem.eval.injector import EventInjector
    from devmem.eval.quota_gate import QuotaGate, RunAborted
    from devmem.eval.run_support import LedgerWindows, count_fence_strips, make_checkpoint, write_status
    from devmem.api.movement_archive import MovementExporter
    from devmem.memory import consolidation, episodic, identity
    from devmem.memory.episodic import get_db_path
    from devmem.router import call_counter, key_pool, llm_router, output_normalizer

    storage = Path(utils.fs_storage)
    fork = f"{FORK_SRC}__start_{sim}"
    if not a.resume:
        shutil.rmtree(storage / fork, ignore_errors=True)
        shutil.copytree(storage / FORK_SRC, storage / fork)
        meta_f = storage / fork / "reverie" / "meta.json"
        meta = json.loads(meta_f.read_text())
        meta["curr_time"] = START_STR
        meta_f.write_text(json.dumps(meta, indent=2))
        shutil.rmtree(storage / sim, ignore_errors=True)

    # temporary provider configs: only gemini, only this arm's keys (rotated), per-key daily cap 450; never written into the repo config
    base = yaml.safe_load(open(ROOT / "devmem/config/providers.yaml", encoding="utf-8"))
    gem = next(p for p in base["providers"] if p["name"] == "gemini")
    tmp = Path(tempfile.mkdtemp(prefix=f"p7_{arm}_"))
    cfgs, keys = [], arm_keys
    for i in range(len(keys)):
        p = copy.deepcopy(gem)
        p["keys"] = [{"env": k} for k in keys[i:] + keys[:i]]
        p["model_limits"][MODEL]["rpd"] = PER_KEY_CAP
        p["daily_limit_fast"] = PER_KEY_CAP
        f = tmp / f"rot{i}.yaml"
        f.write_text(yaml.dump({"providers": [p]}), encoding="utf-8")
        cfgs.append(str(f))
    rot = {"i": prior["calls"]}
    real_call = llm_router.call_llm

    def rotating(*args, **kwargs):
        kwargs.setdefault("config_path", cfgs[rot["i"] % len(cfgs)])
        rot["i"] += 1
        return real_call(*args, **kwargs)
    gate = QuotaGate(rotating, keys, MODEL, PER_KEY_CAP, run_dir)
    for mod in (gs, episodic, consolidation, identity):
        mod.call_llm = gate

    call_counter.reset()
    call_counter.set_cap(hard_cap - prior["calls"])
    soft_left = soft_stop - prior["calls"]

    embed_keys = yaml.safe_load(open(ROOT / "devmem/config/embeddings.yaml", encoding="utf-8"))["key_envs"] if pilot else EMBED_KEYS[arm] + [k for k in extra if k in _EMBED_VERIFIED_EXTRA]
    store = EmbeddingStore(stats_path=get_db_path(sim).parent / f"embedding_stats{'_resume' if a.resume else ''}.json", key_envs=embed_keys)
    gate.wrap_embedding_store(store, embed_keys, rpd=1000)
    gs._EMBEDDING_STORE = store

    schedules, spec = checks.load(checks.SCHEDULES), checks.load(checks.EVENTS)
    uninstall = authored_plan.install(schedules, START.date())

    runner = HeadlessRunner(fork, sim, memory_mode=arm, resume=a.resume, final_sweep=False)
    rs = runner.rs
    names = list(rs.personas)
    injector = EventInjector(spec["events"], START, run_dir / "injection_log.jsonl", arm)
    windows = LedgerWindows(key_pool, run_dir, arm, names)
    exporter = MovementExporter(storage / sim, run_dir / "movement.zip")
    label = {"mode": "PILOT: live run (mechanism and readiness check), NOT a result" if pilot else "FULL: live run in progress (Phase 7 comparison)", "origin": "authored schedules and injected events (Phase 7 harness)",
             "model": MODEL, "normalizer": "on", "stages": ("Stages 1 to 4 on, Stage 3 average 0.82" if arm == "staged" else "baseline memory (priors as atomic nodes), upstream reflection on"),
             "note": ("PILOT output is never reported as a result." if pilot else "Phase 7 comparison run.")}
    (run_dir / "run_label.json").write_text(json.dumps(label, indent=1), encoding="utf-8")
    from devmem.memory.consolidation import is_sleeping, load_config as cons_cfg
    markers = cons_cfg()["sleep_markers"]
    why_stop, made, exported = {}, {}, {}
    orig_advance = runner._advance

    def status(state):
        write_status(run_dir / "run_status.json", {
            "arm": arm, "sim_code": sim, "pilot": pilot, "state": state, "sim_clock": str(rs.curr_time), "step": rs.step,
            "router_calls_total": prior["calls"] + call_counter.snapshot()["count"], "quota_pauses": gate.pauses,
            "injection": injector.summary(), "checkpoints_made": sorted(made), "autosave_steps": runner.autosave_steps[-3:],
            "normalizer": output_normalizer.STATS, "router_failures": gs.ROUTER_FAILURES.get("count") if isinstance(gs.ROUTER_FAILURES, dict) else None})

    def counters():
        return {"router_calls_total": prior["calls"] + call_counter.snapshot()["count"], "quota_pauses": gate.pauses,
                "fence_strips_total": count_fence_strips(raw_log), "outage_minutes_total": gate.outage_minutes_total()}

    def advance():
        injector.tick(rs)
        orig_advance()
        windows.observe_step({n: is_sleeping(p.scratch.act_description, markers) for n, p in rs.personas.items()})
        c = rs.curr_time
        if rs.step == 1 and not a.resume:
            windows.record("step_0_day_start_planning", str(c), rs.step, counters(), {"injection": injector.summary()})
        elif c.minute == 0 and c.second == 0:
            windows.record(f"hour_ending_{c:%Y-%m-%d_%H:%M}", str(c), rs.step, counters(), {"injection": injector.summary()})
            state_f.write_text(json.dumps({"calls": counters()["router_calls_total"], "runs": prior["runs"] + 1}))
            status("running")
        if rs.step % 360 == 0:
            print(f"step {rs.step} clock {c} calls {counters()['router_calls_total']} pauses {gate.pauses}", flush=True)
    runner._advance = advance

    def should_stop():
        if (run_dir / "ABORT").exists():
            why_stop["why"] = "ABORT file present"
            return True
        if runner.autosave_steps and runner.autosave_steps[-1] == rs.step and exported.get("step") != rs.step:   # the viewer can read a growing recording
            exporter.export()
            exported["step"] = rs.step
        for label, when in checkpoints.items():  # after the autosave of this step (HeadlessRunner saves before calling should_stop)
            if label not in made and rs.curr_time >= when and runner.autosave_steps and runner.autosave_steps[-1] == rs.step:
                make_checkpoint(storage, sim, rs.step, run_dir, label, str(rs.curr_time))
                made[label] = rs.step
        if (run_dir / "KEY_CHANGE").exists() and runner.autosave_steps and runner.autosave_steps[-1] == rs.step:
            why_stop["why"] = "key change restart at an autosave (the supervisor resumes with the keys in extra_keys.json)"
            return True
        if a.wall_stop and datetime.now().strftime("%H:%M") >= a.wall_stop:
            why_stop["why"] = f"wall-clock stop at {a.wall_stop} local"
            return True
        if a.key_stop and max(gate._used(k) for k in arm_keys) >= a.key_stop:
            why_stop["why"] = f"a key reached {a.key_stop} requests today"
            return True
        if call_counter.snapshot()["count"] >= soft_left:
            why_stop["why"] = f"soft stop: {soft_stop} router calls reached at a step boundary"
            return True
        if rs.curr_time >= until:
            why_stop["why"] = f"reached {until}"
            return True
        return False
    runner.should_stop = should_stop

    outcome, exc_info = "completed", None
    status("starting")
    try:
        runner.run(10 ** 7)
        outcome = why_stop.get("why", "completed")
    except RunAborted as e:
        outcome = f"aborted by the operator: {e}"
    except call_counter.CapReached as e:
        outcome = f"HARD CAP, no save attempted: {e}"
    except Exception as e:  # reporter only: nothing upstream is wrapped, patched or retried
        import traceback
        last = None
        if raw_log.exists():
            lines = [l for l in raw_log.read_text(encoding="utf-8").splitlines() if l.strip()]
            last = json.loads(lines[-1]) if lines else None
        snap = storage / f"{sim}__crash_snapshot_{prior['runs'] + 1}"
        shutil.rmtree(snap, ignore_errors=True)
        shutil.copytree(storage / sim, snap)
        exc_info = {"type": type(e).__name__, "message": str(e)[:300], "traceback": traceback.format_exc(), "last_router_call": last, "snapshot": snap.name}
        outcome = f"upstream exception: {type(e).__name__}: {str(e)[:200]}"
    finally:
        uninstall()
    try:
        exporter.export()
    except Exception as e:  # the export must never mask the real outcome
        print("movement export at run end failed:", e)
    windows.record("final_partial_window", str(rs.curr_time), rs.step, counters(), {"injection": injector.summary()})
    status("finished: " + outcome)
    report = {"arm": arm, "sim_code": sim, "outcome": outcome, "final_clock": str(rs.curr_time), "final_step": rs.step, "exception": exc_info,
              "router_calls_total": counters()["router_calls_total"], "quota_pauses": gate.pauses, "injection": injector.summary(),
              "checkpoints": made, "autosave_steps": runner.autosave_steps, "normalizer_stats": output_normalizer.STATS,
              "schedule_check": json.loads((run_dir / "schedule_check.json").read_text())}
    (run_dir / f"arm_report_{'resume' if a.resume else 'first'}.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("outcome", "final_clock", "router_calls_total", "quota_pauses", "injection")}, indent=1, default=str))


if __name__ == "__main__":
    main()
