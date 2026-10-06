"""
Step A (ZERO live calls): replay the raw replies saved in docs/phase5_step4_artifacts/model_probe.json through upstream's own
parsers, with and without the output normalizer.

Method: the real upstream prompt functions run on the same persona state and inputs as the live probe. Only the model call
(`gpt_structure.call_llm`) is replaced by a stub that returns the saved raw replies of that invocation, in order. Everything
else is upstream's own code: GPT_request's completion cleanup, `safe_generate_response` (its retry loop and 5-attempt limit)
and each prompt's own validator and clean-up function. The normalizer (devmem/router/output_normalizer.py) is applied to the
stub's output, i.e. at the router/output layer, never inside upstream.

Variants:  none | spaces (Unicode spaces to ASCII space) | spaces+duration (also strips "(duration in minutes: N, minutes left: M)").

Fidelity: variant `none` is compared with what the live probe recorded (same output, same validator results) per invocation.
LIMITATION: the live probe saved each raw reply truncated to its first 500 characters. For the daily-plan prompt (replies of
about 1,000+ characters) the replay therefore parses truncated text: item counts are lower bounds and some `none` replays
may differ from the live outcome; this is reported per invocation.
"""
import datetime
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
os.environ["DEVMEM_EMBEDDING_MODE"] = "offline"
from devmem.run_headless import load_runner_config  # chdir + sys.path for upstream imports
import utils
utils.MEMORY_MODE = "staged"
import persona.prompt_template.gpt_structure as gs
import persona.prompt_template.run_gpt_prompt as rgp
from persona.persona import Persona
from devmem.memory.p5_model_probe import HOURS, REF_PLAN
from devmem.router.output_normalizer import has_duration_suffix, has_exotic_space, normalize_output

ART = ROOT / "docs" / "phase5_step4_artifacts"
VARIANTS = {"none": None, "spaces": False, "spaces+duration": True}  # value = strip_duration flag (None = no normalizer)


class RecordedRepliesExhausted(BaseException):
    pass


