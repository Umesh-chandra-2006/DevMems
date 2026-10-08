# Phase 9 rulings of the Project Manager, recorded before any day-3 answer exists

Recorded by the Senior Developer on 2026-10-08 at 18:52 IST (clock of the development machine); this file was first committed as `3cd8df7` on top of `ab4ce7e`. Source: the PM message of 2026-10-08 relayed by the Project Owner. No day-3 answer, judge result or replay result existed at the time of writing (at the last movement file: staged step 20556, baseline step 19752, of 25,920).

1. **R3** is undecidable as written (pivotal events I5, M5, K5 are day-2 events; no pivotal question exists at distance 2). The pivotal-event recall at the actual distance is shown as a separate observation labelled "not pre-registered".
2. **R1 and R2** are undecidable under pre-registration section 6 (n = 1 question each, below 3). Observed values are shown, not scored.
3. **D-2** is recovered offline: for each staged night the same average-linkage clustering (threshold 0.82, min cluster size 3, same inputs, importance floor 3, idle filter, 6 summaries a night, 12 sources a summary) is re-run on the embeddings of the run. If the recorded clusters are reproduced exactly, the merge heights are the cosines and D-2 is scored; if not, D-2 is undecidable and the mismatch is shown. A missing embedding counts as not reproducible unless fetched in the chain step "d1_d2_embedding_fetch".
4. **D-1** is approved: after the replay controls, the chain embeds the traits, their sources and the priors (and any embedding D-2 found missing) on the staged pool with gemini-embedding-001.
5. **S-mismatch** is undecidable; the observed value only.
6. **I6**: question `Q_I6` is excluded from both arms under section 4; the count and the reason I6 was not perceived are reported.
7. Baseline half of the evaluation is built and wired (chain on the baseline finish: checkpoint copies check, baseline day-3 evaluation on the baseline pool, results export day 3); it stops at the first failure and writes to the chain status file.
8. No change to the model, caps, design or arms.
