"""
Probe Step B (all results LIVE). Router-level caps (devmem/router/call_counter.py: every call_llm attempt counts, whatever the
import path; CapReached ends the phase).

  B1  gemini-3.1-flash-lite, daily-plan and hourly-schedule prompts, WITH the output normalizer (Unicode spaces to a plain
      space, "(duration in minutes ...)" suffix stripped) applied at the router/output layer. Hard cap 24 calls.
  B2  openai/gpt-oss-20b, daily-plan prompt only, NO normalizer. Hard cap 16 calls.

Same Isabella state and same fixed inputs as the first probe (p5_model_probe.py): saved fork state at 2023-02-13 00:00, plan asked
for wake-up hour 6, hourly slot 07:00 AM with a reference daily_req and 7 hours of "sleeping" as prior schedule. Upstream's own
prompt functions and retry loop (up to 5 attempts) are used unmodified.

FULL untruncated raw replies are saved for every call (`raw` = exactly what the router returned; `delivered` = what upstream saw
after the normalizer, equal to `raw` when no normalizer is applied). Keys are spread: a temporary provider config (never
written into the repo's providers.yaml) lists only the chosen keys, rotated per invocation: Groq 7, 8, 9 for B2; Gemini 4, 5, 6
for B1 (chat calls use the chat model's quota, not the embedding model's).
"""
import copy
import datetime
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

B1 = {"label": "B1", "model": "gemini-3.1-flash-lite", "provider": "gemini", "keys": ["GEMINI_KEY_4", "GEMINI_KEY_5", "GEMINI_KEY_6"],
      "tasks": ["daily_plan", "hourly_schedule"], "normalize": True, "cap": 24, "max_repeats": 6}
