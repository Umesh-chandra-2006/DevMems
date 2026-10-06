PRE-LAUNCH items P1 (night-key fix) and P3 (Stage 3 clustering freeze), plus the key verification
STATUS: Done offline except the key verification (29 live requests, counted below). P2 (T calibration) waits for the 12:30 IST reset; P4 (Phase 7 Stop 2a) and the Phase 8 Stop 2 follow in their own reports. No launch has been started.

Labels: **synthetic** (scripted ticks on the real hook), **offline-captured** (cached real embeddings, zero requests), **live** (key verification). No em dashes.

## Keys (live, 29 requests; names and statuses only) , commit f28b3be
`docs/key_verification_2026_10_07.md`. Groq: GROQ_KEY_10 to 18 return 200 (9 keys); GROQ_KEY_19 is a name in `.env` with no value (not called). Gemini: GEMINI_KEY_8 and 10 to 17 return 200 for both a `gemini-3.1-flash-lite` chat call and a `gemini-embedding-001` request (9 keys); GEMINI_KEY_9 returns 403 on both and stays out. Added to `devmem/config/providers.yaml` (Groq 18 keys, Gemini 14 keys) and `embeddings.yaml` (14 embedding keys). Chat-capable with the pinned model: GEMINI_KEY_1, 2, 4, 5, 6, 8, 10 to 17 (14 keys). Embedding-capable: GEMINI_KEY_1, 3, 4, 5, 6, 8, 10 to 17 (14 keys; key 3 was verified for embeddings only). Groq is not used for Phase 7 or Phase 9.

## P1. Night-key fix (approved rule 4.1, final-sweep rule 4.3 (i), tests of 4.5)
Changes (`devmem/memory/consolidation.py`, `identity.py`; no upstream edit):
- `sleep_block_night(persona, t, cfg)`: the night is `night_id` of the START of the current sleep block, remembered on the persona from the first sleeping tick after an awake tick, falling back to the current action's start time and then to the tick; a remembered start that is in the future or 24 hours old is discarded as stale (so a test driver or a run that never showed the awake ticks cannot reuse it).
- `maybe_sweep_on_sleep` clears the block start on an awake tick and passes the key to `run_nightly_sweep(night=...)` and to the identity step (`run_identity_step(night=...)`), so both steps use the same key.
- `force_sweep` (the clean-exit final sweep): a sleeping agent is keyed by its block; an AWAKE agent is consolidated under a separate namespace (night = minus the simulated day), no identity step runs for it and no Stage 4 `consolidation_events` row is written for a negative key. Its Stage 3 merges are therefore not counted by Stage 4 (stated limitation).
Tests (`devmem/memory/test_night_key.py`, 13 tests, all pass; run on the real hook with scripted ticks, **synthetic**): the Step D case (sleep from 06:00 still current at noon) now writes NO night 1 marker and the real 22:00 sweep consolidates the day's entries (the three defect tests of the checkpoint flipped); a reload mid-sleep falls back to the action start; awake final sweep is keyed -1, never blocks the real night, and runs no identity step; a sleeping final sweep uses the block key; the identity step uses the same key; the compressed Phase 7 schedule (72 hourly ticks) is keyed exactly as before (nights 0, 1, 2, 3 each once, at 14:00) and Stage 4 gets its three distinct nights; stale block starts are discarded; the brute-force table (old versus new key differ in 136 of 408 start/current pairs, exactly those whose span contains a 12:00 instant); the documented repair on a copy of the Step D database (unused). Residual stated in the checkpoint and tested: a nap that STARTS after noon is a new block keyed as the evening night; schedule constraint (b) excludes it.
Other suites after the change: `test_consolidation` 27 (1 skipped), `test_identity` 36, `test_reconcile` 10, per module in the project venv (running several modules in one process interferes through the shared ReverieServer state, as before). Two test setups now clear the new in-memory attribute. One Phase 5 test, `test_default_linkage_is_single_in_config`, was replaced by the frozen-config test (P3).

## P3. Stage 3 clustering setting (offline, cached embeddings, zero calls)
**What Stop 3 used:** the production config recorded in its own consolidation log (`docs/phase6_stop3_artifacts/consolidation_log.jsonl`): **single linkage, cluster_similarity 0.78**, minimum cluster size 3, importance floor 3.
Script `devmem/memory/p6_linkage_check.py`, artifact `docs/phase6_stop3_artifacts/linkage_check.json`: the same entries, the same real embeddings (from the on-disk cache), clustered under single 0.78 and average 0.82, compared with the scripted theme labels (the author's labels, not a measurement).

| Night | Entries and themes | single 0.78 (Stop 3) | average 0.82 |
|---|---|---|---|
| 1 | 3 baking | one cluster of 3 | one cluster of 3 |
| 2 | 7: baking 3, letters 3, lease 1 | **one cluster of 7**: 15 cross-theme pairs merged, no single-theme cluster | clusters 3, 2, 1, 1: **0 cross-theme pairs merged**; the one summarized cluster (3) is single-theme; same-theme pairs together 4 of 6 (one letters entry split off) |
| 3 | 8: conflict 5, cake 3 | clusters 5 and 3, both pure | identical |
| 4 | 3 baking | one cluster of 3 | identical |

Night 2 cosines: lowest same-theme pair 0.7956, highest cross-theme pair 0.8082 (themes overlap in cosine, so no single threshold separates them perfectly). **Decision (your rule): average 0.82 separates the themes better on the only night where the settings differ (no cross-theme merge, one pure summarized cluster instead of none), at the cost of splitting one same-theme entry. Frozen for the runs in `devmem/config/consolidation.yaml` (`linkage: average`, `cluster_similarity: 0.82`; `match_threshold` stays 0.80), labelled a design choice NOT CALIBRATED ON NATURAL DATA.** The evidence is one mixed night of 7 scripted entries; it says nothing about natural runs.

Tests and ledger: the frozen value is asserted by `test_frozen_clustering_config_is_average_linkage_at_0_82`. Stage 4 reinforcement (0.88, from Stop 2) is unchanged. No past artifact changed.

## Status of the other pre-launch items
P2: waits for 12:30 IST (script and labels already committed, f1063f2). P4: next report. Launch: not requested yet; it needs your approval after P1 to P4.
