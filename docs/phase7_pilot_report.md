# Phase 7 mini pilot report (PILOT, 2026-10-07)

Label: **PILOT. A mechanism and readiness check on live data. Nothing in this report is a result of the comparison.** Every artifact is named in section 5.

## 1. What was built or changed (files)

| Item | Files | Commit |
|---|---|---|
| JSON fence rule in the output normalizer (PM-approved fix spec), counted under `STATS["fence_strip"]` | `devmem/router/output_normalizer.py` | 5efbe9e |
| Fence tests on the two captured crash replies, plus the real upstream parse path | `devmem/router/test_normalizer_fence.py`, `devmem/router/fixtures/fence/captured_fenced_replies.json` | 5efbe9e |
| One existing assertion adjusted (`fence_strip` is a separate key in `STATS`) | `devmem/router/test_normalizer_wiring.py` | 5efbe9e |
| P2 T calibration artifacts, parser fix, offline recompute | `devmem/memory/episodic.py`, `p6_t_calibration*.py`, `docs/phase6_t_calibration_artifacts/` | f25a10b |
| Pilot mode, incremental `movement.zip` export, cumulative call count from the raw reply log on resume, fence-strip count per ledger window | `devmem/eval/run_arm.py`, `run_support.py`, `devmem/api/movement_archive.py` (`MovementExporter`) | d21e0f6 |
| Arm supervisor (resume policy) and tests | `devmem/eval/supervisor.py`, `test_supervisor.py` | d21e0f6 |
| Dead-arm detector (read-only) | `devmem/eval/arm_health.py` | this commit |
| A6 call-rate fix in the canary (all ledger windows, weighted by their own length) and its tests | `devmem/eval/canary.py`, `test_run_readiness.py` | this commit |

## 2. Conditions compliance (PM verdict of 2026-10-07)

| Condition | Status | File and proving test |
|---|---|---|
| Strip a fence only if the whole reply is one fenced block AND the inner text parses with json.loads; inner text unchanged | done | `output_normalizer.py` (`strip_json_fence`); `test_normalizer_fence.TestStripJsonFence` |
| Untouched: unfenced, unterminated or truncated fence, non-JSON fenced, fence inside a JSON string | done | same class (5 tests) |
| Applied regardless of the decomposition veto (no disagreement; the inner-JSON test is what makes it safe) | done | `TestWiring.test_applies_under_the_decomposition_veto` |
| Fence-strips counted per arm in the ledger | done | `run_support.count_fence_strips`; ledger field `fence_strips_total`; `test_run_readiness.TestFenceCountFromRawLog` |
| Tests on the real captured fenced replies from both crash snapshots | done | `TestStripJsonFence.test_real_captured_replies_from_both_crash_snapshots`, `TestRealUpstreamParsePath` (real `ChatGPT_safe_generate_response`: returns `False` without the rule, passes with it) |
| Plain fence, whitespace, default-off with the flag unset | done | `test_plain_fence_and_whitespace`, `TestWiring.test_default_off_with_flag_unset` |
| Resume both arms from the last autosave; caps cumulative (1,100 hard, 1,000 soft); crash snapshots kept; label PILOT | done, with the caveat in 3 | `run_arm.py` resume branch; snapshots `p7pilot_{arm}__crash_snapshot_2` |
| Key scan before every commit; fix, tests, P2 artifacts and exporter committed separately | done (0 hits in 17 files, counts only) | commits 5efbe9e, f25a10b, d21e0f6 |
| GEMINI_KEY_3 to the baseline arm unless staged shows the higher call rate | open | baseline had the higher rate in every comparable window (section 6); applies to the full arms, not the pilot |
| Supervisor: at most 3 resumes per sim day, log every resume, same step twice means ABORT | done | `supervisor.py`; `test_supervisor.py` (5 tests) |
| Launch rule: pilot ran through at least 08:00 sim with no A1 | **partly met** | staged reached 08:02:30; baseline stopped at 07:43:50 (cumulative soft stop of 1,000). No A1 since the fix in either arm |

