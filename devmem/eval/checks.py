"""
Phase 7 run-readiness checkers (offline, no network, no LLM):

  * check_schedules(): the authored compressed-day schedules against the constraints of the approved night-key checkpoint
    (docs/phase6_night_key_checkpoint.md section 3 and docs/phase7_stop1_report.md section 1.3):
      (a) every day tiles exactly 1,440 minutes, all days of an agent have the same awake entries;
      (b) no `sleeping` entry STARTS before 12:00 and runs past it, and there is no nap: a sleeping entry may only start at 00:00 (the
          night's carry-over) or at the end of the awake window (14:00);
      (c) the awake window is 06:00 to 14:00 and the wake-up hour is 6 (the day starts asleep at 00:00 because the run starts at 00:00);
      (d) every agent has the same clock structure (same wake and sleep times: "same wake and sleep times in both arms and for all").
  * check_events(): the injected events and questions: 8 to 10 events per agent, every event inside its agent's awake window on days 1
    to 3, unique ids and unique (agent, time), required type coverage (mundane, social friction, pivotal, a repeated theme on all three
    days, a one-off), persona-neutral wording (no content word shared with the persona's priors text, the overlap script of follow-up A4),
    well-formed fact sheets, and questions that reference existing events and have checklists.
Both return a list of violation strings (empty = pass) and are used by the runner at start and by the unit tests.
"""
import json
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent.parent
SCHEDULES = ROOT / "docs" / "phase7_stop1_schedules.json"
EVENTS = ROOT / "docs" / "phase7_stop1_events_questions.json"
DAY_MIN = 1440
AWAKE_START, AWAKE_END = 6 * 60, 14 * 60
NOON = 12 * 60


