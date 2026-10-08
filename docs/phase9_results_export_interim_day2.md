# Results export: INTERIM day 2 (dry run of the final export)

Built 2026-10-08 19:39:17. Single run per arm, 3 agents: descriptive only, no significance claims, no causal attribution to one stage (periodic reflection (focal-point and insight generation) is off in the staged arm by decision D1; the post-conversation planning-thought and memo calls in reflect() run in both arms). Arm states: {'baseline': 'running', 'staged': 'starting'}.

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
| S-mismatch | mismatch priors move scores toward that persona's direction | **undecidable** | PM ruling 2026-10-08: the registered text gives no sign for Wolfgang Schulz's direction; observed value only | observed_mismatch_mean=None |
| M2 | no directional prediction (two-sided, only if the judge calibration is at least 80 percent) | **undecidable** | day-1 against day-3 judge results or the judge calibration are not available yet |  |
| D-1 | at least one third of Stage 4 traits closer to the priors text than to their sources | **undecidable** | fewer than 3 traits with cached embeddings (traits 13, available 0) | traits=13, available=0, flagged=0 |
| D-2 | Stage 3 entries merged between cosine 0.80 and 0.88 above 0 over the nights, per agent (merge heights recovered offline by re-running the recorded clustering); WEAK BY DESIGN: at threshold 0.82 nearly every merge falls in this band | **right** | entries in final clusters of at least min_cluster_size that took part in a merge at height 0.80 to 0.88, summed over the nights of the copy | Isabella Rodriguez=127, Klaus Mueller=102, Maria Lopez=79 |

## E1 to E3 (checkpoint copies)

| item | baseline | staged |
|---|---|---|
| checkpoint | step 13770, sim 2023-02-14 14:15:00 | step 13770, sim 2023-02-14 14:15:00 |
| E1 calls raw / unique | 7471 / 7302 | 6042 / 6008 |
| E2 mean tokens in per importance call | 418.5 (3781 calls) | 572.3 (3331 calls) |
| E3 consolidated fraction | 0.0 (0 of 0) | 0.0974 (380 of 3901) |

### E1 unique calls by CLASS per simulated day (primary breakdown; rule-based classes from the prompts, devmem/eval/phase9/purpose_classes.py)

| arm | sim day | class | unique calls |
|---|---|---|---|
| baseline | 1 | action_object_description | 1500 |
| baseline | 1 | dialogue | 120 |
| baseline | 1 | importance_scoring | 1588 |
| baseline | 1 | periodic_reflection | 119 |
| baseline | 1 | planning | 77 |
| baseline | 1 | post_conversation_memo | 28 |
| baseline | 2 | action_object_description | 1461 |
| baseline | 2 | dialogue | 83 |
| baseline | 2 | importance_scoring | 2104 |
| baseline | 2 | other | 9 |
| baseline | 2 | periodic_reflection | 131 |
| baseline | 2 | planning | 58 |
| baseline | 2 | post_conversation_memo | 24 |
| baseline | all | other (share of unique) | 0.0012 |
| staged | 1 | action_object_description | 1212 |
| staged | 1 | consolidation | 18 |
| staged | 1 | dialogue | 118 |
| staged | 1 | identity | 11 |
| staged | 1 | importance_scoring | 1245 |
| staged | 1 | planning | 62 |
| staged | 1 | post_conversation_memo | 28 |
| staged | 2 | action_object_description | 1087 |
| staged | 2 | consolidation | 18 |
| staged | 2 | dialogue | 60 |
| staged | 2 | identity | 3 |
| staged | 2 | importance_scoring | 2078 |
| staged | 2 | other | 9 |
| staged | 2 | planning | 43 |
| staged | 2 | post_conversation_memo | 16 |
| staged | all | other (share of unique) | 0.0015 |

Where each ledger keyword tag's calls go in the classes (whole log, both arms):

