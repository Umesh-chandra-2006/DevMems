# Phase 7 spec: evaluation harness (PM, 2026-10-07)

Source: technical_implementation_plan.md Section 11 (metrics) and Section 9 (zero-cost scale rules). This spec adds rules marked NEW. Phase 7 builds the harness and validates it. It does NOT run the Phase 9 comparison.

## 0. Ground rules

- No upstream (reverie) edits. Commit locally, do not push. Key scan before every commit. No em dashes anywhere.
- Every number in a report is labelled live, offline-captured, synthetic or derived.
- All router calls counted at the router. Evaluation calls carry their own ledger purpose (`eval_recall`, `eval_probe`, `eval_judge`) and are NEVER included in the per-simulated-day efficiency figures. They are reported separately.
- One model pinned for both arms and for the judge (Phase 5 decision: gemini-3.1-flash-lite with the output normalizer on, unless I change it). Same router settings for both arms.
- The plan expects the staged arm to reduce cost. Phase 5 showed Stage 3 adds calls and top-k is fixed, so prompt size should not shrink. The harness must report whatever it finds, in either direction. No expected result is written into any report template.

## 1. Experimental protocol (design checkpoint item)

### 1.1 Arms
- Arm B (baseline): upstream memory, priors as atomic thought nodes (existing asymmetry, disclosed).
- Arm S (staged): Stages 1 to 4 on, IDENTITY_FEEDBACK on.
- Controls from Stage 2 are carried forward but run cheaply (1.4), not as full simulations.

