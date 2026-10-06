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
from typing import Any, Dict, List, Optional

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


def load_autosave_interval_minutes(config_path: Path = CONFIG_PATH) -> int:
    with open(config_path, "r", encoding="utf-8") as f:
        return int(yaml.safe_load(f)["autosave_interval_sim_minutes"])


class HeadlessRunner:
    def __init__(
        self,
        fork_sim_code: str,
        sim_code: str,
        memory_mode: str = "baseline",
        autosave_interval_sim_minutes: Optional[int] = None,
        resume: bool = False,
    ):
        os.environ["MEMORY_MODE"] = memory_mode
        utils.MEMORY_MODE = memory_mode  # utils reads the env var once at import time
        self.sim_code = sim_code
        self.memory_mode = memory_mode

        if resume:
            # Re-open the saved folder in place: skip upstream's copytree(fork -> sim).
            original = _reverie_mod.copyanything
            _reverie_mod.copyanything = lambda src, dst: None
            try:
                self.rs = ReverieServer(sim_code, sim_code)
            finally:
                _reverie_mod.copyanything = original
        else:
            self.rs = ReverieServer(fork_sim_code, sim_code)
        os.makedirs(f"{utils.fs_storage}/{sim_code}/movement", exist_ok=True)

        minutes = (
            autosave_interval_sim_minutes
            if autosave_interval_sim_minutes is not None
            else load_autosave_interval_minutes()
        )
        self.autosave_interval_steps = max(1, (minutes * 60) // int(self.rs.sec_per_step))
        self.autosave_steps: List[int] = []
        self.db_path = get_db_path(sim_code)

        self.reconcile_results: List[Dict[str, Any]] = []
        self.purged_files: List[str] = []
        if resume:
            self.purged_files = self._purge_stale_step_files()
        if resume or memory_mode == "staged":
            self.reconcile_results = reconcile_run(self.rs.personas, db_path=self.db_path)

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
        except KeyboardInterrupt:
            self._save()
            return
        self._save()
