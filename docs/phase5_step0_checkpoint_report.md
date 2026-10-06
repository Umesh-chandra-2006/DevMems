PHASE: 5, Step 0 (prerequisites P5.0a to P5.0d and decision checkpoint D1 to D7)
STATUS: Partially complete. P5.0a done. P5.0b done except the local-model timing and the batch-quota question (both need approval, see Section 6). P5.0c and P5.0d done as read-only and derived work. D1 to D7 surfaced, none implemented. This is STOP 1.

All paths are relative to the repo root. Artifacts are in `docs/phase5_step0_artifacts/` (called `ART/` below).

---

## 0. Orientation note (CLAUDE.md Section 9)

- HEAD is `71cfd8f` (Phase 4 episodic). **The working tree is not clean.** The M1 series (router changes, 429 classifier, cooldown, fixtures, `providers.yaml`, the Phase 4 result JSONs, and `docs/technical_implementation_plan.md` Rev 2.2) is uncommitted: 7 modified and about 13 untracked files. CLAUDE.md and the plan say these were approved and closed, but there is no commit for them. I made no commits. I recommend one commit of that approved work before Phase 5 code lands, so the Phase 5 diff is reviewable. Please confirm.
- Tests at start: router 33, priors 9, episodic 10, all OK. This matches CLAUDE.md.
- `GEMINI_KEY_2` returns HTTP 403 on the embeddings endpoint (Section 2). This is not in CLAUDE.md. Only one Gemini embedding project is usable today.
- The existing priors and episodic test modules make live Gemini embedding calls when keys are set: about 20 per full-suite run (Section 2.4). This is not in CLAUDE.md and it consumes the embedding budget.

---

## 1. WHAT WAS BUILT

| File | Lines | What |
|---|---|---|
| `devmem/memory/episodic.py` | 465-537 | `reconcile_mirror(agent_id, live_node_ids, live_descriptions, ...)` and `reconcile_run(personas, ...)`. Appended; nothing existing edited. |
| `devmem/run_headless.py` (new) | 1-126 | `HeadlessRunner`. Autosave interval from `config/runner.yaml` (default 60 simulated minutes = 360 steps at 10 s/step) and on clean exit. An exception propagates with no final save (crash semantics). `resume=True` reopens a saved run in place. It purges stale `environment/` and `movement/` step files beyond the saved step, then reconciles the mirror. |
| `devmem/config/runner.yaml` (new) | all | `autosave_interval_sim_minutes: 60` |
| `devmem/memory/test_reconcile.py` (new) | 1-end | 5 tests, all `scripted`. Real `AssociativeMemory`, real `Persona`, real `ReverieServer`, real SQLite. |
| `devmem/embeddings/vector_store.py` | 1-239 | `EmbeddingStore`: fail-loud mode, on-disk cache keyed by (model, sha256(text)), `embedding_stats.json`, single and batch Gemini requests, key in the `x-goog-api-key` header (never in a URL), key rotation, and a guard so fallback and real vectors are never mixed (including cached real plus fallback in one call). Fallback is allowed only with `allow_fallback=True`. |
| `devmem/config/embeddings.yaml` (new) | all | model, key envs, `fail_loud: true`, cache path |
| `devmem/embeddings/test_vector_store.py` (new) | 1-end | 10 offline tests. The HTTP layer is an injected fake, so these are `synthetic`. |
| `devmem/embeddings/p5_0b_probe.py` (new) | all | The `live` probe, hard-capped by design at 3 requests (4 were sent, see Section 2). |
| `devmem/memory/p5_0d_ledger_analysis.py`, `p5_0d_cost_estimate.py`, `p5_0_pairwise_cosine.py` (new) | all | Scripts that produced the ledger and cost artifacts. |

**`reverie/` was not edited.** `git status --short reverie` is empty after all runs. `run_headless.py` imports `run_baseline_sim.step_environment_bridge` and, for `resume`, temporarily neutralises `reverie.copyanything` in memory only. `upstream get_embedding` is deliberately NOT wired to `vector_store` (that is a `gpt_structure.py` edit; see D5).

---

## 2. P5.0a and P5.0b results

### P5.0a Runner autosave and mirror reconciliation (scripted)

The crash-and-reload scenario is `test_autosave_interval_and_crash_reload`. It runs steps 0 to 7 (autosave at k = start+6), crashes on step 8, reloads the autosave in place, then replays.

