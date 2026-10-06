PHASE: 6, Stage 4 identity memory, STOP 3 (live confirmation, one persona)
STATUS: Complete for Stop 3. Halting. Step D is still running in its worktree and has its own report (not written yet).

Paths are relative to the repository root. Labels: **live** (real provider requests), **scripted** (hand-written events; the fixture importance values are scripted, not scored), **offline-captured** (recomputed from saved live data), **derived**. No em dashes are used in any file added or changed this round. **No behavioral claim is made anywhere in this report.**

## 1. WHAT WAS RUN

`devmem/run_stop3.py` (**live**), one run, started after amendment A2 was committed (019f260):
- Persona: Isabella Rodriguez (real `Persona`, empty memory, staged mode, `STAGE4_ENABLED` on, `IDENTITY_FEEDBACK` on).
- Events: the scripted four-night fixture (21 events, scripted importance), real embeddings (`gemini-embedding-001`, cache first), production Stage 3 settings (`consolidation.yaml`, cluster 0.78 single linkage, match 0.80) and the frozen Stage 4 settings (`identity.yaml`: reinforce 0.88, T 9).
- Real calls: Stage 3 summaries, summary scoring, Stage 4 trait generation through the real sleep hook (`maybe_sweep_on_sleep`), then five NEW events (day 5) scored by the real Stage 2 scorer with the identity context filled.
- Model: pinned `gemini-3.1-flash-lite`, normalizer on, raw-reply log on (every prompt, raw reply and delivered text saved). Chat keys 4, 5, 6 rotated (first-key counts 7, 6, 6).
- Caps: router-counted hard cap 40, embeddings at most 60.

## 2. RESULTS (all **live** unless stated)

| Item | Value | Artifact |
|---|---|---|
| Router-counted LLM calls | **19** of cap 40 (5 `consolidation_summary`, 10 `importance_scoring`, 4 `identity_trait`); equals the 19 records in the raw-reply log | `stop3_report.json` (`router_counter`), `raw_replies.jsonl` |
| Tokens by purpose (in / out) | summaries 1,328 / 143; scoring 5,086 / 1,270; traits 1,033 / 139 | `stop3_analysis.json` (`tokens_by_purpose_main_plus_run_db_ledger`) |
| Embedding requests | **10** of cap 60 (HTTP 200 for all 10; 2 cache hits, 29 misses) | `stop3_report.json` (`embedding_stats`) |
| HTTP 429 | **none**. 4 HTTP 503 (Gemini overload): GEMINI_KEY_5 twice and GEMINI_KEY_6 twice, in the Stop 3 process, each absorbed by the router's fall-through (no call failed) | `stop3_stdout.log` |
| Router failures, normalizer | 0 router failures; normalizer applied to 19 calls, changed 0 | `stop3_report.json` |
| Wall time | 238.7 s | `stop3_report.json` |
| Merge-band count (Stage 3 merges at 0.80 to 0.88) | **0**. The three Stage 3 merges had cosines 0.889, 0.9134, 0.8949 | `stop3_report.json` (`merge_band_rows`), `reinforcement_decisions.jsonl` |
| `pivotal_lost` | **0** | `identity_log.jsonl` |
| `self_reinforced` (nights) and `self_reinforced_pivotal` | **0** and **0**. They could not occur: scripted events were not scored with traits, and no night followed the five new events | `reinforcement_decisions.jsonl` |
| Scoring-context rows | 26 `ok`, **0 `unknown`** | `stop3_report.json` (`scoring_context_status_counts`) |
| Identity markers | nights 1 to 4 all `done`, 1 attempt each | `stop3_report.json` (`tables.identity_sweeps`) |

### 2.1 What the four nights did (the fixture's design was not reproduced)

