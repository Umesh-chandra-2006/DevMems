"""
DevMem-Agents headless runner (Phase 5, P5.0a).

Drives the upstream ReverieServer without the Django frontend, adds:
  * autosave every `autosave_interval_sim_minutes` of simulated time (default 60) and on clean exit;
  * mirror reconciliation on load: SQLite `episodic_memory` rows whose node is absent from the
    loaded associative memory are removed (idempotent), so a reload from an older save cannot
    leave orphan rows or collide with re-executed steps.

No `reverie/` file is edited. `resume=True` re-opens a saved run in place by neutralising the
upstream folder copy (`copyanything`) for that one constructor call.
"""

import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

_BACKEND_DIR = Path(__file__).resolve().parent.parent / "reverie" / "reverie" / "backend_server"
_PROJECT_ROOT = _BACKEND_DIR.parent.parent.parent
CONFIG_PATH = Path(__file__).resolve().parent / "config" / "runner.yaml"

os.chdir(str(_BACKEND_DIR))  # upstream uses cwd-relative storage paths
for _p in (str(_BACKEND_DIR), str(_PROJECT_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import reverie as _reverie_mod  # noqa: E402
import utils  # noqa: E402
from reverie import ReverieServer  # noqa: E402
from run_baseline_sim import step_environment_bridge  # noqa: E402

from devmem.memory.episodic import get_db_path, reconcile_run  # noqa: E402


def load_runner_config(config_path: Path = CONFIG_PATH) -> Dict[str, Any]:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_autosave_interval_minutes(config_path: Path = CONFIG_PATH) -> int:
    return int(load_runner_config(config_path)["autosave_interval_sim_minutes"])


def scan_saved_schedules(sim_code: str, markers: List[str]) -> List[Dict[str, Any]]:
    """Scan the saved scratch.json of every persona for router-failure strings or model echoes
    ("[... Activity: ...]" lines) in f_daily_schedule and f_daily_schedule_hourly_org."""
    import json
    import re

    findings = []
    base = Path(f"{utils.fs_storage}/{sim_code}/personas")
    if not base.is_dir():
        return findings
    echo = re.compile(r"^\[.*Activity:")
    for persona_dir in sorted(base.iterdir()):
        f = persona_dir / "bootstrap_memory" / "scratch.json"
        if not f.exists():
            continue
        with open(f, "r", encoding="utf-8") as fh:
            scratch = json.load(fh)
        for field in ("f_daily_schedule", "f_daily_schedule_hourly_org"):
            for idx, entry in enumerate(scratch.get(field, [])):
                text = str(entry[0])
                hit = next((m for m in markers if m in text), None) or ("model_echo" if echo.match(text) else None)
                if hit:
                    findings.append({"agent": persona_dir.name, "field": field, "index": idx, "marker": hit,
                                     "text": text[:100]})
    return findings


class HeadlessRunner:
    def __init__(
        self,
        fork_sim_code: str,
        sim_code: str,
        memory_mode: str = "baseline",
        autosave_interval_sim_minutes: Optional[int] = None,
        resume: bool = False,
        final_sweep: Optional[bool] = None,
        sweep_kwargs: Optional[Dict[str, Any]] = None,
    ):
        os.environ["MEMORY_MODE"] = memory_mode
        utils.MEMORY_MODE = memory_mode  # utils reads the env var once at import time
        cfg = load_runner_config()
        os.environ["SIM_CODE"] = sim_code  # per-run storage (mirror, embedding stats) resolves from this
        utils.FAIL_LOUD_LLM = bool(cfg.get("fail_loud_llm", True))
        self.markers = list(cfg.get("bad_schedule_markers", []))
        self.sim_code = sim_code
        self.memory_mode = memory_mode
        self.schedule_findings: List[Dict[str, Any]] = []

        if resume:
            # Re-open the saved folder in place: skip upstream's copytree(fork -> sim).
            self._ensure_env_for_saved_step(sim_code)
            original = _reverie_mod.copyanything
            _reverie_mod.copyanything = lambda src, dst: None
            try:
                self.rs = ReverieServer(sim_code, sim_code)
            finally:
                _reverie_mod.copyanything = original
        else:
            self.rs = ReverieServer(fork_sim_code, sim_code)
        os.makedirs(f"{utils.fs_storage}/{sim_code}/movement", exist_ok=True)
        self._tag_agents()

        minutes = (
            autosave_interval_sim_minutes
            if autosave_interval_sim_minutes is not None
            else load_autosave_interval_minutes()
        )
        self.autosave_interval_steps = max(1, (minutes * 60) // int(self.rs.sec_per_step))
        self.autosave_steps: List[int] = []
        self.db_path = get_db_path(sim_code)
        self.should_stop: Optional[Callable[[], bool]] = None  # checked at step boundaries only
        self._write_schedule_check("not_run")

        self.reconcile_results: List[Dict[str, Any]] = []
        self.consolidation_reconcile: List[Dict[str, Any]] = []
        # D7: on clean exit, force a sweep for agents that have not swept the current night (staged only)
        self.final_sweep = (memory_mode == "staged") if final_sweep is None else final_sweep
        self.sweep_kwargs = sweep_kwargs or {}
        self.final_sweep_results: Dict[str, Any] = {}
        self.purged_files: List[str] = []
        if resume:
            self.purged_files = self._purge_stale_step_files()
        if resume or memory_mode == "staged":
            self.reconcile_results = reconcile_run(self.rs.personas, db_path=self.db_path)
            from devmem.memory.consolidation import reconcile_consolidation
            self.consolidation_reconcile = [reconcile_consolidation(p, self.db_path)
                                            for p in self.rs.personas.values()]

    @staticmethod
    def _ensure_env_for_saved_step(sim_code: str) -> None:
        """The upstream constructor reads environment/{saved step}.json, but the loop only creates the file for step N
        at the start of iteration N, so a save taken right after a step has none. Build it from movement/{N-1}.json
        exactly as the loop would."""
        import json
        sim_folder = f"{utils.fs_storage}/{sim_code}"
        with open(f"{sim_folder}/reverie/meta.json", encoding="utf-8") as f:
            saved_step = int(json.load(f)["step"])
        if saved_step > 0:
            step_environment_bridge(sim_folder, saved_step)  # no-op if the file already exists

    def _tag_agents(self) -> None:
        """Wrap each persona's move() so router calls made during it are logged with that persona's agent_id
        (instance attribute; no upstream file is touched)."""
        from devmem.router.agent_context import reset_current_agent, set_current_agent

        for persona in self.rs.personas.values():
            original = persona.move

            def tagged(*args, _orig=original, _name=persona.name, **kwargs):
                token = set_current_agent(_name)
                try:
                    return _orig(*args, **kwargs)
                finally:
                    reset_current_agent(token)

            persona.move = tagged

    def _purge_stale_step_files(self) -> List[str]:
        """After a crash, environment/{j}.json (j > saved step) and movement/{j}.json (j >= saved
        step) belong to steps that will be re-executed; the environment bridge would otherwise reuse
        the stale environment files."""
        sim_folder = Path(f"{utils.fs_storage}/{self.sim_code}")
        saved_step = int(self.rs.step)
        purged = []
        for sub, keep_upto in (("environment", saved_step), ("movement", saved_step - 1)):
            d = sim_folder / sub
            if not d.is_dir():
                continue
            for f in d.glob("*.json"):
                if f.stem.isdigit() and int(f.stem) > keep_upto:
                    f.unlink()
                    purged.append(f"{sub}/{f.name}")
        return sorted(purged)

    def _advance(self) -> None:
        """Run one upstream step (overridable for scripted tests)."""
        self.rs.start_server(1)

    def _save(self) -> None:
        if self.autosave_steps and self.autosave_steps[-1] == self.rs.step:
            return  # already saved at this step
        self.rs.save()
        self.autosave_steps.append(self.rs.step)
        self.schedule_findings = scan_saved_schedules(self.sim_code, self.markers)
        if self.schedule_findings:
            print(f"WARNING: {len(self.schedule_findings)} router-failure/model-echo entries in saved schedules")
        self._write_schedule_check("findings" if self.schedule_findings else "clean")

    def _write_schedule_check(self, status: str) -> None:
        """schedule_check.json status: not_run (no successful save yet) | clean | findings. Rewritten after every
        successful save (the scan runs on the saved scratch.json files)."""
        import json
        with open(self.db_path.parent / "schedule_check.json", "w", encoding="utf-8") as fh:
            json.dump({"status": status, "step": self.rs.step, "scans_run": len(self.autosave_steps),
                       "findings": self.schedule_findings}, fh, indent=1)

    def run(self, steps: int) -> None:
        """Run `steps` steps. Autosave when the step counter hits the interval; save on clean
        exit (including Ctrl-C). An exception propagates WITHOUT a final save (crash semantics)."""
        try:
            for _ in range(steps):
                sim_folder = f"{utils.fs_storage}/{self.sim_code}"
                if self.rs.step > 0:
                    step_environment_bridge(sim_folder, self.rs.step)
                self._advance()
                if self.rs.step % self.autosave_interval_steps == 0:
                    self._save()
                if self.should_stop is not None and self.should_stop():
                    break  # graceful stop at a step boundary; falls through to the clean-exit save
        except KeyboardInterrupt:
            self._final_sweep()
            self._save()
            return
        self._final_sweep()
        self._save()

    def _final_sweep(self) -> None:
        if not self.final_sweep:
            return
        from devmem.memory.consolidation import force_sweep
        for name, persona in self.rs.personas.items():
            self.final_sweep_results[name] = force_sweep(persona, db_path=self.db_path, **self.sweep_kwargs)
