PHASE: 5, follow-up round after the Step 1a verdict (tasks A to F)
STATUS: Partially complete. A, B, C, D done. E ran but is **partial** (it hit its 100-call cap inside step 0; 0 steps completed). F (1-hour baseline measurement) was **not run**, held for your decision (reasons in Section 6).

Stage 3 status label, as instructed: **implemented and verified on scripted data**. It has not completed a live simulated step.

Paths are relative to the repo root. `ART/` = `docs/phase5_step2_artifacts/`. Labels: **live**, **scripted**, **offline-captured** (rebuilt from saved run data and cached vectors, no network), **synthetic**.

---

## 1. Verdict conditions

- `cooldown_state.json` added to `.gitignore` (also `reverie/environment/frontend_server/storage/p5_*` for smoke-run folders).
- Status label as above. Both scripted runs (0.78 default and 0.82) stay in the record; **threshold not frozen**, default stays 0.78.
- **New keys** (names only). Present in `.env`: `GROQ_KEY_1` to `GROQ_KEY_5`, `GEMINI_KEY_1` to `GEMINI_KEY_4`, `NIM_KEY_1`, `NIM_KEY_2`. New this round: `GROQ_KEY_4`, `GROQ_KEY_5`, `GEMINI_KEY_4`, `NIM_KEY_2`. One minimal call each (LLM `max_tokens` 5; Gemini also one embed call), status codes only (`ART/key_verification.json`, **live**):

| Key | Call | Status |
|---|---|---|
| GROQ_KEY_4 | LLM, 5 tokens | 200 |
| GROQ_KEY_5 | LLM, 5 tokens | 200 |
| NIM_KEY_2 | LLM, 5 tokens | ReadTimeout (45 s), then 200 on one retry |
| GEMINI_KEY_4 | LLM, 5 tokens | 200 |
| GEMINI_KEY_4 | embed | 200 |

