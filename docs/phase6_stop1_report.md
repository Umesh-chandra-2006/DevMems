PHASE: 6, Stage 4 identity memory, STOP 1 (design checkpoint; no Stage 4 code, no live calls)
STATUS: Complete for Stop 1. Halting for PM approval. Phase 6 build (Stop 2) has not started.

Paths are relative to the repository root. Labels: **offline-captured** (computed from saved artifacts), **synthetic** (stubbed provider in tests), **derived**, **design** (a proposal, not a measurement). No em dashes are used in this report, the pre-registration, or the code comments added this round.

## 0. Also done this round (not Phase 6): output normalizer wired behind a flag

Per your decision the normalizer is wired but **not adopted**:
- `devmem/router/output_normalizer.py` (`enabled`, `prompt_kind`, `maybe_normalize`, `STATS`) and 2 insertions in `devmem/router/llm_router.py` (a helper `_log_raw_reply` and a block just before the success return in `call_llm`).
- **Default off.** It acts only when `DEVMEM_OUTPUT_NORMALIZER` is exactly `on` (case-insensitive, whitespace ignored; any other value is off). It is an **allow-list** of three upstream prompts (wake-up hour, daily plan, hourly schedule, identified by fragments of the rendered templates) and two decomposition fragments veto any match, so the task-decomposition prompts (`task_decomp_v3`, `new_decomp_schedule_v1`) can never be touched. The flag is process-wide, so it applies identically to baseline and staged.
- An optional raw-reply log (`DEVMEM_RAW_REPLY_LOG=<file>`, default off) appends the full raw reply and the delivered text of every call, for Step C.
- **Tests, offline** (`devmem/router/test_normalizer_wiring.py`, 8 tests): prompts are rendered by upstream's own code from the real templates; provider stubbed. They prove: the allow-list matches exactly the 3 intended prompts and none of 8 others (pronunciatio, event triple, upstream poignancy, focal points, both decomposition templates, the staged scoring prompt, the consolidation summary prompt); decomposition prompts are vetoed even when poisoned with an allow-listed phrase; default off returns the provider text byte for byte for every prompt; with the flag on the three prompts are normalized and the others keep their `(duration in minutes ...)` annotation; identical output for `condition` baseline and staged; `return_obj` keeps token counts; the raw log is off by default and records raw and delivered when on.
- Step C waits until Phase 6 Stop 1 is approved, as instructed. No live call was made this round.

## 1. WHAT WAS BUILT (Stop 1 deliverables)

- `docs/phase6_preregistration.md`, **committed as `2e5e49b` before any histogram was computed**: the section 4 rule, the exact reference population and exclusions, the `REINFORCE_THRESHOLD` tuning protocol, the self-reinforcement choice.
- `devmem/memory/p6_stop1_score_histograms.py` (analysis only, offline) and `docs/phase6_stop1_artifacts/score_histograms.json` / `.md`.
- This report (the design). No Stage 4 module, table, or hook exists yet.

## 2. DESIGN

### 2.1 Where Stage 4 plugs in (no upstream edit)
- The existing sleep hook (`persona.py:239-243`) already calls `maybe_sweep_on_sleep`. Stage 4 runs inside that same call, **after** consolidation, as a second night-keyed step. With `STAGE4_ENABLED` false nothing in this section executes and Phase 5 behavior and artifacts are unchanged.
- Feed-forward uses the existing `identity_context` parameter. `perceive.py` (already staged-only) calls `score_importance_persona_conditioned(...)` without it, so the scorer itself will, when `identity_context` is empty and Stage 4 plus `IDENTITY_FEEDBACK` are on, load the agent's active traits from the run database. That code is in `devmem/memory/episodic.py`, not upstream.
- Config: new `devmem/config/identity.yaml` (values below); the environment variables `STAGE4_ENABLED` and `IDENTITY_FEEDBACK` override it for run scripts.

### 2.2 Schema (new tables, created idempotently in the per-run `memory.db`)

