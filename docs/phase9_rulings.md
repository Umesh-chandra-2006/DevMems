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

## Rulings added 2026-10-08 (PM message after the 18:52 report; recorded at 19:10 IST, repository HEAD `90a218b`, before any day-3 answer exists)

9. **Staged day-2 copy: option (a).** The registered 14:15 primary copies are evaluated: staged as taken (its Maria and Klaus persona files are one save old and Isabella's `embeddings.json` was rebuilt; disclosed), baseline from the repaired copy (embeddings rebuilt from the embedding cache at float32 precision; disclosed). The staged answer harness reads only the persona folder (nodes.json, embeddings.json, kw_strength.json, scratch.json, spatial memory); it does NOT read memory.db, so the stale persona files DO affect the staged evaluation (about 1 percent of nodes missing for Maria and Klaus, the last 15 simulated minutes before the clock, and a scratch clock one save old).
10. **Sensitivity run (pre-registration 7g).** The 23:45 secondary copies of both arms are evaluated as a labelled sensitivity analysis, Isabella's embeddings repaired the same way in both arms. They are the LAST step of each chain, after every day-3 step, so they never delay a day-3 result.
11. **Copy integrity.** The day-1 interim copies pass T1 to T3 (`docs/phase9_copy_integrity.json`). The runner's own day-3 checkpoint is used when it passes the integrity tests (T1, T2), else the external copy (`copy_integrity.choose_day3`); the choice is recorded in each evaluation file. The torn-copy finding and its fix are in claims ledger H23 and pre-registration 7j.
12. **Purpose tags.** The `planning` and `dialogue` tags are audited like `reflection`, offline from the delivered-reply log, sample of 200 rows per tag per arm with the committed seed 20261008 for the large tags (`docs/phase9_purpose_tag_audit.json`); the export shows the false-match rate next to the E1 per-purpose table.
13. **D-2** is marked right in the export with the note that it was weak by design (at threshold 0.82 nearly every merge falls in the 0.80 to 0.88 band); the same note is in the claims-not-supported list.
14. **I6**: the attention-crowding explanation is recorded as plausible and unverified (claims ledger H24).
15. **Claims-list edits** (items 9, 11, 16 and new items 24 to 27 as ordered; item 28 added by the Senior Developer on what "reflection is off" covers) were made through safe_commit.
