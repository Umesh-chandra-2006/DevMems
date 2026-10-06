PHASE: 5, Step 1a (minimal form) plus a scripted Stage 3 sweep (the Stop 1.5 gate was waived for the demo deadline; this is the single report, Stop 2)
STATUS: Partially complete. Step 1a items 1 to 5 and the scripted sweep are done. Skipped on your instruction: item 6 (batch-quota test), item 7 (1-hour measurement run), item 8 (older-release metadata check). The sleep hook, the reflection gate and the retrieval weight are implemented and unit-tested but have not been run inside a live simulation.

Paths are relative to the repo root. `ART/` = `docs/phase5_step1_artifacts/`. Labels: **live** (real API), **scripted** (hand-written events), **synthetic** (constructed vectors or stubbed network), **captured**, **documented**.

---

## 1. WHAT WAS BUILT

**Commits (not pushed).** Before each commit I scanned the staged diff for `AIza`, `gsk_`, `nvapi-`, key-assignment patterns and every `.env` value (7 values): **0 matches** each time, no `.env` file staged.
- `f29a0b8` Phase 4 closure and M1 series (router hardening, 429 classifier, cooldown, captured fixtures, Phase 4 results, plan Rev 2.2). 25 files.
- `aac1d32` Phase 5 Step 0 (runner, reconciliation, embedding store, evidence artifacts, checkpoint report).
- The work in this report is committed as a third commit (hash in my message to you; a report cannot contain its own hash), with the same scan: 0 occurrences of the 7 `.env` values; the only literal matches for the three key-prefix patterns are the pattern names written in this report's own text. `devmem/router/cooldown_state.json` (runtime state) is left out of all commits; I suggest adding it to `.gitignore`.

**Step 1a**
- `devmem/embeddings/vector_store.py` (EmbeddingStore rework): uses the router's primitives. Each HTTP request is counted in `key_usage` with the composite key `{key_env}#{model}` (no schema change). `classify_429` classifies failures and `CooldownManager.set_cooldown` applies them (401/403 skip the key until UTC midnight; 429 follows the router's rules). It rotates across usable keys, skips keys on cooldown or at `rpd_per_key`, and **raises only when every key failed or is unavailable**. No 429 handling of its own. New `offline=True` mode (deterministic vectors, no network) for unit tests only.
- `devmem/config/embeddings.yaml`: `key_envs: [GEMINI_KEY_1, GEMINI_KEY_3]`, `rpd_per_key: 1000`. `GEMINI_KEY_2` is out until fixed.
- `GEMINI_KEY_3` verification: 1 real embed call, HTTP 200, 3072-dim, **live** (`ART/key3_verification_stats.json`). No key was printed.
- `gpt_structure.py` edits (exact lines in Section 4).
- `devmem/run_headless.py`: `fail_loud_llm` set from `config/runner.yaml` (true), scan of saved schedules for router-failure strings after every save (`scan_saved_schedules`, writes `schedule_check.json`), autosave default **15 simulated minutes**, `SIM_CODE` set per run, `reconcile_consolidation` on resume, and a clean-exit `final_sweep` (staged only).
- Tests offline by default: `devmem/testing_env.py` sets `DEVMEM_EMBEDDING_MODE=offline` unless `DEVMEM_LIVE_TESTS=1`. Added as one import line at the top of `test_priors.py`, `test_episodic.py`, `test_reconcile.py`, `test_consolidation.py`, `test_gpt_structure_touch.py`.