- baseline: {"planning": {"planning": 143, "action_object_description": 3079, "dialogue": 31, "periodic_reflection": 92}, "dialogue": {"action_object_description": 340, "dialogue": 174, "post_conversation_memo": 52, "periodic_reflection": 72, "other": 18, "planning": 6}, "importance_scoring": {"importance_scoring": 4019}, "reflection": {"periodic_reflection": 121, "action_object_description": 1}}
- staged: {"planning": {"planning": 125, "action_object_description": 2693, "dialogue": 47}, "dialogue": {"action_object_description": 364, "dialogue": 163, "post_conversation_memo": 52, "other": 18, "planning": 11}, "importance_scoring": {"importance_scoring": 4026}, "consolidation_summary": {"consolidation": 36}, "identity_trait": {"identity": 14}, "reflection": {"action_object_description": 6}}

### E1 unique calls by the ledger KEYWORD tag per simulated day (the ledger record, not a classification); the last column is the purpose-tag audit (false-match rate of the keyword tag, sampled)

| arm | sim day | purpose | unique calls | tag audit |
|---|---|---|---|---|
| baseline | 1 | dialogue | 314 | 0.7347 false-match rate (144 of 196 classified, 200 audited) |
| baseline | 1 | importance_scoring | 1588 | 0.0 false-match rate (0 of 200 classified, 200 audited) |
| baseline | 1 | planning | 1479 | 0.04 false-match rate (8 of 200 classified, 200 audited) |
| baseline | 1 | reflection | 51 | 0.0082 false-match rate (1 of 122 classified, 122 audited) |
| baseline | 2 | dialogue | 279 | 0.7347 false-match rate (144 of 196 classified, 200 audited) |
| baseline | 2 | importance_scoring | 2104 | 0.0 false-match rate (0 of 200 classified, 200 audited) |
| baseline | 2 | planning | 1431 | 0.04 false-match rate (8 of 200 classified, 200 audited) |
| baseline | 2 | reflection | 56 | 0.0082 false-match rate (1 of 122 classified, 122 audited) |
| staged | 1 | consolidation_summary | 18 | not audited (set by the code, not by the keyword rule) |
| staged | 1 | dialogue | 268 | 0.759 false-match rate (148 of 195 classified, 200 audited) |
| staged | 1 | identity_trait | 11 | not audited (set by the code, not by the keyword rule) |
| staged | 1 | importance_scoring | 1245 | 0.0 false-match rate (0 of 200 classified, 200 audited) |
| staged | 1 | planning | 1152 | 0.02 false-match rate (4 of 200 classified, 200 audited) |
| staged | 2 | consolidation_summary | 18 | not audited (set by the code, not by the keyword rule) |
| staged | 2 | dialogue | 203 | 0.759 false-match rate (148 of 195 classified, 200 audited) |
| staged | 2 | identity_trait | 3 | not audited (set by the code, not by the keyword rule) |
| staged | 2 | importance_scoring | 2078 | 0.0 false-match rate (0 of 200 classified, 200 audited) |
| staged | 2 | planning | 1006 | 0.02 false-match rate (4 of 200 classified, 200 audited) |
| staged | 2 | reflection | 6 | 1.0 false-match rate (6 of 6 classified, 6 audited) |

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

## Purpose-tag audit (planning, dialogue, reflection, importance_scoring)