| Check | Result |
|---|---|
| Autosave fires at the interval only; none on the exception | asserted: `autosave_steps == [k0+6]` |
| Reloaded memory has save-k node count | asserted for every persona |
| Orphan rows for steps 6 and 7 removed | asserted: 2 per agent, rows after = 6 |
| Rows at or before k unchanged | asserted (set equality with the pre-reload snapshot) |
| Stale `environment/` and `movement/` files purged | asserted: `environment/{k+7,k+8}.json`, `movement/{k+6,k+7}.json` |
| Second reconcile is a no-op | asserted |
| Replay with different content: no collision, mirror equals live memory exactly | asserted |
| Clean exit saves | asserted |

Control test: `test_stale_row_without_reconcile_would_collide` shows the failure being fixed. Without reconciliation, `INSERT OR IGNORE` keeps the stale row and the replayed content is lost.

New finding: `environment/{j}.json` files from a crashed run were also stale state. The headless bridge skips files that already exist, so replay would have used old positions. The runner now purges them.

Not done, because the tables do not exist yet: semantic rows and sweep markers (see D6 and D7 for how the same rule will cover them).

### P5.0b Embedding policy (live where marked)

**2.1 Probe (live).** Raw: `ART/p5_0b_probe_results.json`, `ART/embedding_stats_p5_0b_probe*.json`, `ART/p5_0b_vectors_7texts.json`.

- Run 1 used both keys. Call 1, a batch of 7 on `GEMINI_KEY_1`, returned 200. Call 2, a batch of 50 on `GEMINI_KEY_2`, returned **HTTP 403** (`ART/embedding_stats_p5_0b_probe_run1_key2_403.json`). Fail-loud raised as designed. I do not know why key 2 is rejected; I did not inspect the response body and did not retry blindly.
- Run 2 used key 1 only. The batch of 7 came from cache. The batch of 50 returned 200 in 18.1 s. A single-text request for the focal point returned 200 in 1.3 s.
- All vectors are **3072-dimensional**. The single-request and batch vectors for the same text have cosine 1.000000. The batch of 50 was accepted. I did not test larger batches.
- Live embedding HTTP requests sent by the probe: 4 (3 returned 200, 1 returned 403).

**2.2 Does a batch count as one request against the 1,000 RPD limit? Unresolved.**
- The Gemini embeddings documentation page that I fetched does not state it (documented: silent on this).
- A client cannot read the quota counter, and 10 calls cannot approach 1,000.
- Proposed decisive test (1 live call, within the cap): you read the RPD counter for the `GEMINI_KEY_1` project in AI Studio, I send one batch of 50 new texts, you read it again. A delta of 1 means per request. A delta of 50 means per text. The counter today also includes the incidental test-suite calls from this session, so only a before/after pair around a single call is clean.
- Practical note either way: upstream embeds one text at the moment it is needed (perceive, new_retrieve), so most embedding traffic cannot be batched.

**2.3 Local model feasibility (documented, not measured).** Raw: `ART/pypi_wheel_sizes.json` (PyPI JSON metadata).
- The latest `sentence-transformers` (6.1.0), `torch` (2.14.1), `fastembed` (0.8.1) and `onnxruntime` (1.30.0) all declare `requires_python >= 3.10` (onnxruntime >= 3.11). `.venv` is Python 3.9.25. So a local model is **not installable in the pinned environment as it stands**.
- Whether older 3.9-compatible releases exist and fit the pinned numpy 1.25.2 is **unverified**.
- A separate interpreter exists on the machine (system Python 3.13.3). Install size, time to embed 100 texts and dimension are **not measured**. I did not download anything. Measuring requires a download of several hundred MB of wheels plus a model (I would state exact filenames and sizes when asking). See Section 6.

**2.4 Retrieval reproduction (live vectors and scripted fallback).** Phase 3 focal point: "Isabella has a disagreement and potential confrontation with a neighbour". Raw: `ART/p5_0b_probe_results.json`. Cosine to the focal point:

| Prior | gemini-embedding-001 | deterministic fallback (768-d) |
|---|---|---|
| 5 (community should look out for one another) | 0.6348 (rank 1) | 0.0169 (rank 2) |
| 2 (avoids confrontation) | 0.6197 (rank 2) | -0.0697 (rank 6) |
| 6 (fix or soften bad news) | 0.5973 (rank 3) | -0.0675 (rank 5) |
| 4 (harmony above honesty) | 0.5576 (rank 4) | 0.0771 (rank 1) |
| 3 (seeks company) | 0.5431 (rank 5) | 0.0062 (rank 3) |
| 1 (trusts strangers) | 0.5285 (rank 6) | -0.0388 (rank 4) |

