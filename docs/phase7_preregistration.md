# Phase 7 pre-registration (FINAL, committed before the full-run launch; derived from the Stop 1 draft with the amendments of 2026-10-07 marked [A])

Status: final for launch. The only live data seen before this document is the PILOT (readiness check, never a result; `docs/phase7_pilot_report.md`) and the Phase 6 runs. No expected result is assumed by the report templates. Labels follow the claims ledger. No em dashes.

## 1. Design
Two arms, B (baseline) and S (staged, Stages 1 to 4, `IDENTITY_FEEDBACK` on), the same pinned model (`gemini-3.1-flash-lite`, normalizer on), 3 agents (Isabella Rodriguez, Maria Lopez, Klaus Mueller), 3 authored compressed days per run (`docs/phase7_stop1_schedules.json`), 27 injected events (`docs/phase7_stop1_events_questions.json`), run start 2023-02-13 00:00. Arm S differs from B by the staged memory AND by decision D1 (upstream reflection is off in S, on in B); this is part of the comparison and is stated wherever a difference is reported. One run per arm unless quota allows more; with one seed, no significance claims.

## 2. Metrics and comparisons (paired by agent and by question; n stated everywhere)
- **M1 recall:** per question, key-fact checklist score (items matched over items) and strict correctness (all items); answers via the agent's own retrieval and one fixed-prompt call on checkpoint copies at the end of day 3. Comparison: S minus B per agent and per question; per distance (0, 1, 2 days) and per question type (injected, theme count, natural).
- **M2 coherence:** 18 day-1 versus day-3 answer pairs per arm; the judge label per pair (consistent, contradictory, unrelated); the contradiction rate per arm and per agent. Interpretable only if judge calibration accuracy is at least 80 percent (printed beside every result).
- **M3 efficiency:** calls and tokens by purpose per simulated day and per agent, mean prompt tokens per call by purpose, consolidated fraction over time; evaluation calls excluded and reported separately.
- **Diagnostics (not outcomes):** trait provenance (fraction of traits closer to the priors than to their sources); Stage 3 cluster quality; Stage 2 scoring controls by replay (staged, mismatch, neutral filler, baseline scoring) on the recorded event stream.
- Effect sizes with bootstrap confidence intervals over agents and questions (resampling questions within agent); no p-values and no significance claims with 3 agents and one seed.

## 3. Grader and judge
- Grader: automatic key-fact checklist, normalization and matching rules as in Stop 1 section 3; validated on at least 30 hand-labelled answers; the agreement is reported with every recall result; below 80 percent the recall results are marked uninterpretable. No LLM judge for the primary score.
- Judge: pinned model, fixed rubric text saved with the results, calibrated on at least 20 authored pairs (7, 7, 6 by class) committed before the judge runs; accuracy and confusion matrix beside every coherence result; parse failures counted and never guessed.

