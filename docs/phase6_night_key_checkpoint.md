PHASE: 6 follow-up A3, NIGHT-KEY DESIGN CHECKPOINT (design and offline tests only; NO product code changed, no live calls)
STATUS: Halting for your approval before any fix and before any follow-up run.

Labels: **synthetic** (scripted ticks on the real hook), **offline-captured** (Step D artifacts), **derived** (from reading code). No em dashes. Tests: `devmem/memory/test_night_key.py` (9 tests, all pass). Nothing in `devmem/memory/consolidation.py` was edited.

## 1. The defect

`night_id(t, 12)` (`devmem/memory/consolidation.py:108-112`) keys a sleep signal by the CURRENT tick: hour < 12 belongs to the previous night, hour >= 12 to the evening night of that day. `maybe_sweep_on_sleep` (`consolidation.py:455`-) calls it on every tick of a sleeping agent and writes a `done` marker for that night. So any tick of a sleeping agent at or after 12:00 is keyed as the evening night of that day, even if the sleep began in the morning.

**Evidence (offline-captured, Step D):** Maria and Klaus were swept at 06:00 (night 0, correct) and again at **12:00 as night 1** with 0 entries (`docs/phase6_stepd_artifacts/consolidation_log.jsonl`). The cause is the run-start artifact described in the Step D report (a `sleeping` entry starts at 06:00 and lasts its full duration, so both were still asleep at noon).

## 2. Reproduced on the real hook (**synthetic** schedules, `TestDefectReproduced`, 3 tests)

1. **Noon sleep (the Step D case):** ticks at 06:00 (night 0), 12:00 (**night 1 marker, done, 0 entries**), the agent wakes at 13:00 and logs entries, goes to sleep at 22:00: the hook returns nothing (in-memory guard); after a reload the SQLite marker returns `skipped: already swept, night 1`. The day's entries stay unconsolidated until night 2.
2. **A nap after noon (13:00):** consolidates only what existed before the nap and blocks the real night.
3. **The D7 clean-exit final sweep at 13:45 of an AWAKE agent** (`force_sweep`, used by `HeadlessRunner._final_sweep`): writes the night 1 marker and the real evening sweep is later skipped after a resume. (Step D ran with `final_sweep=False`, so it did not trigger this; Stop 3 and the Phase 5 runs ended at night time.)

## 3. Phase 7 compressed day (run starts 00:00; awake 06:00 to 14:00; asleep 14:00 to 06:00; three days) (`TestPhase7CompressedDay`, 2 tests)

Hourly ticks for 72 simulated hours on the real hook, with each day's pair of entries logged at 08:00. **The current rule is correct on this schedule:** exactly four sweeps, night 0 at 00:00 (nothing to consolidate), then one real sweep at 14:00 on each of days 1, 2 and 3 (night 1, 2, 3), each covering that day's entries (2 entries considered, 1 summary written or reinforced); the after-midnight ticks of days 2 and 3 (hour < 6) hit the existing night markers and do nothing; markers 0, 1, 2, 3 all `done`. The proposed rule (section 4) gives identical keys at all 72 ticks. Three nights give Stage 4's count path its three distinct days (graduation can occur at the night 3 sweep).

Conditions the compressed schedule must keep, and why (derived from the upstream code read for Step D, `plan.py:559-642`): (a) an authored entry starts when the previous one ends and runs its FULL duration, so the entries must sum to the clock (`sleeping` from 14:00 must be one 600-minute entry or several that tile exactly to 00:00, then 360 minutes from 00:00 to 06:00), which is why the run must start at 00:00 and not at 06:00; (b) no `sleeping` entry may begin before 12:00 and run past it, and no nap after 12:00 outside the 14:00 to 06:00 block, or the defect applies; (c) the run must end either asleep or at a time when no awake final sweep is requested (section 4.3).

## 4. Proposed fix (for approval)

### 4.1 Key the night by the START of the current sleep block, not by the current tick
`night = night_id(block_start)`, where `block_start` is remembered by the hook from the first sleeping tick after an awake tick (kept in memory on the persona) and, when it is unknown (the first tick after a reload while asleep), falls back to `persona.scratch.act_start_time` of the current action, and to the current tick if that is absent. Awake ticks clear it. The prototype in `test_night_key.py` (`SleepBlockKey`) implements exactly this.

Result on the Step D case: the 12:00 tick belongs to the block that began at 06:00, so it is night 0, whose marker already exists: no night 1 marker is written and the 22:00 sleep is night 1 as intended (`TestProposedRule`, 3 tests, including the reload fallback).