**Stage 3 (decisions D1 to D7 as approved)**
- `devmem/memory/consolidation.py`: `cluster_by_similarity` (union-find single linkage, deterministic), `run_nightly_sweep`, `_apply_cluster` (create or reinforce), `force_sweep`, `maybe_sweep_on_sleep` (the hook), `reconcile_consolidation`, `night_id`, plus the two no-op-in-baseline helpers `staged_reflection_disabled` and `apply_consolidated_weight`.
- `devmem/config/consolidation.yaml`: all D4 values as approved (0.78, 0.80, 3, 12, floor 3, idle filter, 6 per night), `consolidated_weight` 0.5, `staged_reflection: false`.
- `devmem/memory/schema.sql`: appended the additive `consolidation_sweeps` table (D7). `semantic_memory` was already defined there and is created by the same code.
- D6: each summary is a thought node `(agent, "consolidated", "memory")` in the live `AssociativeMemory`, `filling` = source node ids, mirrored to `semantic_memory`. D7: marker row per (agent, night) written in the **same SQLite transaction** as the semantic rows and flag flips; a sweep where every cluster fails writes a `failed` marker with an attempt count, not `done`. D3: summaries are scored with `score_importance_persona_conditioned(..., kind="event", persona=persona)`.
- Scenario: `devmem/memory/scripted_sweep.py`, fixture `devmem/memory/fixtures/scripted_day_isabella.json` (16 hand-written events), calibration script `p5_calibrate_scripted_day.py`.
- Tests: `test_consolidation.py` (21 tests, 1 live-gated), `test_gpt_structure_touch.py` (5), new tests in `test_reconcile.py` (7 total) and `test_vector_store.py` (14 total, 1 live-gated).

---

## 2. THE SCRIPTED SWEEP (live embeddings, live LLM, pinned `openai/gpt-oss-20b`)

Setup: 16 scripted events in a real `Persona`/`AssociativeMemory` (staged mode, empty memory), real `gemini-embedding-001` vectors (3072-dim), real SQLite mirror, sleep onset 22:00 via the hook. Groups in the fixture: 5 baking, 4 neighbor conflict, 3 "isolated", 1 below the floor (importance 2), 3 idle (importance 1). Raw: `ART/scripted_sweep_threshold_0_78_default.json`, `ART/scripted_sweep_threshold_0_82_calibrated.json`, `ART/consolidation_log_*.jsonl`, `ART/scripted_day_cosines.json`.

**Threshold, chosen from data and reported both ways.** On this scripted day the within-group cosine mean is 0.845 (baking and conflict) and the cross-group mean is 0.739 (max 0.812). At the approved **0.78** the baking cluster chains in two unrelated "isolated" events (the letter from her sister and the window latch): cluster sizes 7 / 4 / 1. A clean split exists only in a **narrow window, 0.82 to 0.83**; at 0.84 the conflict cluster fragments. I ran 0.78 (approved default) and 0.82 (calibrated on this one day). The 0.82 value is not a recommendation: it comes from 16 events I wrote, and this day is non-evaluation data only. Idle events scored 0.805 to 0.813 against each other, so the importance floor and idle filter, not the threshold, are what keep them out.

**Verbatim results (final runs).**

*Run A, threshold 0.78 (default).* Histogram `{1:1, 4:1, 7:1}`, 11 entries flagged, 2 summaries created.
- node_17, importance 3. Summary: "Isabella consistently demonstrates a caring, community-focused approach, balancing work tasks with personal connections, always ready to fix problems and maintain harmony." Sources:
  - Isabella Rodriguez is baking a batch of croissants at Hobbs Cafe
  - Isabella Rodriguez is kneading dough for the morning pastries
  - Isabella Rodriguez is taking fresh bread out of the oven
  - Isabella Rodriguez is decorating cupcakes for a customer's order
  - Isabella Rodriguez is reading a letter from her sister who lives in another city
  - Isabella Rodriguez is preparing cookie dough for the afternoon rush
  - Isabella Rodriguez is fixing a loose latch on the cafe's back window
- node_18, importance 2. Summary: "When a conflict arises, I should immediately offer a friendly gesture to smooth things over and preserve harmony, even if it means sacrificing my own comfort." Sources:
  - A neighbor shouted at Isabella Rodriguez about the noise coming from the cafe
  - Isabella Rodriguez argued with her neighbor about the late-night noise
  - Isabella Rodriguez apologized to the upset neighbor and offered free coffee
  - Isabella Rodriguez felt tense after the dispute with her neighbor

