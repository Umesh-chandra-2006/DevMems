"""
Offline count of the upstream FAIL-SAFE values (`get_fail_safe` in persona/prompt_template/run_gpt_prompt.py) that reached the simulation, per function and per arm, from the delivered-reply
log (`raw_replies.jsonl`: one row per model attempt, in call order). Upstream calls the model up to `repeat` times (5 for `safe_generate_response`, 3 for
`ChatGPT_safe_generate_response`) and returns the fail-safe value when no attempt passes its validator. Consecutive rows with the same agent and the same prompt are the attempts of one call.

  certain      = a call with exactly `repeat` attempts whose replies are all identical (an identical reply cannot be valid on the 5th attempt and invalid on the 1st);
  ambiguous    = a call with exactly `repeat` attempts whose replies differ (the last attempt may have passed; deciding needs the function's own validator);
  the totals are over the upstream function families identified by the phrase rules of purpose_audit (RULES) and exclude the router-level purposes (importance for the staged arm is
  persona-conditioned, consolidation and identity are not upstream functions).

Pre-registration section 4: a run with more than 1 percent fail-safe calls is flagged. The rate is reported against all upstream function calls and against all calls of the arm.

    python -m devmem.eval.failsafe_count
"""
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent.parent

# phrase-rule name (purpose_audit.RULES) -> (upstream function, attempts, fail-safe value upstream returns, what happens next)
FUNCTIONS = {
    "action_location_sector": ("run_gpt_prompt_action_sector", 5, "kitchen", "upstream then replaces a sector that is not accessible by the persona's living area"),
    "action_location_object": ("run_gpt_prompt_action_arena", 5, "kitchen", "no check: an arena that does not exist in the sector raises KeyError (the staged crash of 2026-10-08)"),
    "action_object": ("run_gpt_prompt_action_game_object", 5, "bed", "upstream then replaces an object that is not in the arena by a random one of its objects"),
    "generate_event_triple": ("run_gpt_prompt_event_triple / act_obj_event_triple", 5, "(name, is, idle)", "the event is stored as idle"),
    "generate_pronunciatio": ("run_gpt_prompt_pronunciatio", 3, "emoji", "a default emoji"),
    "new_decomp_schedule": ("run_gpt_prompt_new_decomp_schedule", 5, "the unchanged schedule slice", "the schedule is not revised"),
    "decide_to_talk": ("run_gpt_prompt_decide_to_talk", 5, "yes", "the decision to start a conversation is 'yes'"),
    "decide_to_react": ("run_gpt_prompt_decide_to_react", 5, "3", "option 3"),
    "task_decomp": ("run_gpt_prompt_task_decomp", 5, "asleep", "a task is decomposed as 'asleep'"),
    "poignancy_event": ("run_gpt_prompt_event_poignancy", 3, "4", "score 4 (baseline only; the staged scorer has its own parser)"),
    "generate_focal_pt": ("run_gpt_prompt_focal_pt", 3, "generic questions", "generic focal points"),
    "insight_and_evidence": ("run_gpt_prompt_insight_and_guidance", 5, "generic insights", "generic insights"),
    "iterative_convo": ("run_gpt_prompt_generate_next_convo_line", 5, "a fixed line", "a fixed utterance"),
}


def calls_of(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: List[Dict[str, Any]] = []
    cur = None
    for i, r in enumerate(rows):
        if cur and cur["prompt"] == r["prompt"] and cur["agent"] == r.get("agent_id") and i == cur["last"] + 1:
            cur["replies"].append(r.get("delivered", ""))
            cur["last"] = i
        else:
            cur = {"prompt": r["prompt"], "agent": r.get("agent_id"), "replies": [r.get("delivered", "")], "last": i, "first": i}
            groups.append(cur)
    return groups


def count(rows: List[Dict[str, Any]], classify) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    total_upstream = 0
    for g in calls_of(rows):
        t = classify(g["prompt"])
        name = t["name"] if t else None
        if name not in FUNCTIONS:
            continue
        func, repeat, fs, effect = FUNCTIONS[name]
        e = out.setdefault(name, {"function": func, "attempts_allowed": repeat, "fail_safe_value": fs, "then": effect, "calls": 0, "certain": 0, "ambiguous": 0, "first_rows": []})
        e["calls"] += 1
        total_upstream += 1
        if len(g["replies"]) == repeat:
            if len(set(g["replies"])) == 1:
                e["certain"] += 1
                if len(e["first_rows"]) < 3:
                    e["first_rows"].append(g["first"])
            else:
                e["ambiguous"] += 1
    certain = sum(v["certain"] for v in out.values())
    amb = sum(v["ambiguous"] for v in out.values())
    for v in out.values():
        v["certain_rate"] = round(v["certain"] / v["calls"], 4) if v["calls"] else None
    return {"by_function": out, "upstream_function_calls": total_upstream, "certain_fail_safe_calls": certain, "ambiguous_calls": amb,
            "rate_of_upstream_calls_certain": round(certain / total_upstream, 4) if total_upstream else None, "rate_of_upstream_calls_certain_plus_ambiguous": round((certain + amb) / total_upstream, 4) if total_upstream else None}


def main():
    sys.path.insert(0, str(ROOT))
    from devmem.eval.phase9 import purpose_audit as PA
    res = {"method": __doc__.strip().split("\n\n")[0], "arms": {}}
    for arm in ("baseline", "staged"):
        rows = [json.loads(l) for l in (ROOT / "devmem" / "storage" / f"p7_{arm}" / "raw_replies.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        r = count(rows, lambda p: PA.classify(p, []))
        r["all_attempt_rows_in_log"] = len(rows)
        r["rate_of_all_rows_certain"] = round(r["certain_fail_safe_calls"] / len(rows), 4)
        res["arms"][arm] = r
    (ROOT / "docs" / "phase9_failsafe_count.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    for arm, v in res["arms"].items():
        print(arm, {k: v[k] for k in ("upstream_function_calls", "certain_fail_safe_calls", "ambiguous_calls", "rate_of_upstream_calls_certain", "rate_of_all_rows_certain")})
        for n, e in v["by_function"].items():
            if e["certain"] or e["ambiguous"]:
                print("   ", n, {k: e[k] for k in ("calls", "certain", "ambiguous", "certain_rate")})


if __name__ == "__main__":
    main()