```sql
CREATE TABLE IF NOT EXISTS semantic_reinforcement (
    agent_id TEXT NOT NULL, semantic_id TEXT NOT NULL,
    day_set_json TEXT NOT NULL,            -- JSON array of night ids that COUNT (birth night first)
    distinct_days INTEGER NOT NULL,        -- len(day_set)
    same_day_max INTEGER NOT NULL,         -- max NEW source events attached in one night
    last_night INTEGER NOT NULL,
    self_reinforced_json TEXT NOT NULL DEFAULT '[]',   -- EXTENSION: nights recorded but not counted (guard, 2.7)
    PRIMARY KEY (agent_id, semantic_id));
CREATE TABLE IF NOT EXISTS identity_traits (
    agent_id TEXT NOT NULL, trait_id TEXT NOT NULL,    -- "{agent}:trait_{n}"
    text TEXT NOT NULL,
    path TEXT NOT NULL,                    -- 'count_based' | 'same_day' | 'pivotal'
    source_semantic_ids_json TEXT NOT NULL, source_event_ids_json TEXT NOT NULL,
    created_night INTEGER NOT NULL, created_sim_time TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,     -- 0 once evicted by the cap; never re-created (idempotent per source)
    PRIMARY KEY (agent_id, trait_id));
CREATE TABLE IF NOT EXISTS identity_sweeps (
    agent_id TEXT NOT NULL, night INTEGER NOT NULL, status TEXT NOT NULL,   -- done | failed
    sweep_time TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,          -- EXTENSION: same fields as consolidation_sweeps
    PRIMARY KEY (agent_id, night));
```
The two marked EXTENSION columns go beyond the spec's column lists; they are needed for rollback (sweep_time) and bounded retry (attempts), exactly as in `consolidation_sweeps`. **Needs your approval** (Q1).

**Two additive tables I propose, needing approval (Q2):**
1. `consolidation_events(agent_id, night, semantic_id, action, match_similarity, new_source_ids_json, PRIMARY KEY (agent_id, night, semantic_id))`, written by Stage 3 **in its existing transaction**, and only when `STAGE4_ENABLED`. Why: Phase 5 keeps per-night results only in `consolidation_log.jsonl`, which is not reconciled and is not in SQLite. The identity step must be a pure function of the database so that "crash between consolidation and identity, then reload" reproduces a clean run and a rerun is a no-op. The table records, per night and entry, whether it was created or reinforced by Stage 3, the match cosine, and the new source ids.
2. `event_scoring_context(agent_id, entry_id, trait_ids_json, status)`, to record `scored_with_identity` (spec 3.5 says "record the flag on the event", but `episodic_memory` has no column and a schema change to it needs its own approval). Mechanism: the scorer, when it renders a non-empty `identity_context`, stores a pending record keyed by (agent, sim time, hash of the scored text) in memory; `log_episodic_node` consumes it when the event is mirrored and writes the row. If the key is not found at mirror time the row is written with `status='unknown'` and treated as self-reinforced (the conservative reading), and the count of unknowns is reported. Alternative if you prefer no new table: derive the flag from `identity_traits.created_sim_time` and the cap rule; that is less exact because evictions are not timestamped. I recommend the table.

**Reconciliation (reload from an older save).** One rule, applied by `reconcile_identity(persona, db)` after `reconcile_consolidation`: delete `identity_sweeps` rows with `sweep_time` later than the loaded clock; delete `identity_traits` rows with `created_sim_time` later than the loaded clock or whose source semantic entry no longer exists, and re-activate traits that were evicted only by a deleted newer trait; rebuild `semantic_reinforcement` for every surviving entry from the surviving `consolidation_events` rows (so it never needs rolling back separately); delete `event_scoring_context` rows whose episodic entry is gone. Idempotent; a reconcile test is in the plan (2.9).

### 2.3 Constants (config, with provenance)

