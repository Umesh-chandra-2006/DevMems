"""
Follow-up A4: pivotal-threshold (T) calibration on an authored, graded event set (docs/phase6_t_calibration_events.json).

Rule (pre-registered in docs/phase6_preregistration.md section 10, committed BEFORE any scoring): T is the smallest integer in 8 to 10
such that EVERY event labelled life_changing scores at or above T AND NO event labelled mundane or moderate scores at or above T. If no
integer qualifies, report that. The config is not changed by this script; the PM decides. `significant` events are reported but are not
part of the rule.

`decide()` is the rule (pure, tested offline). `main()` scores each event ONCE with the real persona-conditioned staged scorer on the
pinned model (cap 40 router-counted calls); run it only after the Gemini daily reset. `check_overlap()` lists every content word that
an event shares with the persona's priors (an offline check; the Phase 7 harness reuses it).
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
EVENTS = ROOT / "docs" / "phase6_t_calibration_events.json"
STOP = set("this that with from have been were will would their there which about after before while into than then them they what when where "
           "who whom whose your yours ours also such only over some more most very just like make made being does done each other another".split())


def decide(scores_by_label, candidates=(8, 9, 10)):
    """scores_by_label: {label: [scores]}. Returns the rule outcome and its evidence."""
    must = scores_by_label.get("life_changing", [])
    forbid = scores_by_label.get("mundane", []) + scores_by_label.get("moderate", [])
    out = {"min_life_changing": min(must) if must else None, "max_mundane_or_moderate": max(forbid) if forbid else None}
    ok = [t for t in candidates if must and all(s >= t for s in must) and all(s < t for s in forbid)]
    out["qualifying_integers"] = ok
    out["T"] = ok[0] if ok else None
    out["status"] = "rule applied" if ok else "no integer in 8 to 10 qualifies"
    return out


def words(text):
    return {w for w in re.findall(r"[a-z]{4,}", text.lower()) if w not in STOP}


def check_overlap(events, priors_text):
    pw = words(priors_text)
    return {e["id"]: sorted(words(e["text"]) & pw) for e in events if words(e["text"]) & pw}


def priors_text(agent):
    import yaml
    path = ROOT / "devmem" / "config" / "personas" / (agent.lower().replace(" ", "_") + ".yaml")
    return " ".join(p["statement"] for p in yaml.safe_load(open(path, encoding="utf-8"))["priors"])


def main():
    import copy
    import os
    import tempfile
    import time
    sys.path.insert(0, str(ROOT))
    spec = json.loads(EVENTS.read_text(encoding="utf-8"))
    art = ROOT / "docs" / "phase6_t_calibration_artifacts"
    art.mkdir(parents=True, exist_ok=True)
    raw_log = art / "raw_replies.jsonl"
    if raw_log.exists():
        raise SystemExit("raw_replies.jsonl already exists: the set is scored ONCE (pre-registration section 10)")
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    for k, v in (("DEVMEM_PINNED_MODEL", "gemini-3.1-flash-lite"), ("DEVMEM_OUTPUT_NORMALIZER", "on"), ("DEVMEM_RAW_REPLY_LOG", str(raw_log)),
                 ("DEVMEM_EMBEDDING_MODE", "offline"), ("SIM_CODE", "p6_t_calibration"), ("STAGE4_ENABLED", "off")):
        os.environ[k] = v
    import yaml
    from devmem.memory import episodic
    from devmem.router import call_counter, llm_router
    keys = [os.environ.get("DEVMEM_T_CAL_KEY", "GEMINI_KEY_17")]   # one fresh key with quota (24 calls); never printed
    base = yaml.safe_load(open(ROOT / "devmem/config/providers.yaml", encoding="utf-8"))
    gem = next(p for p in base["providers"] if p["name"] == "gemini")
    tmp = Path(tempfile.mkdtemp(prefix="p6_t_cal_"))
    cfgs = []
    for i in range(1):
        p = copy.deepcopy(gem)
        p["keys"] = [{"env": k} for k in keys[i:] + keys[:i]]
        f = tmp / f"rot{i}.yaml"
        f.write_text(yaml.dump({"providers": [p]}), encoding="utf-8")
        cfgs.append(str(f))
    real, n = llm_router.call_llm, {"i": 0}

    def rotating(*a, **k):
        k.setdefault("config_path", cfgs[0])
        n["i"] += 1
        return real(*a, **k)
    episodic.call_llm = rotating
    call_counter.reset()
    call_counter.set_cap(40)
    t0, results = time.time(), []
    for e in spec["events"]:
        score = episodic.score_importance_persona_conditioned(spec["agent"], e["text"], kind=spec["kind"])
        results.append({**e, "score": score})
    by = {}
    for r in results:
        by.setdefault(r["label"], []).append(r["score"])
    out = {"label": "live (pinned gemini-3.1-flash-lite, normalizer on, persona-conditioned staged prompt, one call per event)",
           "router_counter": call_counter.snapshot(), "wall_seconds": round(time.time() - t0, 1), "results": results,
           "by_label": by, "decision": decide(by), "config_changed": False, "frozen_provisional_T": 9}
    (art / "t_calibration_report.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("router_counter", "by_label", "decision")}, indent=1))


if __name__ == "__main__":
    main()
