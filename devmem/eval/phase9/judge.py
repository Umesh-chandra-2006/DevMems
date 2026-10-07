"""
Coherence judge (pinned model, fixed rubric, one call per pair). The rubric text below is saved with every result. Parse failures are counted and never guessed.
Calibration on the 20 dev-authored pairs (docs/phase9_judge_calibration_pairs.json: 7 consistent, 7 contradictory, 6 unrelated) prints accuracy and the confusion
matrix beside every coherence result; coherence is not claimed when accuracy is below 80 percent. The call function is injected (purpose `eval_judge`).
"""
import re
from typing import Any, Callable, Dict, List, Optional

LABELS = ("consistent", "contradictory", "unrelated")
RUBRIC = (
    "You compare two answers that the same person gave to the same question on two different days.\n"
    "Choose exactly one label:\n"
    "consistent: the later answer says the same thing or something compatible with the earlier one.\n"
    "contradictory: the later answer says something that cannot be true together with the earlier one.\n"
    "unrelated: the two answers are about different things, so neither agrees nor disagrees.\n"
    "Reply with only the label, one word."
)


def build_prompt(question: str, day1: str, day3: str) -> str:
    return f"{RUBRIC}\n\nQuestion: {question}\nEarlier answer: {day1}\nLater answer: {day3}\nLabel:"


def parse_label(text: str) -> Optional[str]:
    t = re.sub(r"[^a-z]+", " ", str(text or "").lower()).split()
    found = [w for w in t if w in LABELS]
    return found[0] if len(set(found)) == 1 else None            # none, or two different labels: a parse failure, never a guess


def judge_pairs(pairs: List[Dict[str, Any]], call_fn: Callable[[str], str]) -> List[Dict[str, Any]]:
    out = []
    for p in pairs:
        raw = call_fn(build_prompt(p["question"], p["day1_answer"], p["day3_answer"]))
        out.append({**p, "judge_raw": str(raw)[:200], "judge_label": parse_label(raw)})
    return out


def calibration(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    matrix = {a: {b: 0 for b in LABELS + ("parse_failure",)} for a in LABELS}
    for r in results:
        matrix[r["label"]][r["judge_label"] or "parse_failure"] += 1
    correct = sum(matrix[l][l] for l in LABELS)
    return {"pairs": len(results), "correct": correct, "accuracy": round(correct / len(results), 4) if results else None,
            "parse_failures": sum(matrix[l]["parse_failure"] for l in LABELS), "confusion_matrix_true_by_judged": matrix, "coherence_interpretable": bool(results) and correct / len(results) >= 0.8,
            "rubric": RUBRIC}
