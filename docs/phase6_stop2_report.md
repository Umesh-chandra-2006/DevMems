PHASE: 6, Stage 4 identity memory, STOP 2 (offline build, no LLM calls)
STATUS: Complete for Stop 2. Halting for PM review. Stop 3 (live confirmation) has NOT been started.

Paths are relative to the repository root. Labels: **scripted** (hand-written fixture), **synthetic** (unit vectors with chosen cosines, stubbed generators), **live** (a real external request), **offline-captured**, **derived**. No em dashes are used in any file added or changed this round. Step D is a separate parallel task with its own report (`docs/phase6_stepd_report.md`); it is only mentioned here under Deviations because it shares the working session.

## 1. WHAT WAS BUILT

| Piece | Where |
|---|---|
| Stage 4 module (replaces the Phase 1 docstring-only stub) | `devmem/memory/identity.py` (640 lines). Schema DDL 39-85; flags 106-130; Stage 3 side `record_consolidation_events` 160-183; scoring context 187-218; feed-forward `render_identity_context` 241-251, `load_identity_context` 254-270, `log_prompt_render` 273-286; the nightly step `run_identity_step` 305-541; `apply_cap` 543-555; `reconcile_identity` 558-636 |
| Config with provenance | `devmem/config/identity.yaml` (flags default off, all constants) |
| Stage 3 hook points (additive; flag off executes none of them) | `devmem/memory/consolidation.py`: lazy import and table init 332-335; `consolidation_events` write inside the existing transaction 425-426; `force_sweep` and `_run_identity_after` 460-474; the sleep hook chains the identity step and only marks a night finished when both steps are finished 495-506 |
| Scorer feed-forward and scoring-context record (no upstream edit) | `devmem/memory/episodic.py`: scorer 299-329 (renders the traits itself when `identity_context` is empty and feedback is on); `log_episodic_node` 433-435 |
| Reload wiring | `devmem/run_headless.py`: `identity_reconcile` attribute (122) and the call after `reconcile_consolidation` (135-137), only when Stage 4 is on |
| Scripted fixture (spec 5.1) | `devmem/memory/fixtures/scripted_four_nights_isabella.json` |
| Golden Phase 5 prompts | `devmem/memory/fixtures/phase5_staged_prompts.json`, **captured** from the Phase 5 code at HEAD 9c60c86 before any Stage 4 edit (4 cases) |
| Tests | `devmem/memory/test_identity.py` (35 tests) |
| Tuning script (pre-registered protocol) | `devmem/memory/p6_tune_reinforce.py` |
| Fixture replay with artifacts | `devmem/memory/p6_fixture_run.py` |

Behavior as built (matches the approved Stop 1 design unless listed in section 3):
- Nightly order: Stage 3 consolidation commits (its `consolidation_events` rows in the same transaction, only when `STAGE4_ENABLED`), then the identity step reads those rows. A `done` identity marker makes a rerun a no-op; the marker, reinforcement rows, traits and the cap commit in one transaction after every LLM and embedding call has finished.
- Reinforcement counts a night when Stage 3 created the entry, or merged into it at cosine >= `REINFORCE_THRESHOLD`, and the guard passes (pre-registration section 3). Merges between 0.80 (Stage 3) and the threshold are logged as `merged_by_stage3_below_stage4_threshold` and add no day.
- Path A: `distinct_days >= 3` (count_based) or `same_day_max >= 4` (same_day). Path B: an episodic row with importance >= T (9) in the window since the previous done identity sweep, unless it was scored with a matching trait present or has `unknown` scoring context (addendum A1, recorded as `self_reinforced_pivotal`).
- One LLM call per graduating source, third person, one corrective retry, at most 35 words (prompts are the verbatim Stop 1 proposals).
- Cap: more than 5 active traits deactivates the oldest; the context renders at most 5 traits newest first and drops the oldest whole trait until the header plus lines fit 120 estimated tokens.
- `reconcile_identity` implements the single rollback rule from the Stop 1 design.

## 2. REINFORCE_THRESHOLD TUNING (pre-registered protocol, section 2; **live** embeddings, **scripted** text, no LLM)

Artifacts: `docs/phase6_stop2_artifacts/reinforce_tuning.json`, `.md`, `reinforce_tuning_embedding_stats.json`. Model `gemini-embedding-001`, 3072 dimensions. **1 real embedding request** (cap 40), 6 cache misses, HTTP 200.

