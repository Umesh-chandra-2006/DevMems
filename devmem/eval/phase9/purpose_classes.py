"""
Rule-based classes for the per-purpose breakdown of E1 and M3 (PM ruling 2026-10-08: the ledger's keyword tag is not usable for dialogue, 73 to 78 percent false matches).

Every call of an arm is classified from the PROMPT it sent, offline, no call. Classes:
  planning                        daily plan, hourly schedule, wake-up hour, task decomposition, re-planned schedule
  action_object_description       where an action happens and what it uses: area and room choice, object choice, event triple, emoji, object-state description
  dialogue                        conversation lines, whether to talk or react, relationship and idea summaries used in a conversation
  importance_scoring              the poignancy prompts (baseline: upstream; staged: persona-conditioned)
  periodic_reflection             focal-point questions and insights (upstream `run_reflect`; off in the staged arm by D1)
  post_conversation_memo          the planning-thought and memo calls after a conversation (upstream `reflect()`, outside the D1 gate: they run in both arms)
  consolidation                   Stage 3 summaries (purpose set by the code: consolidation_summary)
  identity                        Stage 4 trait generation (purpose set by the code: identity_trait)
  other                           matches no rule and no upstream template

The rules are the ordered phrase rules of `purpose_audit.RULES` (a fixed sentence of the prompt identifies the upstream function) with the table RULE_CLASS below; a prompt that no rule matches
is tried against the upstream template files, then falls to `other`. The delivered-reply log (`raw_replies.jsonl`) holds the prompts but no times; it is in call order, as is the router ledger
(`llm_call_log`, ordered by created_at), and `aligned` pairs them by position and REFUSES to proceed if the purpose and agent of the two disagree on more than 0.1 percent of positions, so every
class row carries the ledger's time and agent. Totals per arm stay the ledger's.
"""
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from devmem.eval.phase9 import purpose_audit as PA

ROOT = PA.ROOT
CLASSES = ["planning", "action_object_description", "dialogue", "importance_scoring", "periodic_reflection", "post_conversation_memo", "consolidation", "identity", "other"]
RULE_CLASS = {
    "generate_focal_pt": "periodic_reflection", "insight_and_evidence": "periodic_reflection",
    "memo_on_convo": "post_conversation_memo", "planning_thought_on_convo": "post_conversation_memo", "convo_to_thoughts": "post_conversation_memo",
    "iterative_convo": "dialogue", "decide_to_talk": "dialogue", "decide_to_react": "dialogue", "summarize_chat_relationship": "dialogue", "summarize_chat_ideas": "dialogue",
    "generate_next_convo_line": "dialogue", "create_conversation": "dialogue", "agent_chat": "dialogue", "summarize_ideas": "dialogue", "summarize_conversation": "dialogue", "whisper_inner_thought": "dialogue",
    "poignancy_event": "importance_scoring", "poignancy_chat": "importance_scoring", "poignancy_thought": "importance_scoring",
    "generate_event_triple": "action_object_description", "generate_pronunciatio": "action_object_description", "generate_obj_event": "action_object_description",
    "action_object": "action_object_description", "action_location_sector": "action_object_description", "action_location_object": "action_object_description",
    "keyword_to_thoughts": "post_conversation_memo",
}
EXPLICIT = {"consolidation_summary": "consolidation", "identity_trait": "identity"}       # purposes the code sets itself, not the keyword rule


def class_of_name(name: str) -> str:
    import re
    base = re.sub(r"_v\d+$", "", name)
    return RULE_CLASS.get(base, "planning")


def classify_prompt(prompt: str, purpose: str = "", templates: Optional[List[Dict[str, Any]]] = None) -> Dict[str, str]:
    if purpose in EXPLICIT:
        return {"class": EXPLICIT[purpose], "by": "purpose set by the code", "name": purpose}
    t = PA.classify(prompt or "", templates if templates is not None else [])
    if t is None:
        return {"class": "other", "by": "none", "name": ""}
    return {"class": class_of_name(t["name"]), "by": t.get("by", "template"), "name": t["name"]}


def aligned(arm: str, db: Path = None, storage: Path = None, since_utc: str = "2026-10-07 10:27:00", templates=None, tolerance: float = 0.001) -> Dict[str, Any]:
    """Ledger rows and delivered-reply rows paired by position; each carries created_at (UTC), agent and the class."""
    db = db or ROOT / "devmem" / "router" / "usage_log.db"
    storage = storage or ROOT / "devmem" / "storage"
    templates = PA.load_templates() if templates is None else templates
    c = sqlite3.connect(f"file:{Path(db).as_posix()}?mode=ro", uri=True)
    led = c.execute("SELECT purpose, COALESCE(agent_id,'none'), created_at FROM llm_call_log WHERE condition=? AND created_at>=? AND purpose NOT LIKE 'eval_%' ORDER BY created_at, rowid", (arm, since_utc)).fetchall()
    c.close()
    log = []
    for line in (Path(storage) / f"p7_{arm}" / "raw_replies.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                log.append(json.loads(line))
            except ValueError:
                pass
    n = min(len(led), len(log))
    bad = sum(1 for i in range(n) if led[i][0] != log[i].get("purpose") or led[i][1] != (log[i].get("agent_id") or "none"))
    if n and bad / n > tolerance:
        raise RuntimeError(f"ledger and delivered log disagree at {bad} of {n} positions: no safe pairing for {arm}")
    rows = []
    for i in range(n):
        k = classify_prompt(log[i].get("prompt", ""), log[i].get("purpose", ""), templates)
        rows.append({"created_at": led[i][2], "agent": led[i][1], "keyword_tag": led[i][0], "class": k["class"], "by": k["by"], "name": k["name"]})
    return {"arm": arm, "ledger_rows": len(led), "log_rows": len(log), "paired": n, "positions_disagreeing": bad, "rows": rows}


def class_totals(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    out = {c: 0 for c in CLASSES}
    for r in rows:
        out[r["class"]] += 1
    return {k: v for k, v in out.items()}


def keyword_vs_class(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    """For each ledger keyword tag, how its rows distribute over the classes (the audit, whole log)."""
    out: Dict[str, Dict[str, int]] = {}
    for r in rows:
        d = out.setdefault(r["keyword_tag"], {})
        d[r["class"]] = d.get(r["class"], 0) + 1
    return out
