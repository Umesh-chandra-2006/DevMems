"""
Model-qualification probe (all results LIVE). Hard cap 40 LLM calls in total, counted at gpt_structure.call_llm (the only path
these upstream prompts use) and cross-checked against the router ledger.

Runs the REAL upstream prompt functions (run_gpt_prompt_wake_up_hour, run_gpt_prompt_daily_plan,
run_gpt_prompt_generate_hourly_schedule) with Isabella Rodriguez's saved fork state (base_the_ville_isabella_maria_klaus,
clock 2023-02-13 00:00) against three pinned models, up to 3 repeats each, in the order repeat -> prompt -> model so the cap cuts
coverage evenly. No upstream file is edited; upstream's own retry loop (safe_generate_response, up to 5 attempts) is left
in place and its attempts are counted.

Inputs held fixed across models:
  * wake-up hour and daily plan: Isabella's saved scratch (iss, lifestyle, date); the plan is asked for wake-up hour 6.
  * hourly schedule: reference daily_req = upstream's own documented default plan (the daily-plan fail-safe list), prior
    schedule = 7 x "sleeping" (00:00 to 06:00), asked for the 07:00 AM slot.

Per invocation it records: calls used (including upstream retries), whether upstream's validator accepted any attempt (a
fail-safe return counts as NOT valid), the verbatim output, the echo flag (same detector as schedule_check.json: the markers
in config/runner.yaml plus a leading "[... Activity:"), exceptions, tokens (ledger).
"""
import datetime
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CAP = 40
MODELS = ["openai/gpt-oss-20b", "openai/gpt-oss-120b", "gemini-3.1-flash-lite"]
TASKS = ["wake_up_hour", "daily_plan", "hourly_schedule"]
REPEATS = 3
REF_PLAN = ["wake up and complete the morning routine at 6:00 am", "eat breakfast at 7:00 am",
            "read a book from 8:00 am to 12:00 pm", "have lunch at 12:00 pm", "take a nap from 1:00 pm to 4:00 pm",
            "relax and watch TV from 7:00 pm to 8:00 pm", "go to bed at 11:00 pm"]
HOURS = ["00:00 AM", "01:00 AM", "02:00 AM", "03:00 AM", "04:00 AM", "05:00 AM", "06:00 AM", "07:00 AM", "08:00 AM",
         "09:00 AM", "10:00 AM", "11:00 AM", "12:00 PM", "01:00 PM", "02:00 PM", "03:00 PM", "04:00 PM", "05:00 PM",
         "06:00 PM", "07:00 PM", "08:00 PM", "09:00 PM", "10:00 PM", "11:00 PM"]


