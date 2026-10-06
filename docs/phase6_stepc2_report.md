PHASE: 6 preparation, revised normalizer, offline gate and Step C rerun
STATUS: **Complete.** The offline gate passed before any live call. The Step C rerun completed both simulated hours (06:00 to 08:00, 720 steps) with **no upstream exception**, 163 router-counted calls (hard cap 400, soft stop 300 not reached), 0 router failures. Validity and cost only; no quality claim. Halting; Phase 6 Stop 2 starts only on your go.

Paths are relative to the repository root. `ART/` = `docs/phase6_stepc2_artifacts/`. Labels: **live** (the rerun), **offline-captured** (analysis and replays of saved data, zero calls), **synthetic** (constructed replies), **code-read** (upstream source). No em dashes are used in new files.

## 1. WHAT WAS BUILT

- **Revised normalizer rule** (`devmem/router/output_normalizer.py`, committed `7581f72` before any live call). Strip ONLY the exact annotation `(duration in minutes: <n>, minutes left: <n>)` (plus the spaces or tabs directly before it); apply it to every reply in the call path EXCEPT the decomposition veto set; Unicode-space mapping unchanged in scope (only the three originally covered prompts: wake-up hour, daily plan, hourly schedule); anything without the exact pattern comes back byte for byte; default off (`DEVMEM_OUTPUT_NORMALIZER`); process-wide, so identical for baseline and staged. Variants handled (all observed, 443 occurrences in 94 saved replies, always preceded by one ASCII space and with exactly this text): V1 followed by a newline 290, V2 followed by a space 55, V3 followed by a comma 47, V4 at the end of the reply 38, V5 followed by a period 11, V6 followed by a semicolon 2. No non-exact lookalike occurred; the tests assert that lookalikes (no `minutes left`, other case, other spacing, newline inside, missing parenthesis) are left untouched.
- **Veto set** (decided by code-reading `run_gpt_prompt.py`: only `run_gpt_prompt_task_decomp` reads the annotation, lines 374 and 381, which also reads `(total duration in minutes` from the prompt): every `task_decomp` template (v1, v2, v3 in both folders) and `new_decomp_schedule_v1`, detected by the fragments `Describe subtasks in 5 min increments`, `(total duration in minutes` and `The revised schedule:`. The tests render all 110 template files and prove the veto fires on exactly these and on nothing else.
- **Offline harness and table** (`devmem/memory/p6_normalizer_harness.py`, `p6_normalizer_table.py`): real upstream functions and validators, the real router `call_llm` with only the provider layer stubbed, live prompts patched in.
- **Tests** (all offline): `test_normalizer_rule.py` (9), `test_normalizer_call_path.py` (7), `test_normalizer_wiring.py` (8, updated to the new rule).
- **Step C rerun script** `devmem/run_step_c2.py`, analysis `p6_stepc_analysis.py` (now also reports the annotation before the normalizer), `p6_stepc2_scores.py`.
- **Claims ledger**: section H (disclosed deviations, with the output-adaptation layer as one deviation applied equally to both conditions, Path B at the night step, offline embeddings in Step C, baseline without traits) and rows D7 and D8.

## 2. THE OFFLINE GATE (before any live call)

Evidence table: `ART/normalizer_prompt_table.md` (and `.json`).

1. **Every upstream template in the call path, rendered from the real template files: stripped yes or no, why.** 49 upstream templates referenced by `run_gpt_prompt.py` plus the 2 devmem prompts (staged scoring, consolidation summary). Stripped: 49 of 51. **Not stripped (veto):** `v2/task_decomp_v3.txt` and `v2/new_decomp_schedule_v1.txt` ("decomposition prompt: its parser reads the annotation"). Every other row says "call path, not decomposition: the annotation is stripped, nothing else is changed", except the three space-mapped prompts (`wake_up_hour_v1`, `daily_planning_v6`, `generate_hourly_schedule_v2` in v2 and `generate_hourly_schedule_v2` in v3_ChatGPT), which also get Unicode spaces mapped. One template, `v2/generate_pronunciatio_v1.txt`, cannot be read by upstream on this machine (it opens files with the default cp1252 encoding), so the live path cannot reach it here; it is listed as such.
2. **Saved live Step C replies replayed through upstream's real validator, with the LIVE prompt (not a rebuilt one), flag off vs on.** (23 instances: wake-up 1, daily plan 1, hourly schedule 18, action sector 1, arena 1, plus the decomposition instance kept as veto.) The prompt each upstream function saw equals the logged live prompt in all 22 replayed instances (this includes the **sector replay, now with the real live prompt**).

