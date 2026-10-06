PHASE: 5, merged live run (E and F), calibration scan and demo
STATUS: Complete as specified, with one target not reached: the continuation stopped at its 266-call soft cap at 07:55:10 sim time, not at 10:00.
Stage 3 label: **implemented and verified on scripted data; hook observed in live step 0 (all 3 agents); no live sweep has yet had entries to consolidate.**

Paths are relative to the repo root. `ART/` = `docs/phase5_step3_artifacts/`. Labels: **live**, **scripted**, **offline-captured** (computed from saved live data, no network), **synthetic**.

---

## 1. New keys (names only; verification calls reported separately from every cap)

Env var names now in `.env`: `GROQ_KEY_1` to `GROQ_KEY_6`, `GEMINI_KEY_1` to `GEMINI_KEY_5`, `NIM_KEY_1` to `NIM_KEY_4`. New this round: `GROQ_KEY_6`, `GEMINI_KEY_5`, `NIM_KEY_3`, `NIM_KEY_4`. One minimal call each (LLM `max_tokens` 5; one embed call for the Gemini key), status codes only (`docs/phase5_step2_artifacts/key_verification.json`, **live**):

| Key | Call | Status |
|---|---|---|
| GROQ_KEY_6 | LLM, 5 tokens | 200 |
| GEMINI_KEY_5 | LLM, 5 tokens | 200 |
| GEMINI_KEY_5 | embed | 200 |
| NIM_KEY_3 | LLM, 5 tokens | 200 |
| NIM_KEY_4 | LLM, 5 tokens | 200 |

All added to `providers.yaml`; `GEMINI_KEY_5` also to `embeddings.yaml` (now `GEMINI_KEY_1`, `_3`, `_4`, `_5`). None returned 401 or 403. Different Gemini accounts are different projects. Verification calls this round: **5**.

---

## 2. Phase 1: day-start planning (live; soft cap 250, hard cap 375)

Before starting, the script printed the remaining Groq `gpt-oss-20b` token budget per key from the ledger (total remaining 958,360 against a projected need of 250 x 2,192 = 548,000, where 2,192 tokens per call was measured in the earlier smoke run) and would have aborted if the projection exceeded it. I also verified the abort path by forcing an absurd projection (it printed the message and ran nothing). Raw: `ART/p5_staged_live_soft_*`.

| Item | Result |
|---|---|
| Outcome | step 0 completed for all 3 agents, **saved** (step 1, clock 00:00:10) |
| LLM calls / tokens | **138 calls**, 122,933 in + 162,821 out = 285,754 tokens; purposes: planning 135, dialogue 3 |
| By agent (measured day-start planning) | Isabella 44 calls (39,400 in / 50,286 out); Maria 50 (45,240 / 65,362); Klaus 44 (38,293 / 47,173) |
| Embedding requests | 3 |
| Wall time | 888 s |
| `ROUTER_FAILURES` | count 0 |
| Sweep rows | 3 markers (one per agent, night 0, `done`, attempts 1); each sweep found 0 entries (nothing to consolidate yet) |

The hook fired in a live step 0 for all three agents (in the earlier smoke run only 2 of 3 got that far).

**Schedule scan: status `findings`.** The scan ran after the successful save (32 scans by the end of the continuation). It flagged 102 schedule entries, all of type `model_echo`: the model copied the prompt's own formatting into the schedule, for example `[(ID:abC12d) Monday February 13 -- 00:00 AM] Activity: Isabella is sleeping`. No entry contains a router-failure string. The saved schedules are degenerate in practice: Isabella is "sleeping" through 11:00 and Maria through 12:00 (blocks of such echo lines), and Klaus wakes at 07:00, repeats one wake-up line (copied with the same ID) 13 times, and is "sleeping" again from 09:00. (Phase 2's saved baseline schedules had the same pattern.) It is a model-quality effect with `openai/gpt-oss-20b`, not a router failure.

---

## 3. Cap handling and the continuation (live; hard cap 400 calls, 150 embedding requests)

