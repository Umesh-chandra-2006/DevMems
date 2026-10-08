"""
Key guard for the Phase 9 evaluation calls (PM rule 2026-10-08): an evaluation call may use ONLY keys of an arm whose run has FINISHED. It can never use a key from the pool of an arm
that is still running, and it never uses a paid key. The pool of an arm is run_arm.ARM_KEYS[arm] plus the keys added to it through extra_keys.json (the pilot keys).

`finished(arm)` is true only when the arm's run_status.json state starts with "finished: " followed by a final outcome AND no run_arm or supervisor process for the arm exists.
`pool(arm)` raises if the arm is not finished. `provider_config(arm, path)` writes a temporary provider config with only that arm's pool (Gemini, the pinned model, the free-tier
per-key cap of 450 per quota day) for the router call function used by the evaluation steps. Keys are handled by NAME only.
"""
import copy
import json
from pathlib import Path
from typing import Callable, List, Optional

import yaml

from devmem.eval import run_arm, supervisor

ROOT = Path(__file__).resolve().parent.parent.parent.parent


class ArmStillRunning(RuntimeError):
    pass


def finished(arm: str, root: Path = ROOT, procs: Optional[List[str]] = None) -> bool:
    run_dir = Path(root) / "devmem" / "storage" / f"p7_{arm}"
    try:
        state = str(json.loads((run_dir / "run_status.json").read_text(encoding="utf-8")).get("state", ""))
    except Exception:
        return False
    if not (state.startswith("finished: ") and state[len("finished: "):].startswith(supervisor.FINAL_PREFIXES)):
        return False
    if procs is None:
        from devmem.eval import arm_health
        procs = arm_health._processes()
    return not any(f"--arm {arm}" in line for line in procs)


def pool(arm: str, root: Path = ROOT, procs: Optional[List[str]] = None) -> List[str]:
    """The chat keys evaluation may use for work on this arm's data: the arm's own pool, and only once that arm has finished."""
    if not finished(arm, root, procs):
        raise ArmStillRunning(f"the {arm} arm has not finished: none of its keys may be used for evaluation")
    return list(run_arm.ARM_KEYS[arm]) + run_arm.load_extra_keys(Path(root) / "devmem" / "storage" / f"p7_{arm}", arm)


def assert_no_running_arm_key(keys: List[str], running_arms: List[str]) -> None:
    """Belt and braces for any call function: refuse when any key belongs to the pool of an arm that is still running."""
    for arm in running_arms:
        mine = set(run_arm.ARM_KEYS[arm]) | set(run_arm.load_extra_keys(ROOT / "devmem" / "storage" / f"p7_{arm}", arm))
        clash = sorted(k.split("_")[-1] for k in keys if k in mine)
        if clash:
            raise ArmStillRunning(f"key index(es) {clash} belong to the still-running {arm} arm")


def provider_config(arm: str, path: Path, root: Path = ROOT, procs: Optional[List[str]] = None) -> Path:
    keys = pool(arm, root, procs)
    base = yaml.safe_load(open(Path(root) / "devmem" / "config" / "providers.yaml", encoding="utf-8"))
    gem = copy.deepcopy(next(p for p in base["providers"] if p["name"] == "gemini"))
    gem["keys"] = [{"env": k} for k in keys]
    gem["model_limits"][run_arm.MODEL]["rpd"] = run_arm.PER_KEY_CAP
    gem["daily_limit_fast"] = run_arm.PER_KEY_CAP
    Path(path).write_text(yaml.dump({"providers": [gem]}), encoding="utf-8")
    return Path(path)
