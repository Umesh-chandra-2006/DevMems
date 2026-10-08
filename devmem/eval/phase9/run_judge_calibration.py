"""
Judge calibration on the 20 dev-authored pairs, scheduled to run on the STAGED arm's keys only AFTER the staged arm has finished (PM rule 2026-10-08): the script polls until
eval_keys.finished("staged") is true, then makes 20 live calls (purpose eval_judge, pinned model, the staged pool, free tier, 3-key limit and the router's own backoff) and
writes devmem/storage/phase9_eval/judge_calibration.json with the accuracy, the confusion matrix and the parse failures. Until then it makes no call and uses no key. It never
touches the baseline arm's keys; if the staged arm never finishes it never runs. `--dry-run` uses a stub and makes no call.
"""
import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--poll", type=float, default=60.0)
    a = ap.parse_args()
    sys.path.insert(0, str(ROOT))
    from devmem.eval.phase9 import eval_keys, judge
    pairs = json.loads((ROOT / "docs" / "phase9_judge_calibration_pairs.json").read_text(encoding="utf-8"))["pairs"]
    out_dir = ROOT / "devmem" / "storage" / "phase9_eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    if a.dry_run:
        truth = {judge.build_prompt(p["question"], p["day1_answer"], p["day3_answer"]): p["label"] for p in pairs}
        res = judge.calibration(judge.judge_pairs(pairs, lambda prompt: truth[prompt]))
        print(json.dumps({k: res[k] for k in ("pairs", "correct", "accuracy", "parse_failures")}))
        return
    while not eval_keys.finished("staged"):
        time.sleep(a.poll)
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    from devmem.eval import run_arm
    from devmem.router import llm_router
    import os
    os.environ["DEVMEM_PINNED_MODEL"] = run_arm.MODEL
    os.environ.setdefault("DEVMEM_OUTPUT_NORMALIZER", "on")
    cfg = eval_keys.provider_config("staged", Path(tempfile.mkdtemp(prefix="p9_judge_")) / "providers.yaml")
    keys = [k["env"] for k in __import__("yaml").safe_load(open(cfg, encoding="utf-8"))["providers"][0]["keys"]]
    eval_keys.assert_no_running_arm_key(keys, [arm for arm in ("baseline",) if not eval_keys.finished(arm)])

    def call(prompt: str) -> str:
        return llm_router.call_llm(prompt, tier="fast", purpose="eval_judge", condition="eval_staged_keys", config_path=str(cfg), pinned_model=run_arm.MODEL, max_tokens=20)
    t0 = time.time()
    results = judge.judge_pairs(pairs, call)
    cal = judge.calibration(results)
    cal["started"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t0))
    cal["wall_seconds"] = round(time.time() - t0, 1)
    (out_dir / "judge_calibration.json").write_text(json.dumps({"calibration": cal, "results": results}, indent=1), encoding="utf-8")
    print(json.dumps({k: cal[k] for k in ("pairs", "correct", "accuracy", "parse_failures", "coherence_interpretable")}))


if __name__ == "__main__":
    main()
