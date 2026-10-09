# Results export: FINAL day-3 export

Built 2026-10-09 08:52:26. Single run per arm, 3 agents: descriptive only, no significance claims, no causal attribution to one stage (periodic reflection (focal-point and insight generation) is off in the staged arm by decision D1; the post-conversation planning-thought and memo calls in reflect() run in both arms). Arm states: {'baseline': 'finished: reached 2023-02-16 00:00:00', 'staged': 'finished: reached 2023-02-16 00:00:00'}.

## Predictions (pre-registration section 5, scored by the rules in the module header)

| id | prediction | outcome | reason | numbers |
|---|---|---|---|---|
| E1 | S makes more calls than B by less than 10 percent of B's calls (unique calls, same checkpoint step) | **wrong** | S made fewer calls than B; the cause is named in the purpose breakdown (E1 table) | baseline_unique=11858, staged_unique=9100, relative_difference=-0.2326 |
| E2 | mean prompt tokens per scoring call higher in S than in B | **right** | direction only; the size of the priors and trait blocks is not separately checked here | baseline=466.6, staged=608.4 |
| E3 | consolidated fraction above 0 in S and exactly 0 in B | **right** | B has no Stage 3 by construction | baseline=0.0, staged=0.1012 |
| R1 | S answers Isabella's theme-count question no worse than B | **undecidable** | n = 1 question(s), below the 3 required by pre-registration section 6; the observed difference is shown, not scored | n=1, baseline_mean=0.5, staged_mean=0.0, staged_minus_baseline_mean=-0.5 |
| R2 | S answers Klaus's theme-count question no worse than B | **undecidable** | n = 1 question(s), below the 3 required by pre-registration section 6; the observed difference is shown, not scored | n=1, baseline_mean=1.0, staged_mean=1.0, staged_minus_baseline_mean=0.0 |
| R3 | pivotal events I5, M5, K5 at distance 2: no checklist difference larger than 0.2 | **undecidable** | the registered definition matches no question (see the note below the table) |  |
| R4 | mundane events at distance 2: S at or below B | **right** | applied literally | n=3, baseline_mean=0.8333, staged_mean=0.8333, staged_minus_baseline_mean=0.0 |
| R5 | same-day questions (distance 0): no difference larger than 0.1 | **right** | applied literally | n=12, baseline_mean=0.8333, staged_mean=0.7917, staged_minus_baseline_mean=-0.0417 |
| S-Isabella | staged minus baseline mean importance on the persona's friction events is above 0 | **right** | n = 2 friction events for this persona (a small n; the sign is the verdict, no more); staged condition = staged_replayed (registered) | staged_replayed_minus_baseline=2.0, sensitivity_recorded_in_run_minus_baseline=2.0 |
| S-Maria | staged minus baseline mean importance on the persona's friction events is above 0 | **wrong** | n = 2 friction events for this persona (a small n; the sign is the verdict, no more); staged condition = staged_replayed (registered) | staged_replayed_minus_baseline=0.0, sensitivity_recorded_in_run_minus_baseline=0.5 |
| S-Klaus | staged minus baseline mean importance on the persona's friction events is below 0 | **wrong** | n = 2 friction events for this persona (a small n; the sign is the verdict, no more); staged condition = staged_replayed (registered) | staged_replayed_minus_baseline=2.5, sensitivity_recorded_in_run_minus_baseline=1.5 |
| S-filler | neutral filler moves scores toward the baseline (closer to baseline than staged is) | **right** | over the whole sample, all personas pooled; staged condition = staged_replayed (registered) | filler_mean=1.94, baseline_mean=1.98, staged_replayed_mean=2.411, sensitivity_recorded_in_run_mean=2.629, sensitivity_filler_closer_than_recorded=True |
| S-mismatch | mismatch priors move scores toward that persona's direction | **undecidable** | PM ruling 2026-10-08: the registered text gives no sign for Wolfgang Schulz's direction; observed value only | observed_mismatch_mean=2.472 |
| M2 | no directional prediction (two-sided, only if the judge calibration is at least 80 percent) | **no prediction** | reported two-sided | calibration_accuracy=1.0, coherence_interpretable=True |
| D-1 | at least one third of Stage 4 traits closer to the priors text than to their sources | **wrong** | cached-embedding cosines; a diagnostic | traits=14, available=14, flagged=1, fraction=0.071 |
| D-2 | Stage 3 entries merged between cosine 0.80 and 0.88 above 0 over the nights, per agent (merge heights recovered offline by re-running the recorded clustering); WEAK BY DESIGN: at threshold 0.82 nearly every merge falls in this band | **right** | entries in final clusters of at least min_cluster_size that took part in a merge at height 0.80 to 0.88, summed over the nights of the copy | Isabella Rodriguez=362, Klaus Mueller=221, Maria Lopez=236 |