Implemented as specified: budgets are checked at step boundaries; the hard cap is 1.5x the soft cap and raises without saving (crash semantics; no save is attempted after a mid-step stop); `schedule_check.json` carries `status: not_run | clean | findings` and is rewritten after every successful save. For the continuation the soft cap is hard/1.5 = **266 calls** (embedding soft cap 100). The pre-run budget check printed: total remaining 672,685 against a projected need of 266 x 2,192 = 583,072, so it proceeded. (I used the soft cap as the projection, because that is where the run stops by design; with the hard cap of 400 the projection, 876,800, would have exceeded the remaining budget and aborted.)

The continuation resumed the same run from the phase-1 save (`HeadlessRunner(resume=True)`). Raw: `ART/p5_staged_live_continue_*`.

| Item | Result |
|---|---|
| Stop reason | soft LLM cap 266 reached at a step boundary; clean save |
| Clock | 00:00:10 to **07:55:10** (steps 1 to 2851); target 10:00 not reached |
| LLM calls / embeddings | 266 calls, 23 embedding requests (caps 400 and 150); 108,626 in + 108,002 out tokens |
| `ROUTER_FAILURES` | count 0 |
| Autosaves | 31 interval saves (every 90 steps = 15 sim minutes) plus the clean-exit save |
| Sweep rows | still the 3 night-0 markers (no sleep onset after them) |
| Mirror rows | Klaus 39, Isabella 8, Maria 8 |
| Wall time | 1,900 s |

**Per-simulated-hour table (measured, from `hourly_ledger.jsonl`; no schema change):**

| Sim interval | LLM calls | Tokens in / out | Embeddings | Calls by agent | Purposes |
|---|---|---|---|---|---|
| step 0 (day start) | 138 | 122,933 / 162,821 | 3 | Isabella 44, Maria 50, Klaus 44 | planning 135, dialogue 3 |
| 00:00 to 01:00 | 6 | 2,751 / 938 | 6 | 2 each | importance_scoring 6 |
| 01:00 to 06:00 (5 hours) | 0 | 0 / 0 | 0 | none | none |
| 06:00 to 07:00 | 16 | 5,129 / 3,807 | 0 | Isabella 16 | planning 15, dialogue 1 |
| 07:00 to 07:55:10 (partial) | 264 | 100,746 / 103,257 | 17 | Klaus 248, Isabella 16 | planning 238, dialogue 12, importance_scoring 14 |

What this measures: while all agents sleep the cost is about zero (0 calls in 5 hours). One awake agent (Klaus, 07:00 to 07:55) cost **248 calls and 195,582 tokens in 55 simulated minutes**, driven by his 5-minute actions at about 8 calls each (238 planning calls). That is roughly 270 calls per awake agent-hour for this schedule. It is one agent, one hour, and a degenerate schedule, so it is a data point, not an estimate of a normal hour. It is also far above the Step 0 mid-scenario assumption of about 50 calls per awake agent-hour. For scale: Phase 1 plus the continuation used 502,000 tokens; the Groq ledger now shows `GROQ_KEY_1`, `_2` and `_4` at about 200K (the daily limit) and `GROQ_KEY_6` untouched, because the router fills lower-numbered keys first.

---

## 4. Calibration dataset and the offline threshold scan (offline-captured, 0 network)

Preserved: the saved run memory and mirror DB for both phases under `devmem/storage/calibration/p5_staged_live_soft` and `p5_staged_live_continue` (1.4 MB and 2.4 MB; git-ignored storage, so not in the commit; the scan outputs are in `ART/`). Script `devmem/memory/p5_calibration_scan.py`, raw `ART/calibration_scan.json`: single and average linkage at 0.70 to 0.90 in steps of 0.02, per agent, on (a) the entries the sweep would consider and (b) all nodes. **No threshold was chosen or frozen.**

The dataset is small and the sweep filter removes almost all of it:

| Agent | Nodes | Importance histogram (value: count) | Eligible for the sweep (importance at least 3, not idle) |
|---|---|---|---|
| Isabella Rodriguez | 9 | 1:7, 3:1, 5:1 | 1 ("bed is occupied") |
| Klaus Mueller | 40 | 1:27, 2:10, 4:1, 5:2 | 2 ("Klaus Mueller is leaving the house", "bed is occupied by Klaus Mueller") |
| Maria Lopez | 9 | 1:8, 5:1 | 0 |