class CapReached(BaseException):
    pass


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    os.environ["DEVMEM_EMBEDDING_MODE"] = "offline"  # the probe prompts use no embeddings
    from devmem.run_headless import load_runner_config  # chdir + sys.path for upstream imports
    import yaml
    import utils
    utils.MEMORY_MODE = "staged"
    utils.FAIL_LOUD_LLM = True
    import persona.prompt_template.gpt_structure as gs
    import persona.prompt_template.run_gpt_prompt as rgp
    from persona.persona import Persona
    from devmem.router import key_pool

    markers = load_runner_config()["bad_schedule_markers"]
    echo_re = re.compile(r"^\[.*Activity:")

    def entry_is_echo(text):  # exactly the schedule_check rule: a configured marker, or a leading "[... Activity:"
        t = str(text)
        return any(m in t for m in markers) or bool(echo_re.match(t))

    def is_echo(output):
        items = output if isinstance(output, list) else [output]
        return any(entry_is_echo(i) for i in items)

    persona_dir = ROOT / "reverie/environment/frontend_server/storage/base_the_ville_isabella_maria_klaus/personas/Isabella Rodriguez"
    persona = Persona("Isabella Rodriguez", str(persona_dir))
    persona.scratch.curr_time = datetime.datetime(2023, 2, 13, 0, 0, 0)
    persona.scratch.daily_req = list(REF_PLAN)

    state = {"calls": 0, "cur": None}
    real_call = gs.call_llm

    def counted(*a, **k):
        if state["calls"] >= CAP:
            raise CapReached(f"cap {CAP} reached")
        state["calls"] += 1
        conn = key_pool.get_db_connection()
        before = conn.execute("SELECT COALESCE(MAX(rowid),0) FROM llm_call_log").fetchone()[0]
        conn.close()
        rec = {"call_no": state["calls"], "exception": None, "raw": None}
        state["cur"]["calls"].append(rec)
        try:
            out = real_call(*a, **k)
            rec["raw"] = str(out)[:500]
            return out
        except Exception as e:
            rec["exception"] = f"{type(e).__name__}: {str(e)[:120]}"
            raise
        finally:
            conn = key_pool.get_db_connection()
            rows = conn.execute("SELECT model, tokens_in, tokens_out FROM llm_call_log WHERE rowid > ?", (before,)).fetchall()
            conn.close()
            rec["ledger_models"] = [r["model"] for r in rows]
            rec["tokens_in"] = sum(r["tokens_in"] or 0 for r in rows)
            rec["tokens_out"] = sum(r["tokens_out"] or 0 for r in rows)
    gs.call_llm = counted

    real_safe = rgp.safe_generate_response

    def safe_spy(prompt, gpt_parameter, repeat, fail_safe_response, func_validate, func_clean_up, verbose=False):
        def v(*a, **k):
            ok = func_validate(*a, **k)
            state["cur"]["validate"].append(bool(ok))
            return ok
        return real_safe(prompt, gpt_parameter, repeat, fail_safe_response, v, func_clean_up, verbose)
    rgp.safe_generate_response = safe_spy

    def run_task(task):
        if task == "wake_up_hour":
            return rgp.run_gpt_prompt_wake_up_hour(persona)[0]
        if task == "daily_plan":
            return rgp.run_gpt_prompt_daily_plan(persona, 6)[0]
        return rgp.run_gpt_prompt_generate_hourly_schedule(persona, "07:00 AM", ["sleeping"] * 7, HOURS)[0]

    results = []
    stopped = "completed all planned invocations"
    t_start = time.time()
    try:
        for rep in range(1, REPEATS + 1):
            for task in TASKS:
                for model in MODELS:
                    os.environ["DEVMEM_PINNED_MODEL"] = model
                    state["cur"] = {"task": task, "model": model, "repeat": rep, "calls": [], "validate": []}
                    t0 = time.time()
                    try:
                        out = run_task(task)
                        err = None
                    except CapReached:
                        raise
                    except Exception as e:  # not expected: upstream catches inside safe_generate_response
                        out, err = None, f"{type(e).__name__}: {str(e)[:120]}"
                    cur = state["cur"]
                    cur.update({"output": out, "error": err, "seconds": round(time.time() - t0, 1)})
                    results.append(cur)
                    print(f"rep {rep} {task:<16} {model:<24} calls {len(cur['calls'])} valid_any {any(cur['validate'])} total {state['calls']}", flush=True)
    except CapReached as e:
        stopped = f"cap reached: {e} (invocation in progress at the cap is recorded as incomplete)"
        if state["cur"] and state["cur"] not in results:
            state["cur"].update({"output": None, "error": "cut off by the cap", "seconds": None})
            results.append(state["cur"])

    # ---- metrics ----------------------------------------------------------------------------------------------------
    summary = {}
    for model in MODELS:
        per = {}
        for task in TASKS + ["ALL"]:
            rows = [r for r in results if r["model"] == model and (task == "ALL" or r["task"] == task)]
            complete = [r for r in rows if r.get("error") != "cut off by the cap"]
            valid = []
            for r in complete:
                ok = any(r["validate"])
                out = r["output"]
                if r["task"] == "daily_plan":
                    ok = ok and isinstance(out, list) and len(out) > 1  # the function prepends the wake-up line itself
                elif r["task"] == "hourly_schedule":
                    ok = ok and isinstance(out, str) and out.strip() != ""
                if ok:
                    valid.append(r)
            echo = [r for r in valid if is_echo(r["output"])]
            calls = sum(len(r["calls"]) for r in complete)
            per[task] = {"invocations": len(complete), "valid": len(valid),
                         "valid_rate": round(len(valid) / len(complete), 3) if complete else None,
                         "echo_among_valid": len(echo),
                         "echo_rate_among_valid": round(len(echo) / len(valid), 3) if valid else None,
                         "calls_total": calls,
                         "calls_per_valid_result": round(calls / len(valid), 2) if valid else None,
                         "tokens_in": sum(c.get("tokens_in", 0) for r in complete for c in r["calls"]),
                         "tokens_out": sum(c.get("tokens_out", 0) for r in complete for c in r["calls"]),
                         "exceptions": sum(1 for r in complete for c in r["calls"] if c["exception"])}
        summary[model] = per
    report = {"label": "live", "cap": CAP, "calls_counted": state["calls"], "stopped": stopped,
              "seconds": round(time.time() - t_start, 1), "models": MODELS, "repeats": REPEATS, "summary": summary,
              "detector": {"markers": markers, "regex": "^\\[.*Activity:"},
              "inputs": {"persona": "Isabella Rodriguez (base fork saved state)", "clock": "2023-02-13 00:00",
                         "wake_hour_asked": 6, "hourly_slot": "07:00 AM", "prior_schedule": "7 x sleeping",
                         "reference_daily_req": REF_PLAN},
              "invocations": results}
    out_f = ROOT / "docs" / "phase5_step4_artifacts"
    out_f.mkdir(parents=True, exist_ok=True)
    (out_f / "model_probe.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print(json.dumps({"calls_counted": state["calls"], "stopped": stopped, "summary": {m: summary[m]["ALL"] for m in MODELS}},
                     indent=1))


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    main()
