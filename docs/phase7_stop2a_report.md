PHASE: 7, STOP 2a (run-readiness, offline). Pre-launch item P4.
STATUS: Complete for Stop 2a. Halting for review. NO LAUNCH has been started. No live call was made in this stop (the only live use before the reset was the key verification, reported separately).

Labels: **synthetic** (stubbed LLM or scripted step body), **offline-captured**, **derived**. Real upstream classes are used wherever integration is claimed (stated per test). No em dashes.

## 1. WHAT WAS BUILT (`devmem/eval/`, no upstream edit)

| Piece | File | What it does |
|---|---|---|
| Schedule checker, event checker | `checks.py` | schedules tile 1,440 minutes, wake hour 6, awake window 06:00 to 14:00, no `sleeping` entry that starts before 12:00 and runs past it, no nap (sleeping entries only at 00:00 and 14:00), same structure for every agent and day; events: 8 to 10 per agent, inside the awake window, unique times, required types, a theme repeated on all three days, persona-neutral wording (the overlap script of A4), fact sheets, questions reference real events. `python -m devmem.eval.checks` prints "none" for both on the authored files |
| Authored schedules through the plan functions | `authored_plan.py` | runtime replacement of `generate_wake_up_hour`, `generate_first_daily_plan` and `generate_hourly_schedule` in `persona.cognitive_modules.plan` (the three names `_long_term_planning` calls); an `uninstall()` restores them |
| Event injector | `injector.py` | adds each due event to the persona's OWN current tile with upstream's `maze.add_event_from_tile` at the first step boundary at or after its time, removes it six steps later, and writes one line per event to `injection_log.jsonl`: planned and injected time and step, tile, asleep or not, **PASS or FAIL for "perceived and stored"**, node id, the importance the arm gave it |
| Quota pause | `quota_gate.py` | wraps every `call_llm` use (and the embedding store): when all arm keys are at the per-key cap or the pinned model is locked out, the process PAUSES until the next 07:00 UTC reset (about 12:30 IST) plus a margin and retries the SAME call; bounded retries for other pinned failures; an `ABORT` file ends a pause; it never calls another model |
| Run support | `run_support.py` | `make_checkpoint` (copy of personas, reverie meta, that step's environment file and an SQLite-backup copy of `memory.db`), `LedgerWindows` (one record per simulated hour from the ONE ledger, by purpose and agent, filtered by arm, plus the fraction of steps asleep), atomic `run_status.json` |
| The arm runner | `run_arm.py` | one arm as one process; `--dry-run` runs every offline check and prints the plan; `--resume` re-opens the last autosave once; see section 3 |
| Canary and abort criteria | `canary.py` | `evaluate()` for the first 20 minutes and the written abort criteria A1 to A9 (section 4); `compare_injections()` across arms |
| Router quota day (the one router change) | `devmem/router/key_pool.py` `get_today_str()` | see Deviations |

Movement files and the simulation folder: upstream writes `movement/{step}.json` and the saved personas at every autosave; the runner does not purge them (the Step D folder held 2,791 movement files). The recording is consistent at every autosave: the mirror database is written immediately (it can run slightly ahead of the last autosave between saves; a viewer reads the saved sim folder and the movement files up to the last autosave).

## 2. TESTS (all offline; `docs/phase7_stop2a_artifacts/full_suite_output.txt`, verbatim)

```
=== devmem.router.test_router
Ran 33 tests in 3.752s
OK
=== devmem.router.test_call_counter
Ran 4 tests in 2.009s
OK
=== devmem.router.test_output_normalizer
Ran 4 tests in 0.000s
OK
=== devmem.router.test_normalizer_wiring
Ran 8 tests in 2.286s
OK
=== devmem.router.test_normalizer_rule
Ran 9 tests in 0.221s
OK
=== devmem.router.test_normalizer_call_path
Ran 7 tests in 5.872s
OK
=== devmem.memory.test_priors
Ran 9 tests in 2.031s
OK
=== devmem.memory.test_episodic
Ran 11 tests in 1.768s
OK
=== devmem.memory.test_reconcile
Ran 10 tests in 55.273s
OK
=== devmem.memory.test_gpt_structure_touch
Ran 5 tests in 0.094s
OK
=== devmem.memory.test_consolidation
Ran 27 tests in 7.869s
OK (skipped=1)
=== devmem.memory.test_identity
Ran 36 tests in 77.150s
OK
=== devmem.memory.test_night_key
Ran 13 tests in 2.277s
OK
=== devmem.memory.test_t_calibration
Ran 7 tests in 0.054s
OK
=== devmem.embeddings.test_vector_store
Ran 14 tests in 1.230s
OK (skipped=1)
=== devmem.demo.test_demo
Ran 2 tests in 0.074s
OK
=== devmem.api.test_store
Ran 22 tests in 2.797s
OK
=== devmem.api.test_api_http
Ran 6 tests in 0.000s
OK (skipped=6)
=== devmem.eval.test_run_readiness
Ran 27 tests in 59.106s
OK
=== devmem.eval.test_run_arm_smoke
Ran 1 test in 9.025s
OK
=== devmem.api.test_api_http (system Python 3.13 with fastapi, httpx)
Ran 6 tests in 1.342s
OK
```

Count: 249 tests run and passing in the project venv (2 live-gated tests and the 6 API HTTP tests are skipped there), plus the 6 API HTTP tests passing under Python 3.13. Before this round 217; the additions are the night-key tests (13 against the earlier 9, +4), the linkage and A4 tests already counted, and the 28 new `devmem/eval` tests.

New this stop: `devmem/eval/test_run_readiness.py` (27) and `devmem/eval/test_run_arm_smoke.py` (1), plus the night-key and linkage tests of the pre-launch report. What they prove, with the real classes:
- **Checkers (synthetic mutations of the real authored files):** the real files pass; non-tiling, a sleep across noon (the Step D artifact), a nap, a wrong wake hour, differing days, a different sleep structure, a priors-word overlap, an event outside the awake window, a missing pivotal type, an extra event, a missing fact-sheet field, an unknown question target, two events at one time and a theme missing a day are each detected.
- **Authored plan on the REAL `plan._long_term_planning` with real Personas:** for all three agents and days 1 to 3 the stored `f_daily_schedule` equals the authored list (1,440 minutes), `daily_req` is the authored one, and a mock that fails on any LLM call is never called; upstream's own `get_f_daily_schedule_index` picks `sleeping` at 00:00, 05:59, 14:00 and 23:59 and the authored awake entries at 06:00, 08:00 and 13:59; uninstall restores the originals.
- **Injector on the REAL `Maze` and the REAL `perceive()` with real Personas:** all 27 events are perceived, stored verbatim (`"<subject> is <desc>"`), scored (staged scorer 6, baseline poignancy 5, LLM stubbed: synthetic) and then removed from the tile, in BOTH arms; the injection step is identical in both arms (the first step boundary at or after the authored time); an event nobody perceives gets a FAIL line after six steps and is removed; a sleeping agent at injection is recorded; a resume skips logged events.
- **Quota pause:** with the real router exception classes: all keys at the cap pauses about 7,320 simulated seconds to the 07:00 UTC reset and retries the identical call; a provider lockout of 4,000 s is waited out; generic failures are retried a bounded number of times then re-raised; other exceptions and the call cap pass through; the ABORT file ends a pause; the embedding store is wrapped the same way.
- **Quota day and key plan:** the quota day default is unchanged (local date), the env gate moves the boundary to the reset hour; the two arm key sets are disjoint, verified chat keys, 7 each, no Groq or NIM, no GEMINI_KEY_9; the plan matches the launch spec; `--dry-run` creates nothing; the two checkpoint steps (day 1 and day 3 at 14:00, steps 5,040 and 22,320) are multiples of the 90-step autosave, so a checkpoint is always taken at an autosave.
- **Checkpoint and windows:** a checkpoint copy built from a saved base simulation folder holds personas, meta, one environment file and an independent consistent database, and no movement files; the ledger windows split by hour, exclude the other arm's rows and record sleeping fractions.
- **Canary:** a synthetic clean run passes all checks; each abort criterion A2 to A7 fires on its own violation; the cross-arm injection comparison flags a differing step.
- **The REAL `run_arm.main()` smoke (`test_run_arm_smoke`):** scripted step body, dummy key placeholders, zero calls: 720 steps, the four ledger windows, a checkpoint at the autosave of step 360 with its database copy, `run_status.json`, the report, the autosave steps 90, 180, 270, kept movement files, plan functions restored.

## 3. THE LAUNCH PLAN (for your approval; frozen items marked)

| Item | Setting |
|---|---|
| Processes | two, in parallel: `python -m devmem.eval.run_arm --arm baseline` and `--arm staged` |
| Model | `gemini-3.1-flash-lite` pinned for both, normalizer on, raw-reply log on, real embeddings (cache first, fail loud) |
| Chat keys (disjoint) | baseline: GEMINI_KEY_1, 2, 4, 5, 6, 8, 10; staged: GEMINI_KEY_11 to 17. **7 and 7**, not 7 and 8: only 14 chat-capable keys are verified (GEMINI_KEY_3 was verified for embeddings only; one chat call would make it a 15th key and give an 8/7 split; say if you want that call) |
| Assignment mechanism | per-arm temporary provider configs written outside the repo (only `gemini`, only that arm's keys, rotated): no router change for the key sets |
| Per-key daily cap | 450 requests (the `rpd` of the arm's config); with 7 keys that is 3,150 calls per arm per quota day |
| Quota day and pause | `DEVMEM_QUOTA_RESET_UTC_HOUR=7` (about 12:30 IST); exhausted: pause until the reset, resume the same call |
| Caps | per-arm hard cap 9,500 router-counted calls; soft stop at a step boundary after 8,500; autosave every 15 simulated minutes |
| Clock and span | start 2023-02-13 00:00, three compressed days, end 2023-02-16 00:00 |
| Checkpoints | copies at the end of the day 1 and day 3 awake windows (14:00) |
| Arm S | `STAGE4_ENABLED` on, `IDENTITY_FEEDBACK` on, Stage 3 with the frozen average 0.82 clustering; the night-key fix in force |
| Arm B | baseline memory (priors as atomic nodes); upstream reflection stays on (decision D1, disclosed) |
| Evaluation | not part of the runs; it runs later on the checkpoint copies |
| Expected duration | derived: 9,000 calls per arm at about 6 calls per minute is about 25 hours of calls, but 3,150 calls per arm per quota day means **about 3 quota days** (about 2.7 to the soft stop; the 2.3 days of the spec assumed 8 keys). I will report measured calls per awake agent-hour from the first hours |

**Canary (first 20 minutes) and the ABORT CRITERIA, written now, before any launch** (the same text is in `devmem/eval/canary.py`): A1 an upstream exception not cleared by the one allowed resume; A2 injection: with at least 3 events resolved, fewer than 90 percent PASS, or any pivotal event FAIL; A3 schedule adherence below 85 percent of steps for any agent once 60 simulated minutes are checked; A4 router failures above 1 percent of calls (or fail-safe scoring above 2 percent); A5 a night-key anomaly (a marker for night k above 0 not written at 14:00 of day k, or a night 0 marker at or after 12:00); A6 more than 1.5 times the budgeted 110 calls per awake agent-hour over at least 4 awake hours; A7 any record whose model is not the pinned model, any Groq or NIM provider in the arm's ledger rows, or any chat key above 450 in the quota day; A8 a missing ledger window for an elapsed hour, or an agent asleep for more than two consecutive windows the schedule says are awake; A9 an injection at a different step in the two arms. The operator stops an arm by creating `ABORT` in its run folder.

## 4. CONDITIONS COMPLIANCE TABLE (your P4 and LAUNCH text)

| Condition | Status | Evidence |
|---|---|---|
| Runner: authored schedules through the plan-function replacement | Done | `authored_plan.py`; real `_long_term_planning` test |
| Event injector with a per-event perceived PASS or FAIL line | Done | `injector.py`; real `Maze` and `perceive` test, 27 events x 2 arms |
| Hourly ledger windows | Done | `LedgerWindows`; smoke test |
| Checkpoint copies at the end of the day 1 and day 3 awake windows | Done | `run_arm.CHECKPOINTS`, `make_checkpoint`; smoke and step-alignment tests |
| Movement files and the sim folder kept for replay; recording usable while it grows | Done | not purged; consistent at every autosave (section 1) |
| Schedule checker (tiling, no sleep across noon, no naps), overlap checker, unit tests | Done | `checks.py`, `test_run_readiness` |
| Pause on quota exhaustion until the daily reset; no crash; no other model | Done | `quota_gate.py`; tests with the real router exceptions |
| Disjoint chat-key sets, about 7 and 8, assigned in config, router unchanged unless unavoidable | 7 and 7 (14 verified keys); assigned in per-arm temporary configs; ONE minimal router change proposed (quota day) | section 3, Deviations |
| Per-key cap 450 a day; per-arm hard cap 9,500; soft stop 8,500; autosave 15 min; raw-reply log on | Done | `run_arm.plan` test |
| Canary in the first 20 minutes and abort criteria written before launch | Done (written; evaluator tested) | section 3, `canary.py` |
| Report measured calls per hour from the first hours | Will be done after launch | n/a |
| Launch needs your approval after P1 to P4 | Not launched | n/a |

## 5. DEVIATIONS (complete)
- **ONE router change, proposed here for your approval** (`devmem/router/key_pool.py`, `get_today_str()`, 6 lines): when `DEVMEM_QUOTA_RESET_UTC_HOUR` is set the ledger's quota "day" starts at that UTC hour instead of local midnight, so the per-key cap, the exhaustion marks and the pause logic all reset when the provider's quota does (about 12:30 IST). Without it, the ledger would reset at 00:00 IST while the provider has not, and a key could be driven past the provider's real daily limit. Default behaviour (variable unset) is identical to before and is tested. It is unavoidable for the pause to be correct; revert is one function.
- Key split 7 and 7 instead of 7 and 8 (section 3).
- The per-arm configs are temporary files outside the repository (as in Step D), so `providers.yaml` keeps the full key list for tests and the presentation.
- No full simulation step was executed (that needs live LLM calls); the smoke test scripts the step body. The first real execution is the canary after launch.
- `test_run_arm_smoke` must run as its own module (shared `ReverieServer` state), like `test_reconcile`.
- `docs/prelaunch_p1_p3_report.md` (earlier this round) lists `test_reconcile` among the modules run; no change needed.

## 6. OPEN QUESTIONS
1. Approve the router change (quota day gate), or do you prefer a different mechanism?
2. 7 and 7 keys (about 3 quota days) or spend one chat call on GEMINI_KEY_3 to get 8 and 7?
3. T calibration (P2) runs after 12:30 IST; freeze T before launch as planned. The runs cannot start before then anyway.
4. Phase 7 Stop 2b (grader, judge calibration pairs, ledger splitter, diagnostics) can be built while the runs execute, as you said.

REQUEST: Review of Stop 2a, your answers to 1 and 2, and, when P2 is done, approval to launch. Halting.