Spearman rank correlation of fallback versus Gemini: **-0.086** (n = 6). The fallback does not preserve the ranking; it behaves as noise. The local-model column is **not measured**. This is the only retrieval comparison I ran, with one focal point and six items. It shows the fallback is unusable for retrieval; it says nothing about how a local model would rank.

Ranking preserved? Gemini: yes by definition (it is the reference). Fallback: no. Local: unknown.

**2.5 Live embedding budget accounting.** Spec caps: 50 embedding calls total, 40 for the reproduction test.
- The existing tests call upstream `get_embedding` against the live endpoint. I counted calls per module with a fake key and a stubbed `requests.post` (no network): priors 14, episodic 6, reconcile 0 (`ART/count_embed_calls.py`, `ART/count_embed_calls_output.jsonl`, `synthetic` run of real test code).
- The orientation runs (priors twice, episodic once) therefore sent **at most 34** live calls (an upper bound; I did not log which succeeded).
- The probe sent 4. Total: **at most 38 of 50**.
- To stay under the cap I ran the final full suite with `GEMINI_KEY_1` and `GEMINI_KEY_2` blanked. Those runs used the deterministic fallback and spent 0 live embedding calls. All tests still pass on the fallback, which means the real-class integration tests cannot detect fallback use. A normal run would have pushed the total to about 58, over the cap.
- Live LLM calls in Step 0: **0** (cap 10).

**2.6 Embeddings per simulated hour and day (derived).** Call sites (code-read): `perceive.py` embeds each new event description (cached by description in `a_mem.embeddings`); chats embed `act_description` (perceive.py:175); `new_retrieve` embeds each focal point (`retrieve.py:189`) and is called from converse.py, plan.py:413 and reflect.py:113; thoughts embed once each (plan.py:510, reflect.py:128/224/240, converse.py:251/288). Upstream per-step `retrieve()` is keyword-based and uses no embeddings.
- Assumption: 10 to 25 unique new texts per agent-hour (events, object events, focal points). That gives about 480 to 1,200 requests per simulated day for 3 agents. This is **unmeasured**; no run has covered more than a few simulated seconds. The persistent cache should make a second condition on the same events mostly cache hits.
- Capacity: one working Gemini project means 1,000 RPD. A day at the upper assumption could hit it.

**2.7 Data on hand (captured).** `ART/embedding_dims_survey.json` covers every saved `embeddings.json` in storage: 7,335 vectors at 1536 dims (OpenAI ada precomputed in `base_the_ville_n25`; not used by the 3-agent fork), 25 at 3072 (real Gemini), 0 at 768. The saved Phase 2 run contains no fallback vectors.

---

## 3. P5.0c Sleep discovery (read-only, verbatim code)

**How sleeping is represented.** There is no sleep flag or event. It is the action description string.
1. The hourly schedule is built with `"sleeping"` entries for the wake-up hours, then LLM-written hours (`plan.py:103-106`):
```
 104:         if wake_up_hour > 0: 
 105:           n_m1_activity += ["sleeping"]
 106:           wake_up_hour -= 1
```
2. Sleep entries are never decomposed (`plan.py:545-552`):
```
 545:     if "sleep" not in act_desp and "bed" not in act_desp: 
 546:       return True
 547:     elif "sleeping" in act_desp or "asleep" in act_desp or "in bed" in act_desp:
 548:       return False
 549:     elif "sleep" in act_desp or "bed" in act_desp: 
 550:       if act_dura > 60: 
 551:         return False
```
3. A filler sleep block pads the schedule to 1,440 minutes (`plan.py:606-613`; it appends `1440 - x_emergency` minutes of "sleeping" whenever `_determine_action` runs).
4. The action becomes current in `Scratch.add_new_action` (`scratch.py:498-514`): `self.act_description = action_description` and `self.act_start_time = self.curr_time`. Note that `act_path_set = False` (`scratch.py:516`): the agent has not yet walked to the bed.
5. The bed-object event is added only on arrival, when `planned_path` is empty (`reverie.py:354-360`).
6. Sleeping blocks chats and reactions (`plan.py:722-724` and `753-755`: `"sleeping" in ...act_description` returns False).