- Positives (the three baking pairs, nights 1/2/4): 0.8923, 0.9202, 0.9432. Min 0.8923.
- Negatives (12 different-theme pairs): max 0.8583 (baking n1 vs the author-chosen `cake_negative`); the others 0.7224 to 0.8526.
- Min positive > max negative (margin 0.034), so the protocol gives floor((0.8923 - 0.01) x 100) / 100 = 0.88, inside [0.80, 0.90], and max negative 0.8583 < 0.88. **Chosen and frozen: `reinforce_threshold: 0.88`** (config comment and the artifact record it; a unit test recomputes it from the saved cosines).
- What this does and does not show: there are only three positive pairs from one recurring theme, and the negative is a theme the author chose to be topically close. The margin is a property of those choices, not a measurement of how natural-run summaries behave.
- Observation (not a design change): the real cosines of `cake_negative` to the baking summaries are 0.844 to 0.858, above Stage 3's merge threshold 0.80. A real Stage 3 sweep would therefore merge that different theme into the baking entry (adding its sources to the entry's fillings) while Stage 4 correctly adds no day. That is Phase 5 behavior at 0.80, which you approved keeping (Q4 option a); it means the Stage 3 entry's source list can contain topically close but different events.

## 3. CONDITIONS COMPLIANCE TABLE

| Condition (spec 5.2, Stop 1 approvals, PM rules) | Status | File and line | Proving test |
|---|---|---|---|
| Idempotent rerun of a night: no new traits, counters unchanged | Done | identity.py 329-337 (marker check) | `TestIdempotenceAndCrash.test_rerun_of_a_night_changes_nothing` (full table dump equal, zero extra LLM calls, direct and via the hook after a reload) |
| Crash between consolidation and identity, reload: state equals a clean run | Done | consolidation.py 495-506; identity.py 305-541 | `test_crash_between_consolidation_and_identity_then_reload_matches_a_clean_run` (night 4 consolidation commits, identity skipped, all three reconcilers run and change nothing, hook completes, full dump equals the clean run) |
| Cap: sixth trait evicts the oldest | Done | identity.py 543-555 | `TestCapAndRendering.test_sixth_trait_evicts_the_oldest_and_five_remain_active` |
| 120-token cap holds, no sentence cut | Done | identity.py 241-251 | `test_context_has_at_most_five_traits_newest_first_and_stays_within_the_token_cap` (also a single trait too long to fit is dropped, not cut) |
| Flag off: scoring prompt byte-identical to Phase 5 (saved prompts) | Done | episodic.py 299-329 | `TestFeedForwardPrompt.test_flag_off_prompt_is_byte_identical_to_the_phase_5_golden_prompt` (4 golden cases, through `build_staged_prompt` and the real scorer, even with a trait stored) |
| `IDENTITY_FEEDBACK=false` leaves `identity_context` empty, traits still stored | Done | identity.py 127-130 | `test_feedback_off_leaves_identity_context_empty_although_traits_are_stored` (config flag and the environment override) |
| Path B fires at T, not below | Done | identity.py 434-459 | `TestPathBThreshold.test_fires_at_the_threshold_and_above_not_below` (8, 9, 10 with T=9), `test_threshold_is_config_not_hard_coded`, `test_each_event_is_evaluated_once_and_never_graduates_twice` |
| Third-person trait text, no first-person pronouns, fixture cases | Done | identity.py 461-487 | `test_trait_text_is_third_person_and_names_the_agent`, `test_first_person_reply_gets_one_corrective_retry_then_succeeds`, `test_failed_identity_step_leaves_no_done_marker_and_retries_next_tick` |
| Scripted four nights: Path A on night 4, same day on night 3, once-theme never graduates, Path B, negative just under the threshold | Done | fixture JSON | `TestScriptedFourNights.test_each_theme_follows_its_path_night_by_night` and `test_negative_theme_decision_is_logged_with_its_cosine` |
| Guard (3.5 and A1): matching trait present means no counted night and no Path B graduation; unknown treated as self-reinforced; counted and self-reinforced reported separately | Done | identity.py 382-418, 434-459 | `TestGuard` (6 tests incl. ablation compares like with like) |
| Reload reconcile restores the exact older state, idempotent | Done | identity.py 558-636 | `TestReconcile.test_reload_from_an_older_save_restores_the_exact_older_state_and_is_idempotent` (real `AssociativeMemory` save and reload); `test_traits_evicted_only_by_a_deleted_newer_trait_become_active_again` |
| Real upstream classes, not mocks only | Done | n/a | the fixture tests use the real `Persona`, `AssociativeMemory`, Stage 3 sweep, sleep hook and scorer; `TestRunnerStage4Wiring` uses the real `HeadlessRunner` and `ReverieServer` with save and resume (stub only the step body, as in `test_reconcile`) |
| Stage 4 off executes none of the new code; no new table | Done | consolidation.py 332-335, 425; episodic.py 433 | `TestFlagOffIsPhaseFive`; the 27 Phase 5 consolidation tests and 10 reconcile tests pass unchanged |
| Reinforcement cosine of every decision saved | Done | identity.py 382-418 | artifact `docs/phase6_stop2_artifacts/fixture_run_reinforcement_decisions.jsonl` |
| One exact rendered scoring prompt per agent per night saved | Done | identity.py 273-286 | `test_feedback_on_appends_the_traits_after_the_priors_block` (once per night); artifacts `fixture_run_identity_prompt_renders.jsonl`, `fixture_run_rendered_scoring_prompt.txt` |
| Tuning protocol applied as committed, at most 40 embedding requests, no LLM | Done | p6_tune_reinforce.py | 1 request; `TestTuningProtocol` (4 tests incl. clipping and the keep-0.85 branches) |
| Approved Stop 1 items Q1 to Q7 (extension columns, two additive tables, Path B at night step, option a, T=9 provisional, 40 requests, Step C held) | Applied | identity.py 39-85 | the tests above |
| No upstream (`reverie/`) edit | Compliant | `git status reverie` clean | n/a |
| Do not start Stop 3 | Compliant | n/a | no live LLM call this round |