### 1.2 Compressed-day protocol (NEW, owner's idea, adopted with conditions)
Instead of 24 hour days at about 110 calls per awake agent-hour, each simulated day uses an AUTHORED schedule with an awake window (candidate: 06:00 to 14:00, about what Step D ran) and sleep from 14:00 until 06:00. Sleeping hours cost almost nothing (measured in Step D). Conditions:
- Edit the schedule, never the simulation clock. The clock and the date rollover stay upstream's.
- Schedules are hand-authored per persona, identical in both arms, and NOT derived from or written against the priors. Same event times, same wake and sleep times.
- It is a disclosed deviation from upstream's generated schedules (the daily-plan step is replaced by authored plans). Add it to the claims ledger and the paper.
- A sleep signal at or after hour 12 is keyed by the Stage 3 hook as the evening night. The night-key defect (Stop 3 Step D finding) MUST be fixed or ruled out at its own checkpoint before any Phase 9 run, and the checkpoint must cover this schedule.
- Start the run at 00:00 (not 06:00) so no persona starts mid-"sleeping" from an upstream run-start artifact (Klaus 07:00 vs 13:00).
- Days: 3 compressed days per run (Stage 4's count path needs reinforcement on 3 distinct nights).
- Agents: 3 (Isabella, Maria, Klaus), unless the budget table in 1.5 allows more.

### 1.3 Injected events (NEW)
The "events not written against the priors" rule. Authored list, committed BEFORE any harness output exists:
- 8 to 10 events per agent over the 3 days, mixed significance (mundane, social friction, a pivotal event, a repeated theme across days, a one-off).
- Persona-neutral wording; no event may use a word from that persona's priors text (an offline check script must enforce it and print any overlap).
- Injected through the same code path in both arms at identical sim times. The Senior Dev proposes the mechanism at Stop 1 (no upstream edit allowed); it must reach perceive and scoring exactly as a natural event would.
- Each event has a ground-truth fact sheet (who, what, where, when, one key detail) used by recall scoring.

### 1.4 Controls by replay (NEW)
Record the full event stream of the Arm S run (events and sim times). Replay it through the scorer only under: (a) staged priors, (b) mismatch priors (a different persona's), (c) neutral filler, (d) baseline scoring. Cost is about one scoring call per event per condition, no planning calls. This is the Stage 2 control design (n much larger than the 8 events of Phase 4). It measures scoring effects only and says nothing about behavior.

### 1.5 Budget table (derived, replace with measured)
Using about 110 calls per awake agent-hour (Step D): one arm, 3 agents, 8 awake hours per day is about 2,600 calls per day, about 7,900 for 3 days. Two arms: about 15,800. Replays: about 450 per condition per day. Evaluation: at most 200 recall, 150 probe, 150 judge calls per arm. The Stop 1 report must give the table with its assumptions, per provider, against current quota (Gemini 5 chat keys, Groq 9 keys, NIM keys, plus about 10 incoming key sets).

## 2. Metric 1: recall accuracy

- Question set authored with the events (1.3): at least 12 per agent, at three distances (same day, next day, two days later), mix of injected and natural events. Natural-event questions use ground truth taken from the recorded event stream.
- Answering: the agent's own retrieval (arm's own memory, same top-k) plus one LLM call with a fixed prompt, same for both arms.
- Scoring: automatic key-fact checklist per question (names, objects, times matched by normalized string rules). NO LLM judge for the primary score. Validate the checklist rule on at least 30 hand-labelled answers and report its agreement.
- Report: accuracy per arm, per distance, per agent; raw answers saved verbatim.

## 3. Metric 2: behavioral coherence

- Probe interviews (NEW design): the same standard questions about the agent's self and its relationships, asked at the end of day 1 and of day 3, via the same answering path in both arms.
- Judge: an LLM judge on the pinned model compares each earlier and later answer pair for contradiction, with a fixed rubric (consistent, contradictory, unrelated). Calibrate the judge on at least 20 authored pairs with known labels and report its accuracy next to every result. If accuracy is below 80 percent, say coherence results are not interpretable.
- Natural dialogue was absent in Step D, so do not depend on dialogue for this metric.

## 4. Metric 3: computational efficiency

Per simulated day and per arm, from ONE ledger (needs the db_path fix first): LLM calls and tokens by purpose (planning, decomposition, importance scoring, dialogue, reflection, consolidation, identity, evaluation excluded), mean retrieved-context tokens per call, and the supplementary data point from the plan (fraction of episodic entries consolidated over time; whether raw detail stays reachable when the summary is retrieved). Report differences with both signs possible.

## 5. Diagnostics (NEW)

- Trait provenance (zero LLM): for each Stage 4 trait, cosine to its source events and to the agent's priors text; flag traits closer to priors than to their sources. Report the fraction flagged.
- Stage 3 cluster quality: cluster size histogram, merge cosines, summaries verbatim, number of entries merged between 0.80 and 0.88.

## 6. Statistics and pre-registration

- Write `docs/phase7_preregistration.md` before the first Phase 9 run: metrics, comparisons, the grader, the judge, exclusion rules, and DIRECTIONAL PREDICTIONS per persona pair (what staged should change and for whom). Predictions are written before data and reported whether right or wrong.
- Paired comparisons by agent and by question. Report effect sizes with bootstrap confidence intervals; with 3 agents and one seed, no significance claims. State n everywhere.
- Repeat runs if quota allows; if not, say it is a single run.

## 7. Stops

- Stop 1 (design, no code, no live calls): protocol 1.2, event injection mechanism, event and question lists with fact sheets, grader and judge design, budget table, pre-registration draft, night-key interaction. Halt for PM approval.
- Stop 2 (build, offline): harness code, synthetic fixtures, unit tests (the grader, the judge pair builder, ledger splitter, provenance diagnostic, schedule and event checks). Halt.
- Stop 3 (validation on recorded data): run the harness on the Step D recording (efficiency, provenance, a small recall check against natural events). Live cap 80 router-counted calls. Halt.
- Phase 9 does not start before Stops 1 to 3 are approved.

## 8. Explicit non-claims

- No claim that staged beats baseline from harness validation runs.
- No efficiency claim in either direction from fewer than two full compressed-day runs per arm.
- No coherence claim if the judge calibration is below 80 percent.
