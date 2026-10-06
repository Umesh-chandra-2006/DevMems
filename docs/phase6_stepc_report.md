PHASE: 6 preparation, Step C (live smoke on Gemini with the output normalizer on)
STATUS: **Partially complete.** The run stopped in step 0 on an upstream exception (`KeyError: 'kitchen'`) after **31 of 150** router-counted calls, 0 of the 2 simulated hours, and only Isabella reached. The cap was not the reason. The result still answers the purpose of Step C for the prompts that ran: **Gemini cannot yet drive a run with the current normalizer allow-list**, because of a deterministic failure on the action-location prompts (details below). Nothing here is a quality claim. Halting, as instructed.

Paths are relative to the repository root. `ART/` = `docs/phase6_stepc_artifacts/`. Labels: **live** (the 31 calls), **offline-captured** (analysis and replays of the saved log; zero calls), **code-read** (upstream source).

## 0. Done before the run

- **Addendum A1 and the Step C population** were written into `docs/phase6_preregistration.md` and committed as **`06c733c`** before any Stage 4 code and before Step C ran: the Path B loop guard (`self_reinforced_pivotal`), the recorded approvals (SAME_DAY_COUNT stays 4; T = 9 frozen as provisional; merge-band and `unknown` counts to be reported at Stop 3), and the exact population for the one T re-check (section 7 of that file).
- The router raw-reply log now also stores the **full prompt** (one extra field, still off by default; the wiring test asserts it).

## 1. WHAT WAS BUILT

