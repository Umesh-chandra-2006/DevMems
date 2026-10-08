"""
Audit of the router ledger's `purpose` tag for the upstream calls (PM rule 2026-10-08). The tag comes from a keyword heuristic on the prompt text (`gpt_structure._infer_purpose`), so a
prompt can be tagged `reflection`, `dialogue` or `planning` for a word it merely contains. Offline, from the prompts in the delivered-reply log (`raw_replies.jsonl`):

  1. every prompt is matched to the upstream prompt TEMPLATE it came from (the longest fixed text segment of a template file under persona/prompt_template/v2 and v3_ChatGPT that occurs
     in the prompt; the segments between the `!<INPUT n>!` placeholders);
  2. each template belongs to a FAMILY by what the upstream function does (the table FAMILY below, stated here so that it can be argued with): importance, reflection, dialogue, planning;
  3. for each tag, the false-match rate is the share of audited rows whose template family differs from the tag; rows that match no template are counted as unclassified, not as false.

A tag with at most 200 rows per arm is audited in full; a larger tag is audited on a random sample of 200 rows per arm drawn with the committed seed 20261008. No call, no write to a run.
"""
import json
import random
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent.parent.parent
TEMPLATE_DIRS = [ROOT / "reverie" / "reverie" / "backend_server" / "persona" / "prompt_template" / d for d in ("v3_ChatGPT", "v2")]
SEED = 20261008
SAMPLE = 200
MIN_SEGMENT = 25

FAMILY = {
    "importance": ["poignancy_chat", "poignancy_event", "poignancy_thought"],
    "reflection": ["generate_focal_pt", "insight_and_evidence", "planning_thought_on_convo", "memo_on_convo", "convo_to_thoughts", "keyword_to_thoughts"],
    "dialogue": ["agent_chat", "create_conversation", "iterative_convo", "generate_next_convo_line", "summarize_chat_ideas", "summarize_chat_relationship", "summarize_ideas",
                 "summarize_conversation", "decide_to_talk", "decide_to_react", "whisper_inner_thought"],
}
# every other template (wake up hour, daily and hourly plans, task decomposition, action location and object, event triples, emoji, keywords, bed hour, day summaries) is planning


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def family_of(template_name: str) -> str:
    base = re.sub(r"_v\d+$", "", template_name)
    for fam, names in FAMILY.items():
        if base in names:
            return fam
    return "planning"


def load_templates(dirs: List[Path] = None) -> List[Dict[str, Any]]:
    out = []
    seen = set()
    for d in (dirs or TEMPLATE_DIRS):
        if not Path(d).exists():
            continue
        for f in sorted(Path(d).glob("*.txt")):
            text = f.read_text(encoding="utf-8", errors="replace")
            segs = [_norm(s) for s in re.split(r"!<INPUT \d+>!", text)]
            segs = [s for s in segs if len(s) >= MIN_SEGMENT]
            if segs:
                out.append({"name": f.stem, "segments": segs, "family": family_of(f.stem), "weight": sum(len(s) for s in segs)})
    return out


# Ordered phrase rules (the most specific first) for the prompts the upstream code builds inline or in the JSON-adapted form (the .txt templates do not match them): the phrase is a fixed
# sentence of the prompt, the name is the upstream template/function it identifies. A rule match wins over the template match.
RULES: List[Tuple[str, str]] = [
    (r"scale of 1 to 10|likely poignancy|rate how important", "poignancy_event"),
    (r"most salient high-level questions", "generate_focal_pt"),
    (r"high-level insights", "insight_and_evidence"),
    (r"Write down if there is anything from the conversation", "memo_on_convo"),
    (r"what should .{1,60} say to .{1,60} next in the conversation", "iterative_convo"),
    (r"summarize .{1,80}relationship", "summarize_chat_relationship"),
    (r"determine whether the subject will", "decide_to_talk"),
    (r"three options that a subject", "decide_to_react"),
    (r"summarize the (key )?(ideas|conversation)", "summarize_chat_ideas"),
    (r"Turn the input into \(subject, predicate, object\)", "generate_event_triple"),
    (r"Convert an action description to an emoji", "generate_pronunciatio"),
    (r"choose an appropriate area", "action_location_sector"),
    (r"house that has the following areas", "action_location_object"),
    (r"understand the state of an object", "generate_obj_event"),
    (r"Objects available", "action_object"),
    (r"originally planned schedule", "new_decomp_schedule"),
    (r"Describe subtasks in 5 min increments", "task_decomp"),
    (r"plan today in broad-strokes", "daily_planning"),
    (r"hourly schedule", "generate_hourly_schedule"),
    (r"what hour .{0,40}wake up|wake up hour", "wake_up_hour"),
]
_RULES = [(re.compile(pat, re.I), name) for pat, name in RULES]


