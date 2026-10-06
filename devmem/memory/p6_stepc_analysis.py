"""
Step C offline analysis (zero calls). Reads the full raw-reply log (every router call of the run: prompt, raw reply, delivered text,
agent, normalizer kind) and the hourly ledger, and reports, per prompt type and per agent: instances, calls, upstream retries,
first-attempt success, 5-attempt cases, echo / duration-suffix / exotic-space / empty counts, and decomposition-format checks.

Prompt types are identified by matching the prompt against the literal lines of EVERY upstream template file (all folders under
persona/prompt_template), plus two devmem prompts. Upstream retries re-send the SAME prompt, so one INSTANCE is a run of consecutive
calls by the same agent with the same prompt text; attempts = calls in the run. attempts < 5 means upstream's validator accepted a
reply (it only retries on rejection); attempts == 5 is ambiguous (valid on the 5th attempt, or the fail-safe was returned).
No claim about reply QUALITY is made.
"""
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
ART = ROOT / "docs" / (sys.argv[1] if len(sys.argv) > 1 else "phase6_stepc_artifacts")
TEMPLATES = ROOT / "reverie/reverie/backend_server/persona/prompt_template"
sys.path.insert(0, str(ROOT))
from devmem.router.output_normalizer import STRICT_ANNOTATION as on_strict, has_duration_suffix, has_exotic_space  # noqa: E402
import yaml  # noqa: E402

markers = yaml.safe_load(open(ROOT / "devmem/config/runner.yaml", encoding="utf-8"))["bad_schedule_markers"]
echo_re = re.compile(r"^\[.*Activity:")
dur_re = re.compile(r"\(duration in minutes:\s*\d+,\s*minutes left:\s*\d+\)")


def literal_lines(path):
    text = path.read_text(encoding="utf-8", errors="ignore")
    if "<commentblockmarker>###</commentblockmarker>" in text:
        text = text.split("<commentblockmarker>###</commentblockmarker>", 1)[1]
    return [l.strip() for l in text.splitlines() if "!<INPUT" not in l and len(l.strip()) >= 20]


templates = {p.stem: literal_lines(p) for p in sorted(TEMPLATES.rglob("*.txt"))}


def classify(prompt):
    if "recorded today" in prompt and "Write ONE sentence" in prompt:
        return "consolidation_summary"
    if "core personality traits" in prompt and "poignancy" in prompt:
        return "staged_importance_scoring"  # upstream event or chat poignancy prompt plus the Stage 1 priors block
    from devmem.router.output_normalizer import prompt_kind
    k = prompt_kind(prompt)  # the three allow-listed prompts are identified exactly as the router identifies them
    if k:
        return {"wake_up_hour": "wake_up_hour", "daily_plan": "daily_planning", "hourly_schedule": "generate_hourly_schedule"}[k]
    best, best_score = "unclassified", 0.0
    for name, lines in templates.items():
        if not lines:
            continue
        total = sum(len(l) for l in lines)
        hit = sum(len(l) for l in lines if l in prompt)
        score = hit / total if total else 0.0  # coverage of the template, not absolute matched length
        if hit and score > best_score:
            best, best_score = name, score
    # collapse template version suffixes (daily_planning_v6 -> daily_planning)
    return re.sub(r"_v\d+(_.*)?$", "", best)


def entry_echo(t):
    return any(m in t for m in markers) or bool(echo_re.match(t))