## 4. DEVIATIONS (complete)

- `devmem/memory/identity.py` was the Phase 1 stub (a docstring). It is now the Stage 4 module.
- Non-upstream files outside `identity.py` that changed: `devmem/memory/consolidation.py` (3 additive insertions, all gated by `STAGE4_ENABLED`), `devmem/memory/episodic.py` (scorer block and `log_episodic_node`; both gated), `devmem/run_headless.py` (reconcile call, gated; plus an empty-list default attribute).
- Design details I decided that the Stop 1 text did not spell out (please confirm or change):
  1. **Path B event window.** Each night evaluates events with `sim_timestamp` after the previous done identity sweep and up to this night's sweep time, so each event is judged once. A retry of a failed night keeps the same window. Events that fail trait generation on every attempt (3 attempts) are lost to Path B; Path A candidates are not (they are re-scanned every night).
  2. **`same_day_max`** is updated only on counted nights (born, or merged at or above the threshold, guard passed). Sources attached by a below-threshold merge do not count toward the same-day path.
  3. **Guard match for a trait with no source semantic entry** (a pivotal trait): the entry summary vector is compared with the trait text embedding at `REINFORCE_THRESHOLD`; for Path A traits the source semantic entry or any entry within the threshold of it matches. The pre-registration section 3 defined "matching" through the source semantic entry only.
  4. **Scoring-context statuses.** Besides `ok` and `unknown` I added `rule` (rule-assigned idle rows, which never reach the scorer, so they would otherwise all read as `unknown`). A row for which no scoring note exists and that is not idle is `unknown`; a caller-supplied `identity_context` is also recorded `unknown` because its trait ids are not known. A source with no row at all (mirrored before Stage 4 was enabled) counts as scored without traits.
  5. **Eviction ties:** oldest `created_night`, then lower reinforcement count, then creation order. The rendering order is newest first, ties by higher reinforcement count (spec 3.4).
  6. **Ledger purpose** for trait calls is a new string, `identity_trait`.
  7. **Tuned value 0.88** differs from the 0.85 start by the protocol; it widens the 0.80 to 0.88 band in which Stage 3 merges add no Stage 4 day. The merge-band count is reported at Stop 3 as agreed.
- Runtime artifacts: I ran `ReverieServer` tests; `curr_sim_code.json` restored from git and `curr_step.json` and fork copies removed after each run.
- Step D (parallel, separate report): the worktree `D:\DevMems_stepd` (detached at 9c60c86) holds copies of the git-ignored local files it needs (`.env`, `reverie/reverie/backend_server/utils.py` which is ignored by the upstream `.gitignore`, and the embedding cache `devmem/storage/embedding_cache.db`). The first launch failed immediately with `No module named 'utils'` before any call was made (that file is ignored and was missing from the worktree); it was copied and relaunched. No call was lost or counted twice.

## 5. TESTS

Full suite, offline default, verbatim (`docs/phase6_stop2_artifacts/full_suite_output.txt`):

