"""
Key-fact checklist grader (no LLM). The rules are fixed here BEFORE any day-3 answer exists and are validated on the 30 dev-authored hand-labelled answers
(docs/phase9_grader_validation_labels.json); the agreement is printed beside every recall result and a result below 80 percent is marked uninterpretable.

Rules:
  1. Normalize: lower-case; "n't" becomes " not"; every character that is not a letter or a digit becomes a space; runs of spaces collapse.
  2. An item is matched when ANY of its `any_of` terms occurs in the normalized answer as a whole word or a whole phrase (word boundaries on both sides);
     a plural "s" or "es" after the term is accepted ("croissants" matches "croissant").
  3. Negation: an occurrence is ignored when one of {not, no, never, without, neither, nor} stands within the three tokens before it. The item is matched if at least
     one non-negated occurrence exists.
  4. Score of a question = matched items / items; strict = all items matched. An empty answer or a provider-error string scores 0 (strict False).
No synonyms beyond the authored `any_of` lists, no stemming beyond rule 2, no LLM.
"""
import re
from typing import Any, Dict, List

NEG = {"not", "no", "never", "without", "neither", "nor"}
ERROR_MARKERS = ("ChatGPT ERROR", "RESOURCE_EXHAUSTED", "HTTP 429", "HTTP 503")


def normalize(text: str) -> str:
    t = str(text or "").lower().replace("n't", " not")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", t)).strip()


def item_matched(answer: str, any_of: List[str]) -> bool:
    toks = normalize(answer).split()
    for term in any_of:
        tt = normalize(term).split()
        n = len(tt)
        if not n:
            continue
        for i in range(len(toks) - n + 1):
            window = toks[i:i + n]
            if window[:-1] == tt[:-1] and (window[-1] == tt[-1] or window[-1] in (tt[-1] + "s", tt[-1] + "es")):
                if not any(t in NEG for t in toks[max(0, i - 3):i]):
                    return True
    return False


def grade(answer: str, checklist: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not str(answer or "").strip() or any(m in str(answer) for m in ERROR_MARKERS):
        return {"items": {c["item"]: False for c in checklist}, "score": 0.0, "strict": False, "failure": True}
    items = {c["item"]: item_matched(answer, c["any_of"]) for c in checklist}
    n = sum(items.values())
    return {"items": items, "score": round(n / len(items), 4) if items else 0.0, "strict": n == len(items) and bool(items), "failure": False}


def validate(labels_doc: Dict[str, Any], questions_doc: Dict[str, Any]) -> Dict[str, Any]:
    """Agreement between the grader and the hand labels, per item and per answer, with the disagreements listed (never hidden)."""
    qs = {q["id"]: q for q in questions_doc["questions"]}
    total = agree = ans_ok = 0
    bad = []
    for e in labels_doc["entries"]:
        g = grade(e["answer"], qs[e["question_id"]]["checklist"])
        ok = True
        for item, lab in e["labels"].items():
            total += 1
            if g["items"][item] == lab:
                agree += 1
            else:
                ok = False
                bad.append({"n": e["n"], "question_id": e["question_id"], "item": item, "hand_label": lab, "grader": g["items"][item], "answer": e["answer"], "note": e["note"]})
        ans_ok += ok
    return {"items_checked": total, "items_agreeing": agree, "item_agreement": round(agree / total, 4), "answers": len(labels_doc["entries"]), "answers_fully_agreeing": ans_ok,
            "answer_agreement": round(ans_ok / len(labels_doc["entries"]), 4), "interpretable": agree / total >= 0.8, "disagreements": bad}
