# Phase 6 spec: Stage 4 identity memory (PM, 2026-10-06)

Status: spec for the Senior Dev. Source of design truth: technical_implementation_plan.md Section 8 (Rev 2.2). Where this spec adds a rule, the rule is marked NEW. Nothing here is built yet.

## 0. Ground rules

- Staged mode only. Baseline is unchanged. Stage 4 sits behind `STAGE4_ENABLED` (default false), so every Phase 5 result stays reproducible with the flag off.
- No upstream (reverie) edits. Use existing hook points: the sleep hook already calling consolidation, and the `identity_context` parameter already present in the scoring prompt (empty string today).
- Live calls counted at the router, hard cap per step, CapReached ends the step. No past number changes.
- Keys only in .env. Key scan before every commit. Commit locally, do not push.
- Every claim in a report is tagged live, offline-captured, or derived.
- No em dashes in any document, code comment, or prompt text.

## 1. What Stage 4 is (from the plan)

A slow-changing layer of identity traits that emerge from the agent's own experience. It is separate from Stage 1 priors (who the agent started as) and fed into the same persona-conditioning block used by Stage 2 importance scoring (who the agent became). Two promotion paths:

- Path A, count-based: a semantic entry reinforced on 3 or more distinct simulated days graduates to identity, or reinforced heavily within one day (same-day repetition crossing a threshold, see 3.2).
- Path B, pivotal: a single event whose importance score is at or above `PIVOTAL_THRESHOLD` graduates directly.

## 2. Data model (SQLite mirror, same per-run DB)

New tables, created idempotently:

- `semantic_reinforcement(agent_id, semantic_id, day_set_json, distinct_days, same_day_max, last_night)`
- `identity_traits(agent_id, trait_id, text, path, source_semantic_ids_json, source_event_ids_json, created_night, created_sim_time, active)`
- `identity_sweeps(agent_id, night, status)` night-keyed marker, written in the SAME transaction as the trait writes (same pattern as `consolidation_sweeps`). A rerun of the same night must be a no-op.

Crash safety: the reload reconciliation must restore identity state exactly. Add a reconcile test.

## 3. Behavior

### 3.1 Reinforcement (NEW definition, must be pre-registered)

After each night's consolidation, compare every new semantic summary against existing semantic entries of the same agent by embedding cosine. If cosine is at or above `REINFORCE_THRESHOLD`, the new summary reinforces that entry: add the night's simulated day to `day_set`, update counters. Otherwise it starts its own entry.

- Starting value for `REINFORCE_THRESHOLD`: 0.85. Reason: Phase 5 within-group cosines were mean 0.85 and min 0.80, and the 0.78 to 0.82 clustering margin was about 0.01 wide. Do not tune it on the Phase 7 events. Tune it once on the scripted multi-night fixture (4.1), record the value and the reason, then freeze it.
- Report the cosine of every reinforcement decision in an artifact, so the margin is visible.

### 3.2 Same-day heavy repetition

`SAME_DAY_COUNT` (starting value 4 entries from one cluster in one day, matching the largest scripted clusters). Freeze it with the same rule as above. Record that this value is a design choice, not measured.

### 3.3 Graduation to identity

When a semantic entry meets Path A or Path B, generate ONE third-person trait statement with the LLM (reuse the third-person summary prompt style from Phase 5, which fixed retrieval relevance). Store it in `identity_traits` with its sources. Idempotent per `(agent_id, semantic_id)`.

### 3.4 Feed-forward (Stage 2 scoring)

`identity_context` = the active traits joined as short lines, capped:

- Maximum `MAX_IDENTITY_TRAITS` = 5 (most recently created win, ties by reinforcement count).
- Maximum 120 tokens total. Truncate by dropping the oldest trait, never by cutting a sentence.
- Injected into the existing priors block of the scoring prompt, after the priors. NEW rule: record the exact rendered prompt text for one call per agent per night in the artifact, so a reader can see what the model saw.
- Baseline does not receive identity traits (disclosed asymmetry, add it to the claims ledger).