## E1 to E3 (checkpoint copies)

| item | baseline | staged |
|---|---|---|
| checkpoint | step 22410, sim 2023-02-15 14:15:00 | step 22410, sim 2023-02-15 14:15:00 |
| E1 calls raw / unique | 12027 / 11858 | 9203 / 9100 |
| E2 mean tokens in per importance call | 466.6 (6213 calls) | 608.4 (4917 calls) |
| E3 consolidated fraction | 0.0 (0 of 0) | 0.1012 (589 of 5822) |

### E1 unique calls by CLASS per simulated day (primary breakdown; rule-based classes from the prompts, devmem/eval/phase9/purpose_classes.py)

| arm | sim day | class | unique calls |
|---|---|---|---|
| baseline | 1 | action_object_description | 1500 |
| baseline | 1 | dialogue | 120 |
| baseline | 1 | importance_scoring | 1588 |
| baseline | 1 | periodic_reflection | 119 |
| baseline | 1 | planning | 77 |
| baseline | 1 | post_conversation_memo | 28 |
| baseline | 2 | action_object_description | 1509 |
| baseline | 2 | dialogue | 83 |
| baseline | 2 | importance_scoring | 2104 |
| baseline | 2 | other | 9 |
| baseline | 2 | periodic_reflection | 131 |
| baseline | 2 | planning | 58 |
| baseline | 2 | post_conversation_memo | 24 |
| baseline | 3 | action_object_description | 1658 |
| baseline | 3 | dialogue | 125 |
| baseline | 3 | importance_scoring | 2432 |
| baseline | 3 | other | 9 |
| baseline | 3 | periodic_reflection | 175 |
| baseline | 3 | planning | 85 |
| baseline | 3 | post_conversation_memo | 24 |
| baseline | all | other (share of unique) | 0.0015 |
| staged | 1 | action_object_description | 1212 |
| staged | 1 | consolidation | 18 |
| staged | 1 | dialogue | 118 |
| staged | 1 | identity | 11 |
| staged | 1 | importance_scoring | 1245 |
| staged | 1 | planning | 62 |
| staged | 1 | post_conversation_memo | 28 |
| staged | 2 | action_object_description | 1119 |
| staged | 2 | consolidation | 18 |
| staged | 2 | dialogue | 60 |
| staged | 2 | identity | 3 |
| staged | 2 | importance_scoring | 2078 |
| staged | 2 | other | 9 |
| staged | 2 | planning | 43 |
| staged | 2 | post_conversation_memo | 16 |
| staged | 3 | action_object_description | 1230 |
| staged | 3 | consolidation | 18 |
| staged | 3 | dialogue | 125 |
| staged | 3 | identity | 1 |
| staged | 3 | importance_scoring | 1566 |
| staged | 3 | other | 9 |
| staged | 3 | planning | 83 |
| staged | 3 | post_conversation_memo | 28 |
| staged | all | other (share of unique) | 0.002 |

Where each ledger keyword tag's calls go in the classes (whole log, both arms):

- baseline: {"planning": {"planning": 201, "action_object_description": 4283, "dialogue": 57, "periodic_reflection": 144}, "dialogue": {"action_object_description": 461, "dialogue": 273, "post_conversation_memo": 76, "periodic_reflection": 108, "other": 18, "planning": 21}, "importance_scoring": {"importance_scoring": 6215}, "reflection": {"periodic_reflection": 187, "action_object_description": 1}}
- staged: {"planning": {"planning": 177, "action_object_description": 3200, "dialogue": 71}, "dialogue": {"action_object_description": 441, "dialogue": 232, "post_conversation_memo": 72, "other": 18, "planning": 16}, "importance_scoring": {"importance_scoring": 4917}, "consolidation_summary": {"consolidation": 54}, "identity_trait": {"identity": 15}, "reflection": {"action_object_description": 6}}

### E1 unique calls by the ledger KEYWORD tag per simulated day (the ledger record, not a classification); the last column is the purpose-tag audit (false-match rate of the keyword tag, sampled)