| Night | Stage 3 (real) | Stage 4 decision |
|---|---|---|
| 1 | one cluster of 3 events, entry `node_4` created (summary importance 8) | born, day 1 |
| 2 | **one cluster of 7**: all of night 2's events (baking, letters, the lease event) merged by single linkage at 0.78; merged into `node_4` at cosine **0.889** | counted (>= 0.88), `same_day_max` 7, so `node_4` graduated by the **same_day** path (trait_1); the score-10 lease event graduated by **Path B** (trait_2) |
| 3 | clusters of 5 (conflict) and 3 (cake theme); conflict entry `node_20` created; the cake cluster merged into `node_4` at **0.9134** | `node_20` born with 5 sources, graduated by **same_day** (trait_3); the cake merge counted as a reinforcement of `node_4` |
| 4 | one cluster of 3 (baking), merged into `node_4` at 0.8949 | counted; `node_4` already had a trait, so no count_based trait |

The scripted design expected three separate themes, the cake theme to stay just below the threshold, and a count_based graduation on night 4. None of that happened with real embeddings, the production clustering setting and real Gemini summaries. The two summaries of different themes (baking and the cake theme) both reinforced the same entry above 0.88. Only 4 reinforcement decisions exist, so this shows that the hand-tuned margin did not carry over to these summaries, not how often it fails.

### 2.2 Traits, verbatim, with their sources (**live** generation)

| trait_id | path | text (verbatim) | source |
|---|---|---|---|
| `Isabella Rodriguez:trait_1` | same_day | Isabella Rodriguez demonstrates a deep-seated need to foster communal connection and emotional stability by using her baking as a tool to nurture others and maintain a peaceful environment. | semantic entry `node_4`, summary: "Isabella Rodriguez finds comfort and purpose in the rhythmic, communal act of baking, using her craft to nurture those around her and maintain a sense of harmony within the shop." (distinct counted days 1, 2, 3, 4; `same_day_max` 7) |
| `Isabella Rodriguez:trait_2` | pivotal | Isabella Rodriguez immediately sought to appease the landlord and rally the community, demonstrating her persistent need to preserve harmony and her tendency to prioritize collective stability over processing personal disappointment. | event `node_11`: "Isabella Rodriguez learned that the landlord will not renew the cafe lease" (scripted importance 10) |
| `Isabella Rodriguez:trait_3` | same_day | Isabella Rodriguez consistently demonstrates a deep-seated need to preserve social harmony by reflexively prioritizing the comfort of others over her own needs during moments of conflict. | semantic entry `node_20`, summary: "Isabella Rodriguez instinctively prioritizes the restoration of social harmony over her own comfort by quickly offering concessions to resolve interpersonal friction." (5 sources, night 3) |

Third-person check: all three stored traits pass (`is_third_person`, at most 35 words; word counts trait_1 28, trait_2 30, trait_3 26, from `stop3_analysis.json`). One corrective retry occurred for trait_2: the first raw reply was 38 words (limit 35) and read "Isabella Rodriguez immediately began brainstorming ways to appease the landlord and organize a community petition to save the cafe, demonstrating her deep-seated need to maintain harmony and her tendency to prioritize collective stability over her own emotional processing." The retry produced the stored text. No prompt was tuned.

Observation (no claim about correctness): trait_2 states a reaction ("sought to appease the landlord and rally the community") that the source event does not contain; the wording echoes the Stage 1 priors that sit in the same prompt (for example "reacts to unexpected bad news by trying to immediately fix or soften the situation"). Traits are generated from stated sources plus the priors block, so a trait can carry persona content that the source event lacks. Also trait_1 comes from a 7-event merge of mixed themes (H6), so it describes the mixture.

### 2.3 What the scoring model saw (feed-forward)

The five new events were scored by the real scorer; each saved prompt is in `stop3_report.json` (`new_event_scoring[].prompt`) and `raw_replies.jsonl`. In all five the prompt contained the header and **2 of the 3 active traits** (trait_3 and trait_1); trait_2, the oldest by the cap rule, was dropped by the 120-token cap, and the recorded scoring context lists exactly those two trait ids for all five events. The identity block of the lease-event prompt, verbatim (the full 2,347-character prompt follows the same upstream text and Stage 1 priors block as Phase 5):

```
Traits this agent has developed through experience:
- Isabella Rodriguez consistently demonstrates a deep-seated need to preserve social harmony by reflexively prioritizing the comfort of others over her own needs during moments of conflict.
- Isabella Rodriguez demonstrates a deep-seated need to foster communal connection and emotional stability by using her baking as a tool to nurture others and maintain a peaceful environment.
```

