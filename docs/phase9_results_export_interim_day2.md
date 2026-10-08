# Results export: INTERIM day 2 (dry run of the final export)

Built 2026-10-08 18:31:36. Single run per arm, 3 agents: descriptive only, no significance claims, no causal attribution to one stage (reflection is off in the staged arm, decision D1). Arm states: {'baseline': 'running', 'staged': 'running'}.

## Predictions (pre-registration section 5, scored by the rules in the module header)

| id | prediction | outcome | reason | numbers |
|---|---|---|---|---|
| E1 | S makes more calls than B by less than 10 percent of B's calls (unique calls, same checkpoint step) | **wrong** | S made fewer calls than B; the cause is named in the purpose breakdown (E1 table) | baseline_unique=7302, staged_unique=6008, relative_difference=-0.1772 |
| E2 | mean prompt tokens per scoring call higher in S than in B | **right** | direction only; the size of the priors and trait blocks is not separately checked here | baseline=418.5, staged=572.3 |
| E3 | consolidated fraction above 0 in S and exactly 0 in B | **right** | B has no Stage 3 by construction | baseline=0.0, staged=0.0974 |
| R1 | S answers Isabella's theme-count question no worse than B | **undecidable** | interim day 2: this prediction needs the day-3 checkpoint (pre-registration section 5b) |  |
| R2 | S answers Klaus's theme-count question no worse than B | **undecidable** | interim day 2: this prediction needs the day-3 checkpoint (pre-registration section 5b) |  |
| R3 | pivotal events I5, M5, K5 at distance 2: no checklist difference larger than 0.2 | **undecidable** | interim day 2: this prediction needs the day-3 checkpoint (pre-registration section 5b) |  |
| R4 | mundane events at distance 2: S at or below B | **undecidable** | interim day 2: this prediction needs the day-3 checkpoint (pre-registration section 5b) |  |
| R5 | same-day questions (distance 0): no difference larger than 0.1 | **undecidable** | recall answers are not available yet for both arms |  |
| S-Isabella | staged minus baseline mean importance on the persona's friction events is above 0 | **undecidable** | replay controls have not been run yet (they run on the staged pool after the staged arm finishes) |  |
| S-Maria | staged minus baseline mean importance on the persona's friction events is above 0 | **undecidable** | replay controls have not been run yet (they run on the staged pool after the staged arm finishes) |  |
| S-Klaus | staged minus baseline mean importance on the persona's friction events is below 0 | **undecidable** | replay controls have not been run yet (they run on the staged pool after the staged arm finishes) |  |
| S-mismatch | mismatch priors move scores toward that persona's direction | **undecidable** | the registered text gives no sign for Wolfgang Schulz's direction, so no pre-registered threshold exists; the observed means are in the replay table |  |
| M2 | no directional prediction (two-sided, only if the judge calibration is at least 80 percent) | **undecidable** | day-1 against day-3 judge results or the judge calibration are not available yet |  |
| D-1 | at least one third of Stage 4 traits closer to the priors text than to their sources | **undecidable** | fewer than 3 traits with cached embeddings (traits 13, available 0) | traits=13, available=0, flagged=0 |
| D-2 | Stage 3 entries merged between cosine 0.80 and 0.88 above 0 over the three nights | **undecidable** | the consolidation log records cluster sizes, not the cosines at which entries merged; the metric was never logged, and a re-clustering offline from cached embeddings is not built (open question to the PM) |  |

## E1 to E3 (checkpoint copies)

| item | baseline | staged |
|---|---|---|
| checkpoint | step 13770, sim 2023-02-14 14:15:00 | step 13770, sim 2023-02-14 14:15:00 |
| E1 calls raw / unique | 7471 / 7302 | 6042 / 6008 |
| E2 mean tokens in per importance call | 418.5 (3781 calls) | 572.3 (3331 calls) |
| E3 consolidated fraction | 0.0 (0 of 0) | 0.0974 (380 of 3901) |

### E1 unique calls by purpose per simulated day (both arms)