rows = [json.loads(l) for l in (ART / "raw_replies.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
for i, r in enumerate(rows):
    r["call_no"] = i + 1
    r["type"] = classify(r["prompt"] or "")
    r["psha"] = hashlib.sha1((r["prompt"] or "").encode("utf-8")).hexdigest()

# instances = runs of consecutive calls with the same agent and same prompt
instances = []
for r in rows:
    if instances and instances[-1]["agent"] == r["agent_id"] and instances[-1]["psha"] == r["psha"]:
        instances[-1]["calls"].append(r)
    else:
        instances.append({"agent": r["agent_id"], "psha": r["psha"], "type": r["type"], "calls": [r]})

by_type = defaultdict(lambda: {"instances": 0, "calls": 0, "first_attempt_accepted": 0, "attempts_2_to_4": 0, "attempts_5": 0,
                               "delivered_empty": 0, "delivered_echo": 0, "delivered_duration_suffix": 0,
                               "delivered_exotic_space": 0, "decomp_format_ok": 0, "decomp_format_checked": 0,
                               "normalizer_applied_calls": 0, "raw_with_annotation": 0})
by_agent_type = defaultdict(lambda: defaultdict(lambda: {"instances": 0, "calls": 0, "first_attempt_accepted": 0, "attempts_5": 0,
                                                         "final_clean": 0}))
for inst in instances:
    t, a = inst["type"], inst["agent"] or "none"
    n = len(inst["calls"])
    s, sa = by_type[t], by_agent_type[a][t]
    for d in (s, sa):
        d["instances"] += 1
        d["calls"] += n
        d["first_attempt_accepted"] += 1 if n == 1 else 0
        d["attempts_5"] += 1 if n >= 5 else 0
    s["attempts_2_to_4"] += 1 if 2 <= n <= 4 else 0
    final = inst["calls"][-1]["delivered"] or ""
    clean = bool(final.strip()) and not entry_echo(final) and not has_duration_suffix(final) and not has_exotic_space(final)
    if t not in ("task_decomp", "new_decomp_schedule"):
        sa["final_clean"] += 1 if clean else 0
    for c in inst["calls"]:
        d = c["delivered"] or ""
        s["delivered_empty"] += 1 if not d.strip() else 0
        s["delivered_echo"] += 1 if d.strip() and entry_echo(d) else 0
        s["normalizer_applied_calls"] += 1 if c["normalizer_kind"] else 0
        s["raw_with_annotation"] += 1 if on_strict.search(c["raw"] or "") else 0
        if t in ("task_decomp", "new_decomp_schedule"):
            s["decomp_format_checked"] += 1
            s["decomp_format_ok"] += 1 if dur_re.search(d) else 0  # these prompts REQUIRE the annotation
        else:
            s["delivered_duration_suffix"] += 1 if has_duration_suffix(d) else 0
            s["delivered_exotic_space"] += 1 if has_exotic_space(d) else 0

# per-agent valid schedule rate: the three schedule-making prompts
sched_types = ("wake_up_hour", "daily_planning", "generate_hourly_schedule")
sched = {}
for a, d in by_agent_type.items():
    sched[a] = {t: dict(d[t]) for t in sched_types if t in d}

report = {"label": "offline analysis of the live Step C raw-reply log", "total_router_calls_logged": len(rows),
          "instances": len(instances), "calls_by_agent": {a: sum(1 for r in rows if (r["agent_id"] or "none") == a)
                                                         for a in sorted({(r["agent_id"] or "none") for r in rows})},
          "by_prompt_type": {k: v for k, v in sorted(by_type.items(), key=lambda kv: -kv[1]["calls"])},
          "schedule_prompts_by_agent": sched,
          "unclassified_calls": sum(1 for r in rows if r["type"] == "unclassified"),
          "models_in_log": sorted({r["model"] for r in rows})}
(ART / "step_c_analysis.json").write_text(json.dumps(report, indent=1), encoding="utf-8")

lines = ["| prompt type | instances | calls | retries (calls - instances) | first-attempt accepted | 2 to 4 attempts | 5 attempts | echo replies | duration-suffix replies | exotic-space replies | empty replies | decomposition format present | raw replies with the annotation (before the normalizer) |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
for k, v in report["by_prompt_type"].items():
    dec = f"{v['decomp_format_ok']} of {v['decomp_format_checked']}" if v["decomp_format_checked"] else "n/a"
    lines.append(f"| {k} | {v['instances']} | {v['calls']} | {v['calls'] - v['instances']} | {v['first_attempt_accepted']} | {v['attempts_2_to_4']} | "
                 f"{v['attempts_5']} | {v['delivered_echo']} | {v['delivered_duration_suffix']} | {v['delivered_exotic_space']} | {v['delivered_empty']} | {dec} | {v['raw_with_annotation']} of {v['calls']} |")
(ART / "step_c_analysis.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines))
print("\nschedule prompts by agent:")
for a, d in sched.items():
    print(a, json.dumps(d))
print("unclassified calls:", report["unclassified_calls"], "| models:", report["models_in_log"], "| calls by agent:", report["calls_by_agent"])