B2 = {"label": "B2", "model": "openai/gpt-oss-20b", "provider": "groq", "keys": ["GROQ_KEY_7", "GROQ_KEY_8", "GROQ_KEY_9"],
      "tasks": ["daily_plan"], "normalize": False, "cap": 16, "max_repeats": 8}


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    os.environ["DEVMEM_EMBEDDING_MODE"] = "offline"
    from devmem.run_headless import load_runner_config  # chdir + sys.path for upstream imports
    import yaml
    import utils
    utils.MEMORY_MODE = "staged"
    utils.FAIL_LOUD_LLM = True
    import persona.prompt_template.gpt_structure as gs
    import persona.prompt_template.run_gpt_prompt as rgp
    from persona.persona import Persona
    from devmem.memory.p5_model_probe import HOURS, REF_PLAN
    from devmem.router import call_counter, key_pool, llm_router
    from devmem.router.output_normalizer import has_duration_suffix, has_exotic_space, normalize_output

    markers = load_runner_config()["bad_schedule_markers"]
    echo_re = re.compile(r"^\[.*Activity:")

    def is_echo(x):
        items = x if isinstance(x, list) else [x]
        return any(any(m in str(i) for m in markers) or echo_re.match(str(i)) for i in items)

    persona_dir = ROOT / "reverie/environment/frontend_server/storage/base_the_ville_isabella_maria_klaus/personas/Isabella Rodriguez"
    persona = Persona("Isabella Rodriguez", str(persona_dir))
    persona.scratch.curr_time = datetime.datetime(2023, 2, 13, 0, 0, 0)
    persona.scratch.daily_req = list(REF_PLAN)

    base_cfg = yaml.safe_load(open(ROOT / "devmem/config/providers.yaml", encoding="utf-8"))
    tmpdir = Path(tempfile.mkdtemp(prefix="p5_probe_v2_"))
    state = {"cur": None, "cfg": None, "normalize": False, "phase": None}
    real_call = llm_router.call_llm

    def routed(*a, **k):
        k["config_path"] = state["cfg"]  # temporary config with the rotated key list; ledger/cooldown stay the real ones
        rec = {"call_no": len(state["cur"]["calls"]) + 1, "exception": None, "raw": None, "delivered": None}
        state["cur"]["calls"].append(rec)
        conn = key_pool.get_db_connection()
        before = conn.execute("SELECT COALESCE(MAX(rowid),0) FROM llm_call_log").fetchone()[0]
        conn.close()
        try:
            out = real_call(*a, **k)
            raw = str(out)
            rec["raw"] = raw  # FULL, untruncated
            delivered = normalize_output(raw, strip_duration=True) if state["normalize"] else raw
            rec["delivered"] = delivered
            return delivered
        except call_counter.CapReached:
            state["cur"]["calls"].remove(rec)  # a call refused by the cap never happened and is not recorded
            raise
        except Exception as e:
            rec["exception"] = f"{type(e).__name__}: {str(e)[:160]}"
            raise
        finally:
            conn = key_pool.get_db_connection()
            rows = conn.execute("SELECT model, tokens_in, tokens_out FROM llm_call_log WHERE rowid > ?", (before,)).fetchall()
            conn.close()
            rec["ledger_models"] = [r["model"] for r in rows]
            rec["tokens_in"] = sum(r["tokens_in"] or 0 for r in rows)
            rec["tokens_out"] = sum(r["tokens_out"] or 0 for r in rows)
    gs.call_llm = routed

    real_safe = rgp.safe_generate_response

    def safe_spy(prompt, gpt_parameter, repeat, fail_safe_response, func_validate, func_clean_up, verbose=False):
        def v(*a, **k):
            ok = func_validate(*a, **k)
            state["cur"]["validate"].append(bool(ok))
            return ok
        return real_safe(prompt, gpt_parameter, repeat, fail_safe_response, v, func_clean_up, verbose)
    rgp.safe_generate_response = safe_spy

    def run_task(task):
        if task == "daily_plan":
            return rgp.run_gpt_prompt_daily_plan(persona, 6)[0]
        return rgp.run_gpt_prompt_generate_hourly_schedule(persona, "07:00 AM", ["sleeping"] * 7, HOURS)[0]

    def write_cfg(spec, rot):
        prov = next(p for p in base_cfg["providers"] if p["name"] == spec["provider"])
        prov = copy.deepcopy(prov)
        ks = spec["keys"][rot % len(spec["keys"]):] + spec["keys"][:rot % len(spec["keys"])]
        prov["keys"] = [{"env": e} for e in ks]
        path = tmpdir / f"{spec['label']}_{rot}.yaml"
        path.write_text(yaml.dump({"providers": [prov]}), encoding="utf-8")
        return str(path), ks[0]

    results, phases = [], {}
    t_start = time.time()
    for spec in (B1, B2):
        call_counter.reset()
        call_counter.set_cap(spec["cap"])
        os.environ["DEVMEM_PINNED_MODEL"] = spec["model"]
        state["normalize"] = spec["normalize"]
        stopped = "completed all planned invocations"
        rot = 0
        try:
            for rep in range(1, spec["max_repeats"] + 1):
                for task in spec["tasks"]:
                    state["cfg"], first_key = write_cfg(spec, rot)
                    rot += 1
                    state["cur"] = {"phase": spec["label"], "task": task, "model": spec["model"], "repeat": rep, "calls": [],
                                    "validate": [], "normalizer_applied": spec["normalize"], "first_key_env": first_key}
                    t0 = time.time()
                    try:
                        out, err = run_task(task), None
                    except call_counter.CapReached:
                        raise
                    except Exception as e:
                        out, err = None, f"{type(e).__name__}: {str(e)[:160]}"
                    cur = state["cur"]
                    cur.update({"output": out, "error": err, "seconds": round(time.time() - t0, 1)})
                    results.append(cur)
                    print(f"{spec['label']} rep {rep} {task:<16} calls {len(cur['calls'])} validate {cur['validate']} router_count {call_counter.snapshot()['count']}", flush=True)
        except call_counter.CapReached as e:
            stopped = f"router cap reached: {e}"
            cur = state["cur"]
            cur.update({"output": None, "error": "cut off by the cap", "seconds": None})
            results.append(cur)
        phases[spec["label"]] = {"model": spec["model"], "cap": spec["cap"], "router_counter": call_counter.snapshot(),
                                 "stopped": stopped, "normalizer_applied": spec["normalize"], "keys": spec["keys"]}
        print(spec["label"], "stopped:", stopped, call_counter.snapshot(), flush=True)

    # ---- metrics (live outcomes; every invocation here is its own live outcome, so all are faithful) --------------------
    def metrics(phase, task):
        rs = [r for r in results if r["phase"] == phase and r["task"] == task and r.get("error") != "cut off by the cap"]
        valid, usable, echo, clean = 0, 0, 0, 0
        for r in rs:
            out = r["output"]
            ok = any(r["validate"])
            if task == "daily_plan":
                items = [i for i in (out or [])[1:] if str(i).strip()] if isinstance(out, list) else []
                ok = ok and len(items) >= 2
                u = ok
                e = is_echo(items)
                c = ok and not e and not any(has_duration_suffix(i) or has_exotic_space(i) for i in items)
            else:
                ok = ok and isinstance(out, str) and out.strip() != ""
                u = ok
                e = ok and is_echo(out)
                c = ok and not is_echo(out) and not has_duration_suffix(out) and not has_exotic_space(out)
            valid += ok; usable += u; echo += (1 if e else 0); clean += c
        calls = sum(len(r["calls"]) for r in rs)
        return {"invocations": len(rs), "valid": valid, "usable_plan": usable if task == "daily_plan" else None,
                "echo": echo, "clean": clean, "calls": calls,
                "calls_per_valid_result": round(calls / valid, 2) if valid else None,
                "tokens_in": sum(c.get("tokens_in", 0) for r in rs for c in r["calls"]),
                "tokens_out": sum(c.get("tokens_out", 0) for r in rs for c in r["calls"]),
                "exceptions": sum(1 for r in rs for c in r["calls"] if c["exception"])}
    summary = {"B1 gemini-3.1-flash-lite (normalizer applied)": {t: metrics("B1", t) for t in B1["tasks"]},
               "B2 openai/gpt-oss-20b (no normalizer)": {t: metrics("B2", t) for t in B2["tasks"]}}
    report = {"label": "live", "seconds": round(time.time() - t_start, 1), "phases": phases, "summary": summary,
              "inputs": {"persona": "Isabella Rodriguez (base fork saved state)", "clock": "2023-02-13 00:00", "wake_hour_asked": 6,
                         "hourly_slot": "07:00 AM", "prior_schedule": "7 x sleeping", "reference_daily_req": REF_PLAN},
              "detector": {"markers": markers, "regex": "^\\[.*Activity:"},
              "note": "raw replies are FULL (untruncated); `delivered` is what upstream saw after the optional normalizer",
              "invocations": results}
    out_dir = ROOT / "docs" / "phase5_step4_artifacts"
    (out_dir / "model_probe_v2.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print(json.dumps({"phases": phases, "summary": summary}, indent=1, default=str))


if __name__ == "__main__":
    main()