| arm | sim day | purpose | unique calls |
|---|---|---|---|
| baseline | 1 | dialogue | 314 |
| baseline | 1 | importance_scoring | 1588 |
| baseline | 1 | planning | 1479 |
| baseline | 1 | reflection | 51 |
| baseline | 2 | dialogue | 279 |
| baseline | 2 | importance_scoring | 2104 |
| baseline | 2 | planning | 1431 |
| baseline | 2 | reflection | 56 |
| staged | 1 | consolidation_summary | 18 |
| staged | 1 | dialogue | 268 |
| staged | 1 | identity_trait | 11 |
| staged | 1 | importance_scoring | 1245 |
| staged | 1 | planning | 1152 |
| staged | 2 | consolidation_summary | 18 |
| staged | 2 | dialogue | 203 |
| staged | 2 | identity_trait | 3 |
| staged | 2 | importance_scoring | 2078 |
| staged | 2 | planning | 1006 |
| staged | 2 | reflection | 6 |

### E1 unique calls per agent (simulated day, purpose)

| arm | agent | sim day | purpose | raw | unique |
|---|---|---|---|---|---|
| baseline | Isabella Rodriguez | 1 | dialogue | 92 | 92 |
| baseline | Isabella Rodriguez | 1 | importance_scoring | 679 | 679 |
| baseline | Isabella Rodriguez | 1 | planning | 479 | 479 |
| baseline | Isabella Rodriguez | 1 | reflection | 21 | 21 |
| baseline | Klaus Mueller | 1 | dialogue | 91 | 91 |
| baseline | Klaus Mueller | 1 | importance_scoring | 280 | 280 |
| baseline | Klaus Mueller | 1 | planning | 422 | 422 |
| baseline | Klaus Mueller | 1 | reflection | 9 | 9 |
| baseline | Maria Lopez | 1 | dialogue | 131 | 131 |
| baseline | Maria Lopez | 1 | importance_scoring | 629 | 629 |
| baseline | Maria Lopez | 1 | planning | 578 | 578 |
| baseline | Maria Lopez | 1 | reflection | 21 | 21 |
| baseline | Isabella Rodriguez | 2 | dialogue | 96 | 95 |
| baseline | Isabella Rodriguez | 2 | importance_scoring | 1133 | 1100 |
| baseline | Isabella Rodriguez | 2 | planning | 636 | 610 |
| baseline | Isabella Rodriguez | 2 | reflection | 34 | 31 |
| baseline | Klaus Mueller | 2 | dialogue | 88 | 87 |
| baseline | Klaus Mueller | 2 | importance_scoring | 432 | 432 |
| baseline | Klaus Mueller | 2 | planning | 426 | 419 |
| baseline | Klaus Mueller | 2 | reflection | 12 | 12 |
| baseline | Maria Lopez | 2 | dialogue | 101 | 97 |
| baseline | Maria Lopez | 2 | importance_scoring | 628 | 572 |
| baseline | Maria Lopez | 2 | planning | 437 | 402 |
| baseline | Maria Lopez | 2 | reflection | 16 | 13 |
| staged | Isabella Rodriguez | 1 | consolidation_summary | 6 | 6 |
| staged | Isabella Rodriguez | 1 | dialogue | 70 | 69 |
| staged | Isabella Rodriguez | 1 | identity_trait | 2 | 2 |
| staged | Isabella Rodriguez | 1 | importance_scoring | 505 | 501 |
| staged | Isabella Rodriguez | 1 | planning | 369 | 362 |
| staged | Klaus Mueller | 1 | consolidation_summary | 6 | 6 |
| staged | Klaus Mueller | 1 | dialogue | 90 | 89 |
| staged | Klaus Mueller | 1 | identity_trait | 4 | 4 |
| staged | Klaus Mueller | 1 | importance_scoring | 282 | 281 |
| staged | Klaus Mueller | 1 | planning | 393 | 385 |
| staged | Maria Lopez | 1 | consolidation_summary | 6 | 6 |
| staged | Maria Lopez | 1 | dialogue | 111 | 110 |
| staged | Maria Lopez | 1 | identity_trait | 5 | 5 |
| staged | Maria Lopez | 1 | importance_scoring | 466 | 463 |
| staged | Maria Lopez | 1 | planning | 413 | 405 |
| staged | Isabella Rodriguez | 2 | consolidation_summary | 6 | 6 |
| staged | Isabella Rodriguez | 2 | dialogue | 58 | 58 |
| staged | Isabella Rodriguez | 2 | identity_trait | 2 | 2 |
| staged | Isabella Rodriguez | 2 | importance_scoring | 972 | 972 |
| staged | Isabella Rodriguez | 2 | planning | 343 | 343 |
| staged | Isabella Rodriguez | 2 | reflection | 6 | 6 |
| staged | Klaus Mueller | 2 | consolidation_summary | 6 | 6 |
| staged | Klaus Mueller | 2 | dialogue | 57 | 57 |
| staged | Klaus Mueller | 2 | identity_trait | 1 | 1 |
| staged | Klaus Mueller | 2 | importance_scoring | 357 | 357 |
| staged | Klaus Mueller | 2 | planning | 318 | 318 |
| staged | Maria Lopez | 2 | consolidation_summary | 6 | 6 |
| staged | Maria Lopez | 2 | dialogue | 88 | 88 |
| staged | Maria Lopez | 2 | importance_scoring | 749 | 749 |
| staged | Maria Lopez | 2 | planning | 345 | 345 |