{
 "seed": 20261008,
 "sample_per_tag_per_arm": 200,
 "templates_loaded": 91,
 "arms": {
  "baseline": {
   "log_rows": 8156,
   "tags": {
    "planning": {
     "rows_with_this_tag_in_log": 3345,
     "audited": 200,
     "sampled": true,
     "true_family": 192,
     "false_match": 8,
     "unclassified": 0,
     "false_match_rate_of_classified": 0.04,
     "false_matches_belong_to": {
      "reflection": 5,
      "dialogue": 3
     },
     "examples": [
      "generate_focal_pt: '\"\"\"\\nMaria Lopez shares a close, collaborative, and mutually supportive'",
      "summarize_chat_relationship: '\"\"\"\\n[Statements]\\nMaria Lopez values deep, meaningful relationships wit'"
     ]
    },
    "dialogue": {
     "rows_with_this_tag_in_log": 662,
     "audited": 200,
     "sampled": true,
     "true_family": 52,
     "false_match": 144,
     "unclassified": 4,
     "false_match_rate_of_classified": 0.7347,
     "false_matches_belong_to": {
      "planning": 107,
      "reflection": 37
     },
     "examples": [
      "action_object: 'Current activity: sleep in bed\\nObjects available: {bed, easel, closet,'",
      "action_object: 'Current activity: sleep in bed\\nObjects available: {bed, easel, closet,'"
     ]
    },
    "reflection": {
     "rows_with_this_tag_in_log": 122,
     "audited": 122,
     "sampled": false,
     "true_family": 121,
     "false_match": 1,
     "unclassified": 0,
     "false_match_rate_of_classified": 0.0082,
     "false_matches_belong_to": {
      "planning": 1
     },
     "examples": [
      "generate_event_triple: 'Task: Turn the input into (subject, predicate, object). \\n\\nInput: Sam J'"
     ]
    },
    "importance_scoring": {
     "rows_with_this_tag_in_log": 4027,
     "audited": 200,
     "sampled": true,
     "true_family": 200,
     "false_match": 0,
     "unclassified": 0,
     "false_match_rate_of_classified": 0.0,
     "false_matches_belong_to": {},
     "examples": []
    }
   },
   "reflection_family_prompts_whole_log": {
    "by_tag_and_template": {
     "dialogue": {
      "memo_on_convo": 52,
      "generate_focal_pt": 72
     },
     "reflection": {
      "insight_and_evidence": 121
     },
     "planning": {
      "generate_focal_pt": 92
     }
    },
    "total": 337
   }
  },
  "staged": {
   "log_rows": 7555,
   "tags": {
    "planning": {
     "rows_with_this_tag_in_log": 2865,
     "audited": 200,
     "sampled": true,
     "true_family": 196,
     "false_match": 4,
     "unclassified": 0,
     "false_match_rate_of_classified": 0.02,
     "false_matches_belong_to": {
      "dialogue": 4
     },
     "examples": [
      "summarize_chat_relationship: '\"\"\"\\n[Statements]\\nThis is Isabella Rodriguez\\'s plan for Monday February'",
      "summarize_chat_relationship: '\"\"\"\\n[Statements]\\nKlaus Mueller is conversing about Klaus Mueller and M'"
     ]
    },
    "dialogue": {
     "rows_with_this_tag_in_log": 608,
     "audited": 200,
     "sampled": true,
     "true_family": 47,
     "false_match": 148,
     "unclassified": 5,
     "false_match_rate_of_classified": 0.759,
     "false_matches_belong_to": {
      "planning": 128,
      "reflection": 20
     },
     "examples": [
      "action_object: 'Current activity: sleep in bed\\nObjects available: {bed, easel, closet,'",
      "action_object: 'Current activity: sleep in bed\\nObjects available: {bed, easel, closet,'"
     ]
    },
    "reflection": {
     "rows_with_this_tag_in_log": 6,
     "audited": 6,
     "sampled": false,
     "true_family": 0,
     "false_match": 6,
     "unclassified": 0,
     "false_match_rate_of_classified": 1.0,
     "false_matches_belong_to": {
      "planning": 6
     },
     "examples": [
      "action_location_sector: 'Task -- choose an appropriate area  from the area options for a task a'",
      "action_location_object: \"Jane Anderson is in kitchen in Jane Anderson's house.\\nJane Anderson is\""
     ]
    },
    "importance_scoring": {
     "rows_with_this_tag_in_log": 4026,
     "audited": 200,
     "sampled": true,
     "true_family": 200,
     "false_match": 0,
     "unclassified": 0,
     "false_match_rate_of_classified": 0.0,
     "false_matches_belong_to": {},
     "examples": []
    }
   },
   "reflection_family_prompts_whole_log": {
    "by_tag_and_template": {
     "dialogue": {
      "memo_on_convo": 52
     }
    },
    "total": 52
   }
  }
 },
 "note": "false-match rate = rows whose upstream template belongs to another family, over rows matched to a template; unclassified rows are listed apart; keyword tag from gpt_structure._infer_purpose"
}


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