## 4. Exclusion rules (written before data)
- A run is excluded from a comparison only if it did not complete the three days, if a router hard cap ended it, or if its schedule check or event check reports a violation; excluded runs are listed with the reason.
- [A] A run stopped before day 3 by quota, a router cap, the supervisor's ABORT or the operator is **incomplete and reported as interim**: it is not silently dropped and is never presented as a three-day result. Whatever checkpoints exist (day 1, day 3) are analysed as stated in section 5b and labelled with the clock and step at which the run stopped.
- An injected event that was not perceived in an arm (not found in that arm's memory) is excluded from that arm's recall questions AND from the paired question in the other arm; the number excluded is reported.
- Router failures: any call that fell back to a fail-safe value is counted per arm; a run with more than 1 percent fail-safe calls is flagged in every result line (not silently dropped).
- Evaluation answers that are empty or contain a provider error string are counted as failures and scored 0 in both arms alike.
- No post hoc exclusions. No question, event, checklist or rubric is changed after the first harness output exists.

## 5. Frozen parameters, amendments and directional predictions (written before any data; reported whether right or wrong)

**[A] Frozen parameters and stop rules (decided before the full runs).**
- **T (pivotal threshold) = 9, frozen** (`devmem/config/identity.yaml`, `pivotal_threshold: 9`, no value change). This is a disclosed deviation: the pre-registered rule (lowest integer at which the authored life-changing events qualify and no mundane or moderate event does) selects 8 on the corrected P2 scores, which would make all five authored significant events (each scored 8) pivotal. The PM set T = 9, which separates the authored classes with 0 of 24 misclassified, before any run data. Margin one point (L5 scored exactly 9); basis 24 hand-authored events, one model, one run of calls. Claims ledger H11.
- **A6 (calls per awake agent-hour):** WARN above 165; ABORT above 260 sustained over 3 consecutive ledger windows of at least 0.5 awake agent-hours each. Basis: the pilot (about 2 awake hours per arm, conversation legs 182 to 207). Claims ledger H12.
- **Caps per arm:** hard cap 16,500 router calls, soft stop 15,500 (a step boundary); per-key cap 450 requests per quota day, not raised. Quota pause at all-keys-at-cap, resume after the reset (about 12:30 IST, `DEVMEM_QUOTA_RESET_UTC_HOUR=7`).
- **Importance parser:** the corrected `parse_importance_score` (labelled value first; a "1 to 10" range phrase ignored) is in both the full-run code path (staged scorer only; the baseline path is upstream's JSON integer parse). Claims ledger H10.

**5b. Declared interim analyses [A].**
- **Checkpoint timing.** Checkpoints are taken at the first autosave at or after 14:15 on day 1 and on day 3 (steps 5,130 and 22,410), that is AFTER the 14:00 sleep block has begun. The sleep hook (night sweep and Stage 4 step) runs on the first sleeping step, which comes after the autosave at 14:00:00 (step 5,040); a checkpoint at 14:00 would therefore precede the night-1 sweep. The checkpoint copy records each agent's sweep marker, so whether every night-1 sweep reached `done` before the copy is read from the copy and reported; any agent without a `done` marker is listed. Both arms use the same checkpoint clock.
- **Day-1 interim (and day-2 interim if the run reaches 2023-02-14 14:15):** only E1 to E3, R5, and the Stage 2 scoring controls (replay). No Stage 4 count-based claims by day 1 (Path A needs three distinct counted nights including the birth night; Path B is evaluated at the nightly step, claims ledger H2). M2 coherence needs day 3 and is not run at an interim point. Every interim number is labelled "interim" with the run's clock and step.
- **Final analysis:** the day-3 checkpoint, all of section 2, for runs that completed three days (section 4).

**Directional predictions.**
These are predictions, not hypotheses with evidence behind them; reasons are given so a wrong prediction is informative. "Staged" means Arm S.

**Efficiency (all agents).**
- E1: S makes MORE calls than B per simulated day in total: Stage 3 and Stage 4 add summarization, summary scoring and trait calls (Phase 5 measured about 2 calls per summary), partly offset by removing upstream reflection. Direction: S more than B by less than 10 percent of B's calls. If S makes fewer calls, the cause will be named from the purpose breakdown.
- E2: Mean prompt tokens per scoring call are higher in S than in B (the priors block and the trait block are appended); direction: S above B by the size of those blocks.
- E3: The consolidated fraction of episodic entries is above 0 in S and exactly 0 in B.

**Recall (per agent).**
- R1 (Isabella, repeated theme "left without ordering", question `Q_I_theme`): S answers the theme-count question no worse than B, because the summary of repeated observations should keep the theme. Reason for doubt: summaries are thematic and may drop the count.
- R2 (Klaus, repeated theme "noise disturbance", `Q_K_theme`): same direction as R1.
- R3 (all agents, pivotal events I5, M5, K5 at distance 2 days): no difference larger than 0.2 in checklist score between arms; staged importance scoring changes which events are consolidated, but pivotal events are retrieved by relevance in both arms.
- R4 (all agents, mundane events at distance 2): S at or below B, because Stage 3 consolidates sources and gives them a lower retrieval weight (`consolidated_weight` 0.5), so raw mundane detail may rank lower. Direction: S below B.
- R5 (same-day questions, distance 0): no difference larger than 0.1 (nothing is consolidated before the first night).

**Scoring effect of the priors (replay controls, per persona; direction of staged minus baseline mean importance on social-friction events I3, I9, M3, M9, K3, K9).**
- Isabella (avoids confrontation; reacts to bad news by fixing): staged scores friction events higher than baseline.
- Maria (excitable; hard time hiding feelings): staged scores friction events higher than baseline.
- Klaus (intellectualizes conflict, solitary): staged scores friction events lower than baseline.
- Mismatch priors (another persona's) move the scores toward that persona's direction; neutral filler moves them toward the baseline. Basis: the Stage 2 friction experiment of Phase 4 (n small); the claim is about scoring only and says nothing about behavior.

**Coherence.** No directional prediction: the plan gives no reason to expect S to be more or less self-consistent over 3 days, and the Stop 3 observation that traits can carry content from the priors cuts both ways. Reported two-sided, only if the judge calibration is at least 80 percent.

**Diagnostics.**
- D-1: at least one third of Stage 4 traits will be flagged closer to the priors text than to their sources (basis: Stop 3, 1 of 3 traits shown to contain content absent from its source; n is tiny, so this is a guess).
- D-2: the number of Stage 3 entries merged between 0.80 and 0.88 will be above 0 over the three nights per agent that consolidate (basis: the real cosines of the author-chosen negative in the Stop 2 tuning artifact were 0.844 to 0.858).

## 6. What would count as the prediction being wrong
Each prediction above is scored right, wrong or undecidable (undecidable when the grader or the judge fails its validation, or the relevant n is below 3 questions) and the table of outcomes is part of the Phase 9 report regardless of direction.

## 7. Deviations from the original design and from upstream (to be listed in every report and in the paper's limitations)
1. **Output normalizer** (claims ledger H1) and the **JSON fence rule** (H9): router-level, identical for both arms; per-arm strip counts are reported.
2. **Importance parser fix** (H10): the staged scorer misread the echoed "Rate (return a number between 1 to 10): N" as 1 until commit f25a10b; Step D and the P2 calibration are affected (audit `docs/phase7_parser_echo_audit.json`); past artifacts are not rewritten.
3. **Model.** The pinned model of the full runs is `gemini-3.1-flash-lite` on the Gemini free tier (chat and `gemini-embedding-001`), not the `gpt-oss-20b` model used in the Phase 4 measurements and not any model of the original Smallville paper; Phase 4 numbers are not comparable with Phase 7 numbers. Baseline and staged use the identical model.
4. **T = 9** (PM override of the rule; H11) and the **A6 and cap amendment** (H12).
5. **Arm difference D1:** upstream reflection is off in S and on in B (section 1); baseline receives no identity traits (H4).
6. **Operational measures:** a supervisor resumes an arm after an A1 exit or a kill from the last autosave (at most 3 per simulated day; the same step crashing twice creates ABORT); a resumed leg replays simulated time, so ledger and raw logs hold duplicate calls for that stretch and replies differ because the model is not deterministic; every resume is logged in `resume_log.jsonl`. A Windows at-logon task restarts the supervisor only for a FULL-labelled arm without an ABORT file. Quota pauses are logged in `quota_pauses.jsonl`.
7. **Keys.** The arms use disjoint Gemini key sets (no overlap): baseline 16 chat keys and 15 embedding keys, staged 15 and 15 (31 verified pool keys; the odd chat key to baseline); the eight pilot keys are outside the pool; the sets are fixed at launch and change mid-run only through a supervisor resume. Per-key cap 450 chat requests per quota day. Claims ledger H16.
7a. **Network outages.** A connection failure or a timeout pauses the arm with backoff and no attempt limit; outage minutes are recorded per ledger window and reported; nothing reaches the simulation as a fail-safe. Claims ledger H15.
7b. **Injected events** carry an object-style subject (a ":" prefix) so the simulation never reacts socially to them. Claims ledger H14.
8. **Checkpoint timing** (section 5b) differs from the 14:00 of the Stop 1 draft.
9. **PILOT** recordings (labelled PILOT) are used only for the viewer demonstration and the readiness report; their numbers are never results (H13).
