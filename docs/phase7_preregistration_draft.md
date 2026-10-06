# Phase 7 pre-registration (DRAFT, written at Phase 7 Stop 1; becomes `docs/phase7_preregistration.md` and is committed before the first Phase 9 run)

Status: draft for PM review. Nothing has been run. No expected result is assumed by the report templates. Labels follow the claims ledger. No em dashes.

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
- An injected event that was not perceived in an arm (not found in that arm's memory) is excluded from that arm's recall questions AND from the paired question in the other arm; the number excluded is reported.
- Router failures: any call that fell back to a fail-safe value is counted per arm; a run with more than 1 percent fail-safe calls is flagged in every result line (not silently dropped).
- Evaluation answers that are empty or contain a provider error string are counted as failures and scored 0 in both arms alike.
- No post hoc exclusions. No question, event, checklist or rubric is changed after the first harness output exists.

## 5. Directional predictions (written before any data; reported whether right or wrong)
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