- `devmem/run_step_c.py`: 3 agents, start 06:00 (fork copy with a changed clock), stop at 08:00, staged mode, Stage 4 absent, pinned `gemini-3.1-flash-lite`, `DEVMEM_OUTPUT_NORMALIZER=on`, `DEVMEM_RAW_REPLY_LOG` on, `fail_loud_llm` on, agent tagging on, **router-level hard cap 150** (`CapReached` ends the run, no save attempted after a mid-step stop). Calls rotate round-robin over `GEMINI_KEY_4`, `_5`, `_6` through temporary provider configs applied to every caller (gpt_structure, episodic scoring, consolidation); the router's own per-key pacing (15 RPM for this model) applies per key. Hourly ledger deltas recorded to a jsonl.
- **Embeddings:** `DEVMEM_EMBEDDING_MODE=offline` for the whole run (deterministic vectors, **zero embedding requests**, cache not read, so real and fallback vectors can never mix in the run's memory). This is my reading of "no embeddings beyond the cache"; retrieval relevance is meaningless in this run.
- `devmem/memory/p6_stepc_analysis.py` (offline analysis of the raw log) and `devmem/memory/p6_stepc_replay.py` (offline replay of the failed prompts through upstream's own code).

## 2. RESULTS (live; raw data in `ART/raw_replies.jsonl`, full prompt, raw reply and delivered text of all 31 calls)

| Item | Result |
|---|---|
| Outcome | `exception: KeyError: 'kitchen'` in step 0, clock still 06:00:00, **no save** (no autosave interval reached); wall time 223 s |
| Router-counted calls | **31 of 150** (all `planning`, all Isabella Rodriguez); Maria and Klaus never started (the crash happened in Isabella's first move) |
| Tokens (ledger) | 32,820 in, 9,272 out for the 31 calls |
| Key spread and pacing | first key per call: `GEMINI_KEY_4` 11, `_5` 10, `_6` 10; about 8 calls per minute in total (roughly 3 per key per minute), well below 15 RPM per key; no 429; `ROUTER_FAILURES` count 0 |
| Embedding requests | 0 (offline mode) |
| Normalizer | applied to 20 calls (wake-up 1, daily plan 1, hourly schedule 18) and **changed the text in all 20** (every reply carried the `(duration in minutes: N, minutes left: M)` annotation or similar); applied to 0 decomposition or action prompts, as designed |

**Per prompt type (analysis of the log; `ART/step_c_analysis.md`).** An instance is a run of consecutive calls by one agent with the identical prompt (upstream retries re-send the same prompt):

| Prompt type | Instances | Calls | Retries | First attempt accepted | 5 attempts | Replies with the duration annotation left in |
|---|---|---|---|---|---|---|
| wake-up hour | 1 | 1 | 0 | 1 | 0 | 0 (stripped) |
| daily plan | 1 | 1 | 0 | 1 | 0 | 0 (stripped) |
| hourly schedule | 18 | 18 | 0 | 18 | 0 | 0 (stripped) |
| task decomposition | 1 | 1 | 0 | 1 | 0 | required by that prompt; present in 1 of 1 |
| **action location, sector** | 1 | 5 | 4 | **0** | **1** | **5 of 5** |
| **action location, arena** | 1 | 5 | 4 | **0** | **1** | **5 of 5** |

Echo replies 0; exotic-space replies 0; empty replies 0. "5 attempts" means upstream rejected every attempt for the sector prompt and for the arena prompt (upstream retries only on rejection and stops after 5).

**Valid schedule rate per agent.** Isabella: wake-up 1 of 1, daily plan 1 of 1, hourly schedule 18 of 18 accepted on the first attempt and clean after normalization (no echo, no annotation, no unusual spaces). Maria: no data. Klaus: no data. These are validity and format measures only.

**Calls and tokens per simulated hour:** not measurable; no simulated hour completed. Only the partial step 0 exists (31 calls, 32,820 in, 9,272 out, all Isabella).

## 3. THE FAILURE (found in the log, confirmed in upstream code, reproduced offline)

1. **What happened.** After her hourly schedule (18 calls) and one decomposition call, Isabella's first action needed a location. Gemini answered the sector prompt five times with `Isabella Rodriguez's apartment} (duration in minutes: 60, minutes left: 1440)` and the arena prompt five times with `main room} (duration in minutes: 15, minutes left: 15)`. Upstream rejected all ten replies.
2. **Why (code-read).** `run_gpt_prompt.py` validators for the action sector and arena prompts reject any reply that contains a comma (`if "," in gpt_response: return False`, around lines 560 to 565 and the arena equivalent); the annotation contains a comma. After 5 rejections upstream returns its fail-safe, which for both the sector and the arena prompt is the string `"kitchen"` (line 569 in the sector function, line 699 in the arena function). For the sector prompt a later check replaces an unknown sector with the living area, so it survived; for the arena there is no such check, and the next step (`generate_action_game_object`) looks up arena `kitchen` in Isabella's apartment, which has only `main room`: `KeyError: 'kitchen'`.
3. **Why the annotation appears (hypothesis).** The repo's `GPT_request` system prompt (added in Phase 2 to make decomposition work) tells the model that every subtask line must carry `(duration in minutes: <int>, minutes left: <int>)`. Gemini applied it to every answer, including these one-word location answers. I did not test the system prompt (no variant was run).
4. **Offline replay (`ART/step_c_replay.json`, zero calls).** The real upstream arena function was run with the saved replies. The prompt it builds equals the logged live prompt (**faithful**): unmodified, all 5 attempts are rejected and the result is `kitchen`; with the annotation stripped at the output layer, attempt 1 is accepted and the result is `main room`. The sector replay reproduces the same direction (5 rejections; 1 acceptance after stripping) but my rebuilt sector prompt does **not** equal the live one, so it is indicative only.
5. **The normalizer's allow-list does not include these prompts** (it covers wake-up, daily plan and hourly schedule only, by design). So in this run they failed. This is not a defect of the wiring; it is the information Step C was meant to produce.

## 4. WHAT STEP C DOES AND DOES NOT SAY

- It says: with the current allow-list and the repo's system prompt, a Gemini-driven run **cannot get past the first action** of an agent (deterministic upstream failure on the arena prompt, 5 of 5 replies rejected, then a crash). The three schedule prompts (wake-up, daily plan, hourly schedule) were valid and clean on the first attempt in 20 of 20 cases once normalized.
- It does not say anything about the prompt types that never ran: the game-object prompt, pronunciatio, event triple, object description and object event triple, perception scoring, decide-to-talk and react, and all conversation prompts; nor about Maria and Klaus; nor about the second simulated hour.
- 119 of the 150 calls were not used. The run is not repeated (no other live runs are allowed). A second Step C would be a new run and needs your go.

## 5. THE ONE T RE-CHECK (pre-registered population)

The population written before the run is every importance score returned during Step C for non-idle events. **There were 0 scores** (the run never reached perception), so the re-check cannot be done: **T = 9 stays provisional**, as the verdict specified for fewer than 30 scored events. Nothing was tuned.

## 6. COMPLIANCE TABLE

| Item | Status | Artifact |
|---|---|---|
| 3 agents, 06:00, 2 simulated hours, staged, Stage 4 off | Setup done; **run reached 0 of 2 hours** (crash in step 0) | `devmem/run_step_c.py`, `ART/step_c_report.json` |
| Normalizer on, allow-list only, never decomposition | Honored (applied to 20 calls, 0 decomposition) | `normalizer_stats` |
| Hard cap 150 counted at the router, CapReached ends the step | Honored (31 used) | `router_counter` in the report |
| Raw-reply log on, full replies saved | Done | `ART/raw_replies.jsonl` |
| Spread across the working Gemini keys; 15 RPM per key | Done (11/10/10; about 3 calls per key per minute) | `calls_by_first_key` |
| No embeddings beyond the cache | Honored (offline mode, 0 requests) | `embedding_mode` |
| Valid schedule rate per agent | Isabella only (see section 2) | `ART/step_c_analysis.json` |
| Echo and degenerate counts | 0 echo, 0 empty, 0 exotic-space; annotation leaks only in the two un-normalized prompts | `ART/step_c_analysis.md` |
| Upstream retries per prompt type | Table in section 2 | same |
| Calls and tokens per simulated hour | Not measurable (no hour completed) | `ART/hourly_ledger.jsonl` (partial step 0 only) |
| Any prompt type that fails | **Action sector and arena (5 of 5 rejected); arena fail-safe crash** | sections 2 and 3 |
| No quality claims | Honored | n/a |
| T re-check on Step C scores | Not possible (0 scores); T = 9 provisional | section 5 |

## 7. DEVIATIONS (complete)

- **Embeddings offline** for the whole run (my interpretation of "no embeddings beyond the cache"; the alternative, cache-first with deterministic fallback, would mix 3072-dimensional and 768-dimensional vectors).
- **No soft stop was used:** the verdict gave only the hard cap of 150, so a mid-step stop would have lost the state; the run ended on an exception, so the point is moot here, but the autosave interval (15 simulated minutes) was never reached.
- The run's fork copy (clock set to 06:00) was deleted afterwards; the runtime files it rewrote were restored. The run folder is git-ignored; the raw log and report were copied to `ART/`.
- The raw-reply log gained a `prompt` field (router, off by default).
- `devmem/memory/p6_stepc_analysis.py` classifies prompts by matching every upstream template file; the label `action_location_object` in its table is the **arena** prompt (`run_gpt_prompt_action_arena` uses the template `action_location_object_vMar11`, line 705). I fixed my first classifier after it mislabelled two prompts; the numbers above are from the final version.
- Router calls were rotated across keys by patching `call_llm` names in memory in the run script; no file other than the run script changed for that.

## 8. TESTS

Full suite, offline default (`ART/full_suite_output_offline_default.txt`), verbatim:
```
=== devmem.router.test_router
Ran 33 tests in 3.727s
OK
=== devmem.router.test_call_counter
Ran 4 tests in 1.692s
OK
=== devmem.router.test_output_normalizer
Ran 4 tests in 0.000s
OK
=== devmem.router.test_normalizer_wiring
Ran 8 tests in 2.250s
OK
=== devmem.memory.test_priors
Ran 9 tests in 2.011s
OK
=== devmem.memory.test_episodic
Ran 10 tests in 1.585s
OK
=== devmem.memory.test_reconcile
Ran 10 tests in 39.035s
OK
=== devmem.memory.test_gpt_structure_touch
Ran 5 tests in 0.055s
OK
=== devmem.memory.test_consolidation
Ran 27 tests in 7.028s
OK (skipped=1)
=== devmem.embeddings.test_vector_store
Ran 14 tests in 1.312s
OK (skipped=1)
=== devmem.demo.test_demo
Ran 2 tests in 0.095s
OK
```
126 tests, 2 live-gated skipped (unchanged).

## 9. OPEN QUESTIONS FOR HIGHER AUTHORITY

Step C decided the model question for now: **Gemini plus the three-prompt allow-list is not enough.** The options, each needing your decision (none touches the task-decomposition prompts):
1. **Extend the allow-list** to the single-answer action-location prompts (sector, arena, game object), whose replies must not carry the annotation. The faithful arena replay shows this turns the failure into an accepted first attempt. Smallest change, applies identically to both conditions, tested offline first.
2. **Make the system prompt conditional** in `GPT_request` (annotation instruction only for decomposition prompts). Fixes the cause instead of the symptom, but it is an edit of an upstream file (sanctioned touch point 1, Phase 2).
3. **Use a different model for the planning prompts** (the `gpt-oss` models did not show this crash in the earlier live runs, but they had their own schedule problems).
I recommend option 1, with an offline test over all action-location prompts rendered from the real templates, then a second Step C with a small cap on the same prompts (new run, needs your go) to see whether the remaining action prompts, perception scoring and conversations also parse.

REQUEST: Your decision on the options above and approval of this report. Then Phase 6 Stop 2 (offline build) per your order. Halting.