| Prompt | Live replies | Before (flag off) | After (flag on) |
|---|---|---|---|
| action sector | 5 | validator [False x5], 5 attempts, result "Isabella Rodriguez's apartment" (via upstream's own living-area fallback) | validator [True], 1 attempt, same result |
| action arena | 5 | validator [False x5], 5 attempts, result **`kitchen`** (the fail-safe that caused the live `KeyError`) | validator [True], 1 attempt, result **`main room`** |
| hourly schedule (18 instances) | 1 each | accepted, but the delivered text carries the annotation in the instances that had it | accepted, text clean |
| wake-up hour, daily plan | 1 each | accepted | accepted (text clean) |
| task decomposition | 1 | annotation kept | annotation kept (veto) |

   No prompt type got worse (validator passes after are at least those before, in every instance).
3. **Synthetic checks for the other stripped prompt functions** (label: synthetic; the reply is a plausible clean value, and the annotated variant appends the observed annotation; for the JSON chat path it is placed inside the value, the harder case). Flag on equals the clean result in all 7; flag off breaks 5: action game object picks a wrong object (`desk` instead of `bed`), pronunciatio returns `'😴 ('`, object description keeps `(duration ...` inside, and **both poignancy prompts crash with `TypeError`**; event triple and object event triple are unaffected by the annotation.
4. **Veto prompts keep their annotation** through the real router (rendered real templates, tests in `test_normalizer_wiring.py` and `test_normalizer_rule.py`), and **unannotated text is byte-identical with the flag on**: a corpus of odd strings (empty, whitespace, CRLF, emoji, NBSP, narrow no-break space, braces) and every saved live reply without the pattern (more than 20 from Step C and the two probes) come back unchanged on non-space-mapped prompts.

## 3. STEP C RERUN (live; raw data in `ART/raw_replies.jsonl`: full prompt, raw reply and delivered text of all 163 calls)

Setup as before except the caps: `gemini-3.1-flash-lite` pinned, 3 agents, 06:00 to 08:00, staged mode, Stage 4 absent, normalizer on, raw-reply log on, fail_loud_llm on, agent tagging on, **hard cap 400 router-counted calls, soft stop at a step boundary after 300**, calls rotated over `GEMINI_KEY_4`, `_5`, `_6` (router pacing 15 RPM per key), embeddings offline (zero embedding requests; same interpretation as the first run). No exception handling was added around upstream; none was needed.

| Item | Result |
|---|---|
| Outcome | reached 08:00:00; **no upstream exception**; saved at the end; 8 autosaves (every 15 simulated minutes); schedule scan `clean` (8 scans, 0 findings) |
| Router-counted calls | **163** of 400 (planning 131, dialogue 10, staged importance scoring 22); soft stop (300) not reached; `ROUTER_FAILURES` 0 |
| Wall time | 1,421 s; first key per call: `GEMINI_KEY_4` 55, `_5` 54, `_6` 54 (about 3 calls per key per minute, well under 15 RPM; no 429) |
| Normalizer | applied to 3 wake-up, 3 daily plan and 50 hourly replies (all changed) and to 102 other replies, of which 27 carried the annotation; 5 decomposition replies were vetoed |
| Embedding requests | 0 |

**Per-agent progress.** Isabella Rodriguez: awake and acting ("preparing for the day and commuting to Hobbs Cafe" at 08:00), 104 calls, 48 memory nodes. Maria Lopez: 28 calls, "sleeping" at 08:00, 9 nodes. Klaus Mueller: 31 calls, "sleeping" at 08:00, 8 nodes. Maria's wake-up answer was 9 am, so her sleeping at 08:00 is consistent with it; Klaus's wake-up answer was 7 am, yet he is recorded as "sleeping" at 08:00, which I did not investigate. Only Isabella has more than the day-start burst. The sleep hook fired at the start for both sleeping agents (Stage 3 night 0, nothing to sweep).

**Retries per prompt type, and acceptance (analysis of the log, `ART/step_c_analysis.md`).** An instance is a run of consecutive calls by one agent with an identical prompt (upstream resends the same prompt on rejection):

| Prompt type | Instances | Calls | Retries | Accepted on first attempt | Raw replies that carried the annotation (before the normalizer) |
|---|---|---|---|---|---|
| hourly schedule | 50 | 50 | 0 | 50 | 50 of 50 |
| staged importance scoring | 22 | 22 | 0 | 22 | 0 of 22 |
| pronunciatio | 20 | 20 | 0 | 20 | 0 of 20 |
| event triple | 20 | 20 | 0 | 20 | 9 of 20 |
| action sector | 10 | 10 | 0 | 10 | 9 of 10 |
| action arena | 10 | 10 | 0 | 10 | 9 of 10 |
| action object | 10 | 10 | 0 | 10 | 0 of 10 |
| object event | 10 | 10 | 0 | 10 | 0 of 10 |
| task decomposition | 5 | 5 | 0 | 5 | 5 of 5 (required; kept; format present in 5 of 5) |
| wake-up hour | 3 | 3 | 0 | 3 | 3 of 3 |
| daily plan | 3 | 3 | 0 | 3 | 3 of 3 |

Echo replies 0, replies still carrying the annotation after normalization 0 (outside the veto set), unusual-space replies 0, empty replies 0. **No prompt type failed.** Not exercised in this run: conversations (no two agents met), reflection (disabled in staged mode by decision D1), consolidation summaries (no sweep had entries).

**Valid schedule rate per agent** (accepted on the first attempt and clean after normalization): Isabella wake-up 1 of 1, daily plan 1 of 1, hourly schedule 18 of 18; Maria 1 of 1, 1 of 1, 15 of 15; Klaus 1 of 1, 1 of 1, 17 of 17. Validity and format only.

**Calls and tokens per simulated hour (measured, ledger):**

| Interval | Calls | Tokens in / out | By agent | Purposes |
|---|---|---|---|---|
| step 0, day-start planning (06:00:00) | 84 | 84,679 / 23,957 | Isabella 29, Maria 26, Klaus 29 | planning 81, dialogue 3 |
| 06:00 to 07:00 | 6 | 2,463 / 24 | 2 each | importance scoring 6 |
| 07:00 to 08:00 | 73 | 22,471 / 1,594 | Isabella 73 | planning 50, dialogue 7, scoring 16 |

These figures are for this model and prompts; Gemini returns short outputs, so they are not comparable with the gpt-oss runs (for example the earlier day-start burst was 138 calls with 286K tokens), and no efficiency claim is made.

**T re-check (pre-registered population, section 7 of the pre-registration, committed before the run).** The population is every importance score from Step C for non-idle events: **22 scores** (18 Isabella, 2 Maria, 2 Klaus; cross-check: equals the 22 scoring calls in the router log; 40 idle rows were rule-assigned and excluded). Histogram: 1: 18, 3: 1, 4: 2, 6: 1; none reached 8. Fewer than 30 scores, so **T = 9 stays provisional** (nothing tuned, nothing pooled). Scoring replies were of the form `Rate: 1`, parsed by the existing regex parser.

## 4. COMPLIANCE TABLE

| Item | Status | Artifact |
|---|---|---|
| Strip only the exact trailing pattern; variants recorded | Done (V1 to V6 with counts) | `output_normalizer.py`, `test_normalizer_rule.py` |
| Apply to every call-path prompt except the decomposition veto set | Done | `normalizer_prompt_table.md`, `test_normalizer_call_path.py` |
| Unicode-space mapping stays as now; text without the pattern byte for byte | Done (scope unchanged; see deviation 1) | `test_normalizer_rule.py` |
| Identical for baseline and staged; default off, same flag | Done | `test_normalizer_wiring.py` |
| Render every upstream prompt from the real templates; table prompt, stripped yes/no, why | Done (49 + 2) | `ART/normalizer_prompt_table.md` |
| Replay saved Step C replies through upstream's real validator, valid before/after | Done (22 instances) | table section 2 |
| Veto prompts keep their annotation; unannotated text byte-identical | Done | tests |
| Sector replay with the REAL live prompt | Done (prompt equals live) | table section 2 |
| Step C rerun only if the offline gate passed | Done after the gate; committed `7581f72` first | `full_suite_before_live.txt` |
| Hard cap 400, soft stop 300 after, router-counted | Honored (163 used) | `router_counter` |
| 3 agents, 06:00, 2 hours, staged, Stage 4 off, normalizer on, raw log on, no embeddings, 15 RPM per key, keys spread | Done | `step_c_report.json` |
| No exception handling added around upstream; on an exception stop, save, report prompt | No exception occurred; the reporting path exists and was not triggered | `run_step_c2.py` |
| Valid schedule rate per agent, echo and degenerate counts, retries per prompt type, per-agent progress, calls and tokens per sim hour, failing prompt types | Done (none failed) | section 3 |
| Disclosure in the claims ledger as one deviation applied equally to both conditions | Done (H1) | `docs/CLAIMS_LEDGER.md` |
| T = 9 stays provisional; re-check | 22 scores, provisional again | `ART/step_c2_score_check.json` |
| Commit locally, key scan | Done (hashes in my message) | n/a |

## 5. DEVIATIONS AND INTERPRETATIONS (complete)

1. **Interpretation to confirm:** "Unicode-space mapping stays as now" was read as keeping its scope (the three originally covered prompts), because mapping on every prompt would contradict "text without that exact pattern must come back byte for byte". On all other prompts the only change ever made is removing the annotation. (Step A showed the space mapping changed no outcome.)
2. **Embeddings offline** for the whole rerun (same reading of "no embeddings beyond the cache" as the first run; deterministic vectors, zero requests, so retrieval relevance is meaningless in this run; ledger H3).
3. The offline harness patches `generate_prompt` so an upstream function sees the exact logged live prompt, and stubs only the provider layer; the real router, normalizer, upstream functions and validators run unmodified. An upstream exception inside a replay is recorded as a result.
4. The first Step C analysis script was extended (annotation-before column, a label for the staged scoring prompt); I re-generated the first run's analysis once and then **restored the committed first-run analysis files** so no past number changed.
5. Router edits this round: none beyond the normalizer module (the earlier prompt field in the raw log was committed with the previous round). The rerun's fork copy was deleted; runtime files restored.
6. The Phase 6 spec's rule "no em dashes" was followed in all new files.

## 6. TESTS

Full suite, offline default (`ART/full_suite_final.txt`), verbatim:
```
=== devmem.router.test_router
Ran 33 tests in 4.296s
OK
=== devmem.router.test_call_counter
Ran 4 tests in 8.667s
OK
=== devmem.router.test_output_normalizer
Ran 4 tests in 0.001s
OK
=== devmem.router.test_normalizer_wiring
Ran 8 tests in 2.723s
OK
=== devmem.router.test_normalizer_rule
Ran 9 tests in 0.223s
OK
=== devmem.router.test_normalizer_call_path
Ran 7 tests in 5.367s
OK
=== devmem.memory.test_priors
Ran 9 tests in 2.153s
OK
=== devmem.memory.test_episodic
Ran 10 tests in 1.715s
OK
=== devmem.memory.test_reconcile
Ran 10 tests in 47.926s
OK
=== devmem.memory.test_gpt_structure_touch
Ran 5 tests in 0.111s
OK
=== devmem.memory.test_consolidation
Ran 27 tests in 9.621s
OK (skipped=1)
=== devmem.embeddings.test_vector_store
Ran 14 tests in 1.173s
OK (skipped=1)
=== devmem.demo.test_demo
Ran 2 tests in 0.047s
OK
```
142 tests (126 before this round plus 16 new), 2 live-gated skipped.

## 7. HONEST LIMITS AND OPEN QUESTIONS

Limits: one run, 163 calls, one model; Isabella supplies most of the post-planning activity; conversations, reflection and consolidation summaries did not run; no output was judged for quality, only for whether upstream's own validators accepted it and whether format artifacts remained. Maria and Klaus were recorded as asleep at 08:00 (Klaus's reason not investigated).

Questions:
1. Confirm interpretation 1 (space-mapping scope).
2. Step C now says Gemini plus the revised normalizer can drive the first two simulated hours of a three-agent staged run. A longer run would exercise conversations, consolidation and the sleep cycle; that is a separate live run needing your go and its own cap. Do you want it before Phase 6 Stop 3, or only the Phase 6 confirmation run?
3. T = 9 remains provisional (22 scores, none at 8 or above); the next run with at least 30 scored events should re-check it.

REQUEST: Approval of this round. Then Phase 6 Stop 2 (offline build) on your go. Halting.
