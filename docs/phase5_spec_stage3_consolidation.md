# PHASE 5 SPEC: Stage 3, Sleep-Triggered Semantic Consolidation

**To:** Senior Developer
**From:** Project Manager (via Project Owner)
**Reference:** `docs/technical_implementation_plan.md` Rev 2.2, Sections 2, 7, 9.0 and 11. Where that document conflicts with this spec, this spec wins.
**Preceding phase:** Phase 4 and tasks M1, M1.1, M1.2 (approved and closed)
**Gate rules:** this phase has TWO stops. Stop 1 is the Step 0 checkpoint report. Stop 2 is the Step 1 phase report. Do not write Stage 3 code (clustering, summarization, sleep hook, retrieval or reflection changes) before Stop 1 is approved. The prerequisite tasks P5.0a and P5.0b in Step 0 are the only code allowed before Stop 1.

---

## 1. Goal and definition of done

Stage 3 plays the "neocortex": when an agent goes to sleep, that agent's unconsolidated episodic memories are embedded, clustered by similarity, and each multi-member cluster is summarized by the LLM into one semantic memory that references its source entries. Source entries get `consolidated = TRUE`. Isolated memories stay as they are.

"Stage 3 done" (from the technical plan, Section 10): after a full simulated day plus sleep, at least one semantic memory exists with correct source references, and `consolidated` flags are flipped correctly. In this phase that must hold both in the SQLite mirror and in the live upstream memory (see decision D6).

Baseline mode must remain byte-identical in behavior. Every change is gated on `MEMORY_MODE == "staged"`.

## 2. Scope

Allowed to create or edit: `devmem/memory/consolidation.py`, `devmem/memory/episodic.py` (flag helpers), `devmem/embeddings/vector_store.py`, the headless runner script, tests, `devmem/config/` for thresholds, and per-run files under `devmem/storage/{sim_code}/`.

`reverie/` touch points in this phase: sanctioned point 4 (the sleep hook) once approved. Changes to reflection or retrieval are NOT sanctioned yet; each needs its own approval through decisions D1 and D2 below.

No schema change. Distinct-day counts are derived from source entries' `sim_day` (see Section 5), so the existing `semantic_memory` table is enough. If you believe a schema change is unavoidable, raise it as a checkpoint item.

## 3. Step 0: prerequisites, evidence, and decision checkpoint

### P5.0a Runner autosave and mirror reconciliation (implement now; report at Stop 1)

Known problem: upstream saves only on an explicit `save()`, while the SQLite mirror writes immediately. After a crash and reload from an older save, mirror rows can be orphaned or collide with re-executed steps.

Required:
- The headless runner autosaves on a configurable interval (default one simulated hour) and on clean exit.
- On load, reconcile the mirror to the loaded memory: remove `episodic_memory` rows whose nodes are not present in the loaded associative memory, and (once they exist) the corresponding semantic rows and sweep markers. Reconciliation must be idempotent.
- Test with a crash-and-reload scenario: run N steps, save at step k, continue to k+m, simulate a crash, reload from save k, confirm no orphan rows, no collisions on replay, and unchanged counts for rows at or before k. Use real `AssociativeMemory` and real SQLite. Label the scenario `scripted`.

### P5.0b Embedding policy evidence (measure now; decide at Stop 1)

Facts: `gemini-embedding-001` allows 100 RPM, 1,000 RPD and 30K TPM per project. The deterministic fallback in `gpt_structure.py` is 768-dimensional while real embeddings are 3,072-dimensional, so they cannot be compared. Vectors from different models are not comparable either.

Required:
- Make the embedding path configurable with a **fail-loud mode**: in evaluation runs, any embedding failure raises and is counted; the deterministic fallback is allowed only in offline unit tests. Record per-run embedding stats (calls, cache hits, failures, fallbacks) in `devmem/storage/{sim_code}/embedding_stats.json`.
- Add a persistent on-disk embedding cache keyed by (embedding model, text hash).
- Measure, and report with raw output: (1) whether one batch request of many texts counts as one request against the 1,000 RPD limit (cap 10 live embedding calls for this test); (2) if a local model is feasible on this machine (for example a small sentence-transformers model): install size, time to embed 100 texts, embedding dimension; (3) reproduce the Phase 3 retrieval test ("Isabella has a disagreement and potential confrontation with a neighbour") with each embedding source and report whether the ranking of the six atomic priors is preserved (cap 40 live embedding calls in total for Step 0).
- Estimate embeddings per simulated hour and per day from the existing logs and code paths (count `get_embedding` call sites per perceive and retrieve), and state the assumptions.