*Run B, threshold 0.82.* Histogram `{1:3, 4:1, 5:1}`, 9 entries flagged, 2 summaries created.
- node_17, importance 7. Summary: "I notice Isabella is constantly baking and preparing treats for others, which reminds me of the importance of caring for our community and keeping everyone satisfied." Sources: the five baking events (croissants, kneading dough, fresh bread from the oven, decorating cupcakes, cookie dough).
- node_18, importance 6. Summary: "I realize that to keep harmony I often apologize and offer a remedy, even if it leaves me feeling uneasy." Sources: the same four conflict events as run A.

**Checks (all passed in both runs, and again in the live-gated test `TestScriptedSweepLive`, 2 live tests OK):**
- Semantic rows exist with source ids equal to the entries in the prompt; `source_entry_ids` matches the `filling` of the live thought node.
- Flags flipped exactly for the summarized entries (11 in run A, 9 in run B); the idle events, the below-floor event and, in run B, the three "isolated" events stayed `consolidated = 0`. (In run A two of the isolated events were absorbed by the chained cluster; the town-clock event stayed unconsolidated.)
- Second sweep: the hook returned `None`, a direct call returned `{"skipped": "already swept", "night": 1}`; no new nodes or rows.
- `new_retrieve` (real function, all 18 nodes, 15 ranked because upstream excludes "idle" nodes): both summary nodes appear in the ranking.

**What retrieval actually showed (descriptive; 18 nodes, one persona, one run each).** Summary ranks for the three focal points (neighbor argument / conflict handling / baking), weight 0.5:
- Run A: baking-and-more summary (node_17) 7 / 1 / 3; conflict summary (node_18) **15 / 14 / 15** of 15.
- Run B: baking summary (node_17) 1 / 1 / 1; conflict summary (node_18) **9 / 10 / 15** of 15.
The conflict summary was not near the top for the focal points where I expected it to be. I did not investigate why; the ranking combines recency, importance and relevance (`gw = [0.5, 3, 2]`), and node_18 was scored 2 in run A and 6 in run B for what is the same cluster of sources (the summary text differed between runs). So "retrievable" is shown; "retrieved when relevant" is **not** shown for the conflict summary.

**D2 weight, descriptive.** With `consolidated_weight` 0.5 versus 1.0 the mean rank of the consolidated source events moved from 6.45 to 8.09 (run A, neighbor argument) and from 6.44 to 9.33 (run B, neighbor argument), and the mean rank of unconsolidated events moved from 10.0 to 4.5 and from 10.75 to 6.5. All focal points and both runs are in the artifacts. This shows the weight does what the code says on 18 scripted nodes; it says nothing about recall quality.

**Observations, no causal claim.** The summaries are written in first person ("I realize ...", "I should ...") and several echo the priors block text ("harmony", "smooth over", "uneasy", "community"). I did not run a control without the priors block, so I cannot say the priors caused this. Importance scores for summaries of the same cluster differed across runs (2 vs 6; 3 vs 7 for the baking one).

**Call accounting.**
- LLM calls: **28** (14 summaries plus 14 scores, all `staged`, all `openai/gpt-oss-20b`) against the 40 cap. Seven sweeps ran (7 x 4 calls): two early runs before I extended the retrieval analysis, two that I aborted myself through script bugs after the sweep had finished (a console-encoding crash in a print, and an index error on idle nodes in my analysis code), the two final runs reported above, and one run inside the live-gated test.
- Embedding requests recorded in the router ledger today: GEMINI_KEY_3 9, GEMINI_KEY_1 10 (19 total, counted by the new store from the moment it was wired; the ≤38 uncounted calls from Step 0 are separate).

---

## 3. HOW IT MATCHES THE SPEC (compliance table)