## 3. Deviations (complete)

- The first launch was by `nohup` from the shell. Windows Update restarted the machine (see 7); both arms died with no report. Resumed twice, detached, by `Start-Process`.
- First resume (08:50 IST) ended in two A1 exits: `TypeError: 'NoneType' object is not subscriptable` at `plan.py:297` (baseline) and `converse.py:53` (staged), caused by a fenced reply (section 4). The crash report files were overwritten by the later resume report; the facts above are kept here and in the snapshots.
- The resumed legs replay simulated time the earlier legs had already done (baseline from 07:00, staged from 07:15; the replies differ because the model is not deterministic). The raw reply logs and the ledger therefore hold duplicate calls for those stretches. The pilot totals include them.
- `arm_state.json` is written only on the hour, so after the kills it recorded 33 calls against 538 delivered replies. `run_arm.py` now takes the larger of that and the raw log line count on resume (hence the cumulative caps). Before this fix the reported "router_calls_total" of the first resumed legs under-counted (284 and 302 at the crash).
- The canary's A6 rate counted only whole hourly windows and treated partial windows as full hours (printed 58.3 and 87.0). Fixed in `canary.py` (section 6); the numbers below use the fix.
- `canary.py` must be run from `reverie/reverie/backend_server` as the working directory (`utils.fs_storage` is a relative path); run from the repo root it reads an empty folder and printed "checked 0". Not changed.
- Existing test `test_normalizer_wiring` adjusted (see 1). Two ledger fixtures in `test_run_readiness.py` got `steps_in_window`.
- Runtime artifacts left uncommitted and not cleaned: `devmem/router/fixtures/429/observed.jsonl` (the router appends observed 429s), `reverie/.../temp_storage/curr_sim_code.json`, `curr_step.json`, `devmem/router/usage_log.db-journal`.
- Raw reply logs are git-ignored (they contain prompts); summaries are in `docs/phase7_pilot_artifacts/raw_reply_summary.json`.

## 4. The A1 cause and a correction

The first conversation of the day crashed both arms. Gemini wrapped valid `{"output": ...}` JSON in a markdown fence, upstream `json.loads` failed three times, the function returned `False`, upstream returned `None`, and the caller indexed `None[0]`.

**Correction of a number I gave earlier.** I wrote "3 of 10 (baseline dialogue) versus 5 of 148 (staged planning)". Those were two small slices of the last categories I looked at, not rates per arm. Over the whole raw logs the fenced raw replies are **7 of 991 (baseline) and 7 of 992 (staged)**. Of these, 4 (baseline) and 2 (staged) were delivered after the fix with the fence removed, and 3 (baseline) and 5 (staged) were delivered fenced before the fix (the crash legs). The fence rate does not differ between the arms in this pilot. Fence-strips per ledger: baseline 4, staged 2. This is a disclosure item.

## 5. Raw artifacts (all in `docs/phase7_pilot_artifacts/`, label live PILOT unless noted)

`{arm}_hourly_ledger.jsonl` (every window, per-purpose calls, `fence_strips_total`), `{arm}_run_status.json`, `{arm}_arm_report_resume.json` (final leg), `{arm}_canary_evaluation.json` (corrected A6, run from the backend folder), `{arm}_run_label.json` (PILOT label), `{arm}_schedule_check.json`, `raw_reply_summary.json` (derived), and the captured fenced replies in `devmem/router/fixtures/fence/`. Not in the repo: `devmem/storage/p7pilot_*/raw_replies.jsonl` and the two crash snapshots under `reverie/environment/frontend_server/storage/`.

## 6. Pilot status against the canary criteria (live, PILOT)

Stopped: baseline at 07:43:50 sim (step 2783), staged at 08:02:30 (step 2895), both by the cumulative soft stop of 1,000 router calls at a step boundary (cumulative calls 1,000 and 1,001; hard cap 1,100 not reached). Router failures 0, quota pauses 0, models other than `gemini-3.1-flash-lite` 0 records, Groq and NIM calls 0.