So on this live data the sweep, as configured (floor 3), would consolidate nothing: 37 of Klaus's 40 nodes are idle or object events scored 1 or 2. Histograms on the eligible sets are all singletons at every setting. Histograms on **all nodes** (unfiltered, for contrast), sizes as `size:count`:

| Klaus (40 nodes) | 0.70 | 0.78 | 0.82 | 0.90 |
|---|---|---|---|---|
| single | 3:1, 37:1 | 1:4, 3:1, 4:1, 29:1 | 1:8, 2:1, 3:1, 4:1, 23:1 | 1:16, 2:4, 3:3, 7:1 |
| average | 1:4, 3:2, 4:1, 26:1 | 1:5, 2:1, 3:1, 4:1, 10:1, 16:1 | 1:8, 2:3, 3:2, 4:1, 6:1, 10:1 | 1:16, 2:4, 3:4, 4:1 |

Without the filter, single linkage at 0.78 puts 29 of Klaus's 40 nodes in one cluster (idle and object events chain together), and average linkage still produces clusters of 16 and 10. Isabella and Maria (9 nodes each) fold into one 6-node cluster at 0.78 single. The full per-agent tables for all 22 settings are in the artifact. What this does and does not show: the filter, not the threshold, decides whether anything gets consolidated on real early-morning data; there is not yet any real awake data (more than a few non-idle events) on which to calibrate a threshold. Pairwise cosine over Klaus's nodes: min 0.48, median 0.66, 90th percentile 0.82, max 1.00 (duplicate texts).

---

## 5. Findings list

1. **Upstream recency in `new_retrieve` (observation only; no change made).** `persona/cognitive_modules/retrieve.py:224-227` builds the node list sorted ascending by `last_accessed`; `extract_recency` (`retrieve.py:132`, assignment at `:145-146`) gives value `decay**i` for `i = 1..n` in that order, so the **oldest** node gets the highest raw recency (`:231` consumes it) and the newest the lowest; min-max normalization then maps the newest node to 0. After every `new_retrieve` call `last_accessed` is set to the current time for the returned nodes (`:271`), which makes later ties follow list order. Evidence is in `docs/phase5_step2_artifacts/diag_retrieval_tables.md` (first-person scripted runs): 10:20 event 0.707, 10:35 event 0.635, 16:45 event 0.139, 22:00 summary nodes 0.000 to 0.069.
2. **Model-echo schedules** with `openai/gpt-oss-20b` (Section 2); the scan reports them as `findings`, not as router failures.
3. **Resume bug found by the live run and fixed:** a save taken right after a step had no `environment/N.json`, so the upstream constructor failed on resume. `HeadlessRunner` now builds it from `movement/{N-1}.json` (`run_headless.py`, `_ensure_env_for_saved_step`); regression test added. The failed attempt cost no LLM calls.
4. **Router key skew:** the router fills lower-numbered Groq keys first, so `GROQ_KEY_1`, `_2`, `_4` were exhausted while `GROQ_KEY_6` had 0 usage; per-key daily budget is not spread.
5. **Awake cost is far above the earlier assumption** (Section 3): 248 calls in one awake agent-hour.
6. **Day-start planning is a fixed burst** of about 138 calls and 286K tokens for 3 agents (Section 2).

---

## 6. The demo (scripted; `devmem/demo/run_demo.py`)

- **Replay** (default, no network, no keys): reads `ART/demo_replay_data.json`, built by `devmem/demo/export_demo_data.py` from the saved third-person scripted sweeps (live embeddings and summaries saved earlier) plus an offline rebuild of the retrieval ranking with the real `new_retrieve` (the export asserts the rebuild reproduces the saved summary ranks; 0 network requests). It prints the scripted day's episodic entries (with consolidated flags and the reason each unconsolidated entry stayed), the clusters and histogram, each summary with its source entries, the second-sweep result, and the ranking for three focal points with `consolidated_weight` 0.5 versus 1.0 side by side (with scores). `--run 0.82` selects one threshold run.
- **Live** (`--live`): real embeddings (cached) and **at most 4 LLM calls** (a counting guard raises at 4), pinned `openai/gpt-oss-20b`, one sweep at the default 0.78. I ran it once: exactly 4 calls (2 summaries, 2 scores), 2 semantic memories, second sweep skipped, same layout (ranking without scores). The live events table has no time column (the mirror query does not return it).
- Tests: `devmem/demo/test_demo.py` (2 tests, socket creation blocked during replay).
- Label printed in the demo itself: SCRIPTED.