| Item | Status | File and line | Proving test or artifact |
|---|---|---|---|
| 1. Commits, key scan counts only, hashes | Done: `f29a0b8`, `aac1d32`; 0 matches; later work uncommitted | n/a | `git log` |
| 2. Remove GEMINI_KEY_2, add GEMINI_KEY_3, verify with one real call | Done, 1 live call 200, 3072-dim | `config/embeddings.yaml:8` | `ART/key3_verification_stats.json` (live) |
| 2. Reuse router key pool, ledger, cooldown; skip on 401/403; fail loud only when all keys fail; no own 429 handling | Done | `vector_store.py` `_candidate_keys`, `_request` | `test_403_skips_key_...`, `test_requests_are_counted_in_router_ledger_...`, `test_per_key_daily_limit_...`, `test_fail_loud_...` (synthetic) |
| 3a. `get_embedding` through EmbeddingStore, same for both conditions | Done | `gpt_structure.py:436-443`, `:416-426` | `test_gpt_structure_touch.py` offline and fail-loud tests; live scripted runs |
| 3b. `fail_loud_llm`: re-raise after counting; runner sets it; upstream behavior preserved when false | Done (applies to all four request wrappers, see Deviations) | `gpt_structure.py:28-40, 69, 108, 143, 357`; `run_headless.py` | `test_default_preserves_upstream_failsafe_but_counts`, `test_fail_loud_flag_reraises_after_counting`, `test_runner_sets_fail_loud_and_scan_flags_...` |
| 3. Runner scan of saved schedules for router-failure strings | Done | `run_headless.py` `scan_saved_schedules` | same runner test |
| 4. Autosave default 15 simulated minutes | Done (Deviation) | `config/runner.yaml` | `test_runner_sets_fail_loud_...` asserts 15 |
| 5. Tests offline by default, live only with `DEVMEM_LIVE_TESTS=1`, report calls per mode | Done | `devmem/testing_env.py` | offline mode: 0 embedding HTTP calls per module (`ART/offline_mode_embedding_calls.jsonl`, synthetic stub run); live mode: 2 live-gated tests, about 4 LLM calls and a few embedding requests |
| 6. Batch-quota test | Skipped by instruction | n/a | n/a |
| 7. 1-hour measurement run | Skipped by instruction | n/a | n/a |
| 8. Older-release metadata check | Skipped by instruction | n/a | n/a |
| 9. Exact lines for scaling, reflect gate, sleep hook | Done (implemented, Section 4) | Section 4 | tests below |
| 10. List copyanything patch and os.chdir under Deviations | Done (Section 5) | n/a | n/a |
| (b) Scripted sweep: real embeddings, real AssociativeMemory and SQLite, at most 40 LLM calls, at least one semantic memory with correct sources, flipped flags, thought node retrievable via new_retrieve | Done, 28 LLM calls | `scripted_sweep.py` | Section 2, `TestScriptedSweepLive` |
| D1 Option A plus B flag | Done in code and tested on the real `reflect()` | `reflect.py:183-186`, `consolidation.py:479` | `test_d1_flag_matrix_on_real_reflect_function` (baseline calls it, staged does not, staged plus flag does) |
| D2 (ii) weight 0.5 | Done, tested on the real `new_retrieve` | `retrieve.py:251-254`, `consolidation.py:486` | `test_d2_weight_demotes_consolidated_sources_in_real_new_retrieve` (offline vectors) and Section 2 (live) |
| D3 scoring | Done | `consolidation.py` `run_nightly_sweep` | `ART/scripted_sweep_*.json` rows |
| D4 values as config, thresholds not frozen yet | Done | `config/consolidation.yaml` | cap and floor tests |
| D5 gemini-embedding-001, no local download | Done | `config/embeddings.yaml` | live runs |
| D6 thought node with sources in `filling`, mirrored | Done | `consolidation.py:223` `_apply_cluster` | `test_creates_semantic_memory_with_sources_and_flags` |
| D7 `consolidation_sweeps`, night keying, transaction, failure retry, `force_sweep`, rollback on reload | Done | `consolidation.py:105, 275, 403, 408, 430`; `schema.sql` | `TestSleepGuardAndReload` (6 tests), `test_failed_sweep_...`, runner `test_clean_exit_forces_a_sweep_...` |
| Baseline unchanged | Helpers are no-ops, existing suites pass | Section 4 | `test_helpers_are_noops_in_baseline`, full suite |