### 3.5 Feedback-loop guard (NEW)

Traits raise importance of trait-consistent events, which can reinforce the same trait. Guard against runaway:

- `MAX_IDENTITY_TRAITS` cap above.
- A trait cannot be reinforced by an event scored with that same trait in `identity_context` more than once per day (record the flag on the event: `scored_with_identity`). Counted reinforcements must come from entries scored without that trait present, or must be reported separately as "self-reinforced". State which choice you took and why.
- Ablation flag `IDENTITY_FEEDBACK` (default true when Stage 4 is on). When false, traits are stored but `identity_context` stays empty. Required for Phase 7.

## 4. Pivotal threshold calibration (NEW, pre-registered rule)

The plan's 9.5 is a placeholder; upstream importance scores are integers from 1 to 10, so 9.5 means "exactly 10" and may never fire.

1. Collect every real importance score already recorded in the Phase 5 and earlier artifacts (staged scoring calls, the friction experiment, the live run). Report the histogram per condition and per agent. No new live calls for this.
2. Decision rule, written down before looking: choose the smallest integer threshold T such that fewer than 5 percent of scored events reach T. If no integer from 8 to 10 satisfies it, use 10 and report that Path B is rare by design.
3. If fewer than 30 scored events exist in total, the threshold is NOT frozen. The report must say "provisional" and Phase 7 must re-check on its own scored events.
4. Do not tune T on the Phase 7 events.

## 5. Tests and fixtures

### 5.1 Scripted multi-night fixture (offline, no quota)

Four simulated nights for Isabella, hand-written: one theme recurs on nights 1, 2 and 4 (should graduate by Path A on night 4), one theme occurs 5 times on night 3 only (same-day path), one theme appears once (must not graduate), plus one event scored 10 (Path B). Use stubbed LLM and cached or deterministic embeddings for the unit tests. Include a negative case where a topically similar but different theme sits just under `REINFORCE_THRESHOLD`.

### 5.2 Required tests

- Idempotent rerun of the same night (no new traits, counters unchanged).
- Crash between consolidation and identity step, then reload: state matches a clean run.
- Cap behavior: the sixth trait evicts the oldest; the 120-token cap holds.
- Feed-forward: with the flag off, the prompt is byte-identical to Phase 5's prompt (regression test against a saved Phase 5 prompt).
- Ablation: `IDENTITY_FEEDBACK=false` leaves `identity_context` empty.
- Path B fires at T and not below T.
- Third-person trait text contains no first-person pronouns for the fixture cases.
- Full suite still 118 pass, 2 live-gated skipped, plus the new tests.

## 6. Live work in this phase (small, capped)

One live confirmation only: the scripted 4-night fixture for ONE persona, real embeddings (cache first), real summarization and trait generation, real scoring of a handful of new events with `identity_context` filled. Hard cap 40 router-counted calls. Model per the Phase 5 Step B decision (see the PM message). Save full raw replies. Report what the traits say, verbatim, and whether the scoring prompt actually contained them. Do NOT report any behavioral effect; one persona and 4 scripted nights cannot show one.

## 7. Stops

- Stop 1 (design checkpoint, no live calls): schema, constants, the pre-registered rules from 3.1, 3.2, 3.5 and 4, the threshold histograms. Halt for PM approval.
- Stop 2 (build, offline): code and tests green. Halt.
- Stop 3 (live confirmation, section 6) plus claims-ledger update. Halt.

Use the standard phase report template from PRD.md (what was built, compliance table, deviations, tests, open questions).

## 8. Explicit non-claims for this phase

- No claim that identity feedback improves recall, coherence or efficiency.
- No claim that traits are "correct"; only that they are generated from stated sources and stored.
- No claim from a single scripted run that thresholds generalize.
- The consolidation efficiency claim stays unsupported (Stage 3 adds calls; top-k is fixed).