| arm | sim day | purpose | unique calls | tag audit |
|---|---|---|---|---|
| baseline | 1 | dialogue | 314 | 0.7107 false-match rate (140 of 197 classified, 200 audited) |
| baseline | 1 | importance_scoring | 1588 | 0.0 false-match rate (0 of 200 classified, 200 audited) |
| baseline | 1 | planning | 1479 | 0.04 false-match rate (8 of 200 classified, 200 audited) |
| baseline | 1 | reflection | 51 | 0.0053 false-match rate (1 of 188 classified, 188 audited) |
| baseline | 2 | dialogue | 285 | 0.7107 false-match rate (140 of 197 classified, 200 audited) |
| baseline | 2 | importance_scoring | 2104 | 0.0 false-match rate (0 of 200 classified, 200 audited) |
| baseline | 2 | planning | 1473 | 0.04 false-match rate (8 of 200 classified, 200 audited) |
| baseline | 2 | reflection | 56 | 0.0053 false-match rate (1 of 188 classified, 188 audited) |
| baseline | 3 | dialogue | 350 | 0.7107 false-match rate (140 of 197 classified, 200 audited) |
| baseline | 3 | importance_scoring | 2432 | 0.0 false-match rate (0 of 200 classified, 200 audited) |
| baseline | 3 | planning | 1651 | 0.04 false-match rate (8 of 200 classified, 200 audited) |
| baseline | 3 | reflection | 75 | 0.0053 false-match rate (1 of 188 classified, 188 audited) |
| staged | 1 | consolidation_summary | 18 | not audited (set by the code, not by the keyword rule) |
| staged | 1 | dialogue | 268 | 0.7268 false-match rate (141 of 194 classified, 200 audited) |
| staged | 1 | identity_trait | 11 | not audited (set by the code, not by the keyword rule) |
| staged | 1 | importance_scoring | 1245 | 0.0 false-match rate (0 of 200 classified, 200 audited) |
| staged | 1 | planning | 1152 | 0.005 false-match rate (1 of 200 classified, 200 audited) |
| staged | 2 | consolidation_summary | 18 | not audited (set by the code, not by the keyword rule) |
| staged | 2 | dialogue | 207 | 0.7268 false-match rate (141 of 194 classified, 200 audited) |
| staged | 2 | identity_trait | 3 | not audited (set by the code, not by the keyword rule) |
| staged | 2 | importance_scoring | 2078 | 0.0 false-match rate (0 of 200 classified, 200 audited) |
| staged | 2 | planning | 1034 | 0.005 false-match rate (1 of 200 classified, 200 audited) |
| staged | 2 | reflection | 6 | 1.0 false-match rate (6 of 6 classified, 6 audited) |
| staged | 3 | consolidation_summary | 18 | not audited (set by the code, not by the keyword rule) |
| staged | 3 | dialogue | 294 | 0.7268 false-match rate (141 of 194 classified, 200 audited) |
| staged | 3 | identity_trait | 1 | not audited (set by the code, not by the keyword rule) |
| staged | 3 | importance_scoring | 1566 | 0.0 false-match rate (0 of 200 classified, 200 audited) |
| staged | 3 | planning | 1181 | 0.005 false-match rate (1 of 200 classified, 200 audited) |

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
| baseline | Klaus Mueller | 2 | dialogue | 89 | 88 |
| baseline | Klaus Mueller | 2 | importance_scoring | 432 | 432 |
| baseline | Klaus Mueller | 2 | planning | 433 | 426 |
| baseline | Klaus Mueller | 2 | reflection | 12 | 12 |
| baseline | Maria Lopez | 2 | dialogue | 106 | 102 |
| baseline | Maria Lopez | 2 | importance_scoring | 628 | 572 |
| baseline | Maria Lopez | 2 | planning | 472 | 437 |
| baseline | Maria Lopez | 2 | reflection | 16 | 13 |
| baseline | Isabella Rodriguez | 3 | dialogue | 121 | 121 |
| baseline | Isabella Rodriguez | 3 | importance_scoring | 979 | 979 |
| baseline | Isabella Rodriguez | 3 | planning | 564 | 564 |
| baseline | Isabella Rodriguez | 3 | reflection | 30 | 30 |
| baseline | Klaus Mueller | 3 | dialogue | 102 | 102 |
| baseline | Klaus Mueller | 3 | importance_scoring | 473 | 473 |
| baseline | Klaus Mueller | 3 | planning | 492 | 492 |
| baseline | Klaus Mueller | 3 | reflection | 15 | 15 |
| baseline | Maria Lopez | 3 | dialogue | 127 | 127 |
| baseline | Maria Lopez | 3 | importance_scoring | 980 | 980 |
| baseline | Maria Lopez | 3 | planning | 595 | 595 |
| baseline | Maria Lopez | 3 | reflection | 30 | 30 |
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
| staged | Isabella Rodriguez | 2 | dialogue | 60 | 60 |
| staged | Isabella Rodriguez | 2 | identity_trait | 2 | 2 |
| staged | Isabella Rodriguez | 2 | importance_scoring | 972 | 972 |
| staged | Isabella Rodriguez | 2 | planning | 357 | 357 |
| staged | Isabella Rodriguez | 2 | reflection | 6 | 6 |
| staged | Klaus Mueller | 2 | consolidation_summary | 6 | 6 |
| staged | Klaus Mueller | 2 | dialogue | 58 | 58 |
| staged | Klaus Mueller | 2 | identity_trait | 1 | 1 |
| staged | Klaus Mueller | 2 | importance_scoring | 357 | 357 |
| staged | Klaus Mueller | 2 | planning | 325 | 325 |
| staged | Maria Lopez | 2 | consolidation_summary | 6 | 6 |
| staged | Maria Lopez | 2 | dialogue | 89 | 89 |
| staged | Maria Lopez | 2 | importance_scoring | 749 | 749 |
| staged | Maria Lopez | 2 | planning | 352 | 352 |
| staged | Isabella Rodriguez | 3 | consolidation_summary | 6 | 6 |
| staged | Isabella Rodriguez | 3 | dialogue | 100 | 97 |
| staged | Isabella Rodriguez | 3 | importance_scoring | 690 | 682 |
| staged | Isabella Rodriguez | 3 | planning | 445 | 417 |
| staged | Klaus Mueller | 3 | consolidation_summary | 6 | 6 |
| staged | Klaus Mueller | 3 | dialogue | 82 | 81 |
| staged | Klaus Mueller | 3 | importance_scoring | 339 | 330 |
| staged | Klaus Mueller | 3 | planning | 383 | 375 |
| staged | Maria Lopez | 3 | consolidation_summary | 6 | 6 |
| staged | Maria Lopez | 3 | dialogue | 117 | 116 |
| staged | Maria Lopez | 3 | identity_trait | 1 | 1 |
| staged | Maria Lopez | 3 | importance_scoring | 557 | 554 |
| staged | Maria Lopez | 3 | planning | 397 | 389 |

