# Claims the final data will NOT support (a guard for the paper's wording)

Written 2026-10-08, before any day-3 answer exists. Design facts behind every item: one run per arm, three agents, one pinned free-tier model, three authored compressed days, 27 authored events, 39 authored questions, an automatic grader validated on 30 hand labels, a judge calibrated on 20 authored pairs, and a staged arm that differs from the baseline in more than the memory stages.

## Statistics
1. **Significance.** No p-value, "significant", "reliably" or "consistently" for any difference. One run per arm and 3 agents give no variance estimate; the bootstrap interval resamples questions within 3 agents and is descriptive of this run only.
2. **Generalization.** Nothing about other agents, personas, models, simulation lengths, other days or real-time (non-compressed) operation. Three agents, three compressed days (8,640 steps of 10 s per day, awake 06:00 to 14:00 in the authored schedule), one model.
3. **Effect sizes from small n.** R1 and R2 rest on one question each; R3 to R5 pool 3 to 12 questions; the replay friction comparison uses 2 events per persona. State n beside every number and do not rank personas or questions by size of difference.
4. **Rare outcomes.** Parse failures, fail-safe scores and judge parse failures are counted; a count of 0 or 1 does not show a rate.

## Causal attribution
5. **Stage-level causes.** No difference in recall, calls, tokens or coherence can be attributed to Stage 2, 3 or 4 alone. The staged arm turns on all four stages together, and upstream reflection is OFF in the staged arm and ON in the baseline (decision D1), so every difference mixes the stages with the reflection difference. No ablation arm exists.
6. **Reflection.** The call-count and recall differences cannot be split into "stages added" and "reflection removed".
7. **Stage 1 priors.** The priors reach the agent only through the scoring prompt (and the identity context). Any claim about "personality" shaping behavior or recall is not supported; only the scoring-direction comparison from the replay controls bears on the priors, and only for scores.
8. **Replay controls.** They show how the scoring prompt variants score the recorded events (one call each, single reply per event and condition). They say nothing about what the agents did, and a single reply per condition carries the scorer's own sampling noise, which is not measured.
9. **Consolidation and identity.** "Stage 3 preserves meaning" or "Stage 4 traits are faithful" is not supported: E3 counts what was consolidated; D-1 is a cosine diagnostic on cached embeddings (when available), not a judgement of a trait. D-2 was not logged (merge cosines are not in the consolidation log).

## Behavior and interpretation
10. **Behavior.** Nothing about agent behavior, plans, social outcomes, believability or "human-likeness". Recall is measured by answering authored questions through the agent's retrieval and one fixed-prompt call on a checkpoint copy, not by watching the agents act.
11. **Human-validity.** No claim that the grader or judge matches human preference beyond the stated agreement (grader: item agreement on 30 labels, answer-level agreement; judge: accuracy and confusion matrix on 20 pairs, written by the developers, so the labels are not independent of the rubric).
12. **Coherence (M2).** No directional claim (none was registered). Interpretable only if the calibration accuracy is at least 80 percent; with 18 pairs per arm, a difference of one or two pairs is not a finding.
13. **Memory quality in general.** The questions are authored around injected events and two repeated themes; they test detail recall and theme counting, not open-ended memory use.

## Efficiency (E1 to E3)
14. **Cost of the method in general.** Calls and tokens are for this model, this prompt set and these three days. They include rate-limit retries only as unique calls (replayed spans removed); they say nothing about dollars (all calls were free tier) or about wall time (wall time was dominated by 429 waves, outages and one power loss, and differs by arm for reasons unrelated to the method).
15. **Prompt tokens (E2).** The token difference is measured by the ledger's token counts per importance call; it covers the scoring prompt only, not the identity context or the answer prompts.
16. **Interim figures.** Day-1 and day-2 numbers are interim checkpoints (14:15 and 23:45 sim clock) taken at saved autosaves, with replayed stretches removed from the unique counts; they are not a result for the three-day run.

## Process and data integrity
17. **Run conditions.** The two arms ran on different key pools, at different wall times, after different restarts (including an app restart and a laptop power-off), with correlated 429 waves of different length. The wave and outage shares are reported per arm; they are not controlled.
18. **Restarts.** Each restart replays a stretch of steps from the last autosave; the second pass is excluded from "unique" counts but the simulated state after a restart is a continuation, not the same random path an uninterrupted run would have taken. No claim that the run equals an uninterrupted run.
19. **Excluded events.** An injected event that failed its injection check in either arm is excluded from both arms (pre-registration section 4); the paper must state the number excluded and not describe the 27 events as all evaluated.
20. **Pre-registration wording.** R1 and R2 are undecidable by the registered rule (n below 3 questions); R3 as registered (pivotal events at distance 2) matches no question because I5, M5 and K5 are day-2 events (distance 1 at the day-3 checkpoint). The paper must report them as undecidable and present any other reading as an observation, not as a confirmed or refuted prediction.
21. **Not run.** No upstream-comparison claim against published Generative Agents results; the baseline arm is the upstream memory run on this model and these keys, not a reproduction of the original paper's numbers.
