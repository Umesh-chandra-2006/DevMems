"""
Offline replay of every recorded area-choice call (sector and arena prompts) of both arms through the validator of upstream and through the changed validator (claims ledger H28):
how many replies, and how many calls, would have been parsed differently. No call, no write to a run; output docs/phase9_arena_validator_replay.json.

    PYTHONPATH=<repo>;<repo>/reverie/reverie/backend_server python -m devmem.eval.arena_validator_replay
"""
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND = ROOT / "reverie" / "reverie" / "backend_server"


def area_options(prompt: str) -> Tuple[Optional[str], Optional[str]]:
    """(kind, options string) for a sector or arena prompt, else (None, None)."""
    p = prompt.rstrip()
    if p.endswith("should go to the following area: {"):
        m = re.findall(r"Area options: \{([^}]*)\}", prompt)
        return ("sector", m[-1]) if m else (None, None)
    if p.endswith("Answer: {"):
        m = re.findall(r"MUST pick one of \{([^}]*)\}", prompt)
        if m:
            return "arena", m[-1]
    return None, None


def old_valid(reply: str) -> bool:
    return len(reply.strip()) >= 1 and "}" in reply and "," not in reply


def make_new_valid(helper):
    def new_valid(reply: str, options: str) -> bool:
        if len(reply.strip()) < 1 or "}" not in reply:
            return False
        return "," not in reply or helper(reply, options)
    return new_valid


def outcome(valid_flags: List[bool], repeat: int = 5) -> str:
    for i, v in enumerate(valid_flags[:repeat]):
        if v:
            return f"accepted at attempt {i + 1}"
    return "fail-safe" if len(valid_flags) >= repeat else "incomplete (fewer than 5 attempts logged)"


def replay_rows(rows: List[Dict[str, Any]], helper) -> Dict[str, Any]:
    new_valid = make_new_valid(helper)
    n_rows = diff_rows = 0
    calls: List[Dict[str, Any]] = []
    cur = None
    for i, r in enumerate(rows):
        kind, opts = area_options(r.get("prompt", ""))
        if kind is None:
            continue
        reply = r.get("delivered", "") or ""
        o, n = old_valid(reply), new_valid(reply, opts)
        n_rows += 1
        diff_rows += (o != n)
        if cur and cur["prompt"] == r["prompt"] and i == cur["last"] + 1 and len(cur["old"]) < 5 and not (cur["old"] and cur["old"][-1]):
            cur["old"].append(o)
            cur["new"].append(n)
            cur["last"] = i
        else:
            cur = {"prompt": r["prompt"], "kind": kind, "agent": r.get("agent_id"), "old": [o], "new": [n], "last": i, "first_row": i, "reply_start": reply[:60]}
            calls.append(cur)
    changed = [c for c in calls if outcome(c["old"]) != outcome(c["new"])]
    return {"area_replies": n_rows, "replies_judged_differently": diff_rows, "calls": len(calls),
            "calls_with_a_different_outcome": len(changed),
            "different_calls": [{"kind": c["kind"], "agent": c["agent"], "row_in_log": c["first_row"], "upstream": outcome(c["old"]), "changed": outcome(c["new"]), "reply_start": c["reply_start"]} for c in changed]}


def main():
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    from persona.prompt_template import run_gpt_prompt as R
    out = {}
    for arm in ("baseline", "staged"):
        rows = [json.loads(l) for l in (ROOT / "devmem" / "storage" / f"p7_{arm}" / "raw_replies.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        out[arm] = {"log_rows": len(rows), **replay_rows(rows, R._devmem_comma_after_brace_ok)}
    (ROOT / "docs" / "phase9_arena_validator_replay.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    for arm, v in out.items():
        print(arm, {k: v[k] for k in ("area_replies", "replies_judged_differently", "calls", "calls_with_a_different_outcome")}, v["different_calls"])


if __name__ == "__main__":
    main()