## Sweep markers per agent and night (staged)

- Isabella Rodriguez: night 0 done, night 1 done, night 2 done
- Klaus Mueller: night 0 done, night 1 done, night 2 done
- Maria Lopez: night 0 done, night 1 done, night 2 done

## Recall (R1 to R5): per question

Grader validation: {'items_checked': 57, 'item_agreement': 0.9474, 'answers': 30, 'answer_agreement': 0.9333, 'interpretable': True}. Excluded questions: ['Q_I6'].

| question | agent | type | event | distance | baseline score | staged score | note |
|---|---|---|---|---|---|---|---|
| Q_I1 | Isabella Rodriguez | injected | I1 | 1 | n/a | n/a |  |
| Q_I2 | Isabella Rodriguez | injected | I2 | 1 | n/a | n/a |  |
| Q_I3 | Isabella Rodriguez | injected | I3 | 1 | n/a | n/a |  |
| Q_I4 | Isabella Rodriguez | injected | I4 | 0 | n/a | n/a |  |
| Q_I5 | Isabella Rodriguez | injected | I5 | 0 | n/a | n/a |  |
| Q_I6 | Isabella Rodriguez | injected | I6 | 0 | n/a | n/a | injection of I6 failed its check in an arm; excluded from both arms (pre-registration section 4) |
| Q_M1 | Maria Lopez | injected | M1 | 1 | n/a | n/a |  |
| Q_M2 | Maria Lopez | injected | M2 | 1 | n/a | n/a |  |
| Q_M3 | Maria Lopez | injected | M3 | 1 | n/a | n/a |  |
| Q_M4 | Maria Lopez | injected | M4 | 0 | n/a | n/a |  |
| Q_M5 | Maria Lopez | injected | M5 | 0 | n/a | n/a |  |
| Q_M6 | Maria Lopez | injected | M6 | 0 | n/a | n/a |  |
| Q_K1 | Klaus Mueller | injected | K1 | 1 | n/a | n/a |  |
| Q_K2 | Klaus Mueller | injected | K2 | 1 | n/a | n/a |  |
| Q_K3 | Klaus Mueller | injected | K3 | 1 | n/a | n/a |  |
| Q_K4 | Klaus Mueller | injected | K4 | 0 | n/a | n/a |  |
| Q_K5 | Klaus Mueller | injected | K5 | 0 | n/a | n/a |  |
| Q_K6 | Klaus Mueller | injected | K6 | 0 | n/a | n/a |  |
| N_I1 | Isabella Rodriguez | natural | schedule day 2 09:00 | 0 | n/a | n/a |  |
| N_I2 | Isabella Rodriguez | natural | schedule day 1 12:00 | 1 | n/a | n/a |  |
| N_M1 | Maria Lopez | natural | schedule day 2 09:00 | 0 | n/a | n/a |  |
| N_M2 | Maria Lopez | natural | schedule day 1 11:30 | 1 | n/a | n/a |  |
| N_K1 | Klaus Mueller | natural | schedule day 2 09:00 | 0 | n/a | n/a |  |
| N_K2 | Klaus Mueller | natural | schedule day 1 11:30 | 1 | n/a | n/a |  |