## Sweep markers per agent and night (staged)

- Isabella Rodriguez: night 0 done, night 1 done, night 2 done, night 3 done
- Klaus Mueller: night 0 done, night 1 done, night 2 done, night 3 done
- Maria Lopez: night 0 done, night 1 done, night 2 done, night 3 done

## Recall (R1 to R5): per question

Grader validation: {'items_checked': 57, 'item_agreement': 0.9474, 'answers': 30, 'answer_agreement': 0.9333, 'interpretable': True}. Excluded questions: ['Q_I6'].

| question | agent | type | event | distance | baseline score | staged score | note |
|---|---|---|---|---|---|---|---|
| Q_I1 | Isabella Rodriguez | injected | I1 | 2 | 1.0 | 1.0 |  |
| Q_I2 | Isabella Rodriguez | injected | I2 | 2 | 1.0 | 0.0 |  |
| Q_I3 | Isabella Rodriguez | injected | I3 | 2 | 1.0 | 1.0 |  |
| Q_I4 | Isabella Rodriguez | injected | I4 | 1 | 1.0 | 1.0 |  |
| Q_I5 | Isabella Rodriguez | injected | I5 | 1 | 1.0 | 1.0 |  |
| Q_I6 | Isabella Rodriguez | injected | I6 | 1 | 1.0 | 0.0 | injection of I6 failed its check in an arm; excluded from both arms (pre-registration section 4) |
| Q_I7 | Isabella Rodriguez | injected | I7 | 0 | 1.0 | 1.0 |  |
| Q_I8 | Isabella Rodriguez | injected | I8 | 0 | 1.0 | 1.0 |  |
| Q_I9 | Isabella Rodriguez | injected | I9 | 0 | 1.0 | 1.0 |  |
| Q_M1 | Maria Lopez | injected | M1 | 2 | 1.0 | 1.0 |  |
| Q_M2 | Maria Lopez | injected | M2 | 2 | 1.0 | 1.0 |  |
| Q_M3 | Maria Lopez | injected | M3 | 2 | 1.0 | 1.0 |  |
| Q_M4 | Maria Lopez | injected | M4 | 1 | 1.0 | 1.0 |  |
| Q_M5 | Maria Lopez | injected | M5 | 1 | 1.0 | 1.0 |  |
| Q_M6 | Maria Lopez | injected | M6 | 1 | 1.0 | 1.0 |  |
| Q_M7 | Maria Lopez | injected | M7 | 0 | 1.0 | 1.0 |  |
| Q_M8 | Maria Lopez | injected | M8 | 0 | 1.0 | 1.0 |  |
| Q_M9 | Maria Lopez | injected | M9 | 0 | 1.0 | 1.0 |  |
| Q_K1 | Klaus Mueller | injected | K1 | 2 | 0.5 | 0.5 |  |
| Q_K2 | Klaus Mueller | injected | K2 | 2 | 0.5 | 0.5 |  |
| Q_K3 | Klaus Mueller | injected | K3 | 2 | 1.0 | 1.0 |  |
| Q_K4 | Klaus Mueller | injected | K4 | 1 | 1.0 | 1.0 |  |
| Q_K5 | Klaus Mueller | injected | K5 | 1 | 1.0 | 1.0 |  |
| Q_K6 | Klaus Mueller | injected | K6 | 1 | 1.0 | 1.0 |  |
| Q_K7 | Klaus Mueller | injected | K7 | 0 | 0.0 | 1.0 |  |
| Q_K8 | Klaus Mueller | injected | K8 | 0 | 1.0 | 1.0 |  |
| Q_K9 | Klaus Mueller | injected | K9 | 0 | 0.5 | 0.5 |  |
| Q_I_theme | Isabella Rodriguez | theme_count | I2,I4,I7 | None | 0.5 | 0.0 |  |
| Q_M_theme | Maria Lopez | theme_count | M2,M6,M8 | None | 1.0 | 0.5 |  |
| Q_K_theme | Klaus Mueller | theme_count | K2,K6,K8 | None | 1.0 | 1.0 |  |
| N_I1 | Isabella Rodriguez | natural | schedule day 2 09:00 | 1 | 1.0 | 1.0 |  |
| N_I2 | Isabella Rodriguez | natural | schedule day 1 12:00 | 2 | 0.0 | 0.0 |  |
| N_I3 | Isabella Rodriguez | natural | schedule day 3 06:30 | 0 | 1.0 | 0.0 |  |
| N_M1 | Maria Lopez | natural | schedule day 2 09:00 | 1 | 1.0 | 1.0 |  |
| N_M2 | Maria Lopez | natural | schedule day 1 11:30 | 2 | 1.0 | 1.0 |  |
| N_M3 | Maria Lopez | natural | schedule day 3 07:30 | 0 | 0.5 | 0.0 |  |
| N_K1 | Klaus Mueller | natural | schedule day 2 09:00 | 1 | 1.0 | 1.0 |  |
| N_K2 | Klaus Mueller | natural | schedule day 1 11:30 | 2 | 0.0 | 1.0 |  |
| N_K3 | Klaus Mueller | natural | schedule day 3 07:30 | 0 | 1.0 | 1.0 |  |