---

## 4. `reverie/` EDITS, exact lines (current file state; all additive, no deletions)

| File | Lines | Change |
|---|---|---|
| `persona/persona.py` | 239-243 | Sleep hook after `plan = self.plan(...)` (`:238`): in staged mode calls `maybe_sweep_on_sleep(self)` (touch point 4). |
| `persona/cognitive_modules/reflect.py` | 183-186 | D1 gate: `if reflection_trigger(persona) and not staged_reflection_disabled():` (touch point 4). |
| `persona/cognitive_modules/retrieve.py` | 251-254 | D2: `master_out = apply_consolidated_weight(persona, master_out)` before `top_highest_x_values` (new touch point 5). |
| `persona/prompt_template/gpt_structure.py` | 28-40 | `ROUTER_FAILURES` counter and `_count_router_failure` (re-raises when `utils.FAIL_LOUD_LLM`). |
| same | 69, 108, 143, 357 | One call to `_count_router_failure` in each of `ChatGPT_single_request`, `GPT4_request`, `ChatGPT_request`, `GPT_request`. |
| same | 416-426 | `_get_embedding_store()` (lazy `EmbeddingStore`, stats path per run). |
| same | 436-443 | `get_embedding` routes through the store unless `DEVMEM_EMBEDDING_MODE=legacy`; the original code below it is intact and unused. |

Baseline reflect and retrieve now import `devmem.memory.consolidation` and call the no-op helpers; their results are unchanged in baseline mode (tested).

---

## 5. DEVIATIONS (complete)

1. **Autosave default changed from 60 to 15 simulated minutes** (verdict item 4).
2. **`reverie.copyanything` in-memory patch:** `HeadlessRunner(resume=True)` replaces `reverie.copyanything` with a no-op for the duration of the `ReverieServer(...)` constructor call and restores it in a `finally`. Nothing on disk in `reverie/` changes.
3. **`os.chdir`:** `devmem/run_headless.py` calls `os.chdir` to `reverie/reverie/backend_server` at import (upstream paths are cwd-relative), as `run_baseline_sim.py` does. The runner test restores the working directory in `tearDownClass`.
4. **`_count_router_failure` added to all four request wrappers**, not only `GPT_request` (they have the same masking; 1 extra line each).
5. **`get_embedding` is now fail-loud in baseline too** (identical for both conditions, as directed). Baseline previously fell back silently to a 768-dim vector on any embedding error; it now raises `EmbeddingError`. `DEVMEM_EMBEDDING_MODE=legacy` restores the old path.
6. **Upstream still swallows re-raised exceptions in places:** `safe_generate_response` (`gpt_structure.py`) catches `Exception` and retries, then returns the fail-safe. So `fail_loud_llm` makes the failure counted and visible (`ROUTER_FAILURES`), not necessarily fatal. The counter and the schedule scan are the authoritative records.
7. **Summarization prompt:** the template text is the plan's, plus a one-line system prompt ("Reply with exactly one sentence and nothing else"). `summary_tier` is `strong`, overridden by the pinned model in these runs.
8. **New files:** `devmem/testing_env.py`, `devmem/config/consolidation.yaml`, `devmem/memory/scripted_sweep.py`, `fixtures/scripted_day_isabella.json`, `p5_calibrate_scripted_day.py`, `test_consolidation.py`, `test_gpt_structure_touch.py`, `docs/phase5_step1_artifacts/`. **Edited existing files:** `episodic.py` unchanged this round; `test_priors.py`, `test_episodic.py` (one import line each), `test_reconcile.py`, `test_vector_store.py`, `run_headless.py`, `vector_store.py`, `embeddings.yaml`, `runner.yaml`, `schema.sql` (appended table).
9. **Runtime artifacts:** git-ignored directories `devmem/storage/p5_scripted_sweep_threshold_*` (the final run databases) and caches; tracked `temp_storage` files restored by the runner test as before. The `live_test` run directory is removed by the test.
10. **Router test flake (observed once, not investigated):** `test_router` took 88 s in one run (3 s normally). It shares the real `cooldown_state.json`, which is untracked runtime state.
11. **Not done on purpose:** no live simulated step has run with the new hook; `persona.move` itself was not executed end to end in a test (the hook function, the real `reflect()` gate and the real `new_retrieve` weight were).