| Criterion | Baseline | Staged | Status |
|---|---|---|---|
| A1 exception | none after the fix (2 earlier, from the fence) | same | pass after the fix |
| A2 injection pass under 90% or a pivotal FAIL | 0 events resolved | 0 resolved | **not tested**: the first authored event is I1 at day 1 08:20, after both stops |
| A3 schedule adherence under 85% | 98.9%, 97.7%, 97.7% | 98.4%, 95.2%, 98.2% | pass, but the rate includes the asleep hours (6 of the first 7.7 simulated hours), so it is inflated; awake-only adherence was not computed |
| A4 router failure rate over 1% | 0 of 1,000 | 0 of 1,001 | pass (note: a reply that fails to parse is not a router failure; that is the A1 path) |
| A5 night-key anomaly | no markers | night markers present for the 3 agents at 2023-02-13 00:00 only (the expected day-start sleep block) | pass |
| A6 more than 1.5 x 110 = 165 calls per awake agent-hour | 164.4 over 4.28 awake agent-hours (all windows) | 146.5 over 4.79 | pass by 0.6 for baseline; see the split below |
| A7 non-pinned model, Groq or NIM, key over 450 per day | 0, 0 | 0, 0 | pass (per-key counts not re-audited here) |
| A8 missing ledger windows or asleep when awake | 10 and 11 windows | | pass |
| A9 cross-arm injection step mismatch | no events | | **not tested** |

Calls per awake agent-hour split by window (derived from the ledgers; windows from different legs, so they overlap in simulated time and include replayed stretches):

| Window | Chat steps | Baseline | Staged |
|---|---|---|---|
| 06:30 to 07:00 sim (7.5% of steps with a chat line in hour 6) | | 169 calls over 1.5 awake agent-hours = 113 | 146 over 1.5 = 97 |
| Crash legs (07:00 to 07:12; 07:15 to 07:22) | | 82 over 0.59 = 139 | 123 over 0.92 = 134 |
| Final legs after the fix (baseline 07:00 to 07:43:50; staged 07:15 to 08:02:30) | about 12% of steps | 453 over 2.19 = **207** | 433 over 2.38 = **182** |

The pilot has no hour without conversation after the wake-up, so the split is by leg, not "conversation hours versus none". The data show higher rates in the legs with more chat steps; it does not show that conversations cause the rate (the legs also differ in time of day, replay and Stage 4 context). By purpose in the final baseline leg: planning 213, importance scoring 195, dialogue 39, reflection 6 of 453.

Viewer on live data: `MovementSource.open` on each run folder read the growing `movement.zip` (baseline 2,783 frames, staged 2,895, frames equal to steps), thoughts present for all three agents. The HTTP viewer itself was not started in this pilot (it runs under the system Python 3.13; 8 of the 83 tests skip under the venv for that reason).

## 7. Operational answers

1. **Cause of the 05:30 kill:** the System log shows `MoUsoCoreWorker.exe` initiating a restart at 05:33, shutdown at 05:35, boot at 08:17, and a second restart by `TrustedInstaller` at 08:20 (back at 08:22). Source: Windows event log (captured, read-only). The arms run on this Windows laptop only (on AC, sleep set to never, no reboot pending now). Further risks over 1 to 3 days: more update restarts, power loss, closing the desktop app. Pausing updates is a system setting, so it is for the Project Owner. Detection: `python -m devmem.eval.arm_health [--pilot]` (read-only, exit 1 if an arm is dead or its heartbeat is older than the threshold); the supervisor does not survive a machine reboot, and I will not create a scheduled task without approval.
2. **Crash policy:** `supervisor.py` as specified (disclosure: an operational measure; a kill or an A1 exit triggers `--resume` from the last autosave, at most 3 per sim day, same step twice creates ABORT). Tested with a stub child, not on a live run.
3. **Other upstream `None[0]` sites** (all 12 active `ChatGPT_safe_generate_response` call sites return `None` after three failed parses): unguarded callers are `plan.py:269`, `plan.py:297`, `converse.py:53`, `:65`, `:190`, `:233`, `:235`, `reflect.py:35`, `:80`, `:82`, `:94`. Guarded: `plan.py:243`, `converse.py:34` (try/except), `perceive.py:32` and `:35` (our guard). The prompts most exposed are the free-text sentence prompts: conversation summary, relationship summary, agent chat, summarize ideas, memo on convo, object description. A parse can also fail on a validator that rejects three times or a truncated reply, not only on a fence. No upstream edit made.