def main(src="model_probe.json", tag="probe_replay"):
    probe = json.loads((ART / src).read_text(encoding="utf-8"))
    markers = load_runner_config()["bad_schedule_markers"]
    echo_re = re.compile(r"^\[.*Activity:")

    def is_echo(x):
        items = x if isinstance(x, list) else [x]
        return any(any(m in str(i) for m in markers) or echo_re.match(str(i)) for i in items)

    persona_dir = ROOT / "reverie/environment/frontend_server/storage/base_the_ville_isabella_maria_klaus/personas/Isabella Rodriguez"
    persona = Persona("Isabella Rodriguez", str(persona_dir))
    persona.scratch.curr_time = datetime.datetime(2023, 2, 13, 0, 0, 0)
    persona.scratch.daily_req = list(REF_PLAN)

    def run_task(task):
        if task == "wake_up_hour":
            return rgp.run_gpt_prompt_wake_up_hour(persona)[0]
        if task == "daily_plan":
            return rgp.run_gpt_prompt_daily_plan(persona, 6)[0]
        return rgp.run_gpt_prompt_generate_hourly_schedule(persona, "07:00 AM", ["sleeping"] * 7, HOURS)[0]

    real_safe = rgp.safe_generate_response
    cur = {}

    def safe_spy(prompt, gpt_parameter, repeat, fail_safe_response, func_validate, func_clean_up, verbose=False):
        def v(*a, **k):
            ok = func_validate(*a, **k)
            cur["validate"].append(bool(ok))
            return ok
        return real_safe(prompt, gpt_parameter, repeat, fail_safe_response, v, func_clean_up, verbose)
    rgp.safe_generate_response = safe_spy
    gs.temp_sleep = lambda *a, **k: None
    from devmem.router import llm_router
    llm_router.call_llm = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("network path used in an offline replay"))

    invocations = [r for r in probe["invocations"] if r.get("error") != "cut off by the cap"]
    results = []
    for inv in invocations:
        recorded_outputs = inv["output"]
        replies = [c["raw"] for c in inv["calls"]]
        for vname, strip in VARIANTS.items():
            it = iter(replies)

            def stub(prompt, **kw):
                try:
                    raw = next(it)
                except StopIteration:
                    raise RecordedRepliesExhausted()
                return raw if strip is None else normalize_output(raw, strip_duration=strip)
            gs.call_llm = stub
            cur.clear()
            cur["validate"] = []
            exhausted = False
            try:
                out = run_task(inv["task"])
            except RecordedRepliesExhausted:
                out, exhausted = None, True
            validator_passed = any(cur["validate"])
            if inv["task"] == "wake_up_hour":
                valid = validator_passed and isinstance(out, int) and 0 <= out <= 23
                clean = valid
            elif inv["task"] == "daily_plan":
                items = [i for i in (out or [])[1:] if str(i).strip()]  # first item is the prepended wake-up line
                valid = validator_passed and len(items) >= 2
                clean = valid and not is_echo(items) and not any(has_duration_suffix(i) or has_exotic_space(i) for i in items)
            else:
                valid = validator_passed and isinstance(out, str) and out.strip() != ""
                clean = valid and not is_echo(out) and not has_duration_suffix(out) and not has_exotic_space(out)
            results.append({"model": inv["model"], "task": inv["task"], "repeat": inv["repeat"], "variant": vname,
                            "live_variant": "spaces+duration" if inv.get("normalizer_applied") else "none",
                            "replies_available": len(replies), "replies_consumed": len(replies) - sum(1 for _ in it) if not exhausted else len(replies),
                            "reply_possibly_truncated": any(len(r or "") == 500 for r in replies),
                            "recorded_live_validate": inv["validate"], "replay_validate": list(cur["validate"]),
                            "recorded_live_output": recorded_outputs, "replay_output": out, "exhausted_recorded_replies": exhausted,
                            "validator_passed": validator_passed, "valid": valid, "clean": clean,
                            "fidelity_identical_to_live": (vname == ("spaces+duration" if inv.get("normalizer_applied") else "none")
                                                           and out == recorded_outputs
                                                           and list(cur["validate"]) == inv["validate"])})

    # ---- aggregate -------------------------------------------------------------------------------------------------------
    # An invocation is FAITHFUL when the unmodified replay (variant none) reproduces the live outcome exactly; the others were
    # affected by the 500-character truncation of the saved replies and are reported separately, never silently dropped.
    faithful = {(r["model"], r["task"], r["repeat"]) for r in results
                if r["variant"] == r["live_variant"] and r["fidelity_identical_to_live"]}

    def cnt(rs):
        return {"invocations": len(rs), "validator_passed": sum(r["validator_passed"] for r in rs),
                "valid": sum(r["valid"] for r in rs), "valid_and_clean": sum(r["clean"] for r in rs),
                "exhausted_recorded_replies": sum(r["exhausted_recorded_replies"] for r in rs)}

    agg = {}
    tasks_present = [t for t in ("wake_up_hour", "daily_plan", "hourly_schedule") if any(r["task"] == t for r in results)]
    for model in sorted({r["model"] for r in results}):
        for task in tasks_present:
            row = {}
            for vname in VARIANTS:
                rs_all = [r for r in results if r["model"] == model and r["task"] == task and r["variant"] == vname]
                rs_f = [r for r in rs_all if (r["model"], r["task"], r["repeat"]) in faithful]
                row[vname] = {"all": cnt(rs_all), "faithful_only": cnt(rs_f)}
            agg[f"{model} | {task}"] = row
    fid = [r for r in results if r["variant"] == r["live_variant"]]  # the variant that matches how the live run was made
    summary = {"label": "offline replay of saved live replies through upstream's own code; zero network, zero LLM calls",
               "variants": list(VARIANTS), "aggregate": agg,
               "fidelity_variant_none": {"invocations": len(fid), "identical_to_live": sum(r["fidelity_identical_to_live"] for r in fid),
                                         "not_identical": [{"model": r["model"], "task": r["task"], "repeat": r["repeat"],
                                                            "reply_possibly_truncated": r["reply_possibly_truncated"]}
                                                           for r in fid if not r["fidelity_identical_to_live"]]},
               "limitation": ("some saved raw replies are exactly 500 characters long (truncated by the saving script); replays of those parse "
                              "truncated text" if any(r["reply_possibly_truncated"] for r in results) else
                              "no saved reply is 500 characters long: replies are full length"),
               "results": results}
    (ART / f"{tag}.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    lines = ["| model | prompt | variant | all: valid / clean of n | faithful only: valid / clean of n |", "|---|---|---|---|---|"]
    for key, row in agg.items():
        m, t = key.split(" | ")
        for v, x in row.items():
            a_, f_ = x["all"], x["faithful_only"]
            lines.append(f"| {m} | {t} | {v} | {a_['valid']} / {a_['valid_and_clean']} of {a_['invocations']} | "
                         f"{f_['valid']} / {f_['valid_and_clean']} of {f_['invocations']} |")
    (ART / f"{tag}_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print("fidelity (variant none identical to the live outcome):", summary["fidelity_variant_none"]["identical_to_live"], "of",
          summary["fidelity_variant_none"]["invocations"], "| not identical:", summary["fidelity_variant_none"]["not_identical"])


if __name__ == "__main__":
    main(*sys.argv[1:3])