All four were added to `providers.yaml` (`GEMINI_KEY_4` for chat as well) and `GEMINI_KEY_4` to `embeddings.yaml` (now `GEMINI_KEY_1`, `GEMINI_KEY_3`, `GEMINI_KEY_4`). None returned 401 or 403. Verification calls: **7** (reported separately from the caps below). `GEMINI_KEY_2` is still excluded from embeddings.
- **New summarization prompt (deviation from the plan's template), verbatim.** The persona context block (the priors) comes first, then:
```
The following are related observations about {agent_name}, recorded today:
{cluster_entries}

Write ONE sentence, in the third person, that names {agent_name} and states the underlying pattern or takeaway
these related observations show about {agent_name}.
```
System prompt: `Reply with exactly one sentence and nothing else: no preamble, no list, no explanation. Write in the third person and use the person's name; never use I, me, my or we.`
New check `is_third_person` (the summary must contain the agent's full or first name and no I/me/my/mine/myself/we/our). A violating reply gets one corrective retry (`summary_retries: 1` in config, suffix: `Your previous reply was: "..." That is not acceptable: it must be written in the third person and name {agent_name}. Reply with one corrected sentence only.`); still wrong means a counted failure and no semantic memory. `kind="event"` scoring is kept.

---

## 2. A. Retrieval diagnosis (offline-captured, zero network, zero LLM)

Method: `devmem/memory/p5_diagnose_retrieval.py` rebuilds each saved scripted run (events and semantic rows from its SQLite DB, vectors from the persistent cache with network disabled, so a cache miss would have raised) in a real Persona, then calls the real `new_retrieve` with the same three focal points, capturing recency, importance and relevance before and after `normalize_dict_floats`. **Check:** the rebuild reproduces all 12 saved summary ranks (2 runs x 3 focal points x 2 weights, summary ranks) exactly; 0 network requests. Raw: `ART/diag_retrieval_threshold_*.json`, tables in `ART/diag_retrieval_tables.md`.

Findings from those numbers (the first-person summaries, the runs the Step 1a report described):
1. **Relevance is the main driver for the conflict summary (node_18).** Its raw cosine to the three focal points was 0.603, 0.674 and 0.517 (run A) and 0.572, 0.611 and 0.525 (run B), the lowest of the 15 ranked nodes in 5 of 6 cases (normalized relevance **0.000**, i.e. 0 of the 3.0 relevance points) and 0.169 in the sixth. The top-3 events in the same tables had cosines of 0.65 to 0.93. Its text was first person ("When a conflict arises, I should ..."), the focal points third person about "Isabella".
2. **Importance:** node_18 was scored 2 in run A (normalized 0.000) and 6 in run B (0.8, worth 1.6 of 2.0 points). In run B it still ranked 9 to 15 because relevance and recency were 0.
3. **Recency is inverted in this code path.** `extract_recency` assigns `decay**i` in ascending `last_accessed` order, so the oldest node gets the highest value. In the first focal point (distinct timestamps) normalized recency fell with creation time: 10:20 event 0.707, 10:35 event 0.635, 16:45 event 0.139, the 22:00 summary nodes 0.000 to 0.069. A newly written summary therefore starts with the lowest recency. For the second and third focal points `last_accessed` had been set equal by the first, so recency follows list order, which for events is insertion order newest first (the 07:10 event, inserted 13th, got 1.000). I did not edit anything; any change to retrieval needs its own approval.
4. Combined effect: summary nodes get 0.0 to 0.07 of 0.5 recency points, so they rank high only when relevance and importance are both high (node_17 baking summary, run B: relevance 1.000, importance 7, rank 1).

What this does not show: that third-person wording fixes it (task D gives the only evidence, below), or how this behaves on real simulation memory.

---

## 3. B. Average-linkage option (offline-captured, cached vectors, 0 network)

New config key `linkage` (`single` default, `average`) in `config/consolidation.yaml`, parameter of `cluster_by_similarity`; the sweep reads it and logs it. Average linkage is agglomerative on mean pairwise cosine (ties: lowest indices first), deterministic. Default unchanged. Raw: `ART/linkage_comparison.json`, script `devmem/memory/p5_linkage_compare.py`. Same filters as the sweep (importance at least 3, no "idle"): 12 eligible events.

| linkage @ threshold | cluster-size histogram (size: count) | multi-member clusters |
|---|---|---|
| single @ 0.78 | {1:1, 4:1, 7:1} | baking 5 + letter + latch; conflict 4 |
| single @ 0.82 | {1:3, 4:1, 5:1} | baking 5; conflict 4 |
| average @ 0.78 | {1:2, 4:1, 6:1} | baking 5 + latch; conflict 4 |
| average @ 0.82 | {1:3, 4:1, 5:1} | baking 5; conflict 4 |

The full scan is in the artifact. On this one scripted day: single linkage is clean only at 0.82 to 0.83; average linkage is clean at 0.80 to 0.82, and at 0.78 it absorbs one off-topic event instead of two. Average linkage splits the conflict cluster at 0.83 and above. One day, 12 events, not evidence for the real simulation.

---

## 4. C. The sleep hook inside the real `persona.move()` (scripted, no network)

`test_consolidation.py` class `TestSleepHookInsideRealMove` (2 tests, both OK). The real `Persona.move()` runs; only `perceive`, `plan` and `execute` are replaced (the plan stub sets `act_description = "sleeping"` and returns a bed address). In staged mode the hook is reached inside `move()` at the first call: the real sweep runs (LLM and scorer patched), writes 1 semantic row and 1 marker; five further `move()` calls the same night add nothing (LLM called once). In baseline mode `move()` never reaches the hook (0 LLM calls, 0 marker rows). This is the first test that executes the `persona.py:239-243` lines.

---

## 5. D. Scripted sweep re-run with the third-person prompt (scripted events, live embeddings, live LLM)

Pinned `openai/gpt-oss-20b`; **8 LLM calls** (cap 20); 0 retries were needed; no failures. Raw: `ART/scripted_sweep_threshold_0_78_default_third_person.json`, `..._0_82_calibrated_third_person.json`.

**Run A, threshold 0.78 (default).** Histogram {1:1, 4:1, 7:1}, 11 entries flagged.
- node_17, importance 4. Summary: "Isabella Rodriguez demonstrates a pattern of proactive, community‑oriented multitasking, balancing culinary duties with personal care and maintenance to support both her coworkers and customers." Sources: croissants; kneading dough; fresh bread from the oven; decorating cupcakes for a customer's order; reading a letter from her sister who lives in another city; cookie dough for the afternoon rush; fixing a loose latch on the cafe's back window (all "Isabella Rodriguez is ...").
- node_18, importance 2. Summary: "Isabella Rodriguez tends to smooth over conflicts by apologizing and offering compensation, prioritizing harmony even when she feels tense." Sources: "A neighbor shouted at Isabella Rodriguez about the noise coming from the cafe"; "Isabella Rodriguez argued with her neighbor about the late-night noise"; "Isabella Rodriguez apologized to the upset neighbor and offered free coffee"; "Isabella Rodriguez felt tense after the dispute with her neighbor".

**Run B, threshold 0.82.** Histogram {1:3, 4:1, 5:1}, 9 entries flagged.
- node_17, importance 4. Summary: "Isabella Rodriguez consistently prepares a variety of baked goods at Hobbs Cafe, demonstrating her dedication to her craft and her role as a reliable baker." Sources: the five baking events.
- node_18, importance 4. Summary: "Isabella Rodriguez consistently prioritizes harmony by smoothing over conflicts and offering conciliatory gestures, even though it leaves her feeling tense." Sources: the same four conflict events.

All four summaries are third person and name the agent; second sweep: hook returned `None`, direct call `{"skipped": "already swept", "night": 1}`.

**Summary ranks of 15 (weight 0.5), neighbor argument / conflict handling / baking:**

| Run | node_17 (baking) | node_18 (conflict) |
|---|---|---|
| A (0.78) | 9 / 4 / 1 | 11 / **1** / 15 |
| B (0.82) | 13 / 10 / 1 | 7 / **1** / 15 |

The conflict summary is now first for the conflict-handling query in both runs and the baking summary is first for the baking query in both. For the neighbor-argument query the conflict summary ranked 11 and 7, not near the top. Single runs; the model's summary wording differs between runs and I did not isolate the cause of the change from the first-person runs (importance also changed from 2 and 6 to 2 and 4). The summaries still echo the priors text ("harmony", "smooth over", "tense"); no control run, so no causal claim.

---

## 6. E. Live staged smoke (live; **partial**)

Command: `devmem/run_live_smoke.py --mode staged --steps 6 --llm-cap 100 --embed-cap 60`, fresh fork from 00:00, pinned `openai/gpt-oss-20b`, `fail_loud_llm` on, agent tagging on. Raw: `ART/p5_staged_smoke_report.json`, `_consolidation_log.jsonl`, `_embedding_stats.json`.

| Item | Result |
|---|---|
| Stop reason | **LLM call cap 100 reached during step 0**; steps completed 0; clock still 00:00:00; wall time 612 s |
| Embedding requests | 10 (cap 60) |
| `ROUTER_FAILURES` | count 0 |
| 429s | transient per-minute Groq 429s were handled by the router (visible in the log); none became failures |
| Models/conditions in the ledger | only `openai/gpt-oss-20b`, only `staged` |
| `consolidation_sweeps` rows | Isabella Rodriguez: night 0, `done`, attempts 1; Maria Lopez: night 0, `done`, attempts 1; **none for Klaus Mueller** (cap reached before his move) |
| Sweep content | both sweeps logged `entries_considered: 0`, 0 summaries (nothing to sweep, as expected) |
| `schedule_check.json` | **not produced and not evidence.** The final save failed (`AttributeError: 'NoneType' object has no attribute 'strftime'`: the run was stopped mid-step, so Klaus's scratch clock was unset), so the saved-schedule scan never ran. The report's empty `schedule_check_findings` list means "not scanned", not "clean". |
| Ledger by agent (tagging works) | Isabella 39 calls, Maria 51, Klaus 10 |
| Ledger by purpose | planning 98 calls (87,389 in / 130,951 out), dialogue 2 calls (754 / 127) |

So the hook did fire inside a live step 0 for two agents, with nothing to sweep and no failure, but E did not meet its "6 steps" scope: the first-day planning burst for 3 agents alone needs more than 100 calls (about 218K tokens for the first 2.5 agents' worth). I stopped at the cap as instructed.

**F was not run.** Reasons: (1) E shows day-start planning alone consumes roughly 100 to 130 calls for 3 agents, so F's cap of 300 would leave about 170 to 200 calls for the simulated hour and would likely stop before the hour ends, giving data dominated by day-start planning; (2) E took 612 s for 100 calls, so F would take roughly 30 to 40 minutes and use on the order of 650K tokens of the pinned model's quota; (3) the stop condition for E was not met. Keys are healthy (0 router failures). I need your decision: run F as specified, raise its caps, or start the measured hour from a saved post-planning state so planning cost is not mixed into the hour.

---

## 7. Compliance table

| Item | Status | File and line | Proof |
|---|---|---|---|
| `cooldown_state.json` in `.gitignore` | Done | `.gitignore` | `git status` |
| New keys verified (names and status only), config updated, verification calls reported separately | Done, 7 calls | `providers.yaml`, `embeddings.yaml` | `ART/key_verification.json` (live) |
| Threshold not frozen, both runs kept | Done | `config/consolidation.yaml:7` | `ART/scripted_sweep_*` |
| Third-person prompt, verbatim, as deviation | Done | `consolidation.py` (`SUMMARIZATION_PROMPT_TEMPLATE`, `is_third_person`) | `test_first_person_reply_gets_one_corrective_retry...`, `test_is_third_person`, D runs |
| A. component diagnosis, zero LLM | Done | `p5_diagnose_retrieval.py` | `ART/diag_retrieval_*`, reproduces 12 of 12 ranks |
| B. `linkage` key, default single, histograms at 0.78 and 0.82 | Done | `consolidation.py` `cluster_by_similarity`, `config/consolidation.yaml:11` | `ART/linkage_comparison.json`, `test_average_linkage_...`, `test_default_linkage_is_single_in_config` |
| C. real `persona.move()` reaches the hook, no network | Done | `persona.py:239-243` | `TestSleepHookInsideRealMove` (2 tests) |
| D. re-run at 0.78 and 0.82, cap 20 | Done, 8 calls | `scripted_sweep.py` | `ART/scripted_sweep_*_third_person.json` |
| E. staged smoke, caps 100 and 60, report ROUTER_FAILURES, schedule_check, sweeps | **Partial**: cap hit in step 0, 0 steps, schedule scan not run | `run_live_smoke.py` | `ART/p5_staged_smoke_*` |
| F. 1-hour baseline measurement | **Not run, awaiting decision** | n/a | Section 6 |
| Minimal `reverie/` edits, listed | **No `reverie/` source edit this round**; the persona hook, reflect gate, retrieve weight and `gpt_structure` edits are unchanged since `c3733ab` | Section 8 | `git status reverie` |

---

## 8. Deviations (complete)

1. **New summarization prompt** (Section 1). 
2. **Router edit:** `devmem/router/llm_router.py` in `call_llm`, 3 added lines before `providers = load_providers_config(...)`: if `agent_id` is `None`, read it from `devmem/router/agent_context.py` (new, a `ContextVar`). `HeadlessRunner._tag_agents` sets it around each persona's `move()` (instance attribute wrapper, no upstream file touched). Test: `test_persona_move_runs_with_agent_tag_for_ledger_logging`; live evidence: the ledger by agent in Section 6.
3. **New files:** `devmem/router/verify_new_keys.py`, `devmem/router/agent_context.py`, `devmem/run_live_smoke.py`, `devmem/memory/p5_diagnose_retrieval.py`, `p5_diagnose_summary.py`, `p5_linkage_compare.py`, `docs/phase5_step2_artifacts/`. Edited: `consolidation.py`, `consolidation.yaml`, `scripted_sweep.py` (CLI arguments for artifact folder and tag), `run_headless.py`, `providers.yaml`, `embeddings.yaml`, tests.
4. **Bug in my smoke script, fixed:** output paths were relative and the runner `chdir`s into `reverie/reverie/backend_server`, so the three output files landed in a new `docs/` folder there. I moved them to `ART/` and removed the stray folders; no tracked `reverie/` file was changed.
5. **A stray live embedding request, found and fixed:** my fail-loud routing test blanked only `GEMINI_KEY_1` to `_3`; after `GEMINI_KEY_4` was added to the config, the test made one real request on it and cached the vector (so the test then failed). The test now blanks whatever keys the config lists and uses a unique text; I deleted that one cache row. Cost: 1 embedding request on `GEMINI_KEY_4`.
6. **Runtime artifacts:** the smoke run rewrote the tracked `temp_storage/curr_sim_code.json` and created `curr_step.json`; restored and deleted. `reverie/environment/frontend_server/storage/p5_staged_smoke/` (the smoke run folder, with partial state) is untracked and now git-ignored. `devmem/router/fixtures/429/observed.jsonl` (a tracked fixture) was appended by the router's passive 429 capture during the smoke run (real 429s, label **captured**); I will commit it as such.
7. **Counts for the record:** verification 7 calls; D 8 LLM calls; E 100 LLM calls and 10 embedding requests (plus the tests: 1 stray, above). Embedding requests recorded in the router ledger today (all uses, since the store counts them): `GEMINI_KEY_1` 16, `GEMINI_KEY_3` 13, `GEMINI_KEY_4` 5.
8. **Not demonstrated:** a completed live step with Stage 3; the saved-schedule scan on a real run; F.

---

## 9. Tests

Full suite, offline default (`ART/full_suite_output_offline_default.txt`), verbatim:

```
=== devmem.router.test_router
Ran 33 tests in 3.367s
OK
=== devmem.memory.test_priors
Ran 9 tests in 1.839s
OK
=== devmem.memory.test_episodic
Ran 10 tests in 1.444s
OK
=== devmem.memory.test_reconcile
Ran 8 tests in 27.494s
OK
=== devmem.memory.test_gpt_structure_touch
Ran 5 tests in 0.026s
OK
=== devmem.memory.test_consolidation
Ran 27 tests in 7.129s
OK (skipped=1)
=== devmem.embeddings.test_vector_store
Ran 14 tests in 1.209s
OK (skipped=1)
```
106 tests (up from 99), 2 live-gated skipped. New this round: 6 in `test_consolidation.py` (linkage, third person, hook inside `move()`), 1 in `test_reconcile.py` (agent tag).

---

## 10. Open questions for higher authority

1. F: run as specified (cap 300 LLM calls, 150 embeddings), raise the caps, or start the hour from a saved post-planning state? I recommend the last, so the hour is not mixed with day-start planning (about 100 to 130 calls).
2. E: rerun with a higher cap (about 200 calls) so step 0 completes and all three agents' hook rows and the schedule scan can be shown? Or accept the partial result?
3. The final save after a mid-step stop fails. Do you want the smoke script to skip the save in that case (current behavior reports the failure), or should the stop happen only at step boundaries?
4. Recency in `new_retrieve` is inverted (oldest node highest). It affects how freshly consolidated summaries compete. Do you want a separate checkpoint on that, or leave upstream retrieval as is?

REQUEST: Approval of A to D and the partial E, and a decision on F and the questions above. Halting here.