def classify(prompt: str, templates: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The upstream template/function a prompt came from: first by the phrase rules, then by the template whose fixed segments cover the most text of the prompt; None when neither matches."""
    prompt = _norm(prompt)
    for rx, name in _RULES:
        if rx.search(prompt):
            return {"name": name, "family": family_of(name), "by": "rule"}
    best, best_score = None, 0
    for t in templates:
        longest = max(t["segments"], key=len)
        if longest not in prompt:
            continue
        score = sum(len(s) for s in t["segments"] if s in prompt)
        if score > best_score:
            best, best_score = t, score
    return best


def audit_arm(rows: List[Dict[str, Any]], templates: List[Dict[str, Any]], tags=("planning", "dialogue", "reflection", "importance_scoring")) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for tag in tags:
        fam = "importance" if tag == "importance_scoring" else tag
        pool = [r for r in rows if r.get("purpose") == tag and r.get("prompt")]
        sampled = pool if len(pool) <= SAMPLE else random.Random(SEED).sample(pool, SAMPLE)
        n_true = n_false = n_unclassified = 0
        confusion: Dict[str, int] = {}
        examples: List[str] = []
        for r in sampled:
            t = classify(r["prompt"], templates)
            if t is None:
                n_unclassified += 1
            elif t["family"] == fam:
                n_true += 1
            else:
                n_false += 1
                confusion[t["family"]] = confusion.get(t["family"], 0) + 1
                if len(examples) < 2:
                    examples.append(f"{t['name']}: {r['prompt'][:70]!r}")
        classified = n_true + n_false
        out[tag] = {"rows_with_this_tag_in_log": len(pool), "audited": len(sampled), "sampled": len(pool) > SAMPLE, "true_family": n_true, "false_match": n_false, "unclassified": n_unclassified,
                    "false_match_rate_of_classified": round(n_false / classified, 4) if classified else None, "false_matches_belong_to": confusion, "examples": examples}
    return out


def family_counts(rows: List[Dict[str, Any]], templates: List[Dict[str, Any]], family: str = "reflection") -> Dict[str, Any]:
    """Over the WHOLE delivered-reply log (not a sample): the prompts of one upstream family by the tag the router gave them and by the upstream template."""
    out: Dict[str, Dict[str, int]] = {}
    for r in rows:
        if r.get("purpose") in ("planning", "dialogue", "reflection") and r.get("prompt"):
            t = classify(r["prompt"], templates)
            if t and t["family"] == family:
                d = out.setdefault(r["purpose"], {})
                d[t["name"]] = d.get(t["name"], 0) + 1
    return {"by_tag_and_template": out, "total": sum(sum(v.values()) for v in out.values())}


def audit(storage: Path = None, arms=("baseline", "staged"), templates: List[Dict[str, Any]] = None) -> Dict[str, Any]:
    storage = storage or ROOT / "devmem" / "storage"
    templates = templates if templates is not None else load_templates()
    res: Dict[str, Any] = {"seed": SEED, "sample_per_tag_per_arm": SAMPLE, "templates_loaded": len(templates), "family_table": FAMILY, "arms": {}}
    for arm in arms:
        f = Path(storage) / f"p7_{arm}" / "raw_replies.jsonl"
        rows = []
        if f.exists():
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    try:
                        rows.append(json.loads(line))
                    except ValueError:
                        pass
        res["arms"][arm] = {"log_rows": len(rows), "tags": audit_arm(rows, templates), "reflection_family_prompts_whole_log": family_counts(rows, templates)}
    res["note"] = "false-match rate = rows whose upstream template belongs to another family, over rows matched to a template; unclassified rows are listed apart; keyword tag from gpt_structure._infer_purpose"
    return res


def main():
    r = audit()
    (ROOT / "docs" / "phase9_purpose_tag_audit.json").write_text(json.dumps(r, indent=1), encoding="utf-8")
    for arm, v in r["arms"].items():
        for tag, x in v["tags"].items():
            print(arm, tag, {k: x[k] for k in ("rows_with_this_tag_in_log", "audited", "true_family", "false_match", "unclassified", "false_match_rate_of_classified")}, x["false_matches_belong_to"])


if __name__ == "__main__":
    main()