---

## 7. Compliance table

| Item | Status | File and line | Proof |
|---|---|---|---|
| New keys: names, verify, add to config, status only, calls reported separately | Done, 5 calls | `providers.yaml`, `embeddings.yaml` | `docs/phase5_step2_artifacts/key_verification.json` (live) |
| Decision 1: merged run, soft cap 250 in phase 1; step 0 completes for 3 agents and saves; per-agent day-start calls and tokens | Done: 138 calls | `run_live_staged.py` | `ART/p5_staged_live_soft_report.json` (live) |
| Decision 1: continuation from the saved state, hard cap 400/150, pinned model, fail_loud_llm on | Done (`resume=True`), stopped at soft cap 266 at 07:55:10 | `run_live_staged.py` | `ART/p5_staged_live_continue_report.json` (live) |
| Decision 1: print remaining token budget per Groq key; abort if projected need exceeds it | Done; abort path verified | `run_live_staged.py` `budget_table` | `ART/*_budget.json`, console output |
| Decision 2: budgets at step boundaries; hard cap at 1.5x raises, no save; no save after mid-step stop | Done | `run_live_staged.py`, `run_headless.py` (`should_stop`) | `test_should_stop_breaks_at_a_step_boundary_with_a_clean_save`; live stop |
| Decision 2: `schedule_check.json` status `not_run`, `clean` or `findings`; scan after every successful save | Done | `run_headless.py` `_write_schedule_check` | `test_runner_sets_fail_loud_and_scan_flags_...` (not_run, clean, findings, clean); live: `findings`, 32 scans |
| Decision 3: hour-boundary ledger deltas to per-run jsonl; per-sim-hour table | Done | `run_live_staged.py` `record` | `ART/*_hourly_ledger.jsonl`, Section 3 |
| Decision 4: preserve memory and embeddings as calibration data; offline scan single and average 0.70 to 0.90; no frozen threshold | Done | `p5_calibration_scan.py` | `ART/calibration_scan.json`, Section 4 |
| Decision 5: recency inversion in findings with file and lines, no upstream change | Done | `retrieve.py:132, 145-146, 224-231, 271` | Section 5; `git status reverie` clean |
| Decision 6: demo, replay (no network) and live (at most 4 calls), prints entries, clusters, summaries with sources, ranking at weight 0.5 vs 1.0, labeled scripted | Done | `devmem/demo/run_demo.py`, `export_demo_data.py` | `test_demo.py`; one live run (4 calls) |
| Decision 7: commit with key scan (counts only), report hash | Done (see my message) | n/a | scan counts below |

---

## 8. Deviations (complete)

1. **Soft-cap projection:** the pre-run budget check uses the soft cap (where the run stops) times the measured 2,192 tokens per call, not the hard cap; with the hard cap of 400 the continuation would have aborted (Section 3).
2. **Continuation target not reached:** stopped at 07:55:10 by the soft cap, as the cap rules require, not at 10:00.
3. **Runner changes:** `schedule_check.json` always written with a status; `should_stop` hook; resume builds the missing environment file; agent tagging from the previous round. **Router:** none this round beyond the earlier 3-line `agent_id` default.
4. **New files:** `devmem/run_live_staged.py`, `devmem/memory/p5_calibration_scan.py`, `devmem/demo/` (`run_demo.py`, `export_demo_data.py`, `test_demo.py`), `docs/phase5_step3_artifacts/`. Edited: `p5_diagnose_retrieval.py` (parameters `saved_dir`, `out_dir`, `full`; adds `consolidated_node_ids`), `scripted_sweep.py` (stores the full ranking order), `run_headless.py`, `providers.yaml`, `embeddings.yaml`, `test_reconcile.py`.
5. **`reverie/`:** no source file edited. The runs rewrote the tracked `temp_storage/curr_sim_code.json` and created `curr_step.json`; restored and deleted. The run folders under `reverie/environment/frontend_server/storage/` (`p5_staged_live`, earlier smoke) are untracked and git-ignored.
6. **Calibration datasets** are in git-ignored `devmem/storage/calibration/`, so they are not in the commit; scan results and report data are.
7. **Counts:** verification 5 calls; phase 1 138 LLM calls and 3 embedding requests; continuation 266 LLM calls and 23 embedding requests; demo live run 4 LLM calls; one failed continuation attempt (resume bug) made 0 calls.
8. **Not demonstrated:** a live sweep that consolidates real entries (the real data has almost none above the floor); behavior from 08:00 to 10:00; agents with healthy schedules.