```
=== devmem.router.test_router
Ran 33 tests in 3.956s
OK
=== devmem.router.test_call_counter
Ran 4 tests in 1.863s
OK
=== devmem.router.test_output_normalizer
Ran 4 tests in 0.000s
OK
=== devmem.router.test_normalizer_wiring
Ran 8 tests in 2.261s
OK
=== devmem.router.test_normalizer_rule
Ran 9 tests in 0.163s
OK
=== devmem.router.test_normalizer_call_path
Ran 7 tests in 5.685s
OK
=== devmem.memory.test_priors
Ran 9 tests in 1.997s
OK
=== devmem.memory.test_episodic
Ran 10 tests in 1.721s
OK
=== devmem.memory.test_reconcile
Ran 10 tests in 50.595s
OK
=== devmem.memory.test_gpt_structure_touch
Ran 5 tests in 0.031s
OK
=== devmem.memory.test_consolidation
Ran 27 tests in 9.696s
OK (skipped=1)
=== devmem.memory.test_identity
Ran 35 tests in 80.575s
OK
=== devmem.embeddings.test_vector_store
Ran 14 tests in 1.429s
OK (skipped=1)
=== devmem.demo.test_demo
Ran 2 tests in 0.008s
OK
```

Count: 177 tests, 2 live-gated skipped (142 before this round plus 35 new). New tests by class: `TestScriptedFourNights` 5, `TestIdempotenceAndCrash` 5, `TestPathBThreshold` 3, `TestGuard` 6, `TestCapAndRendering` 3, `TestFeedForwardPrompt` 4, `TestReconcile` 2, `TestFlagOffIsPhaseFive` 1, `TestTuningProtocol` 4, `TestRunnerStage4Wiring` 2.

## 6. RAW ARTIFACTS (`docs/phase6_stop2_artifacts/`)

| File | Label | What it holds |
|---|---|---|
| `reinforce_tuning.json`, `.md`, `reinforce_tuning_embedding_stats.json` | live embeddings, scripted text | every cosine, the decision, request count and HTTP statuses |
| `fixture_run_tables.json` | scripted, synthetic vectors, stubbed generators | all Stage 4 tables and the Stage 3 tables after the four nights |
| `fixture_run_reinforcement_decisions.jsonl` | same | one line per reinforcement and pivotal decision with the cosine and threshold |
| `fixture_run_identity_log.jsonl` | same | per night: decision counts, traits created with their prompts |
| `fixture_run_consolidation_log.jsonl` | same | Stage 3 per-night records |
| `fixture_run_rendered_scoring_prompt.txt`, `fixture_run_identity_prompt_renders.jsonl` | rendered by the real scorer from scripted traits; no model called | the exact scoring prompt once traits exist |
| `full_suite_output.txt` | offline | the output pasted above |

Fixture result (**synthetic**, from `fixture_run_reinforcement_decisions.jsonl`): night 1 baking born; night 2 baking counted at cosine 0.95, letters born, the score-10 event graduates (pivotal); night 3 conflict born with 5 sources (same_day trait), the cake negative merged by Stage 3 at 0.87 and recorded `merged_by_stage3_below_stage4_threshold` (threshold 0.88); night 4 baking counted at 0.95 and graduates by count_based on distinct days [1, 2, 4]. Letters stays at one day and three sources and never graduates. The cosines are constructed (unit vectors), so they illustrate the logic and are not evidence about real embeddings; the real-embedding evidence is section 2.

## 7. SCRIPTED VS LIVE

Everything except section 2 is scripted or synthetic and offline. Section 2 is the only live item: one embedding request, zero LLM calls. No router LLM call was made by Stop 2 work.

## 8. JUNIOR DEVELOPER TASKS

None.

## 9. OPEN QUESTIONS

1. Confirm or change the seven design details in section 4 (Path B window, `same_day_max` accounting, pivotal-trait guard match, `rule` and `unknown` statuses, eviction ties, ledger purpose, 0.88).
2. Stage 3 merges at 0.80 while Stage 4 counts at 0.88 (section 2 observation). Keep as approved, or revisit at Stop 3 after the merge-band count?
3. Stop 3 estimate (not started): about 16 LLM calls plus retries against the cap of 40, and embeddings for the fixture sentences are already cached; the live run needs trait-text embeddings (one per trait per night, cache first). Model per the Step B decision (Gemini, pinned). Please confirm that is the intended Stop 3 setup.

REQUEST: Review of Stop 2 and answers to the questions above. Halting. Stop 3 will not start until you approve.