D-1: 13 traits, 0 with cached embeddings, 0 closer to the priors than to the best source.

D-2 NOTE: right, but weak by design: with the clustering threshold at 0.82 nearly every merge falls in the 0.80 to 0.88 band, so a count above 0 was close to certain. D-2 reproduction (nights, reproduced, count): {"Isabella Rodriguez": [[0, true, null], [1, true, 30], [2, true, 97]], "Klaus Mueller": [[0, true, null], [1, true, 21], [2, true, 81]], "Maria Lopez": [[0, true, null], [1, true, 30], [2, true, 49]]}; verdict {'outcome': 'right', 'reason': 'entries in final clusters of at least min_cluster_size that took part in a merge at height 0.80 to 0.88, summed over the nights of the copy', 'numbers': {'Isabella Rodriguez': 127, 'Klaus Mueller': 102, 'Maria Lopez': 79}}

## Run conditions per arm (failures, restarts, replayed spans, outage minutes, 429 wave shares)

### baseline

- state running; router failures 0; fail-safe: not logged as a separate counter (the scorer returns 4 and the call counts as a router success); router_failures counts calls that raised
- restart log events {'exit': 3, 'key_change_resume': 3, 'start': 6, 'external_kill_watchdog_restart': 1}; replayed spans (restart wall time, pre-kill step): [('2026-10-08 00:53:32', 3599), ('2026-10-08 16:14:25', 13306)]
- outage minutes (outage log) 82.6; counters at the last hourly row {'outage_minutes_total': 82.64, 'rate_limit_wait_minutes_total': 356.75, 'quota_pauses': 0, 'step': 13680, 'sim_clock': '2023-02-14 14:00:00'}
- 429 waves, whole run to now: {'waves': 233, 'waited_seconds': 22398, 'mean_wave_seconds': 96.1, 'max_wave_seconds': 438.8, 'share_of_wall_time_since_launch': 0.2247, 'note': 'wall time includes a stoppage (power off) in which no wave could occur; see the per-hour tables of devmem.eval.wave_report for windows'}
- injection check {'events_total': 27, 'resolved': 18, 'pass': 18, 'fail': [], 'pending': [], 'asleep_at_injection': []}

### staged

- state starting; router failures 0; fail-safe: not logged as a separate counter (the scorer returns 4 and the call counts as a router success); router_failures counts calls that raised
- restart log events {'exit': 4, 'key_change_resume': 3, 'start': 7, 'resume': 1}; replayed spans (restart wall time, pre-kill step): [('2026-10-08 00:54:01', 4012), ('2026-10-08 16:15:24', 19809), ('2026-10-08 19:34:36', 20826)]
- outage minutes (outage log) 90.1; counters at the last hourly row {'outage_minutes_total': 90.07, 'rate_limit_wait_minutes_total': 300.51, 'quota_pauses': 0, 'step': 13680, 'sim_clock': '2023-02-14 14:00:00'}
- 429 waves, whole run to now: {'waves': 231, 'waited_seconds': 22046, 'mean_wave_seconds': 95.4, 'max_wave_seconds': 509.1, 'share_of_wall_time_since_launch': 0.2211, 'note': 'wall time includes a stoppage (power off) in which no wave could occur; see the per-hour tables of devmem.eval.wave_report for windows'}
- injection check {'events_total': 27, 'resolved': 21, 'pass': 20, 'fail': ['I6'], 'pending': [], 'asleep_at_injection': []}