Bootstrap of the mean staged-minus-baseline difference: {'available': True, 'mean': -0.0438, 'ci95': [-0.1421, 0.0609], 'resamples': 2000, 'agents': 3, 'questions': 38}

- R3 as registered says distance 2, but I5, M5 and K5 are day-2 events: at the day-3 checkpoint their distance is 1; the literal registered definition matches no question. The observed pivotal pool is shown separately.
- R1 and R2 each rest on one question (n = 1 < 3): undecidable under pre-registration section 6; the observed values are shown.

## Purpose-tag audit (planning, dialogue, reflection, importance_scoring)

{
 "seed": 20261008,
 "sample_per_tag_per_arm": 200,
 "templates_loaded": 91,
 "arms": {
  "baseline": {
   "log_rows": 12045,
   "tags": {
    "planning": {
     "rows_with_this_tag_in_log": 4685,
     "audited": 200,
     "sampled": true,
     "true_family": 192,
     "false_match": 8,
     "unclassified": 0,
     "false_match_rate_of_classified": 0.04,
     "false_matches_belong_to": {
      "reflection": 4,
      "dialogue": 4
     },
     "examples": [
      "generate_focal_pt: 'Maria Lopez maintains a disciplined academic schedule balanced with so'",
      "generate_focal_pt: 'library table is being cleared\\nwalking to Hobbs Cafe from the library\\n'"
     ]
    },
    "dialogue": {
     "rows_with_this_tag_in_log": 957,
     "audited": 200,
     "sampled": true,
     "true_family": 57,
     "false_match": 140,
     "unclassified": 3,
     "false_match_rate_of_classified": 0.7107,
     "false_matches_belong_to": {
      "planning": 106,
      "reflection": 34
     },
     "examples": [
      "action_object: 'Current activity: sleep in bed\\nObjects available: {bed, easel, closet,'",
      "action_object: 'Current activity: sleep in bed\\nObjects available: {bed, easel, closet,'"
     ]
    },
    "reflection": {
     "rows_with_this_tag_in_log": 188,
     "audited": 188,
     "sampled": false,
     "true_family": 187,
     "false_match": 1,
     "unclassified": 0,
     "false_match_rate_of_classified": 0.0053,
     "false_matches_belong_to": {
      "planning": 1
     },
     "examples": [
      "generate_event_triple: 'Task: Turn the input into (subject, predicate, object). \\n\\nInput: Sam J'"
     ]
    },
    "importance_scoring": {
     "rows_with_this_tag_in_log": 6215,
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
      "memo_on_convo": 76,
      "generate_focal_pt": 108
     },
     "reflection": {
      "insight_and_evidence": 187
     },
     "planning": {
      "generate_focal_pt": 144
     }
    },
    "total": 515
   }
  },
  "staged": {
   "log_rows": 9219,
   "tags": {
    "planning": {
     "rows_with_this_tag_in_log": 3448,
     "audited": 200,
     "sampled": true,
     "true_family": 199,
     "false_match": 1,
     "unclassified": 0,
     "false_match_rate_of_classified": 0.005,
     "false_matches_belong_to": {
      "dialogue": 1
     },
     "examples": [
      "summarize_chat_relationship: '\"\"\"\\n[Statements]\\nThis is Isabella Rodriguez\\'s plan for Monday February'"
     ]
    },
    "dialogue": {
     "rows_with_this_tag_in_log": 779,
     "audited": 200,
     "sampled": true,
     "true_family": 53,
     "false_match": 141,
     "unclassified": 6,
     "false_match_rate_of_classified": 0.7268,
     "false_matches_belong_to": {
      "planning": 118,
      "reflection": 23
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
     "rows_with_this_tag_in_log": 4917,
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
      "memo_on_convo": 72
     }
    },
    "total": 72
   }
  }
 },
 "note": "false-match rate = rows whose upstream template belongs to another family, over rows matched to a template; unclassified rows are listed apart; keyword tag from gpt_structure._infer_purpose"
}


