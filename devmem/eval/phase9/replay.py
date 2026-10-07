"""
Replay controls (scorer only, no planning calls). For each event of the fixed stratified sample (devmem/eval/phase9/sample_plan.py: all 27 injected plus 273 natural events) the
scorer is run under three conditions; the staged condition reuses the run's own recorded score and costs no call:
  mismatch  = the upstream scoring prompt plus ANOTHER persona's priors block (Wolfgang Schulz, as in Phase 4 task 4.1),
  filler    = the upstream prompt plus the neutral factual filler block of Phase 4 (same text),
  baseline  = the upstream prompt alone (no priors block).
Scores are parsed with the corrected `parse_importance_score` (the same parser for every condition). The call function is injected (purpose `eval_replay`); run it only after
the arms have ended or on a key that is not in an arm's pool. This measures scoring effects only and says nothing about behavior.
"""
from typing import Any, Callable, Dict, List, Sequence, Tuple

from devmem.memory.episodic import get_upstream_prompt, parse_importance_score
from devmem.memory.priors import get_prompt_context

MISMATCH_PERSONA = "Wolfgang Schulz"
CONDITIONS = ("mismatch", "filler", "baseline")


def _filler() -> str:
    from devmem.memory.run_phase4_task4_1 import NEUTRAL_FILLER
    return NEUTRAL_FILLER


def build_prompt(condition: str, agent: str, text: str, kind: str = "event") -> str:
    upstream = get_upstream_prompt(agent, text, kind=kind)
    if condition == "mismatch":
        return f"{upstream}\n\n{get_prompt_context(MISMATCH_PERSONA)}"
    if condition == "filler":
        return f"{upstream}\n\n{_filler()}"
    if condition == "baseline":
        return upstream
    raise ValueError(condition)


def replay(events: Sequence[Tuple[str, str, str]], call_fn: Callable[[str], str], own_scores: Dict[Tuple[str, str, str], float] = None,
           conditions: Sequence[str] = CONDITIONS) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    for ev in events:
        agent, when, text = ev
        for cond in conditions:
            raw = call_fn(build_prompt(cond, agent, text))
            rows.append({"agent": agent, "sim_time": when, "text": text, "condition": cond, "score": parse_importance_score(raw), "raw_start": str(raw)[:120]})
        if own_scores and ev in own_scores:
            rows.append({"agent": agent, "sim_time": when, "text": text, "condition": "staged_own", "score": own_scores[ev], "raw_start": "recorded in the run"})
    return {"rows": rows, "summary": summarize(rows)}


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key in ("condition", "agent"):
        groups: Dict[str, List[float]] = {}
        for r in rows:
            k = r["condition"] if key == "condition" else f'{r["agent"]}|{r["condition"]}'
            groups.setdefault(k, []).append(float(r["score"]))
        out["by_" + key] = {k: {"n": len(v), "mean": round(sum(v) / len(v), 3)} for k, v in sorted(groups.items())}
    return out