Scores returned (no control run without traits exists, so these say nothing about the effect of traits): greeting customers 3; shaping baguettes 3; neighbor complaint 7; lease notice 9; wiping tables 2. The model's replies were of the form "Rate: N" followed by a paragraph of reasoning; the parser took the first integer. One exact scoring prompt per night is also in `identity_prompt_renders.jsonl` (nights 3, 4 and 5; for nights 3 and 4 these are the summary-scoring calls inside the sweep, which also receive the identity context).

## 3. CONDITIONS COMPLIANCE TABLE (PM verdict on Stop 2 and Stop 3 settings)

| Condition | Status | File | Evidence |
|---|---|---|---|
| Design detail 1: count and report events lost to Path B after 3 failed trait generations | Done | `devmem/memory/identity.py` (`pivotal_lost`, `pivotal_lost_events` in the identity log record) | `test_pivotal_events_lost_after_the_last_attempt_are_counted_and_named`; Stop 3 value 0 |
| Design detail 3 committed as amendment A2 BEFORE any Stop 3 live call | Done | `docs/phase6_preregistration.md` section 9, commit 019f260 | the Stop 3 run started after that commit |
| Q2: keep Stage 3 merge at 0.80; report the 0.80 to 0.88 merge-band count at Stop 3 | Done | n/a | merge-band count 0 (section 2) |
| Stage 3 cosines from Step D, for information | Pending: Step D has not finished | n/a | will be in the Step D report |
| cake_negative observation added to the claims ledger as a Stage 3 limitation | Done | `docs/CLAIMS_LEDGER.md` H6 | n/a |
| Scripted four-night fixture, ONE persona (Isabella), pinned gemini-3.1-flash-lite, normalizer on | Done | `devmem/run_stop3.py` | section 1 |
| Hard cap 40 router-counted calls, CapReached ends the step | Respected | `devmem/run_stop3.py` | 19 calls |
| Embeddings: cache first, at most 60 requests | Respected | `devmem/run_stop3.py` | 10 requests |
| Full raw replies saved (raw-reply log on) | Done | `docs/phase6_stop3_artifacts/raw_replies.jsonl` | 19 records = 19 calls |
| Third-person failure after the corrective retry: report with the raw reply, do not tune prompts | No failure after the retry; the one pre-retry rejection is quoted in 2.2 | n/a | `stop3_analysis.json` |
| Run concurrently with Step D; each process its own counter; report any 429 with key and process | Done: 0 HTTP 429 in the Stop 3 process (4 HTTP 503 listed above) and 0 in the Step D process so far; Step D caps unchanged | n/a | `stop3_stdout.log`; Step D log |
| Report: traits verbatim with sources, rendered prompt with traits, whether the prompt contained them, merge-band, `pivotal_lost`, self-reinforced counts, calls and tokens by purpose; no behavioral claim | Done | this report | sections 2.1 to 2.3 |
| Claims ledger updated: Stage 4 rows, baseline asymmetry, Path B at the night step, 0.88 limit, cake_negative | Done | `docs/CLAIMS_LEDGER.md` D9, G16 to G19, H4 to H7 (H2, Path B at the night step, already present and unchanged) | n/a |

## 4. DEVIATIONS (complete)

- **Ledger split (H7).** `score_importance_persona_conditioned(db_path=...)` forwards `db_path` to `call_llm` as the router ledger path. The Stop 3 script passed the run database for the five new-event scoring calls, so their rows (and key-usage counts) are in the run's `memory.db`, not in `devmem/router/usage_log.db`. The first version of the report script therefore showed 5 scoring calls where 10 were made; `devmem/memory/p6_stop3_analysis.py` combines both ledgers (10 scoring calls, equal to the router counter and the raw-reply log). Simulation runs are not affected (`perceive.py` passes no `db_path`). I did not change the scorer.
- New purpose string `identity_trait` in the ledger (disclosed at Stop 2).
- New files: `devmem/run_stop3.py`, `devmem/memory/p6_stop3_analysis.py`, `docs/phase6_stop3_artifacts/`. Modified: `devmem/memory/identity.py` (pivotal_lost), `devmem/memory/test_identity.py` (one test), `docs/phase6_preregistration.md` (A2), `docs/CLAIMS_LEDGER.md`.
- Runtime artifacts: none left (no `ReverieServer` was started; the run database lives in `devmem/storage/`, which is git-ignored, and a copy is in the artifacts).
- Gemini chat keys 4, 5, 6 were shared with Step D (as instructed); this run used 19 requests spread over them.

