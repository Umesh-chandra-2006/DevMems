"""
Offline post-processing of docs/phase5_step4_artifacts/model_probe.json (zero network, zero LLM). Adds metrics that the
live script did not compute, from the same recorded outputs, and writes model_probe_summary.json and .md.

Definitions (all stated so nothing is implied beyond the data):
  upstream_valid  : upstream's own validator accepted some attempt (a fail-safe return is NOT valid). Also requires, in the
                    live script, a plan with more than the prepended wake-up line and a non-empty hourly string.
  echo            : the schedule_check rule (configured marker, or a leading "[... Activity:").
  contaminated    : output contains "(duration in minutes" (the decomposition-format suffix), which schedule_check does not flag.
  usable_plan     : a daily plan with at least 2 non-empty items after the prepended wake-up line.
  clean_hourly    : upstream_valid, not echo, not contaminated.
"""
import json
import re
from pathlib import Path

ART = Path(__file__).resolve().parent.parent.parent / "docs" / "phase5_step4_artifacts"
d = json.loads((ART / "model_probe.json").read_text(encoding="utf-8"))
markers = d["detector"]["markers"]
echo_re = re.compile(r"^\[.*Activity:")


def echo(x):
    items = x if isinstance(x, list) else [x]
    return any(any(m in str(i) for m in markers) or echo_re.match(str(i)) for i in items)


def contaminated(x):
    items = x if isinstance(x, list) else [x]
    return any("(duration in minutes" in str(i) for i in items)


out = {"label": "offline post-processing of live probe data", "calls_counted": d["calls_counted"], "models": {}}
for m in d["models"]:
    rows = [r for r in d["invocations"] if r["model"] == m and r.get("error") != "cut off by the cap"]
    per = {}
    for task in ("wake_up_hour", "daily_plan", "hourly_schedule"):
        rs = [r for r in rows if r["task"] == task]
        e = {"invocations": len(rs), "calls": sum(len(r["calls"]) for r in rs),
             "upstream_validator_passed_some_attempt": sum(1 for r in rs if any(r["validate"])),
             "fail_safe_returned": sum(1 for r in rs if not any(r["validate"]))}
        if task == "daily_plan":
            e["usable_plan"] = sum(1 for r in rs if isinstance(r["output"], list)
                                   and sum(1 for i in r["output"][1:] if str(i).strip()) >= 2 and any(r["validate"]))
            e["validator_passed_but_empty_items"] = sum(
                1 for r in rs if any(r["validate"]) and isinstance(r["output"], list)
                and sum(1 for i in r["output"][1:] if str(i).strip()) < 2)
        if task == "hourly_schedule":
            ok = [r for r in rs if any(r["validate"]) and isinstance(r["output"], str) and r["output"].strip()]
            e["echo"] = sum(1 for r in ok if echo(r["output"]))
            e["contaminated_duration_suffix"] = sum(1 for r in ok if contaminated(r["output"]))
            e["clean_hourly"] = sum(1 for r in ok if not echo(r["output"]) and not contaminated(r["output"]))
        if task == "wake_up_hour":
            e["answers"] = [r["output"] for r in rs]
        e["tokens_in"] = sum(c.get("tokens_in", 0) for r in rs for c in r["calls"])
        e["tokens_out"] = sum(c.get("tokens_out", 0) for r in rs for c in r["calls"])
        per[task] = e
    out["models"][m] = per
    # the unfinished invocation cut off by the cap
cut = [r for r in d["invocations"] if r.get("error") == "cut off by the cap"]
out["cut_off_by_cap"] = [{"task": r["task"], "model": r["model"], "repeat": r["repeat"], "calls_used": len(r["calls"])} for r in cut]
(ART / "model_probe_summary.json").write_text(json.dumps(out, indent=1), encoding="utf-8")

lines = ["| model | wake-up valid | daily plan: validator passed / usable plans / calls | hourly: valid / echo / duration-suffix / clean / calls | tokens in / out |",
         "|---|---|---|---|---|"]
for m, per in out["models"].items():
    w, p, h = per["wake_up_hour"], per["daily_plan"], per["hourly_schedule"]
    tin = sum(x["tokens_in"] for x in per.values())
    tout = sum(x["tokens_out"] for x in per.values())
    lines.append(f"| {m} | {w['upstream_validator_passed_some_attempt']}/{w['invocations']} (answers {w['answers']}, {w['calls']} calls) | "
                 f"{p['upstream_validator_passed_some_attempt']}/{p['invocations']} / {p['usable_plan']}/{p['invocations']} / {p['calls']} | "
                 f"{h['upstream_validator_passed_some_attempt']}/{h['invocations']} / {h['echo']} / {h['contaminated_duration_suffix']} / "
                 f"{h['clean_hourly']} / {h['calls']} | {tin} / {tout} |")
(ART / "model_probe_summary.md").write_text("\n".join(lines) + f"\n\nCut off by the cap: {out['cut_off_by_cap']}\n", encoding="utf-8")
print("\n".join(lines)); print("cut off:", out["cut_off_by_cap"])