| Name | Value | Status |
|---|---|---|
| `STAGE4_ENABLED` | false | spec; default off |
| `IDENTITY_FEEDBACK` | true when Stage 4 is on | spec; ablation flag |
| `COUNT_THRESHOLD_DAYS` | 3 | plan section 8; distinct days including the birth night |
| `SAME_DAY_COUNT` | 4 | spec 3.2; **design choice, not measured** |
| `REINFORCE_THRESHOLD` | 0.85 start; tuned once at Stop 2 by the committed protocol, then frozen | spec 3.1 |
| `PIVOTAL_THRESHOLD` (T) | **9** by the pre-registered rule (2.8) | see Q5 |
| `MAX_IDENTITY_TRAITS` | 5 | spec 3.4 |
| `IDENTITY_TOKEN_CAP` | 120, estimated with the router's `estimate_tokens` (about 1.35 tokens per word) | spec 3.4; an estimate, the Stop 3 report quotes ledger tokens |
| `trait_max_words` | 35 | design; keeps one trait far below the cap |
| `trait_retries` | 1 | design; same corrective retry as summaries |

### 2.4 Nightly identity step (design)
After `run_nightly_sweep` commits for night n (the existing marker), the identity step for (agent, n) runs once: skip if an `identity_sweeps` row with status `done` exists.
1. **Reinforcement (3.1).** Read tonight's `consolidation_events` rows. A `created` row starts `semantic_reinforcement` with day_set `[n]` and `same_day_max` = number of new sources. A `reinforced` row with `match_similarity >= REINFORCE_THRESHOLD` and a passing guard (2.7) adds n to day_set and updates `same_day_max` and `last_night`; every decision (cosine, threshold, counted or `self_reinforced`) is appended to `reinforcement_decisions.jsonl`, so the margin is visible. A `reinforced` row below the threshold is logged as `merged_by_stage3_below_stage4_threshold`.
2. **Path A.** An entry with `distinct_days >= 3` (count-based) or `same_day_max >= 4` (same-day) and no existing trait for (agent, semantic_id) graduates.
3. **Path B.** Scan the agent's episodic rows with `sim_timestamp <=` the sweep time and `importance_score >= T` whose id is in no trait's `source_event_ids`; each graduates.
4. **Trait text.** One LLM call per graduating source (2.5). Written with the marker row in one transaction, after all LLM calls, exactly as in Stage 3. A failure leaves no `done` marker and retries on a later tick up to `max_attempts_per_night`.
5. **Cap.** After writing, if more than 5 traits are active, deactivate the oldest (ties: lower reinforcement count first).

**Deviation from the plan, disclosed:** plan section 8 has Path B fire immediately from `episodic.py`. Without editing `perceive.py` there is no point at which a scored event can trigger it, so Path B is evaluated at the night step (latency up to one simulated day). `PIVOTAL_THRESHOLD` events are therefore promoted at the next sleep. Q3.