## Coherence (M2)

{
 "available": true,
 "calibration_accuracy": 1.0,
 "coherence_interpretable": true,
 "confusion_matrix_true_by_judged": {
  "consistent": {
   "consistent": 7,
   "contradictory": 0,
   "unrelated": 0,
   "parse_failure": 0
  },
  "contradictory": {
   "consistent": 0,
   "contradictory": 7,
   "unrelated": 0,
   "parse_failure": 0
  },
  "unrelated": {
   "consistent": 0,
   "contradictory": 0,
   "unrelated": 6,
   "parse_failure": 0
  }
 },
 "calibration_pairs": 20,
 "calibration_parse_failures": 0,
 "arms": {
  "baseline": {
   "pairs": 18,
   "contradiction_rate": 0.0556,
   "per_agent": {
    "Isabella Rodriguez": {
     "consistent": 6,
     "contradictory": 0,
     "unrelated": 0,
     "parse_failure": 0,
     "n": 6
    },
    "Maria Lopez": {
     "consistent": 6,
     "contradictory": 0,
     "unrelated": 0,
     "parse_failure": 0,
     "n": 6
    },
    "Klaus Mueller": {
     "consistent": 5,
     "contradictory": 1,
     "unrelated": 0,
     "parse_failure": 0,
     "n": 6
    }
   }
  },
  "staged": {
   "pairs": 18,
   "contradiction_rate": 0.0,
   "per_agent": {
    "Isabella Rodriguez": {
     "consistent": 6,
     "contradictory": 0,
     "unrelated": 0,
     "parse_failure": 0,
     "n": 6
    },
    "Maria Lopez": {
     "consistent": 6,
     "contradictory": 0,
     "unrelated": 0,
     "parse_failure": 0,
     "n": 6
    },
    "Klaus Mueller": {
     "consistent": 6,
     "contradictory": 0,
     "unrelated": 0,
     "parse_failure": 0,
     "n": 6
    }
   }
  }
 }
}