### P5.0c Sleep discovery (read-only)

Find, in the upstream code, exactly how "sleeping" is represented. Report with verbatim code and file and line numbers: candidates are `scratch.act_description` containing "sleeping", the act address or bed object occupancy, a scratch field, and the daily schedule entries. State: the earliest reliable signal that an agent has fallen asleep; how wake-up is detected; what happens when sleep spans midnight (which `sim_day` the events during sleep belong to); and how the schedule can yield zero or two sleep events in one day. Propose the sweep window: recommended is **all unconsolidated entries with `sim_timestamp` at or before the sweep time**, so a missed sweep catches up rather than losing entries.

### P5.0d Cost estimate

From the existing logs, estimate the live cost of one simulated day for 3 agents in calls and tokens per purpose, and the extra cost Stage 3 adds per night (summarization calls, summary-scoring calls, embeddings), under a proposed cap on summaries per agent per night. Do NOT run a full live simulated day or any measurement run without approval. If you want a measurement run, propose its exact size and call cap in the checkpoint.

### Decision checkpoints (surface all, with options and your recommendation; implement none)

- **D1, reflection in staged mode.** Options: (A) staged disables upstream reflection and Stage 3 replaces it; (B) keep both. Project Manager's lean: A as the main configuration, with B kept available as a config flag for an ablation. Show where upstream reflection is triggered and what disabling it touches.
- **D2, effect of `consolidated` on retrieval.** Options: (i) exclude consolidated source entries from retrieval candidates; (ii) keep them but down-weight with a configurable factor; (iii) additive only (semantic summaries are added, sources unchanged). Without (i) or (ii) there is no efficiency benefit to claim; (i) risks hurting recall of specific details. Project Manager's lean: (ii) with the factor as a config knob. (i) and (ii) require a new sanctioned touch point in the retrieval code; propose the exact function and lines.
- **D3, scoring of summaries.** Which prompt kind scores a semantic summary, and how the priors block applies, keeping the priors as the only differential versus baseline thoughts. State how baseline reflection thoughts are scored upstream.
- **D4, thresholds and bounds.** Proposed clustering similarity threshold (start 0.75 to 0.80 cosine), threshold for matching a new summary to an existing semantic memory, minimum cluster size, maximum entries per summarization prompt (Groq TPM is 8,000; account for the priors block), an importance floor below which entries are not clustered (to avoid summarizing trivia such as "bed is empty"), and a maximum number of summaries per agent per night. All as config values.
- **D5, embedding source.** Recommend one, with the P5.0b numbers. It must be used for both clustering and retrieval and be identical in both conditions.
- **D6, how semantic memory enters live memory.** Proposed design for writing each summary into the upstream `AssociativeMemory` as a thought node (embedding, keywords, poignancy, and the source node IDs in the node's filling or equivalent field), so it is retrievable without further changes, and for mirroring it to `semantic_memory`. Confirm that no baseline code path is affected.
- **D7, sweep guard.** Where the once-per-agent-per-day marker lives (it must be idempotent, atomic, and rolled back by the same reconciliation as P5.0a), and how the sweep behaves for an agent who never sleeps before the run ends (provide a `force_sweep` for tests and end-of-run).

### STOP 1: Checkpoint report

Use the PRD Section 6 template plus: a compliance table for P5.0a to P5.0d; the raw artifacts (embedding stats, reproduction output, code excerpts with line numbers); and D1 to D7 with options and recommendations. Halt and wait for approval.

## 4. Step 1: implementation (only after Stop 1 is approved, following the decisions as approved)

1. `vector_store.embed_batch(texts)` returns normalized vectors, uses the persistent cache, honors fail-loud mode, updates embedding stats.
2. `cluster_by_similarity(embeddings, threshold)` by single-linkage (union-find) over pairwise cosine similarity. Deterministic. Start simple; do not add a clustering library unless real data shows it is needed.
3. `run_nightly_sweep(agent_id, sweep_time)` per technical plan Section 7 and the approved decisions:
   - select unconsolidated entries up to the sweep time above the importance floor;
   - embed, cluster, drop clusters below the minimum size, order by size and total importance, apply the per-night cap;
   - summarize each cluster with the summarization prompt (priors as persona context), capped cluster size in the prompt;
   - score the summary per D3;
   - `create_or_reinforce`; flip `consolidated` in SQLite and in the live memory structures as approved;
   - append one JSON line per sweep to `devmem/storage/{sim_code}/consolidation_log.jsonl`: agent, sim time, entry count, cluster-size histogram, threshold, summaries written, tokens in and out, any fallback or failure.
4. `create_or_reinforce(agent_id, summary, source_ids, importance, sim_day)`: match against the agent's existing semantic memories by embedding similarity at the approved threshold. If matched: append new source IDs, increment `times_reinforced`, update `last_reinforced_at`. If not: create. **Derive `distinct_days_reinforced` as the number of distinct `sim_day` values across all of the semantic memory's source episodic entries.** Do not rely on wall-clock timestamps.
5. Sleep hook at the approved location (sanctioned touch point 4), staged mode only, once per agent per sleep, idempotent across reload.
6. Reflection and retrieval changes exactly as approved in D1 and D2, each reported as a sanctioned touch point with line numbers.
7. Use the router for every LLM call, with `purpose="consolidation_summary"` for summaries and the existing purposes for scoring, `condition="staged"`, and pinned model `openai/gpt-oss-20b` for any comparison or test run.

## 5. Tests

Unit tests:
- Clustering on fixed synthetic embeddings (label them `synthetic`): correct groups, deterministic output, threshold edge cases, isolated points stay isolated.
- `create_or_reinforce`: creates, reinforces on match, appends sources without duplicates, derives `distinct_days_reinforced` from source `sim_day` values (including a multi-day case), and is idempotent on retry.
- Sleep guard: fires once per agent per day even if the agent stays asleep for many ticks; a reload after a sweep does not re-sweep; reconciliation after reload from an older save removes later markers.
- Embedding fail-loud mode raises and counts; fallback vectors are never mixed with real ones.
- Baseline mode: behavior unchanged (run the full existing suite).

Integration test, real `AssociativeMemory` and SQLite, scripted events labeled `scripted`, at most 40 live LLM calls in total for Step 1 testing:
1. Insert a scripted day of episodic events with real embeddings (include several that should cluster and several that should not).
2. Run the sweep through the real router.
3. Assert: at least one semantic memory with correct source references; source rows flagged; isolated rows untouched; the summary exists as a retrievable thought node in the live memory; `new_retrieve` can return it for a relevant focal point; a second sweep does nothing new.

A full live simulated day is NOT part of this task. If after Stop 2 the Project Owner approves one, it will be specified separately with an exact call cap.

## 6. Budgets and rules

- Step 0 live call budget: at most 50 embedding calls and 10 LLM calls in total. Step 1 live call budget: at most 40 LLM calls plus the embedding calls those tests need (state them). Stop and report if a cap is reached.
- Never print or log keys. Redact IDs in saved payloads.
- Keep upstream functions intact but unused; do not delete anything.
- List every file touched, including tests, `__init__.py` files, reverted runtime artifacts, and cleanups, under Deviations.

## 7. Report requirements (Stop 2)

PRD Section 6 template, plus:
1. Conditions compliance table: one row per item in this spec, status, file and line, proving test.
2. Full test suite output pasted verbatim (router, priors, episodic, and the new tests).
3. Raw artifacts for every number: consolidation logs, embedding stats, ledger queries, saved test outputs, named in the report.
4. Every result labeled `scripted`, `live`, `synthetic`, `captured` or `documented`.
5. Verbatim summaries produced and the verbatim source entries they came from (at least three clusters), so quality can be judged.
6. The cluster-size histogram across the test data and the chosen thresholds with the reasoning.
7. Honest limits: what is not demonstrated. No causal or "proves" language.
8. Open questions, then an explicit approval request, then halt.

## 8. What the Project Owner will provide

Decisions on D1 to D7 after Stop 1. The number of Groq keys, Gemini projects and NVIDIA keys available, to size any later measurement or comparison runs.