**Captured evidence** (`reverie/environment/frontend_server/storage/baseline_validation_run/personas/*/bootstrap_memory/scratch.json`, saved Phase 2 state):
- All three agents end with `act_description: "sleeping"` and `act_address` ending in `:bed` (Klaus's ends in `:desk` with `planned_path` length 3).
- Isabella's `f_daily_schedule_hourly_org` has 17 consecutive entries that are all sleeping (`sleeping` 360, then 16 entries whose text contains "is sleeping").
- Maria's and Klaus's schedules contain `"TOKEN LIMIT EXCEEDED"` and `"Here are the completed entries for the user"` as activity strings. The string comes from upstream's fail-safe in `GPT_request` (`gpt_structure.py:341`), which now masks every router exception, not only token limits. See Section 7 (Observations).

**Answers.**
- *Earliest reliable signal:* the moment a new action is added whose `act_description` contains "sleeping" or "asleep". Hook point: `persona.move()` right after `self.plan(...)` (`persona.py:238`), so it covers all paths. Physical arrival at the bed (`reverie.py:354`) is later and is not visible from the persona; the memory content changes very little during the walk, so the description signal is adequate.
- *Wake-up:* there is no wake event. It is the next `add_new_action` whose description no longer contains sleeping. With the night-keyed marker in D7 it does not need to be detected.
- *Across midnight:* events perceived after 00:00 get the next `sim_day` (`sim_day` comes from the node timestamp). Day 1 starts at 00:00 with the agent already asleep (the `wake_up_hour` block), so the first sleep signal occurs at step 0 with nothing to sweep. Each calendar day also contains the previous night's carry-over block at its start.
- *Zero or two sleep events in one day:* two, from the evening onset plus the 00:00 carry-over block, and potentially many (Isabella's captured schedule has 17 consecutive sleeping entries, each a new `add_new_action`). Zero when a run ends before an agent's evening, or when the schedule is degenerate. A guard is required (D7).
- *Sweep window (as you recommended):* all unconsolidated entries with `sim_timestamp <= sweep time`, so a missed sweep catches up. I agree.

---

## 4. P5.0d Cost estimate (derived; nothing was run)

Raw: `ART/p5_0d_ledger_analysis.json` (captured ledger rows), `ART/p5_0d_cost_estimate.json` (derived).

**What the ledger can and cannot tell us.** All baseline simulation calls in `llm_call_log` come from runs of 2 to 3 steps (10 simulated seconds per step). **Calls per simulated hour have never been measured.** `agent_id` is NULL on most simulation rows, so per-agent splits are not possible. Baseline bursts include retries and failed-run debris (Section 7).

**Captured inputs** (gpt-oss-20b rows): planning mean 1,269 in + 1,050 out per call (n = 272); dialogue 2,190 in + 863 out (n = 26); importance scoring baseline 373 + 90 (n = 84), staged 498 + 140 (n = 79). The first burst (61 calls, 225,044 in, 63,967 out) is consistent with day-start planning for 3 agents (about 20 calls and 96K tokens per agent). Treat that match as my interpretation.

**Derived per-day estimate, 3 agents** (call-per-action count of 8 is code-read from `plan.py` `_determine_action`; actions per hour, perceived events and chat load are assumptions, shown in the artifact):

| Scenario | Calls per sim hour | Tokens per sim hour | Calls per sim day | Tokens per sim day | Days of the 3-key Groq gpt-oss-20b token quota (600K) per sim day |
|---|---|---|---|---|---|
| low | 84 | 91K | 1,453 | 1.8M | 3.0 |
| mid | 150 | 314K | 2,509 | 5.4M | 9.1 |
| high | 255 | 677K | 4,189 | 11.3M | 18.8 |

- On Groq, tokens (TPD) bind before requests (RPD). For a pinned comparison on `openai/gpt-oss-20b`, one simulated day for 3 agents is roughly 3 to 19 days of the three keys' token quota under these assumptions. Pinned Gemini 3.1-flash-lite (500 RPD per project, 1 to 2 projects) covers roughly 0.1 to 0.7 of one day of calls per real day. NVIDIA limits are unknown. **A full live simulated day is not feasible on the current free capacity**, and the conclusion holds at the low scenario. I recommend deciding the evaluation window (agents, hours) with this in mind before Phase 7 and 9.
- **Stage 3 nightly addition** (per agent, cap S summaries; summarization tokens 650 in + 350 out are an assumption, scoring-call tokens are measured): S=6 gives 12 calls and about 9.8K tokens per agent per night (36 calls and 29.5K tokens for 3 agents, about 15% of one Groq key-day). S=4: 24 calls and 19.6K tokens for 3 agents. S=8: 48 calls and 39.3K tokens. Plus one embedding request per new summary (12 to 24 for 3 agents). Clustering needs **0 extra embeddings** if it reuses `a_mem.embeddings` (every mirrored node is already embedded at perceive time).
- Reflection (D1) is not in these totals except as the unmeasured part of the assumptions. By code-read one reflection run is about 34 calls (1 focal-point call, 3 insight calls, then an event-triple and a poignancy call per generated thought). Run frequency is unmeasured; the ledger shows only 10 reflection calls in total.

**Proposed measurement run (not started, needs approval):** 3 agents, a short window rather than a day: 1 simulated hour from 09:00 in `baseline` mode on the pinned model, hard cap 300 LLM calls, with `agent_id` tagged and a router-failure counter. At the mid estimate this is about 150 calls and about 314K tokens (about half the 3-key daily token quota), and it would replace my assumptions with measured calls per agent-hour. Please approve or change the size.

---

## 5. DECISIONS D1 to D7 (all options and recommendations; nothing implemented)

**D1. Reflection in staged mode.**
- Where triggered: `persona.py:239` `self.reflect()` calls `reflect()` (`reflect.py:172-184`). `reflection_trigger` (`reflect.py:152-155`) fires when `importance_trigger_curr <= 0`. The counter is decremented per perceived event at `perceive.py:208-209`; it resets in `reset_reflection_counter`. A second block inside `reflect()` (conversation planning-thought and memo thoughts, written when a chat ends) runs regardless of the trigger.
- Option A (staged disables importance-triggered reflection): one gated line at `reflect.py:183` (`if reflection_trigger(persona) and <reflection flag>`). The conversation memos and the perceive counter are untouched. Config flag `staged_reflection: off | on`.
- Option B: keep both.
- **Recommendation: A as the main configuration, B kept as a config flag for the ablation**, as you leaned. Disclose the confound: A changes two things at once (reflection removed, consolidation added), so the B ablation is needed for any claim about consolidation. Under B, reflection thoughts are scored by the upstream thought path (the event prompt, no priors block; `reflect.py` `generate_poig_score`), because `perceive.py` is the only staged scoring hook; that would add a second differential beyond the priors unless a hook is added.

**D2. Effect of `consolidated` on retrieval.**
- Retrieval code: `new_retrieve` (`retrieve.py`, candidate list built from `seq_event + seq_thought`, then `gw = [0.5, 3, 2]` and `master_out[key] = ...`). Per-step `retrieve()` is keyword-based (`retrieve.py:12-45` region) and would still return consolidated source events.
- Option (i) exclude consolidated sources from the candidate list; (ii) multiply their combined score by a config factor; (iii) additive only.
- **Recommendation: (ii) with `consolidated_weight` in config (start 0.5), as you leaned.** Proposed touch point (needs your approval): in `new_retrieve`, after `master_out` is computed, scale the score of any `key` in the agent's consolidated node-id set by the factor, staged mode only. The consolidated set must be derivable from the live memory so it survives reload: it is the union of `filling` over summary nodes (D6), so no extra persisted state is needed. (iii) gives no efficiency benefit to claim. (i) risks recall of specific details. Per-step keyword retrieval is not changed by (ii); I will report that limit.

**D3. Scoring of summaries.**
- Baseline thoughts (including reflection) are scored upstream by `generate_poig_score` (`reflect.py`), which sends `"thought"` through the **event** poignancy prompt, with no priors block.
- Recommendation: score each summary with `score_importance_persona_conditioned(agent, summary, kind="event", persona=persona)`. The staged prompt is then the same event prompt plus the priors block, so the priors block stays the only differential. `kind="chat"` is not applicable. (The technical-plan pseudocode calls the scorer without `kind`; the signature requires it.)

**D4. Thresholds (all config values, proposed starting points, to be calibrated on real data in Step 1 with logged histograms).**
- Evidence (captured, `ART/p5_0_pairwise_cosine.json`, 93 pairs from the real Phase 2 vectors, 3 agents): median 0.718, 90th percentile 0.828, max 0.879. **34 of 93 pairs are at or above 0.75 and 22 at or above 0.80, and the top pairs are trivia**: "Isabella Rodriguez is idle" versus "Isabella Rodriguez is sleeping" (0.870), "desk is idle" versus "shelf is idle" (0.839). Meanwhile meaningfully related sentences scored 0.53 to 0.63 (Section 2.4). With single linkage, a 0.75 to 0.80 threshold will build large clusters of idle and object events and miss real thematic similarity. This is a small sample (9 vectors per agent, one run). It does not show that a different threshold is right; it shows the plan's starting range needs calibration.
- Importance floor: the mirror stores every perceived node including "X is idle" (poignancy 1, `perceive.py:204`). Proposed: floor 3, plus exclude descriptions containing "idle". Config `importance_floor`.
- Proposed values: `cluster_similarity` 0.78 starting point, with the histogram logged per sweep; `min_cluster_size` 3 (the plan pseudocode says 2); `max_entries_per_prompt` 12 (about 650 prompt tokens including the priors block, well below Groq's 8,000 TPM); `match_threshold` for reinforcing an existing semantic memory 0.80; `max_summaries_per_agent_per_night` 6 (cost in Section 4).

**D5. Embedding source.**
- Recommendation: **`gemini-embedding-001`, one model for both conditions, fail-loud, with the persistent cache**, and cluster on the vectors already in `a_mem.embeddings` (0 extra calls). Evidence: Sections 2.1 to 2.6. The fallback must never be used in evaluation (Spearman -0.086). A local model is the alternative if Gemini embedding capacity proves too small, but it is not feasible in the pinned venv (Section 2.3) and is not measured.
- Needs approval: wiring upstream `get_embedding` (`gpt_structure.py:400`) to `EmbeddingStore` is a `reverie/` edit (extension of sanctioned touch point 1). Without it, retrieval and clustering would not share the cache or the fail-loud policy, and in evaluation the silent fallback inside upstream would remain active.
- Capacity risk: one usable Gemini project (key 2 gives 403). Whether batches count per request is unresolved (Section 2.2).

**D6. How semantic memory enters live memory.**
- Write each summary with `a_mem.add_thought(created=sweep_time, expiration=+30 days as upstream, s,p,o = fixed triple (agent, "consolidated", "memory") to avoid an extra LLM triple call, description=summary, keywords=union of source keywords plus a marker keyword, poignancy=D3 score, embedding_pair=(summary, vector from the same embedding source), filling=[source node ids])`. `add_thought` already computes depth from `filling` (`associative_memory.py:209-210`) and persists `filling` in `nodes.json`, so the source references survive `save()` and reload. Retrievable by `new_retrieve` and by keyword retrieval with no further change.
- Mirror to `semantic_memory` with `entry_id = f"{agent_id}:{node_id}"`, `source_entry_ids` as the JSON array of episodic `entry_id`s.
- Consequence for reconciliation: with sources in `filling`, the live memory is the truth and SQLite stays a mirror. On reload, `consolidated` can be recomputed as "entry is in the sources of a surviving summary node", and semantic rows whose node is absent are dropped. This reuses the P5.0a rule.
- Baseline impact: all of this is gated on staged mode in new code paths; none of the baseline code paths in `perceive.py`, `persona.py`, `reflect.py` or `retrieve.py` change for baseline. I will prove this in Step 1 by running the existing suite plus a baseline byte-comparison test. Known limit: mirrored episodic entries are events and chats only; thoughts (plan thoughts, reflection thoughts) are never mirrored today.

**D7. Sweep guard.**
- Recommendation: a marker row per (agent, night) in a small new table `consolidation_sweeps(agent_id, night, sweep_time, max_node_id, attempts)`, written in the **same SQLite transaction** as the semantic rows and flag flips, so it is atomic. On reload, reconciliation removes markers (and semantic rows, and un-flags sources) whose `max_node_id` exceeds the loaded memory, the same node-presence rule as P5.0a. **This is an additive table; the spec's "no schema change" means I need your approval for it.** Alternative without a new table: a per-agent sidecar JSON written by the runner inside the same autosave (consistent with save k by construction), at the cost of covering only the headless runner.
- Key by **night**, not by calendar day: night id = the `sim_day` of the evening onset; a sleeping signal at an hour before 12:00 belongs to the previous night. This avoids two sweeps per night from the evening block plus the 00:00 carry-over, and it makes the 17 consecutive sleeping entries seen in the captured schedule harmless. This refines the spec's "once per agent per day"; please confirm.
- Retry: a sweep that fails (for example an LLM error) writes no marker and retries on a later tick, up to `max_attempts` per night (config), so a failing router cannot burn calls every step.
- Never sleeps before the run ends: `force_sweep(agent_id, sweep_time)` is called by the runner's clean-exit path for any agent without a marker for the last night, and directly by tests.

---

## 6. CONDITIONS COMPLIANCE TABLE

| Condition | Status | File and line | Proving test or artifact |
|---|---|---|---|
| P5.0a autosave on interval (default 1 sim hour) and on clean exit | Done | `devmem/run_headless.py:106-126`, `config/runner.yaml` | `test_reconcile.py` `test_autosave_interval_and_crash_reload` (scripted) |
| P5.0a reconcile on load, idempotent | Done (episodic only; semantic and markers deferred until they exist, D6 and D7) | `episodic.py:465-537` | same test; `test_crash_and_reload_from_save_k` |
| P5.0a crash-and-reload with real AssociativeMemory and SQLite, labeled scripted | Done | `test_reconcile.py` classes 1 and 2 | 5 tests OK (`ART/full_suite_output.txt`) |
| P5.0b fail-loud mode, failures counted | Done | `vector_store.py:EmbeddingStore.embed_texts` | `test_fail_loud_raises_counts_and_never_falls_back` (synthetic); live 403 in `ART/embedding_stats_p5_0b_probe_run1_key2_403.json` |
| P5.0b fallback only offline, never mixed with real vectors | Done | `vector_store.py` `_set_source`, mixing guards | `test_fallback_only_when_allowed_...`, `test_never_mixes_cached_real_...` (synthetic) |
| P5.0b persistent cache keyed (model, text hash) | Done | `vector_store.py` `_cache_get`/`_cache_put` | `test_persistent_cache_across_instances_and_stats`, `test_duplicates_sent_once_and_cache_keyed_by_model` |
| P5.0b per-run stats in `embedding_stats.json` | Done (writer and path support; production path `devmem/storage/{sim_code}/embedding_stats.json` is set by the caller, not yet wired) | `vector_store.py` `flush_stats` | probe stats in `ART/` |
| P5.0b (1) batch counts as one request against RPD | **Not resolved** | none | docs silent; needs one live call plus your counter readings (Section 2.2) |
| P5.0b (2) local model: install size, time for 100 texts, dimension | **Partial**: not installable on the venv's Python; timing and dimension not measured | none | `ART/pypi_wheel_sizes.json`; awaiting approval to download |
| P5.0b (3) Phase 3 retrieval reproduction per embedding source | **Partial**: Gemini and fallback done; local not measured | `p5_0b_probe.py` | `ART/p5_0b_probe_results.json` |
| P5.0b embeddings per hour and day with assumptions | Done (derived) | none | Section 2.6 |
| P5.0b caps (10 batch calls, 40 reproduction, 50 total) | Probe 4 requests; incidental suite runs at most 34; total at most 38 | none | `ART/count_embed_calls_output.jsonl`, `ART/embedding_stats_*.json` |
| P5.0c sleep representation, verbatim with lines | Done | Section 3 | `reverie/` excerpts and captured scratch files |
| P5.0c sweep window | Proposed (agree with `<=` sweep time) | none | Section 3 |
| P5.0d cost from existing logs, calls and tokens per purpose, extra Stage 3 cost under a cap | Done as derived; per-hour calls unmeasured | `p5_0d_*.py` | `ART/p5_0d_ledger_analysis.json`, `ART/p5_0d_cost_estimate.json` |
| P5.0d no live run without approval; measurement run proposed | Held: 0 LLM calls; run proposed in Section 4 | none | none |
| D1 to D7 surfaced with options and recommendations, none implemented | Done | Section 5 | none |
| No Stage 3 code, no `reverie/` edits | Compliant | none | `git status --short reverie` is empty |
| Baseline unchanged | Compliant (no baseline code touched) | none | full suite OK |

---

## 7. DEVIATIONS (complete)

- **New files outside the spec's listed scope** (all additive, in `devmem/` or `docs/`): `devmem/run_headless.py` (the spec says "the headless runner"; the only existing runner, `reverie/reverie/backend_server/run_baseline_sim.py`, sits inside `reverie/`, so I did not edit it and wrote a new one beside the package), `devmem/config/runner.yaml`, `devmem/config/embeddings.yaml`, `devmem/memory/test_reconcile.py`, `devmem/embeddings/test_vector_store.py`, `devmem/embeddings/p5_0b_probe.py`, `devmem/memory/p5_0d_ledger_analysis.py`, `p5_0d_cost_estimate.py`, `p5_0_pairwise_cosine.py`, and `docs/phase5_step0_artifacts/`. No `__init__.py` files were added (the packages work as namespace packages, as before). Please confirm the runner location.
- **Edited existing file:** `devmem/memory/episodic.py` (two functions appended after line 465). Allowed by spec scope.
- **Import-time side effects of `run_headless.py`:** it calls `os.chdir` to the backend directory (upstream paths are cwd-relative, as in `run_baseline_sim.py`), and sets `utils.MEMORY_MODE` explicitly. The new runner test restores the working directory in `tearDownClass`.
- **Runtime artifacts and cleanups:** `ReverieServer.__init__` rewrites the tracked file `reverie/environment/frontend_server/temp_storage/curr_sim_code.json` and creates `curr_step.json`. The runner test restores the tracked files to their original bytes and deletes new ones. My first failed run left an untracked `curr_step.json`, which I deleted. No test simulation folders remain under `storage/` or `devmem/storage/` (checked). Git-ignored files created: `devmem/storage/p5_0b_probe_cache.db` and `p5_0b_probe_single_cache.db`.
- **No commits made.** The pre-existing uncommitted M1-series work is untouched (Section 0). My Phase 5 files are also uncommitted.
- **Test run with keys blanked** (Section 2.5): the final full-suite output is labeled accordingly. It is not the same as a normal run.
- **Probe overshoot of my own design cap:** designed for 3 requests, sent 4 because the first run hit the 403. Within the spec caps.
- **Observations about existing code, not changed** (they affect Step 1 and the evaluation; reporting once):
  1. `GPT_request` (`gpt_structure.py:339-341`) converts any router exception into the string `"TOKEN LIMIT EXCEEDED"`, which upstream then uses as activity text. The saved Phase 2 schedules contain it (Maria and Klaus), plus a chat-style sentence as an activity. Router failures during a run are therefore silent and corrupt agent plans. Any measurement run needs a failure counter, and I recommend a decision on this before Phase 7. It is an upstream-file edit, so I have not touched it.
  2. `run_baseline_sim.py` sets `os.environ["MEMORY_MODE"]` after `utils` has been imported, so it has no effect there (baseline is the default, so nothing changes). The new runner sets both.
  3. The mirror stores every perceived node including "X is idle" rows (`perceive.py:204`), and never stores thoughts.

---

## 8. TESTS RUN / VERIFICATION

Full-suite output (`ART/full_suite_output.txt`), run with `GEMINI_KEY_1` and `GEMINI_KEY_2` blanked (fallback embeddings, zero live embedding calls), verbatim:

```
=== devmem.router.test_router
Ran 33 tests in 3.492s
OK
=== devmem.memory.test_priors
Ran 9 tests in 1.484s
OK
=== devmem.memory.test_episodic
Ran 10 tests in 1.237s
OK
=== devmem.memory.test_reconcile
Ran 5 tests in 7.836s
OK
=== devmem.embeddings.test_vector_store
Ran 10 tests in 0.339s
OK
```

Counts: router 33, priors 9, episodic 10 (unchanged), reconcile 5 (new, scripted), vector store 10 (new, synthetic). Total 67.

Artifact labels: `ART/p5_0b_probe_results.json`, `embedding_stats_p5_0b_probe*.json`, `p5_0b_vectors_7texts.json` are **live**. `p5_0_pairwise_cosine.json` and `embedding_dims_survey.json` are **captured** data with offline computation. `p5_0d_ledger_analysis.json` is **captured** ledger rows aggregated. `p5_0d_cost_estimate.json` is **derived** (assumptions stated). `pypi_wheel_sizes.json` is **documented** (PyPI JSON API). `count_embed_calls_output.jsonl` is a **synthetic** run (stubbed network) of real test code. The reconcile tests are **scripted**. The vector store unit tests are **synthetic**.

---

## 9. OPEN QUESTIONS FOR HIGHER AUTHORITY

1. Approve D1 to D7 as recommended, or change them (including the night-keyed marker in D7 and the new `consolidation_sweeps` table).
2. Approve the `reverie/` edit that routes upstream `get_embedding` through `EmbeddingStore` (D5), and the proposed `new_retrieve` and `reflect()` touch points (D2, D1) when Step 1 starts.
3. Approve the one-call batch-quota test with your RPD counter readings (Section 2.2).
4. Approve a local-model measurement: a download into a separate Python 3.13 environment outside the repo (I would state exact package and model filenames and sizes first), or drop the local option.
5. `GEMINI_KEY_2` returns 403 on embeddings. Is it from a different project, and is embeddings access enabled for it? How many working Gemini projects should I plan for?
6. Approve or resize the proposed measurement run (1 simulated hour, 3 agents, baseline, cap 300 calls), given that a full simulated day exceeds the free capacity under every scenario in Section 4.
7. Decide how to handle the silent `"TOKEN LIMIT EXCEEDED"` masking in `GPT_request` before any longer run.
8. Commit the approved M1-series work before Phase 5 code lands?
9. Confirm the location of the new runner (`devmem/run_headless.py`).

REQUEST: Approval to proceed to Phase 5 Step 1 under the decisions as approved. Halting here until I hear back.