## 5. TESTS

Full suite re-run after the `pivotal_lost` change (offline default); output in `docs/phase6_stop3_artifacts/full_suite_output.txt`, verbatim:

```
=== devmem.router.test_router
Ran 33 tests in 4.303s
OK
=== devmem.router.test_call_counter
Ran 4 tests in 1.537s
OK
=== devmem.router.test_output_normalizer
Ran 4 tests in 0.000s
OK
=== devmem.router.test_normalizer_wiring
Ran 8 tests in 3.119s
OK
=== devmem.router.test_normalizer_rule
Ran 9 tests in 0.383s
OK
=== devmem.router.test_normalizer_call_path
Ran 7 tests in 5.434s
OK
=== devmem.memory.test_priors
Ran 9 tests in 2.229s
OK
=== devmem.memory.test_episodic
Ran 10 tests in 1.403s
OK
=== devmem.memory.test_reconcile
Ran 10 tests in 61.676s
OK
=== devmem.memory.test_gpt_structure_touch
Ran 5 tests in 0.032s
OK
=== devmem.memory.test_consolidation
Ran 27 tests in 8.872s
OK (skipped=1)
=== devmem.memory.test_identity
Ran 36 tests in 77.321s
OK
=== devmem.embeddings.test_vector_store
Ran 14 tests in 1.542s
OK (skipped=1)
=== devmem.demo.test_demo
Ran 2 tests in 0.009s
OK
```

Count: 178 tests, 2 live-gated skipped (177 at Stop 2 plus the `pivotal_lost` test).

## 6. RAW ARTIFACTS (`docs/phase6_stop3_artifacts/`)

`stop3_report.json` (all tables, the saved prompts, counters), `raw_replies.jsonl` (full prompt, raw reply and delivered text of all 19 calls), `stop3_analysis.json` (offline recomputation: calls and tokens by purpose from both ledgers, per-prompt trait inclusion, trait word counts), `identity_log.jsonl`, `reinforcement_decisions.jsonl`, `consolidation_log.jsonl`, `identity_prompt_renders.jsonl`, `embedding_stats.json`, `stop3_stdout.log`, `full_suite_output.txt`. The run database `memory.db` (copied beside them) is not committed because `*.db` is git-ignored; every table it holds is in `stop3_report.json`.

## 7. SCRIPTED VS LIVE

Live: every summary, summary score, trait and new-event score, and every embedding. Scripted: the fixture events, their importance values (so the pivotal graduation came from a scripted 10, not a model score) and the five new event texts.

## 8. JUNIOR DEVELOPER TASKS

None.

## 9. OPEN QUESTIONS

1. The fixture's themes did not stay separate under production clustering (cluster 0.78, single linkage), and real summaries of different themes reinforced one entry above 0.88. This is a result about the fixture and these four decisions, not about natural runs. Does the PM want a follow-up checkpoint on it (for example, how Stage 4 behaves on Step D's natural Stage 3 summaries, offline), or is it left as the limitation recorded in H5, H6 and G16?
2. Trait text can contain persona-prior content that its source event lacks (trait_2). The spec makes no claim that traits are correct; is a ledger note enough, or should a grounding check be considered later?
3. H7: fix the scorer's `db_path` forwarding (a devmem-only change) or leave it documented?
4. Step D is at simulated 07:30 on day 1 (145 router calls, 13 embedding requests at the last check). It will take hours of wall time; its report comes when it ends.

REQUEST: Review of Stop 3 and answers to the questions above. Halting.
