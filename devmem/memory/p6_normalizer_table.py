"""
Builds the normalizer evidence table (offline, zero live calls) and writes docs/phase6_stepc2_artifacts/normalizer_prompt_table.{json,md}:

  1. every upstream template in the call path, rendered from the real template file: stripped yes/no and why;
  2. the saved live Step C replies replayed through the REAL router wiring and upstream's REAL functions and validators, with the LIVE
     prompt text (not a rebuilt one), flag off vs on: valid before and after;
  3. synthetic checks (labelled synthetic) for the other stripped prompt functions.

The call path here is "every template referenced by upstream's run_gpt_prompt.py" plus the two devmem prompts (staged scoring and
consolidation summary). Templates upstream cannot read on this machine (cp1252 default encoding) are marked: the live path cannot reach them.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from devmem.memory import consolidation, episodic  # noqa: E402
from devmem.memory import p6_normalizer_harness as h  # noqa: E402
from devmem.router import output_normalizer as on  # noqa: E402

ART = ROOT / "docs" / "phase6_stepc2_artifacts"
VETO_NAME_PARTS = ("task_decomp", "new_decomp_schedule")


def template_rows():
    rows = []
    for path, rendered in h.render_all_templates().items():
        vetoed = on.vetoed(rendered)
        kind = on.prompt_kind(rendered)
        name = Path(path).stem
        expected_veto = any(part in name for part in VETO_NAME_PARTS)
        if vetoed:
            why = "decomposition prompt: its parser reads the annotation (run_gpt_prompt.py lines 374 and 381); reply returned untouched"
        elif kind:
            why = f"{kind}: Unicode spaces mapped (original scope) and the annotation stripped"
        else:
            why = "call path, not decomposition: the annotation is stripped, nothing else is changed"
        rows.append({"template": path, "upstream_can_read_it_here": h.upstream_can_read(path), "stripped": not vetoed,
                     "veto_expected_from_name": expected_veto, "veto_matches_expectation": vetoed == expected_veto, "why": why})
    # the two devmem prompts in the simulation call path
    staged = episodic.build_staged_prompt("Isabella Rodriguez", "Isabella argued with a neighbor", kind="event")
    summary = consolidation.SUMMARIZATION_PROMPT_TEMPLATE.format(persona_context="priors", agent_name="Isabella Rodriguez",
                                                                  cluster_entries="- a")
    for name, text in (("devmem staged importance scoring prompt", staged), ("devmem consolidation summary prompt", summary)):
        rows.append({"template": name, "upstream_can_read_it_here": True, "stripped": not on.vetoed(text),
                     "veto_expected_from_name": False, "veto_matches_expectation": not on.vetoed(text),
                     "why": "call path, not decomposition: the annotation is stripped, nothing else is changed"})
    return rows


def _instances(rows):
    inst, last = [], None
    for r in rows:
        if inst and inst[-1]["agent"] == r["agent_id"] and inst[-1]["prompt"] == r["prompt"]:
            inst[-1]["raw"].append(r["raw"])
        else:
            inst.append({"agent": r["agent_id"], "prompt": r["prompt"], "raw": [r["raw"]]})
    return inst


def stepc_replays():
    log = [json.loads(l) for l in (ROOT / "docs/phase6_stepc_artifacts/raw_replies.jsonl").read_text(encoding="utf-8").splitlines()]
    factories = {"wake_up_hour": h.fn_wake_up, "daily_plan": h.fn_daily_plan, "hourly_schedule": h.fn_hourly,
                 "action_sector": h.fn_sector, "action_arena": h.fn_arena, "task_decomp": None}
    out = []
    for inst in _instances(log):
        p = inst["prompt"]
        if "Hourly schedule format:" in p:
            kind = "hourly_schedule"
        elif "plan today in broad-strokes" in p:
            kind = "daily_plan"
        elif "wake up hour:" in p:
            kind = "wake_up_hour"
        elif "Describe subtasks in 5 min increments" in p:
            kind = "task_decomp"
        elif "following area in" in p and "MUST pick one of" in p:
            kind = "action_arena"
        else:
            kind = "action_sector"
        rec = {"prompt_type": kind, "live_replies": len(inst["raw"]), "stripped_by_rule": not on.vetoed(p)}
        if kind == "task_decomp":
            # the veto prompt: its reply must come back identical with the flag on or off
            rec["reply_identical_flag_on_vs_off"] = True
            rec["note"] = "veto set: verified through the router in test_normalizer_call_path, not replayed through upstream (state-dependent)"
            out.append(rec)
            continue
        fn = factories[kind]()
        off = h.run_upstream(fn, inst["raw"], False, live_prompt=p)
        on_ = h.run_upstream(fn, inst["raw"], True, live_prompt=p)
        rec.update({"prompt_equals_live_prompt": off["prompt_seen"] == p and on_["prompt_seen"] == p,
                    "before": {"validate": off["validate"], "attempts": off["attempts"], "result": off["result"], "error": off["error"]},
                    "after": {"validate": on_["validate"], "attempts": on_["attempts"], "result": on_["result"], "error": on_["error"]},
                    "delivered_after_has_annotation": any(on.STRICT_ANNOTATION.search(str(d)) for d in on_["delivered"])})
        out.append(rec)
    return out


def synthetic_checks():
    out = []
    for name, factory, form, value in h.SYNTHETIC:
        fn = factory()
        clean, annotated = h.synthetic_replies(form, value)
        c = h.run_upstream(fn, [clean] * 5, False)
        off = h.run_upstream(fn, [annotated] * 5, False)
        on_ = h.run_upstream(fn, [annotated] * 5, True)
        out.append({"function": name, "reply_form": form, "label": "synthetic",
                    "clean_result": c["result"], "annotated_flag_off": {"result": off["result"], "attempts": off["attempts"], "error": off["error"]},
                    "annotated_flag_on": {"result": on_["result"], "attempts": on_["attempts"], "error": on_["error"]},
                    "flag_on_equals_clean": on_["result"] == c["result"],
                    "flag_off_equals_clean": off["result"] == c["result"] and off["error"] is None})
    return out


def build():
    return {"label": "offline; zero live calls", "templates": template_rows(), "stepc_replays": stepc_replays(),
            "synthetic_validator_checks": synthetic_checks()}


def write(result):
    ART.mkdir(parents=True, exist_ok=True)
    (ART / "normalizer_prompt_table.json").write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
    lines = ["## 1. Rendered upstream prompts in the call path (from the real template files)", "",
             "| template | readable by upstream on this machine | stripped | why |", "|---|---|---|---|"]
    for r in result["templates"]:
        lines.append(f"| {r['template']} | {'yes' if r['upstream_can_read_it_here'] else 'no (cp1252)'} | {'yes' if r['stripped'] else 'NO (veto)'} | {r['why']} |")
    lines += ["", "## 2. Saved live Step C replies replayed (live prompt, real upstream function and validator, real router wiring)", "",
              "| prompt type | live replies | stripped | prompt equals live prompt | before: validator results, attempts, result | after: validator results, attempts, result |",
              "|---|---|---|---|---|---|"]
    for r in result["stepc_replays"]:
        if "before" not in r:
            lines.append(f"| {r['prompt_type']} | {r['live_replies']} | NO (veto) | n/a | annotation kept | annotation kept |")
        else:
            b, a = r["before"], r["after"]
            lines.append(f"| {r['prompt_type']} | {r['live_replies']} | yes | {r['prompt_equals_live_prompt']} | {b['validate']}, {b['attempts']}, {str(b['result'])[:40]!r} {b['error'] or ''} | "
                         f"{a['validate']}, {a['attempts']}, {str(a['result'])[:40]!r} {a['error'] or ''} |")
    lines += ["", "## 3. Synthetic validator checks (label: synthetic)", "",
              "| function | reply form | clean result | annotated, flag off | annotated, flag on | on equals clean |", "|---|---|---|---|---|---|"]
    for r in result["synthetic_validator_checks"]:
        lines.append(f"| {r['function']} | {r['reply_form']} | {str(r['clean_result'])[:30]!r} | {str(r['annotated_flag_off']['result'])[:30]!r} {r['annotated_flag_off']['error'] or ''} | "
                     f"{str(r['annotated_flag_on']['result'])[:30]!r} | {r['flag_on_equals_clean']} |")
    (ART / "normalizer_prompt_table.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return "\n".join(lines)


if __name__ == "__main__":
    print(write(build()))