---

## 9. Tests

Full suite, offline default (`ART/full_suite_output_offline_default.txt`), verbatim:

```
=== devmem.router.test_router
Ran 33 tests in 4.021s
OK
=== devmem.memory.test_priors
Ran 9 tests in 1.721s
OK
=== devmem.memory.test_episodic
Ran 10 tests in 1.947s
OK
=== devmem.memory.test_reconcile
Ran 10 tests in 34.965s
OK
=== devmem.memory.test_gpt_structure_touch
Ran 5 tests in 0.025s
OK
=== devmem.memory.test_consolidation
Ran 27 tests in 7.327s
OK (skipped=1)
=== devmem.embeddings.test_vector_store
Ran 14 tests in 1.062s
OK (skipped=1)
=== devmem.demo.test_demo
Ran 2 tests in 0.006s
OK
```
110 tests, 2 live-gated skipped (up from 106). New this round: 3 in `test_reconcile.py` (schedule-check statuses extended, resume after a clean save, stop at a step boundary), 2 in `test_demo.py`.

---

## 10. Honest limits and open questions

Limits: the live run covers 00:00 to 07:55 with schedules that are mostly sleeping echo lines; the only awake agent is Klaus for 55 minutes. The calibration data has 1, 2 and 0 eligible entries, so no threshold can be calibrated from it. The awake-cost figure is one agent, one hour. Nothing here is evidence about recall, efficiency or coherence.

Questions:
1. The model-echo schedules make the agents sleep through the morning. Do you want a prompt-side or parsing-side mitigation (an upstream edit, so a checkpoint), a different pinned model for the evaluation, or a hand-authored schedule for the calibration run?
2. The sweep floor (3) removes almost everything on real early data. Calibrating needs real awake data: do you want a longer live run once schedules are healthy, and what token budget (Klaus alone used about 196K tokens in 55 awake minutes)?
3. Recency in `new_retrieve` (Section 5, item 1): leave as is, or a separate checkpoint?
4. Router key skew (Section 5, item 4): leave, or have the router balance by remaining budget?

REQUEST: Approval of this round and decisions on the questions above. Halting here.

---

## ERRATUM (appended after review; no other number in this report was changed)

**Continuation LLM call count.** Section 3 states 266 LLM calls for the continuation. The router ledger (`ART/p5_staged_live_continue_hourly_ledger.jsonl`, excluding the day-start record) shows **286 calls**: planning 253, dialogue 13, importance_scoring 20. The per-hour table in Section 3 already summed to 286 (6 + 16 + 264); only the headline figures "266 calls", "108,626 in + 108,002 out tokens" (which are ledger tokens and correct for all 286 calls), and the caps text were inconsistent with it.

**Cause.** The 266 is the value of my live cap counter, which wraps `gpt_structure.call_llm`, i.e. the upstream request wrappers (planning, dialogue, reflection paths). The 20 staged importance-scoring calls (6 in the first hour, 14 in the last partial hour) are made by `devmem/memory/episodic.py` through its own `call_llm` import, so they never passed through the counter. It is not a step-boundary effect: the counter stopped the run at a step boundary exactly when it reached 266 (the soft cap), and the 20 uncounted scoring calls had already happened. Phase 1 is unaffected: its counter (138) equals its ledger count (138), because no staged scoring calls occurred in step 0. The earlier 100-call smoke run is also unaffected (ledger 100).

**Consequences.** (1) The cap rules were enforced on non-scoring calls only; measured by the ledger, the continuation used 286 calls, below the 400 hard cap but above the 266 soft cap I reported. (2) The embedding counter was not affected (it counts HTTP requests at the store). (3) Future capped runs should count at the router (or count both `gpt_structure.call_llm` and `episodic.call_llm`); I will do that in any further run.