## Stage 2 replay controls

{
 "summary": {
  "by_condition": {
   "baseline": {
    "n": 299,
    "mean": 1.98
   },
   "filler": {
    "n": 299,
    "mean": 1.94
   },
   "mismatch": {
    "n": 299,
    "mean": 2.472
   },
   "staged_own": {
    "n": 299,
    "mean": 2.629
   },
   "staged_replayed": {
    "n": 299,
    "mean": 2.411
   }
  },
  "by_agent": {
   "Isabella Rodriguez|baseline": {
    "n": 101,
    "mean": 1.812
   },
   "Isabella Rodriguez|filler": {
    "n": 101,
    "mean": 1.782
   },
   "Isabella Rodriguez|mismatch": {
    "n": 101,
    "mean": 1.842
   },
   "Isabella Rodriguez|staged_own": {
    "n": 101,
    "mean": 2.614
   },
   "Isabella Rodriguez|staged_replayed": {
    "n": 101,
    "mean": 2.257
   },
   "Klaus Mueller|baseline": {
    "n": 99,
    "mean": 2.182
   },
   "Klaus Mueller|filler": {
    "n": 99,
    "mean": 2.192
   },
   "Klaus Mueller|mismatch": {
    "n": 99,
    "mean": 3.0
   },
   "Klaus Mueller|staged_own": {
    "n": 99,
    "mean": 2.889
   },
   "Klaus Mueller|staged_replayed": {
    "n": 99,
    "mean": 2.768
   },
   "Maria Lopez|baseline": {
    "n": 99,
    "mean": 1.949
   },
   "Maria Lopez|filler": {
    "n": 99,
    "mean": 1.848
   },
   "Maria Lopez|mismatch": {
    "n": 99,
    "mean": 2.586
   },
   "Maria Lopez|staged_own": {
    "n": 99,
    "mean": 2.384
   },
   "Maria Lopez|staged_replayed": {
    "n": 99,
    "mean": 2.212
   }
  }
 },
 "label": "Stage 2 replay controls on the fixed sample, staged pool, live (staged_replayed registered; staged_own sensitivity)",
 "seed": 20261008,
 "n_injected": 26,
 "n_natural": 273,
 "allocation": {
  "Isabella Rodriguez|day1": {
   "available": 483,
   "quota": 31,
   "chosen": 31
  },
  "Isabella Rodriguez|day2": {
   "available": 960,
   "quota": 31,
   "chosen": 31
  },
  "Isabella Rodriguez|day3": {
   "available": 656,
   "quota": 31,
   "chosen": 31
  },
  "Klaus Mueller|day1": {
   "available": 261,
   "quota": 30,
   "chosen": 30
  },
  "Klaus Mueller|day2": {
   "available": 343,
   "quota": 30,
   "chosen": 30
  },
  "Klaus Mueller|day3": {
   "available": 311,
   "quota": 30,
   "chosen": 30
  },
  "Maria Lopez|day1": {
   "available": 439,
   "quota": 30,
   "chosen": 30
  },
  "Maria Lopez|day2": {
   "available": 732,
   "quota": 30,
   "chosen": 30
  },
  "Maria Lopez|day3": {
   "available": 532,
   "quota": 30,
   "chosen": 30
  }
 },
 "friction_events_staged_minus_baseline_inputs": {
  "Isabella Rodriguez": {
   "mismatch": {
    "n": 2,
    "mean": 7.0
   },
   "filler": {
    "n": 2,
    "mean": 3.0
   },
   "baseline": {
    "n": 2,
    "mean": 3.0
   },
   "staged_replayed": {
    "n": 2,
    "mean": 5.0
   },
   "staged_own": {
    "n": 2,
    "mean": 5.0
   }
  },
  "Klaus Mueller": {
   "mismatch": {
    "n": 2,
    "mean": 7.0
   },
   "filler": {
    "n": 2,
    "mean": 3.5
   },
   "baseline": {
    "n": 2,
    "mean": 3.5
   },
   "staged_replayed": {
    "n": 2,
    "mean": 6.0
   },
   "staged_own": {
    "n": 2,
    "mean": 5.0
   }
  },
  "Maria Lopez": {
   "mismatch": {
    "n": 2,
    "mean": 8.0
   },
   "filler": {
    "n": 2,
    "mean": 3.0
   },
   "baseline": {
    "n": 2,
    "mean": 3.0
   },
   "staged_replayed": {
    "n": 2,
    "mean": 3.0
   },
   "staged_own": {
    "n": 2,
    "mean": 3.5
   }
  }
 },
 "calls_made_at_most": 1196,
 "new_calls_this_run": 249,
 "conditions_note": "staged_replayed = the registered staged condition (fresh replay of the staged scorer prompt with the identity context recorded for each event); staged_own = the run's recorded in-run scores, kept as a labelled sensitivity line (the first run of this step used it as the staged condition)"
}