Bootstrap of the mean staged-minus-baseline difference: {'available': False}

- R3 as registered says distance 2, but I5, M5 and K5 are day-2 events: at the day-3 checkpoint their distance is 1; the literal registered definition matches no question. The observed pivotal pool is shown separately.
- R1 and R2 each rest on one question (n = 1 < 3): undecidable under pre-registration section 6; the observed values are shown.

## Coherence (M2)

{
 "available": false,
 "note": "day-1 against day-3 judge results or the judge calibration are not available yet",
 "calibration_available": false
}

## Stage 2 replay controls

{
 "available": false,
 "note": "not run yet"
}

## D-1 provenance and D-2

D-1: 13 traits, 0 with cached embeddings, 0 closer to the priors than to the best source. D-2: merge cosines were never logged.

## Run conditions per arm (failures, restarts, replayed spans, outage minutes, 429 wave shares)

### baseline

- state running; router failures 0; fail-safe: not logged as a separate counter (the scorer returns 4 and the call counts as a router success); router_failures counts calls that raised
- restart log events {'exit': 3, 'key_change_resume': 3, 'start': 6, 'external_kill_watchdog_restart': 1}; replayed spans (restart wall time, pre-kill step): [('2026-10-08 00:53:32', 3599), ('2026-10-08 16:14:25', 13306)]
- outage minutes (outage log) 82.6; counters at the last hourly row {'outage_minutes_total': 82.64, 'rate_limit_wait_minutes_total': 356.75, 'quota_pauses': 0, 'step': 13680, 'sim_clock': '2023-02-14 14:00:00'}
- 429 waves, whole run to now: {'waves': 228, 'waited_seconds': 22028, 'mean_wave_seconds': 96.6, 'max_wave_seconds': 438.8, 'share_of_wall_time_since_launch': 0.2303, 'note': 'wall time includes a stoppage (power off) in which no wave could occur; see the per-hour tables of devmem.eval.wave_report for windows'}
- injection check {'events_total': 27, 'resolved': 18, 'pass': 18, 'fail': [], 'pending': [], 'asleep_at_injection': []}

### staged

- state running; router failures 0; fail-safe: not logged as a separate counter (the scorer returns 4 and the call counts as a router success); router_failures counts calls that raised
- restart log events {'exit': 3, 'key_change_resume': 3, 'start': 6}; replayed spans (restart wall time, pre-kill step): [('2026-10-08 00:54:01', 4012), ('2026-10-08 16:15:24', 19809)]
- outage minutes (outage log) 90.1; counters at the last hourly row {'outage_minutes_total': 90.07, 'rate_limit_wait_minutes_total': 300.51, 'quota_pauses': 0, 'step': 13680, 'sim_clock': '2023-02-14 14:00:00'}
- 429 waves, whole run to now: {'waves': 221, 'waited_seconds': 21151, 'mean_wave_seconds': 95.7, 'max_wave_seconds': 509.1, 'share_of_wall_time_since_launch': 0.2212, 'note': 'wall time includes a stoppage (power off) in which no wave could occur; see the per-hour tables of devmem.eval.wave_report for windows'}
- injection check {'events_total': 27, 'resolved': 18, 'pass': 17, 'fail': ['I6'], 'pending': [], 'asleep_at_injection': []}

