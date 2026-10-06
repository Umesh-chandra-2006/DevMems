PHASE: 6 follow-up, Track A items A1 and A2 (offline, no live calls)
STATUS: Done. A3 (night-key design checkpoint) is a separate document, `docs/phase6_night_key_checkpoint.md`. A4 waits for the 12:30 IST reset.

Labels: **offline-captured** (computed from saved live artifacts), **synthetic** (stubbed tests). No em dashes.

## A1. The scorer no longer forwards `db_path` as the router ledger path

- `devmem/memory/episodic.py` (`score_importance_persona_conditioned`): `db_path` (the run database) is now used only for reading identity traits and saving prompt renders; it is never sent to `call_llm`. A new optional `ledger_db_path` is forwarded as the router ledger path, for tests that need an isolated ledger. With neither, the router uses its single default ledger.
- Two existing tests that used `db_path` to isolate the ledger now pass `ledger_db_path` (`devmem/router/test_call_counter.py`, 2 call sites). No other caller passed `db_path` in a simulation path (`perceive.py` and `consolidation.py` never did).
- New test `devmem/memory/test_episodic.py::test_run_database_is_never_forwarded_to_the_router_as_the_ledger_path`: passing the run database changes nothing sent to the router (identical kwargs with and without it), only `ledger_db_path` reaches `db_path`, and the tier, purpose, agent and condition fields are unchanged.
- **Phase 5 prompts and Step D ledger formats unchanged:** the prompt text is not touched (the golden Phase 5 prompt tests still pass), the call fields (`tier`, `purpose`, `agent_id`, `condition`) are identical, and Step D never passed `db_path`, so its ledger rows are exactly what they were. Past artifacts are not rewritten: the five Stop 3 new-event scoring calls remain in that run's `memory.db`; ledger row H7 now says so and marks the defect fixed.
- `devmem/run_stop3.py` (a historical script) still passes `db_path=db`; it now sends nothing to the router ledger from that argument, so re-running it would put all 19 rows in the main ledger.

## A2. What a night sweep would have had to work with in Step D (**offline-captured**, zero calls, zero embedding requests)

Stage 3 selects entries with importance >= 3 whose text has no "idle". Artifact: `docs/phase6_stepd_artifacts/stepd_floor_check.json` (script `devmem/memory/p6_stepd_floor_check.py`; the run's own saved embeddings; production clustering 0.78, single linkage, minimum cluster 3, at most 6 summaries).

| Agent | Mirror rows | Idle rows | Non-idle below the floor | **Pass the floor** | Cluster sizes of the passing entries |
|---|---|---|---|---|---|
| Isabella | 585 | 146 | 415 | **24** | 3 singletons, 3 pairs, one cluster of 3, three clusters of 4 |
| Maria | 8 | 6 | 2 | **0** | none |
| Klaus | 15 | 11 | 4 | **0** | none |

- Isabella's 585 rows hold only **87 distinct texts**; the 24 passing rows hold **10 distinct texts**: "piano is unused" x4, "cooking area is currently empty" x4, "Isabella Rodriguez is handing out flyers for the February 14th event" x4, "... checking her phone for party supply updates" x3, and six texts of 1 to 2 rows. Passing scores: 17 at 3, 5 at 4, 2 at 6.
- Four clusters would have been summarized (sizes 4, 4, 4, 3). Each cluster is the same observation repeated at different times: two are object states ("piano is unused", "cooking area is currently empty") that do not contain the word "idle" and so pass the filter, one is flyer handing, one is phone checking. So a night sweep on this window would have produced four summaries of repeated observations, two of them about unused objects, and would have had nothing at all to work with for Maria and Klaus (they slept through the window, 0 entries).
- Passing entries were logged between 07:25 and 13:36 on day 1 (so a night sweep that evening would include them, if the night-key defect in A3 did not block it).
- Observation, no change proposed here: the idle filter is a text match on "idle", which misses object-state phrasings such as "is unused" or "is currently empty"; whether to widen it is a Stage 3 design question (it would change Phase 5 behavior and needs its own checkpoint).
- Counts only describe this recording (one agent, 7.75 simulated hours, Gemini scoring, in which 421 of 445 model scores were 1 or 2).

## Tests

The affected files pass: `devmem.memory.test_episodic` and `devmem.router.test_call_counter` (15 tests, OK). The full suite is re-run once for the whole round and pasted in the Stop reports that follow.

REQUEST: none (information). A3 checkpoint follows in its own document.