## 8. Quota projection (derived; a projection, not a measurement)

Per full arm: 3 days, 8 awake hours, 3 agents = 72 awake agent-hours, plus night calls (33 in the first 6 simulated hours). Rates used: 97 to 113 (the early, low-chat leg), 182 to 207 (the final legs, about 12% chat steps).

| Rate (calls per awake agent-hour) | Awake calls per arm | Quota days at 7 keys x 450 = 3,150 | at 8 keys x 450 = 3,600 | Exceeds the 9,500 hard cap |
|---|---|---|---|---|
| 100 | 7,200 | 2.3 | 2.0 | no |
| 146 to 164 (cumulative, all windows) | 10,500 to 11,800 | 3.3 to 3.7 | 2.9 to 3.3 | yes |
| 182 to 207 (final legs, conversation) | 13,100 to 14,900 | 4.2 to 4.7 | 3.6 to 4.1 | yes |

From the conversation-leg rates only: 4.2 to 4.7 quota days at 7 keys (3.6 to 4.1 with the eighth key for the baseline). The quota day resets about 12:30 IST, so a 12:31 launch on Oct 7 ends about Oct 11 to Oct 12, not Oct 10. The day-1 checkpoint (24 awake agent-hours, about 4,400 to 5,000 calls) needs about 1.4 to 1.6 quota days: roughly mid-afternoon IST on Oct 8 at the observed wall pace (about 550 to 620 calls per wall hour per arm, so a quota day is spent in about 5 to 6 hours). The 9,500 hard cap and 8,500 soft stop will be reached before day 3 above about 132 calls per awake agent-hour. Two sample caveats: the sample is 1.7 to 2 awake hours per arm; and the awake window after 08:00 (the café morning, the Valentine party plans) was not sampled, so the range is wide.

Ways to shorten wall time without changing the arms: none by parallelism. At 550 to 620 calls per hour per arm, quota (not speed) binds, so more processes per arm do not help. Levers that leave the arms unchanged: more verified Gemini keys (each adds 450 per day); raising the per-key cap from 450 toward the 500 requests per day provider limit (up to about 11% more, a PM decision on the safety margin); the eighth key to the baseline. Reducing calls would change the arms and is not proposed.

## 9. Tests (verbatim, `python -m unittest discover -s devmem -p "test_*.py" -t . -v`, venv Python 3.9, last lines)

```
Ran 83 tests in 58.925s

OK (skipped=8)
exit 0
```

The 8 skips are the HTTP API tests (`devmem.api.test_api_http`), which need fastapi and httpx in the system Python 3.13 and were run there in Phase 8. The first discover run, before the canary test fixtures were updated, had one failure (`test_each_abort_criterion_fires_on_its_own_violation`); fixed and re-run (full output in `devmem/storage/pilot_logs/full_suite_output2.txt`, not committed). `test_run_arm_smoke` is run as its own module and was not re-run in this report.

## 10. Junior Developer tasks

None.

## 11. Open questions