**Interaction with Phase 5 (a real overlap).** Stage 3 already merges a new summary into an existing semantic entry at cosine >= 0.80 (`match_threshold`). Stage 4 counts a reinforcement only at >= 0.85. Choice taken (option a): Stage 3 stays untouched; a merge at 0.80 to 0.85 is Stage 3's business and is logged but does not add a night to Stage 4's day_set. Option b (raise Stage 3's threshold to 0.85 when Stage 4 is on) would change Stage 3 clustering behavior and is not recommended. Q4.

### 2.5 Trait generation prompt (verbatim proposal; third person, no em dashes)
Persona context first (the priors block), then, for Path A (count-based or same-day; `{occurrence}` is `on 3 different days` or `5 times on one day`):
```
The following pattern was observed in {agent_name}'s experience {occurrence}:
{pattern}

Write ONE sentence, in the third person, that names {agent_name} and states the lasting personality trait this pattern shows about {agent_name}.
```
For Path B:
```
The following single event was extremely important to {agent_name}:
{event_text}

Write ONE sentence, in the third person, that names {agent_name} and states the lasting trait or belief this event shows about {agent_name}.
```
System prompt: the Phase 5 summary system prompt (one sentence, no preamble, third person, never I, me, my or we). The reply is accepted only if it passes `is_third_person` (names the agent, no first-person words) and has at most 35 words; one corrective retry, then a counted failure. Idempotent per (agent, semantic_id) and per source event.

### 2.6 Feed-forward
`identity_context` is the active traits, newest first (ties by reinforcement count), at most 5, rendered as
`Traits this agent has developed through experience:` then `- {trait}` lines, trimmed to 120 estimated tokens **by dropping the oldest whole trait, never cutting a sentence** (the header counts). The existing prompt builder already appends it after the priors block (`upstream prompt + "\n\n" + priors + "\n\n" + identity_context`), so no template changes. With Stage 4 off, or `IDENTITY_FEEDBACK=false`, `identity_context` stays empty and the prompt is byte-identical to Phase 5's (regression test against a saved Phase 5 prompt). One exact rendered prompt per agent per night is saved to `identity_prompt_renders.jsonl`. Baseline never receives traits: a disclosed asymmetry, to be added to `docs/CLAIMS_LEDGER.md` at Stop 3.

### 2.7 Feedback-loop guard: the choice taken (pre-registered in `docs/phase6_preregistration.md` section 3)
A night counts toward an entry's `day_set` (and Path A) only if at least one new source event attached to it that night was scored **without** a matching trait present (an active trait whose source entry is the entry itself or has cosine >= `REINFORCE_THRESHOLD` with it). Otherwise the night is recorded in `self_reinforced_json` and is not counted. I chose "exclude and report separately" over "once per day" because it removes the loop from the graduation criterion instead of rate-limiting it, and because the definition is identical when `IDENTITY_FEEDBACK=false` (no trait is ever present, nothing is excluded), so the ablation compares like with like. Counted and self-reinforced nights are reported separately.

### 2.8 Pivotal threshold (spec section 4): pre-registered rule applied
Rule and population were committed first (`2e5e49b`). Reference population: 95 LLM-assigned staged event/chat scores = 75 from the friction experiment (`staged`) + 20 from the live staged runs. Histogram of the 95 (offline-captured, `docs/phase6_stop1_artifacts/score_histograms.json`):

| score | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| count | 29 | 21 | 9 | 10 | 6 | 7 | 5 | 7 | 1 | 0 |

Fraction reaching 8: 8.4 percent (8 of 95: seven scores of 8 and one of 9); reaching 9: 1.05 percent (1 of 95); reaching 10: 0. The smallest integer with fewer than 5 percent is **T = 9**. Since 95 >= 30 the rule marks T as frozen.

Per condition and agent (all are in the artifact; counts shown, scores 1 to 10): friction experiment, Isabella, 75 each: baseline 19/15/13/12/4/2/1/9/0/0, staged 22/11/8/9/5/7/5/7/1/0, control_mismatch 23/13/5/13/6/1/6/6/2/0, control_filler 30/3/14/15/1/1/3/7/1/0. Live staged run: Isabella 2 (1 at score 1, 1 at 3), Klaus 16 (4/10/0/1/1), Maria 2 (both 1). Rule-assigned idle rows excluded: 52 (upstream scores them 1 without a model call). A cross-check passes: the 20 LLM-scored live rows equal the 20 `importance_scoring` calls in the ledger for that run.

**What this does and does not support (disclosure fixed in advance, 1.4 of the pre-registration):**
- T = 9 rests on **one** score of 9 in 95; no score of 10 was ever observed. 79 percent of the population (75 of 95) is the authored friction experiment, which over-represents high-importance events by design; the natural live events (20) never exceeded 5, and 20 is below 30, so alone they would be provisional (sensitivity S1).
- Sensitivity (not used for the decision): S2 friction-only: T = 9 (1 of 75 reaches 9); S3 all conditions pooled plus a late-found Phase 4 mini run (324 scores): T = 9 (4 of 324 reach 9, 1.2 percent). T = 9 in every population that can decide it.
- Consequence for Path B: with T = 9 and these scores, Path B fires on roughly 1 percent of events and on none of the 20 natural live events; whether it ever fires on a natural run is unknown. Summary scores (a different object, 8 values from the scripted sweeps) are listed separately: they range 2 to 7.
- The model that produced these scores is `openai/gpt-oss-20b`; a different pinned model may score differently, so T should be re-checked if the evaluation model changes (the rule forbids tuning it on Phase 7 events; re-checking on the chosen model's own scored non-Phase-7 events is a separate question for you, Q5).

### 2.9 Test plan (maps to spec 5.2; all offline unless stated)
Fixture: four nights for Isabella, hand-written: one theme on nights 1, 2 and 4 (graduates by Path A on night 4), one theme 5 times on night 3 only (same-day), one theme once (never graduates), one event scored 10 (Path B), plus a topically similar different theme just under `REINFORCE_THRESHOLD` as the negative. LLM stubbed; embeddings deterministic or cached.

| Required test | Plan |
|---|---|
| Idempotent rerun of a night | second step returns skipped; traits, counters, tables unchanged |
| Crash between consolidation and identity, reload | run consolidation only, simulate crash, reload from a save, run identity: tables equal a clean run |
| Cap: sixth trait evicts oldest; 120-token cap holds | create 6 traits; check `active`; render with long traits; estimator <= 120 and no cut sentence |
| Flag off: prompt byte-identical to Phase 5 | golden file of the Phase 5 staged prompt compared with the builder output |
| `IDENTITY_FEEDBACK=false` leaves `identity_context` empty | traits stored, scorer renders none |
| Path B at T, not below T | scores 8, 9, 10 with T=9 |
| Third-person trait text | `is_third_person` on every fixture trait; retry path covered |
| Guard | event scored with a matching trait present does not add a night; counts reported separately; unknown status treated as self-reinforced |
| Reconcile | `reconcile_identity` after reload from an older save restores the exact state; idempotent |
| Full suite | the 118 existing tests (126 with this round's 8 wiring tests) still pass, plus the new tests |

### 2.10 Stop 2 and Stop 3 budgets (planned)
- **Stop 2 (offline build)** needs real embeddings of the fixture's summary and trait sentences to tune `REINFORCE_THRESHOLD` by the committed protocol: about 10 embedding requests (a handful of sentences, cached afterwards). The spec says offline and no quota; please approve **up to 40 embedding requests** for Stop 2 (Q6). No LLM calls.
- **Stop 3 (live confirmation, cap 40 router-counted calls, counted at the router).** Estimated: 4 summaries + 4 summary scores + 3 trait generations + 5 scores of new events with `identity_context` filled = 16 calls, up to about 24 with retries. About 32 embedding requests (cache first). Model: provisional Gemini (the Phase 5 Step B decision); note the summary and trait prompts have not been probed on Gemini. Full raw replies saved (raw-reply log). Reports the traits verbatim and whether the scoring prompt actually contained them; no behavioral claim.

### 2.11 Consequences worth knowing before approval
- `SAME_DAY_COUNT = 4` means any cluster of at least 4 new source entries graduates on its first night (the scripted baking cluster of 5 and conflict cluster of 4 would both graduate on day 1). That is the requested design; on the real live data only 1 to 2 entries per agent passed the importance floor, so it is unobserved in a natural run.
- Stage 3 and Stage 4 reinforcement thresholds differ (0.80 and 0.85); entries merged between them add no Stage 4 day.

## 3. COMPLIANCE TABLE (Stop 1)

| Item | Status | Artifact |
|---|---|---|
| Schema | Done (design), 2 extension columns and 2 additive tables flagged for approval | section 2.2 |
| Constants | Done | section 2.3 |
| Pre-registered rule 3.1 (reinforcement threshold, tuning protocol, cosine artifact) | Done, committed before analysis | `docs/phase6_preregistration.md` (`2e5e49b`), 2.4 |
| Pre-registered rule 3.2 (`SAME_DAY_COUNT`, design choice recorded) | Done | 2.3, 2.11 |
| Pre-registered rule 3.5 (guard choice stated with reason; ablation flag) | Done | 2.7, pre-registration section 3 |
| Section 4 pivotal threshold: histograms per condition and agent, rule applied as written, no new live calls | Done: T = 9 (n = 95), caveats stated | `docs/phase6_stop1_artifacts/score_histograms.json`, `.md` |
| No code, no live calls for Stage 4 | Compliant (analysis script only) | `p6_stop1_score_histograms.py` |
| No upstream edits | Compliant | `git status reverie` clean |
| No em dashes | Compliant (checked in the new files) | n/a |
| Normalizer wired behind a flag, default off, never on decomposition, offline tests | Done | section 0; `test_normalizer_wiring.py` |

## 4. DEVIATIONS (complete)

- `devmem/memory/p6_stop1_score_histograms.py` is analysis code, not Stage 4 code; it reads saved artifacts only.
- A Phase 4 mini-run database (`devmem/storage/staged_mini_run`, 4 staged rows) was found after the pre-registration; it is reported and appears only in the S3 sensitivity population, as pre-registered treatment of late sources.
- Path B timing differs from the plan (night step, not immediate), 2.4.
- `docs/phase6_spec_stage4_identity.md` (the PM's spec file) is committed with this work.
- The normalizer wiring touches `devmem/router/llm_router.py` (2 insertions) and adds a raw-reply log (off by default).

## 5. TESTS

Full suite, offline default (`docs/phase6_stop1_artifacts/full_suite_output_offline_default.txt`), verbatim:
```
=== devmem.router.test_router
Ran 33 tests in 3.963s
OK
=== devmem.router.test_call_counter
Ran 4 tests in 5.860s
OK
=== devmem.router.test_output_normalizer
Ran 4 tests in 0.000s
OK
=== devmem.router.test_normalizer_wiring
Ran 8 tests in 2.951s
OK
=== devmem.memory.test_priors
Ran 9 tests in 2.389s
OK
=== devmem.memory.test_episodic
Ran 10 tests in 1.601s
OK
=== devmem.memory.test_reconcile
Ran 10 tests in 43.721s
OK
=== devmem.memory.test_gpt_structure_touch
Ran 5 tests in 0.044s
OK
=== devmem.memory.test_consolidation
Ran 27 tests in 7.351s
OK (skipped=1)
=== devmem.embeddings.test_vector_store
Ran 14 tests in 1.091s
OK (skipped=1)
=== devmem.demo.test_demo
Ran 2 tests in 0.061s
OK
```
126 tests, 2 live-gated skipped (118 before this round plus 8 wiring tests).

## 6. OPEN QUESTIONS FOR HIGHER AUTHORITY

1. **Q1.** Approve the two extension columns (`semantic_reinforcement.self_reinforced_json`; `identity_sweeps.sweep_time` and `attempts`).
2. **Q2.** Approve the two additive tables `consolidation_events` (written by Stage 3 inside its transaction only when `STAGE4_ENABLED`) and `event_scoring_context`, or choose the alternative of deriving the scoring-context flag without a table.
3. **Q3.** Accept that Path B is evaluated at the night step, not immediately (no upstream edit possible).
4. **Q4.** Stage 3 keeps merging at 0.80; Stage 4 counts at 0.85 (option a), or align them when Stage 4 is on (option b)?
5. **Q5.** T = 9 follows mechanically from the rule, on a population that is 79 percent authored friction events with a single 9 and no 10. Confirm freezing T = 9, or specify a different population or a re-check on the chosen evaluation model's own non-Phase-7 scores.
6. **Q6.** Approve up to 40 embedding requests at Stop 2 for the reinforcement-threshold tuning.
7. **Q7.** Step C stays held until you approve this checkpoint; confirm.

REQUEST: Approval of the Stop 1 design and decisions Q1 to Q7 before the Phase 6 build. Halting.