---

## 6. TESTS RUN / VERIFICATION

Full suite, offline default (`ART/full_suite_output_offline_default.txt`), verbatim:

```
=== devmem.router.test_router
Ran 33 tests in 3.478s
OK
=== devmem.memory.test_priors
Ran 9 tests in 1.968s
OK
=== devmem.memory.test_episodic
Ran 10 tests in 1.695s
OK
=== devmem.memory.test_reconcile
Ran 7 tests in 23.271s
OK
=== devmem.memory.test_gpt_structure_touch
Ran 5 tests in 0.028s
OK
=== devmem.memory.test_consolidation
Ran 21 tests in 2.031s
OK (skipped=1)
=== devmem.embeddings.test_vector_store
Ran 14 tests in 1.343s
OK (skipped=1)
```
99 tests, 2 live-gated skipped. With `DEVMEM_LIVE_TESTS=1` the two live tests (`TestScriptedSweepLive`, `TestLiveEmbedding`) ran separately and passed (OK, 2 tests, 15 s).

Live embedding calls by mode: default offline mode **0** (counted with a stubbed network and fake keys, all six modules, `ART/offline_mode_embedding_calls.jsonl`, synthetic). Live mode for the old-style modules (priors, episodic) I did not re-run; at Step 0 their unique texts needed 14 and 6 requests on a cold cache, and the new persistent cache makes repeats free (not re-measured).

Artifact index: `ART/key3_verification_stats.json` (live), `scripted_day_cosines.json` and `scripted_day_embedding_stats.json` (live embeddings), `scripted_sweep_threshold_0_78_default.json`, `scripted_sweep_threshold_0_82_calibrated.json` (live, scripted events), `consolidation_log_threshold_*.jsonl`, `offline_mode_embedding_calls.jsonl` (synthetic), `full_suite_output_offline_default.txt`.

---

## 7. HONEST LIMITS (what is not demonstrated)

- One scripted day, one persona, one run per threshold. Nothing here is evidence about recall, efficiency or coherence.
- The clean cluster split needs a threshold in a narrow window (0.82 to 0.83) on this data; at the approved 0.78 the clusters chain. How the real simulation's events behave is unknown; thresholds should be re-checked on real calibration data (the skipped measurement run would supply it).
- Summaries are first person, echo the priors text, and their importance scores varied between runs. No quality control or priors-ablation was run.
- The conflict summary was not retrieved near the top for conflict-related focal points; I did not investigate why.
- Hook, gate and weight are unit-tested against real upstream functions but have not run inside a live simulation step.
- `get_embedding` fail-loud: with only two working keys and 1,000 requests per day per key (one counted limit; whether batches count per request is unresolved) a long run can raise.

---

## 8. OPEN QUESTIONS FOR HIGHER AUTHORITY

1. Threshold: keep 0.78 (chains on this day) or calibrate on the real calibration dataset from the deferred measurement run before freezing? I recommend the latter and not freezing 0.82.
2. Summary voice and scoring: summaries come out first person and score unevenly; do you want the prompt to require third person, and the score to use `kind="event"` as approved?
3. Add `cooldown_state.json` to `.gitignore`?
4. When should I run the deferred items: the 1-hour measurement run, the batch-quota test with your counter readings, the older-release metadata check?
5. `GEMINI_KEY_2` is still excluded; tell me when it is fixed.

REQUEST: Approval of Step 1a and the scripted Stage 3 sweep, and a decision on question 1 before any thresholds are frozen. Halting here.