def load(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _entries(day: List[List[Any]]):
    t, out = 0, []
    for desc, minutes in day:
        out.append((t, t + minutes, desc, minutes))
        t += minutes
    return out


def check_schedules(spec: Dict[str, Any] = None) -> List[str]:
    spec = spec or load(SCHEDULES)
    bad: List[str] = []
    agents = spec.get("agents", {})
    if not agents:
        return ["no agents in the schedule file"]
    structures = {}
    for name, a in agents.items():
        if a.get("wake_up_hour") != 6:
            bad.append(f"{name}: wake_up_hour must be 6, got {a.get('wake_up_hour')!r}")
        days = [k for k in sorted(a) if k.startswith("day_")]
        if len(days) != spec.get("days", 3):
            bad.append(f"{name}: expected {spec.get('days', 3)} days, found {days}")
        awake_signature = None
        for k in days:
            ent = _entries(a[k])
            total = sum(m for _, m in a[k])
            if total != DAY_MIN:
                bad.append(f"{name} {k}: entries sum to {total} minutes, not {DAY_MIN} (they must tile the clock)")
            if any(m <= 0 for _, m in a[k]):
                bad.append(f"{name} {k}: an entry has a non-positive duration")
            sleeps = [(s, e, d) for s, e, d, _ in ent if "sleep" in d.lower()]
            for s, e, d in sleeps:
                if s not in (0, AWAKE_END):
                    bad.append(f"{name} {k}: sleeping entry starts at {s // 60:02d}:{s % 60:02d}; only 00:00 and 14:00 are allowed (no nap, no sleep across noon)")
                if s < NOON < e:
                    bad.append(f"{name} {k}: a sleeping entry starts before 12:00 and runs past it")
            if sleeps and sleeps[0][0] == 0 and sleeps[0][1] != AWAKE_START:
                bad.append(f"{name} {k}: the first sleep must end at 06:00 (ends {sleeps[0][1] // 60:02d}:{sleeps[0][1] % 60:02d})")
            if not sleeps or sleeps[-1][0] != AWAKE_END or sleeps[-1][1] != DAY_MIN:
                bad.append(f"{name} {k}: the day must end with one sleeping entry from 14:00 to 24:00")
            awake = [(d, m) for s, e, d, m in ent if AWAKE_START <= s < AWAKE_END]
            if sum(m for _, m in awake) != AWAKE_END - AWAKE_START:
                bad.append(f"{name} {k}: awake entries do not fill 06:00 to 14:00")
            if awake_signature is None:
                awake_signature = awake
            elif awake != awake_signature:
                bad.append(f"{name} {k}: awake entries differ from the first day (the schedules are identical across days)")
        structures[name] = (a.get("wake_up_hour"), tuple((s, e) for s, e, d, _ in _entries(a[days[0]]) if "sleep" in d.lower())) if days else None
    if len({v for v in structures.values()}) > 1:
        bad.append(f"agents do not share the same wake and sleep times: {structures}")
    return bad


def check_events(events_spec: Dict[str, Any] = None, schedules: Dict[str, Any] = None, overlap=None, priors=None) -> List[str]:
    spec = events_spec or load(EVENTS)
    sched = schedules or load(SCHEDULES)
    bad: List[str] = []
    ev = spec["events"]
    ids = [e["id"] for e in ev]
    if len(ids) != len(set(ids)):
        bad.append("duplicate event ids")
    by_agent: Dict[str, List[Dict[str, Any]]] = {}
    for e in ev:
        by_agent.setdefault(e["agent"], []).append(e)
    for name in sched["agents"]:
        if name not in by_agent:
            bad.append(f"{name}: no events")
    for name, lst in by_agent.items():
        if not 8 <= len(lst) <= 10:
            bad.append(f"{name}: {len(lst)} events, expected 8 to 10")
        times = [(e["day"], e["time"]) for e in lst]
        if len(times) != len(set(times)):
            bad.append(f"{name}: two events at the same day and time")
        types = {e["type"] for e in lst}
        for need in ("mundane", "friction", "pivotal", "theme", "one_off"):
            if need not in types:
                bad.append(f"{name}: no {need} event")
        themes = {}
        for e in lst:
            if e["type"] == "theme":
                themes.setdefault(e["theme"], set()).add(e["day"])
        if not any(d == {1, 2, 3} for d in themes.values()):
            bad.append(f"{name}: no theme repeated on all three days")
        subjects = [(e["subject"], e["desc"]) for e in lst]
        if len(subjects) != len(set(subjects)):
            bad.append(f"{name}: identical subject and description in two events (the retention filter would swallow one)")
        for e in lst:
            hh, mm = map(int, e["time"].split(":"))
            minute = hh * 60 + mm
            if not 1 <= e["day"] <= 3:
                bad.append(f"{e['id']}: day {e['day']} outside 1 to 3")
            if not AWAKE_START <= minute < AWAKE_END:
                bad.append(f"{e['id']}: time {e['time']} is outside the awake window 06:00 to 14:00")
            fs = e.get("fact_sheet", {})
            for k in ("who", "what", "where", "when", "key_detail"):
                if not fs.get(k):
                    bad.append(f"{e['id']}: fact sheet lacks {k}")
            if e.get("rendered_memory_text") != f"{e['subject']} is {e['desc']}":
                bad.append(f"{e['id']}: rendered_memory_text is not '<subject> is <desc>'")
            if ":" in e["subject"]:
                bad.append(f"{e['id']}: the subject contains a colon (perceive splits on it)")
    if overlap is None:
        from devmem.memory import p6_t_calibration as t
        overlap, priors = t.check_overlap, t.priors_text
    for name, lst in by_agent.items():
        shared = overlap([{"id": e["id"], "text": e["rendered_memory_text"]} for e in lst], priors(name))
        for eid, words in shared.items():
            bad.append(f"{eid}: shares content words with the priors of {name}: {words}")
    known = set(ids)
    for q in spec["questions"]:
        if q["type"] == "injected" and q["event_id"] not in known:
            bad.append(f"{q['id']}: refers to unknown event {q['event_id']}")
        if q["type"] == "theme_count" and not all(x in known for x in q["event_id"].split(",")):
            bad.append(f"{q['id']}: refers to unknown events {q['event_id']}")
        if not q.get("checklist") or not all(c.get("any_of") for c in q["checklist"]):
            bad.append(f"{q['id']}: empty checklist or an item without acceptable forms")
    per_agent_q = {}
    for q in spec["questions"]:
        per_agent_q[q["agent"]] = per_agent_q.get(q["agent"], 0) + 1
    for name in sched["agents"]:
        if per_agent_q.get(name, 0) < 12:
            bad.append(f"{name}: {per_agent_q.get(name, 0)} questions, expected at least 12")
    return bad


if __name__ == "__main__":
    s, e = check_schedules(), check_events()
    print("schedule violations:", s or "none")
    print("event violations:", e or "none")
    raise SystemExit(1 if (s or e) else 0)
