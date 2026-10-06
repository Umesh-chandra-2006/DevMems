"""
Authored schedules through upstream's own planning hook (Phase 7, no upstream edit).

`plan._long_term_planning` (reverie/.../cognitive_modules/plan.py:461-513) calls three module-level functions by global name:
`generate_wake_up_hour`, `generate_first_daily_plan`, `generate_hourly_schedule`, then stores `f_daily_schedule`. `install()` replaces
those three names in the `plan` module at run time with functions that return the AUTHORED values (docs/phase7_stop1_schedules.json) and
returns an `uninstall()` that restores the originals. Everything downstream is upstream's (task decomposition, action location, new-day
`revise_identity`). The clock and the date rollover are untouched. Identical for both arms: it depends only on the persona name and the
simulated date.
"""
import copy
from datetime import date
from typing import Any, Callable, Dict

NAMES = ("generate_wake_up_hour", "generate_first_daily_plan", "generate_hourly_schedule")


def install(schedules: Dict[str, Any], start_date: date, plan_module: Any = None) -> Callable[[], None]:
    if plan_module is None:
        import persona.cognitive_modules.plan as plan_module  # noqa: WPS433 (backend path is set by the runner)
    originals = {n: getattr(plan_module, n) for n in NAMES}
    agents = schedules["agents"]
    days = int(schedules.get("days", 3))

    def spec(persona):
        return agents[persona.name]

    def day_key(persona):
        d = (persona.scratch.curr_time.date() - start_date).days + 1
        return f"day_{min(max(d, 1), days)}"

    def wake(persona):
        return int(spec(persona)["wake_up_hour"])

    def daily(persona, wake_up_hour):
        return list(spec(persona)["daily_req"])

    def hourly(persona, wake_up_hour):
        return copy.deepcopy([[t, int(m)] for t, m in spec(persona)[day_key(persona)]])

    plan_module.generate_wake_up_hour = wake
    plan_module.generate_first_daily_plan = daily
    plan_module.generate_hourly_schedule = hourly

    def uninstall():
        for n, f in originals.items():
            setattr(plan_module, n, f)
    return uninstall
