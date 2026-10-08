# Interim analysis, day 2 (offline, no interpretation)

Every number is interim and labelled with the copy's own step and sim clock. Single run per arm; this is not a result. Source: read-only checkpoint copies, the router ledger and the movement timestamps (`devmem/eval/phase9/interim_report.py`). E1 raw counts every router row of the arm up to the wall time the copy was made; E1 unique removes the second pass of each replayed stretch after a restart.

## Primary checkpoint

| item | baseline | staged |
|---|---|---|
| checkpoint | step 13770, sim 2023-02-14 14:15:00, made 2026-10-08 17:34:49, exact first autosave True | step 13770, sim 2023-02-14 14:15:00, made 2026-10-08 13:30:03, exact first autosave True |
| E1 consolidation_summary: raw / unique | 0 / 0 | 36 / 36 |
| E1 dialogue: raw / unique | 599 / 593 | 474 / 471 |
| E1 identity_trait: raw / unique | 0 / 0 | 14 / 14 |
| E1 importance_scoring: raw / unique | 3781 / 3692 | 3331 / 3323 |
| E1 planning: raw / unique | 2978 / 2910 | 2181 / 2158 |
| E1 reflection: raw / unique | 113 / 107 | 6 / 6 |
| E1 total: raw / unique | 7471 / 7302 | 6042 / 6008 |
| E2 mean tokens in per importance-scoring call (calls) | 418.5 (3781) | 572.3 (3331) |
| E3 consolidated fraction | 0 by construction (no Stage 3) | 0.0974 (380 of 3901) |
| sweeps done per agent (nights) | not applicable | Isabella Rodriguez: [0, 1, 2], Maria Lopez: [0, 1, 2], Klaus Mueller: [0, 1, 2] |
| summaries and traits | not applicable | 14 summaries, 13 traits |

Replay passes removed from E1 unique: baseline: restart 2026-10-08 00:53:32 removed 0 calls, restart 2026-10-08 16:14:25 removed 169 calls; staged: restart 2026-10-08 00:54:01 removed 34 calls

## Secondary copy at the first autosave at or after 23:45 (sensitivity analysis)

| item | baseline | staged |
|---|---|---|
| checkpoint | step 17190, sim 2023-02-14 23:45:00, made 2026-10-08 17:47:42, exact first autosave True | step 17190, sim 2023-02-14 23:45:00, made 2026-10-08 13:46:45, exact first autosave True |
| E1 consolidation_summary: raw / unique | 0 / 0 | 36 / 36 |
| E1 dialogue: raw / unique | 602 / 596 | 476 / 473 |
| E1 identity_trait: raw / unique | 0 / 0 | 14 / 14 |
| E1 importance_scoring: raw / unique | 3781 / 3692 | 3331 / 3323 |
| E1 planning: raw / unique | 2999 / 2931 | 2195 / 2172 |
| E1 reflection: raw / unique | 113 / 107 | 6 / 6 |
| E1 total: raw / unique | 7495 / 7326 | 6058 / 6024 |
| E2 mean tokens in per importance-scoring call (calls) | 418.5 (3781) | 572.3 (3331) |
| E3 consolidated fraction | 0 by construction (no Stage 3) | 0.0974 (380 of 3901) |
| sweeps done per agent (nights) | not applicable | Isabella Rodriguez: [0, 1, 2], Maria Lopez: [0, 1, 2], Klaus Mueller: [0, 1, 2] |
| summaries and traits | not applicable | 14 summaries, 13 traits |

Replay passes removed from E1 unique: baseline: restart 2026-10-08 00:53:32 removed 0 calls, restart 2026-10-08 16:14:25 removed 169 calls; staged: restart 2026-10-08 00:54:01 removed 34 calls