### 4.2 Effect on Phase 5 behavior
- A brute-force table over every (block start hour, current hour) pair for blocks of up to 16 hours (**synthetic**, `test_the_two_rules_differ_exactly_when_the_sleep_block_spans_a_boundary_hour`): the current rule and the proposed rule differ **if and only if** a 12:00 instant lies in (block start, current tick]: 136 of 408 pairs differ, 272 agree. A normal night (starts 12:00 to 23:59, current until 11:59 next day) never contains such an instant, so every normal night is keyed identically by both rules.
- The committed Phase 5 and Phase 6 consolidation logs (Stop 3: sweeps at 22:00 on nights 1 to 4; Step C: 06:00 night 0; the scripted Phase 5 sweeps at 22:00) contain no marker written at or after 12:00 while the block began earlier, so no past artifact changes. The Phase 5 unit tests set only `curr_time` and `act_description` (no action start), so they use the fallback and are unaffected.
- What changes: only runs in which an agent is asleep across a noon (a sleep-in, a nap spanning noon, the 06:00-start artifact). In those runs the noon marker is no longer written under the evening night.

### 4.3 The final sweep (D7) needs its own rule
An awake agent's final sweep must not claim a night that has not happened. Two options:
- **(i) Recommended:** an awake final sweep consolidates as today but writes its marker under a separate key namespace (night = minus the simulated day, for example -1), which can never collide with a real night; the Stage 4 identity step is not run for it (reported as "final sweep, no identity step"). Consolidated state at exit stays measurable (Phase 7 reports the consolidated fraction over time) and the real evening sweep still happens.
- **(ii)** Skip the final sweep for an awake agent after the boundary hour and report the number of unconsolidated entries at exit. Simpler, but the consolidated fraction at exit then excludes the last day's entries.

A sleeping agent's final sweep uses 4.1.

### 4.4 Residual risk, stated
If a sleep-in were decomposed into several consecutive `sleeping` actions, the block start is still the first one (the hook keeps it across consecutive sleeping ticks); only a reload exactly mid sleep-in would fall back to the current action's start and could mis-key a piece that begins after noon. The compressed schedule has no such block.

### 4.5 Test plan on approval (all offline)
Port the prototype into `consolidation.py` behind no flag (it is the keying rule), flip the three defect tests to assert the fixed behavior, keep the compressed-day tests and the brute-force table as they are, add a reload-mid-sleep test and a final-sweep test for the chosen option, then run the full suite (the 36 identity tests, 27 consolidation tests and 10 reconcile tests must pass unchanged). No live call.

## 5. Manual repair of the stale night-1 marker in the saved Step D state (documented; on a COPY only)

Script `devmem/memory/p6_repair_night_marker.py` (dry run by default). It deletes a `consolidation_sweeps` row only if it is an empty sweep: night 1, written at or after the boundary hour, status done, `entries_considered == 0` in the run's consolidation log, and the agent has no semantic row and no consolidated flag. Test `TestManualRepairOnACopy` runs it on a temporary copy of the real Step D mirror: the dry run lists exactly Maria's and Klaus's 12:00 night 1 rows, apply removes only those, the night 0 rows (06:00) stay, a second apply is a no-op and the original artifact is unchanged.

Procedure for a resume (on copies; the worktree run in `D:\DevMems_stepd` is never edited):
1. Copy the saved simulation folder (`reverie/environment/frontend_server/storage/p6_step_d_gemini`) and the run folder (`devmem/storage/p6_step_d_gemini`) to a new sim code, for example `p6_step_d_gemini_repaired`.
2. `python devmem/memory/p6_repair_night_marker.py --db devmem/storage/p6_step_d_gemini_repaired/memory.db --log devmem/storage/p6_step_d_gemini_repaired/consolidation_log.jsonl` (dry run), then again with `--apply`.
3. Resume with `HeadlessRunner(..., resume=True)` on the copy. (`reconcile_consolidation` on resume does not remove the noon rows because their sweep time, 12:00, is earlier than the saved clock, 13:45.)

**Important:** the repair alone is not enough under the current rule. Maria's `sleeping 540` entry runs until 15:00, so on resume at 13:45 the first tick (the in-memory guard is not saved) would key her as night 1 again and re-create the marker. The repaired state is only safe to resume WITH the fix in 4.1 (her action started at 06:00, so her key stays night 0, which exists). Klaus is awake after 13:00 and is unaffected.

## 6. Decisions requested

1. Approve the keying rule in 4.1 (block start, with the `act_start_time` fallback).
2. Choose the final-sweep rule: 4.3 (i), 4.3 (ii), or another.
3. Confirm that the compressed-day conditions in section 3 (a to c) are the schedule constraints for Phase 7 (they go into the Phase 7 Stop 1 design).
4. Confirm that no follow-up natural run (Step D resume or a new run) starts before this fix is in and tested.

REQUEST: Approval or changes on the four points. Halting; no code change to the hook until you approve.