1. A2 and A9 are untested on live data: the first injection is at 08:20 and neither arm got there. Do you want a second short pilot to 09:00 sim, or accept the injector's offline tests and let the first hours of the full run carry the canary?
2. A6 and the hard cap: at the conversation-leg rates the arms exceed 165 calls per awake agent-hour and the 9,500 hard cap. Keep the criteria and caps as they are (the run would stop early), or revise them?
3. Launch rule: baseline did not reach 08:00 sim (soft stop at 07:43:50); staged did (08:02:30), with no A1 after the fix in either. Is that enough for the 12:31 go, given the resume leg replayed time?
4. Windows Update: the Project Owner needs to pause updates; I have not changed any system setting.
5. T: not mine to freeze; P2 corrected-parser decision is T=8 by the rule, 9 suggested.

## 12. Approval request

I request approval of this pilot report and a decision on questions 1 to 3. I am halting. I will not start the full arms before your go.

## 13. Addendum (2026-10-07, about 13:30 IST): the pilot completed; per-window rates and canary on the finished arms


Label: PILOT, live, not a result. After the fence fix, the injector subject fix and the resumes of section 3, both arms ran to 09:00 sim with no A1 exit after the fixes. Artifacts: `docs/phase7_pilot_artifacts/` (final ledgers, injection logs, run status, canary evaluations; the raw reply logs stay git-ignored). The earlier cumulative totals in this report are not rates; the rates below are per ledger window.

### 13.1 Injected events (3 mundane events, both arms)

| id | agent | authored step | same step in both arms | perceived (baseline, staged) | importance baseline | importance staged |
|---|---|---|---|---|---|---|
| I1 | Isabella Rodriguez | 3000 | yes | yes, yes | 2 | 3 |
| K1 | Klaus Mueller | 2970 | yes | yes, yes | 1 | 2 |
| M1 | Maria Lopez | 3060 | yes | yes, yes | 2 | 2 |

A2: pass in both arms (3 of 3 each; no pivotal event was in the window, so the pivotal clause was not exercised). A9: the authored injection steps match. Source: `*_injection_log.jsonl`.

### 13.2 Calls per awake agent-hour per ledger window (windows under 0.3 awake agent-hours omitted)

| arm | window | sim clock | steps | calls | awake agent-hours | calls per awake agent-hour |
|---|---|---|---|---|---|---|
| baseline | hour_ending_2023-02-13_07:00 | 07:00 | 180 | 169 | 1.5 | 112.7 |
| baseline | final_partial_window | 07:11 | 71 | 82 | 0.59 | 138.6 |
| baseline | final_partial_window | 07:43 | 263 | 453 | 2.19 | 206.7 |
| baseline | final_partial_window | 07:54 | 66 | 74 | 0.55 | 134.5 |
| baseline | final_partial_window | 08:19 | 115 | 133 | 0.96 | 138.8 |
| baseline | hour_ending_2023-02-13_09:00 | 09:00 | 270 | 211 | 2.25 | 93.8 |
| staged | hour_ending_2023-02-13_07:00 | 07:00 | 180 | 146 | 1.5 | 97.3 |
| staged | final_partial_window | 07:18 | 110 | 123 | 0.92 | 134.2 |
| staged | hour_ending_2023-02-13_08:00 | 08:00 | 270 | 370 | 2.25 | 164.4 |
| staged | final_partial_window | 08:15 | 75 | 28 | 0.62 | 44.8 |
| staged | hour_ending_2023-02-13_09:00 | 09:00 | 270 | 186 | 2.25 | 82.7 |

Windows come from different legs (resumes and crash legs), so some overlap in simulated time and include replayed stretches; the table is per window, not a sum. Highest window: baseline 206.7, staged 164.4 (A6 amended: WARN above 165, ABORT above 260 over 3 consecutive windows).

### 13.3 Canary on the finished arms (run from the backend folder)

| arm | all_ok | A6 overall rate | A6 warn | abort list |
|---|---|---|---|---|
| baseline | True | 140.6 over 8.3 awake agent-hours | True | none |
| staged | True | 119.5 over 7.67 awake agent-hours | False | none |

Final totals: baseline 1,454 router calls, staged 1,206 (cumulative, including replays). Reflection calls (D1): baseline 16, staged 0.
