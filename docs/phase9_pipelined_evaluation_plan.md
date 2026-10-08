# Phase 9 pipelined evaluation plan (PREPARED, not started)

Written 2026-10-08. It refines `docs/phase9_evaluation_plan.md`. No em dashes, no key values.

## The key rule, enforced in code
An evaluation call may use ONLY keys of an arm whose run has FINISHED, never a key of an arm that is still running, and never a paid key. `devmem/eval/phase9/eval_keys.py`:
`finished(arm)` is true only when the arm's `run_status.json` state is "finished: <final outcome>" and no run_arm or supervisor process of that arm exists; `pool(arm)` raises
`ArmStillRunning` otherwise and returns the arm's own pool (chat keys plus the keys added through `extra_keys.json`); `assert_no_running_arm_key` is a second check inside every call
function; `provider_config(arm)` writes a temporary provider configuration holding only that pool, the pinned model and the free-tier cap of 450 per key per quota day. Tests
(`test_phase9.TestEvalKeyGuard`) cover a running arm, a crash exit (not a finish), a live process, the cross check, and the configuration content.

## What can start for one arm as soon as THAT arm finishes (on that arm's own pool)
| Step | Calls | Needs | Can start when |
|---|---|---|---|
| Recall answers on the day-3 checkpoint copy (39 questions, purpose `eval_recall`) | 39 | the arm's day-3 checkpoint (made by the runner at step 22,410) | the arm has finished |
| Probe interviews (6 questions x 3 agents) on the day-1 copy and on the day-3 copy (`eval_probe`) | 36 | both copies | the arm has finished |
| Judge on the arm's 18 day-1 against day-3 answer pairs (`eval_judge`) | 18 | the arm's own probe answers | after that arm's probes |
| Judge calibration on the 20 authored pairs (once) | 20 | nothing from any run | after the STAGED arm finishes, on the staged pool (script `run_judge_calibration.py` waits for it) |
| Replay controls (3 conditions on the fixed 300-event sample, `eval_replay`) | 900 | the STAGED arm's final event stream (the sample is drawn from it) | after the staged arm finishes, on the staged pool |
| Offline pieces: grader on the answers, ledger splitter, diagnostics, E1 to E3 on the final data | 0 | final artifacts | when the arm (and for comparisons both arms) have finished |

The baseline-side recall, probes and judge use the BASELINE pool and wait for the baseline arm. Nothing is shared across arms: the staged-side steps never touch a baseline key and the baseline-side
steps never touch a staged key; the model, prompts and top-k are identical, so the key identity changes nothing.

## Estimated times (from the measured rate of about 6 to 7 successful calls per minute on one pool, single sequential process; an estimate, not a promise)
- **Staged side after the staged arm ends** (expected about 20:00 to 23:10 on Oct 8): recall 39 + probes 36 + judge 18 + calibration 20 = 113 calls, about 20 minutes; the grader and tables take minutes offline. **Staged-side results (without replay controls): about 30 to 45 minutes after the staged end.** The replay controls add 900 calls, about 2 to 2.5 hours, so staged-side results including them are about 3 hours after the staged end.
- **Baseline side after the baseline arm ends** (expected about 04:50 to 13:40 on Oct 9): recall 39 + probes 36 + judge 18 = 93 calls, about 15 to 20 minutes. **The full comparison (both arms' answers graded and judged, E1 to E3 on final data, the directional-prediction table): about 45 to 60 minutes after the baseline end**, provided the staged-side work is already done by then, which the order above allows.
- The replay controls can run while the baseline arm is still running because they use only the staged pool.

## Scheduling of the judge calibration
`python -m devmem.eval.phase9.run_judge_calibration` polls every 60 s, makes no call and uses no key until `eval_keys.finished("staged")` is true, then makes 20 calls on the staged pool and writes `devmem/storage/phase9_eval/judge_calibration.json`. It has a dry run that makes no call. If the staged arm never finishes cleanly, it never runs.

## Addendum, 2026-10-08 16:35 IST: re-plan with the new ETA (after the 14:56 power off)

Expected: staged day-3 checkpoint (step 22,410) about 00:20 Oct 9 and staged end about 00:30; baseline day-3 checkpoint about 04:15 and baseline end about 04:25 (estimates; each further stoppage moves them).

Driver: `devmem/eval/phase9/run_arm_evaluation.py` runs, for ONE finished arm and on that arm's own pool, the recall answers (39), the probes at the day-1 and day-3 copies (18 + 18) and the judge on the 18 pairs: 93 calls, tested with stubs (no live call). The judge calibration (20 calls) runs on the staged pool through `run_judge_calibration.py`. The driver is sequential (one process), so the times below assume one call stream of about 6 calls per minute; a faster run needs one process per agent, which is not built.

| Result | Earliest, if every step starts at once and runs in parallel (3 agent processes, about 18 calls per minute) | Realistic (one sequential driver, about 6 calls per minute, review between steps) |
|---|---|---|
| Staged recall, probes and judge (93 calls) plus the calibration (20) | about 00:40 Oct 9 | about 01:00 to 01:15 |
| Staged replay controls (900 calls) | about 01:30 | about 03:00 to 03:30 |
| Baseline recall, probes and judge (93 calls) | about 04:35 | about 04:55 to 05:10 |
| Full comparison (both arms graded and judged, E1 to E3 on final data, the prediction table) | about 04:50 | about 05:30 to 06:30 |

The parallel column needs the one-process-per-agent variant of the driver (not yet written); the realistic column uses what exists.

## Addendum, 2026-10-08 (PM order of 20:00): staged-pool chain and independent modes

On the staged arm's finish, `devmem/eval/phase9/run_staged_chain.py` (running, waits for `eval_keys.finished("staged")`) runs, one process per step and stopping at the first failure, on the staged pool: (1) staged day-3 evaluation (93 calls), (2) judge calibration (20 calls), (3) baseline day-2 interim evaluation with `--pool-arm staged --day 2` (78 calls), (4) replay controls (`run_replay_controls.py`, at most 900 calls, replies cached). The earlier stand-alone calibration waiter was stopped so that the order above holds. Each step writes its output file (`devmem/storage/phase9_eval/...`) and a line to `chain_status.jsonl`. The baseline day-3 evaluation runs on the baseline pool when the baseline finishes. Offline, `results_export.py --day 2|3` writes the paper export.