## D-1 provenance and D-2

D-1: 14 traits, 14 with cached embeddings, 1 closer to the priors than to the best source.

D-2 NOTE: right, but weak by design: with the clustering threshold at 0.82 nearly every merge falls in the 0.80 to 0.88 band, so a count above 0 was close to certain. D-2 reproduction (nights, reproduced, count): {"Isabella Rodriguez": [[0, true, null], [1, true, 30], [2, true, 97], [3, true, 235]], "Klaus Mueller": [[0, true, null], [1, true, 21], [2, true, 81], [3, true, 119]], "Maria Lopez": [[0, true, null], [1, true, 30], [2, true, 49], [3, true, 157]]}; verdict {'outcome': 'right', 'reason': 'entries in final clusters of at least min_cluster_size that took part in a merge at height 0.80 to 0.88, summed over the nights of the copy', 'numbers': {'Isabella Rodriguez': 362, 'Klaus Mueller': 221, 'Maria Lopez': 236}}

## Run conditions per arm (failures, restarts, replayed spans, outage minutes, 429 wave shares)

### baseline

- state finished: reached 2023-02-16 00:00:00; router failures 0; fail-safe: not logged as a separate counter (the scorer returns 4 and the call counts as a router success); router_failures counts calls that raised
- restart log events {'exit': 5, 'key_change_resume': 4, 'start': 7, 'external_kill_watchdog_restart': 1, 'final': 1}; replayed spans (restart wall time, pre-kill step): [('2026-10-08 00:53:32', 3599), ('2026-10-08 16:14:25', 13306)]
- outage minutes (outage log) 93.0; counters at the last hourly row {'outage_minutes_total': 93.01, 'rate_limit_wait_minutes_total': 398.7, 'quota_pauses': 0, 'step': 22320, 'sim_clock': '2023-02-15 14:00:00'}
- 429 waves, whole run to now: {'waves': 262, 'waited_seconds': 23922, 'mean_wave_seconds': 91.3, 'max_wave_seconds': 438.8, 'share_of_wall_time_since_launch': 0.1624, 'note': 'wall time includes a stoppage (power off) in which no wave could occur; see the per-hour tables of devmem.eval.wave_report for windows'}
- injection check {'events_total': 27, 'resolved': 27, 'pass': 27, 'fail': [], 'pending': [], 'asleep_at_injection': []}

### staged

- state finished: reached 2023-02-16 00:00:00; router failures 0; fail-safe: not logged as a separate counter (the scorer returns 4 and the call counts as a router success); router_failures counts calls that raised
- restart log events {'exit': 6, 'key_change_resume': 3, 'start': 8, 'resume': 1, 'abort': 1, 'final': 1}; replayed spans (restart wall time, pre-kill step): [('2026-10-08 00:54:01', 4012), ('2026-10-08 16:15:24', 19809), ('2026-10-08 19:34:36', 20826), ('2026-10-08 20:01:52', 20826)]
- outage minutes (outage log) 90.1; counters at the last hourly row {'outage_minutes_total': 90.07, 'rate_limit_wait_minutes_total': 406.85, 'quota_pauses': 0, 'step': 22320, 'sim_clock': '2023-02-15 14:00:00'}
- 429 waves, whole run to now: {'waves': 267, 'waited_seconds': 24638, 'mean_wave_seconds': 92.3, 'max_wave_seconds': 509.1, 'share_of_wall_time_since_launch': 0.1673, 'note': 'wall time includes a stoppage (power off) in which no wave could occur; see the per-hour tables of devmem.eval.wave_report for windows'}
- injection check {'events_total': 27, 'resolved': 27, 'pass': 26, 'fail': ['I6'], 'pending': [], 'asleep_at_injection': []}

