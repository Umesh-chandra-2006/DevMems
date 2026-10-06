# Phase 6 pre-registration (written and committed BEFORE any score histogram is computed)

Status: committed before the Stop 1 analysis. Nothing in this file may be changed after the commit that adds it; any later
change must be a new dated section that says what changed and why. No em dashes are used in this file.

## 1. Pivotal threshold T (spec section 4)

### 1.1 Rule (spec text, unchanged)

Choose the smallest integer T in {8, 9, 10} such that fewer than 5 percent of scored events reach T (a score reaches T when
score >= T). If no integer from 8 to 10 satisfies it, use T = 10 and report that Path B is rare by design. If fewer than 30
scored events exist in total, T is NOT frozen and is reported as provisional. T is never tuned on Phase 7 events.

### 1.2 Reference population (my operational reading of "scored events", fixed now)

One observation is one importance score returned by the scoring model for one event or chat text, under the **staged**
condition (the priors block present), because Stage 4 only exists in staged mode. Each repeat of the same text is its own
observation, because each is an independent model score. Included sources:

1. `devmem/memory/task7b_differential_results.json`, key `staged` of every event (friction experiment, 25 events x 3 repeats).
2. The live staged runs: LLM-scored event and chat rows of the mirror databases of the saved runs
   `p5_staged_smoke`, `p5_staged_live` (a single database holds the day-start step and the continuation) under
   `devmem/storage/`. An event row is LLM-scored unless its text contains "is idle" (upstream assigns score 1 to those
   without a model call, `perceive.py` `generate_poig_score`); idle rows are excluded because no model scored them.

Excluded from the reference population, and reported separately where noted:

- control conditions (`control_mismatch`, `control_filler`, `baseline`): reported as separate histograms, never pooled into T;
- rule-assigned scores (idle events scored 1 without a model call) and the plan thought's hard-coded 5;
- scores of consolidation summaries (they score a different object, a generated sentence); reported as a separate list;
- scripted fixture importance values (written by hand, not model-assigned).

### 1.3 Sensitivity populations (reported, NOT used for the decision)

S1 live runs only (natural events); S2 the friction experiment only (authored events, over-represents friction by design);
S3 all conditions pooled including controls and baseline. They exist so a reader can see how much T depends on the population.

### 1.4 Disclosure fixed in advance

The friction experiment events were authored to span importance categories, so the reference population is not a natural
distribution. If the rule gives a value that depends on that choice, the report must say so. The rule is applied mechanically
to the reference population; the sensitivity populations only inform the PM's decision at Stop 1.

## 2. REINFORCE_THRESHOLD tuning protocol (spec 3.1; executed at Stop 2, fixed now)

Starting value 0.85. Tune ONCE on the scripted multi-night fixture, then freeze:

1. Compute, with the real embedding model, the cosine of every same-theme pair across nights (positives) and every
   different-theme pair, including the deliberate topically-similar negative (negatives), among the fixture's summary sentences.
2. If min(positives) > max(negatives): choose the value 0.01 below min(positives) rounded down to two decimals, but not below
   0.80 and not above 0.90, and require max(negatives) < chosen value. Record both extremes and the margin.
3. If the groups overlap: keep 0.85, report the overlap, and state that the fixture cannot separate them.
4. The chosen value, the reason and every cosine go into a committed artifact. After that it is frozen; the Phase 7 events
   never touch it. The fixture is hand-written, so the margin is a property of an author-chosen negative and is reported as such.

## 3. Self-reinforcement guard (spec 3.5): the choice taken

A night counts toward a semantic entry's `day_set` (and toward Path A) only if at least one of the new source events attached
to that entry that night was scored WITHOUT the matching trait present in its `identity_context`. "Matching trait" means an
active trait whose source semantic entry is that entry or has cosine >= REINFORCE_THRESHOLD with it. A night where every new
source event was scored with a matching trait present is recorded as `self_reinforced` and is NOT counted. Reason: the loop
is removed from the graduation criterion instead of being rate-limited; the definition is identical when
`IDENTITY_FEEDBACK=false` (no trait is ever present, so nothing is excluded), so the ablation compares like with like. Counts
of counted and self-reinforced nights are reported separately.

## 4. Other fixed choices

- Night key: the Phase 5 night id (sim day of the evening onset); the birth night of an entry is the first element of its day_set.
- `same_day_max` = the largest number of NEW source events attached to one entry in one night; Path A same-day fires at
  `SAME_DAY_COUNT` = 4 (a design choice, not measured).
- Token cap: estimated with the router's own `estimate_tokens` heuristic (about 1.35 tokens per word); an estimate, not the
  provider's count; the Stop 3 report quotes ledger tokens as the measured figure.

## 5. Addendum A1 (added after Phase 6 Stop 1 approval, before any Stage 4 code; the sections above are unchanged)

Source: PM verdict on Stop 1. Path B gets the same loop guard as section 3.

- An event scored while an active trait that **matches** it was present in its `identity_context` does not graduate by Path B.
  "Matches" means: the cosine between the event text and the trait text is >= `REINFORCE_THRESHOLD`.
- Such an event is recorded as `self_reinforced_pivotal` and its count is reported separately from Path B graduations.
- With `IDENTITY_FEEDBACK=false` no trait is ever present in a scoring context, so nothing is excluded and the definition is
  unchanged across the ablation.
- Both texts are embedded with the run's embedding model; an event whose scoring context is `unknown` (section 3 of the Stop 1
  design, status `unknown` in `event_scoring_context`) is treated as self-reinforced and counted under `self_reinforced_pivotal`.

## 6. Other approvals recorded with this addendum (from the same verdict)

- `SAME_DAY_COUNT` stays 4. At Stop 3 an offline sensitivity table reports how many entries would graduate by the same-day path
  at 3, 4 and 5 on the fixture and on Step C data. It is not a retune.
- `PIVOTAL_THRESHOLD` T = 9 is FROZEN AS PROVISIONAL. It is re-checked exactly once on the Step C Gemini scores with the rule
  unchanged and the population written down before looking (written below in section 7, before Step C runs). If Step C has fewer
  than 30 scored events the status is provisional again and the report says so. T is never tuned on Phase 7 events.
- At Stop 3 the report counts how many Stage 3 merges fell in the 0.80 to 0.85 band, and the number of `unknown` scoring-context rows.

## 7. Step C population for the T re-check (written before Step C runs)

Reference population for the one re-check: every importance score returned by the scoring model during Step C (staged condition,
Gemini, event and chat texts only) whose text does not contain "is idle" (those are rule-assigned 1 without a model call).
Rule unchanged (smallest integer T in {8, 9, 10} with fewer than 5 percent of scores reaching it; 10 if none; provisional if fewer
than 30 scores). It is applied to that population alone, reported next to the frozen T = 9, and not pooled with the earlier 95.
