PHASE: 5, probe Step B (modified, as approved)
STATUS: Complete. 28 live calls in total (B1 12 of 24, B2 16 of 16; total cap 40). Halting; no Phase 6 work started.

Paths are relative to the repository root. Labels: **live** (the 28 calls), **offline-captured** (saved full replies replayed through the real upstream functions with the model call stubbed; zero calls).

## WHAT WAS BUILT

- `devmem/memory/p5_model_probe_v2.py`: B1 and B2 with **router-level caps** (`devmem/router/call_counter.py`; `CapReached` ends the phase; a call refused by the cap is neither made nor recorded). **Full untruncated raw replies** for every call are saved in `docs/phase5_step4_artifacts/model_probe_v2.json` (`raw` = what the router returned; `delivered` = what upstream saw after the optional normalizer). Same Isabella state and fixed inputs as the first probe (base fork state, 2023-02-13 00:00, plan asked for wake hour 6, hourly slot 07:00 AM, reference plan, 7 hours of "sleeping").
- **Key spread:** a temporary provider config in the system temp folder (never the repo's `providers.yaml`) listed only the chosen keys, rotated per invocation: B2 on `GROQ_KEY_7`, `_8`, `_9` (first key per invocation recorded: 7, 8, 9, 7, 8, 9); B1 on `GEMINI_KEY_4`, `_5`, `_6` (4, 5, 6, 4, 5, 6, ...). The Gemini chat calls use the chat model's quota; no embedding call was made, so the embedding quota was untouched.
- `devmem/memory/p5_probe_replay.py` generalized (source file and output tag arguments; fidelity is judged against the variant the live run actually used; the "possibly truncated" flag now means a reply of exactly 500 characters). The Step A artifacts were regenerated: aggregate, fidelity and every per-invocation result are identical to the committed Step A numbers (checked programmatically); only fields were added.
- `docs/CLAIMS_LEDGER.md`: new row D6, not-demonstrated item 13 revised, items 14 and 15 added.
- The normalizer stays **unwired**.

## COMPLIANCE TABLE

| Item | Status | File | Proof |
|---|---|---|---|
| B1: gemini-3.1-flash-lite, daily plan and hourly, suffix strip applied (never on task decomposition), cap 24 | Done: 12 calls (6 repeats x 2 prompts, 1 call each), cap not reached | `p5_model_probe_v2.py` | `model_probe_v2.json` (live); router counter 12 |
| B2: gpt-oss-20b, daily plan only, no normalizer, cap 16 | Done: **16 calls (cap reached exactly)**, 5 completed invocations plus one refused at the cap | same | same; router counter 16 |
| Total hard cap 40 counted at the router, CapReached ends the step | Honored (28 total) | `call_counter.py` | ledger: gemini-3.1-flash-lite 12 rows, openai/gpt-oss-20b 16 rows |
| Full untruncated raw replies saved | Done: 28 replies, lengths 0 to 2,565 characters, none truncated | `model_probe_v2.json` | length check in the artifact |
| Same state and inputs as the first probe | Done | `p5_model_probe_v2.py` | `inputs` block in the artifact |
| Report valid, usable-plan, echo, clean, calls per valid result incl. retries, tokens; faithful numbers only | Done (below). Every live outcome is its own faithful result; the replays are 17 of 17 faithful | `probe_v2_replay.json` | `probe_v2_replay_summary.md` |
| Keys spread across the new Groq and Gemini keys; Gemini embedding-capable keys untouched | Done (rotation above; chat quota only) | `p5_model_probe_v2.py` | `first_key_env` per invocation |
| Normalizer unwired; adoption needs approval and is a recorded deviation | Honored | `devmem/router/output_normalizer.py` | not imported by the router |
| No upstream edits; commit locally, no push; key scan | Honored (hash in my message) | n/a | `git status reverie` clean |

## RESULTS (live; verbatim data in `docs/phase5_step4_artifacts/model_probe_v2.json`)

| Phase, model, prompt | Invocations | Valid | Usable plan | Echo | Clean | Calls (per valid result) | Tokens in / out |
|---|---|---|---|---|---|---|---|
| B1 `gemini-3.1-flash-lite`, normalizer applied, daily plan | 6 | 6 | 6 | 0 | 6 | 6 (1.0) | 2,322 / 1,519 |
| B1 `gemini-3.1-flash-lite`, normalizer applied, hourly schedule | 6 | 6 | n/a | 0 | 6 | 6 (1.0) | 7,128 / 4,995 |
| B2 `gpt-oss-20b`, no normalizer, daily plan | 5 | 0 | **0** | 0 | 0 | 16 (none valid) | 7,040 / 19,976 |

Definitions as before: *valid* = upstream's validator accepted some attempt and the result is non-trivial; *usable plan* = at least 2 non-empty items after the prepended wake-up line; *echo* = the `schedule_check` rule; *clean* = valid, not echo, no `(duration in minutes ...)` suffix, no Unicode space.

What the data shows:
1. **B1.** With the normalizer applied at the output layer, Gemini produced a valid, usable, clean plan in 6 of 6 invocations (4 to 7 items after the prepended wake-up line, for example "prepare for the cafe opening at 7:00 am", "open Hobbs Cafe and work at the counter at 8:00 am") and a valid, clean hourly activity in 6 of 6 ("eating breakfast" in 5, "waking up and completing her morning routine" in 1), each on the first call. The same 12 raw replies replayed through upstream's functions **without** the suffix strip: daily plan 0 of 6 valid, hourly 0 of 6 clean; mapping Unicode spaces alone changed nothing. The raw replies do contain the annotation (for example "prepare for the cafe opening at 7:00 am (duration in minutes: 60, minutes left: 1020), 3) open Hobbs Cafe ...").
2. **B2.** `gpt-oss-20b` produced no usable plan in 5 of 5 completed invocations (16 calls): 3 invocations passed upstream's validator but the parser extracted nothing beyond the prepended wake-up line, and 2 failed all 5 attempts and returned upstream's fail-safe plan. Calls per attempt were 2, 5, 3, 1 and 5. A sixth invocation was refused by the cap before its first call.
3. **The Step A question is resolved for this model:** replaying these **full-length** `gpt-oss-20b` replies with no normalizer, with the space mapping, and with space mapping plus suffix strip gives the same outcome in all 5 invocations (0 usable plans each time). The earlier "inconclusive because of truncation" no longer applies to the plan prompt.
4. The cause of the formats is still a hypothesis. In the two `gpt-oss-20b` replies I inspected, the numbered lines carry no terminal period or comma, which upstream's plan parser looks for; I did not test that by changing the replies.

## DEVIATIONS (complete)

- The router-level cap counter replaced the wrapper-level counters used in the first probe; counts here come from `call_counter.snapshot()` and match the ledger (12 and 16).
- `p5_probe_replay.py` was edited (parameters, live-variant fidelity, truncation flag); Step A artifacts were regenerated with identical numbers; the committed diff for those two files is added fields only.
- The tracked fixture `devmem/router/fixtures/429/observed.jsonl` was appended by the router's passive 429 capture during the live calls (real 429s, label captured); committed as captured.
- Agent tagging was not set for these calls (ledger `agent_id` is empty); not needed for this probe.
- B2's last cut-off invocation is stored in the artifact with `error: "cut off by the cap"` and no calls; it is excluded from every rate.

## TESTS

Full suite, offline default (`docs/phase5_step6_artifacts/full_suite_output_offline_default.txt`), verbatim:

```
=== devmem.router.test_router
Ran 33 tests in 4.170s
OK
=== devmem.router.test_call_counter
Ran 4 tests in 1.430s
OK
=== devmem.router.test_output_normalizer
Ran 4 tests in 0.000s
OK
=== devmem.memory.test_priors
Ran 9 tests in 2.092s
OK
=== devmem.memory.test_episodic
Ran 10 tests in 1.385s
OK
=== devmem.memory.test_reconcile
Ran 10 tests in 39.170s
OK
=== devmem.memory.test_gpt_structure_touch
Ran 5 tests in 0.056s
OK
=== devmem.memory.test_consolidation
Ran 27 tests in 6.150s
OK (skipped=1)
=== devmem.embeddings.test_vector_store
Ran 14 tests in 1.093s
OK (skipped=1)
=== devmem.demo.test_demo
Ran 2 tests in 0.042s
OK
```
118 tests, 2 live-gated skipped (unchanged from the previous round).

## HONEST LIMITS AND OPEN QUESTIONS

Limits: B1 is 12 calls and B2 five completed invocations, one persona state, fixed inputs; plans were checked for parse-validity and format, not quality; nothing here says the simulation would behave well with Gemini plus the normalizer, only that these two prompts parse cleanly. The hourly prompt was not run for `gpt-oss-20b` in Step B.

Questions (none blocks the Phase 6 spec):
1. If you want the normalizer adopted for a baseline-versus-staged comparison, it needs your explicit go, would apply to both conditions, and would be recorded in the claims ledger as a disclosed deviation; it must never touch the task-decomposition prompt.
2. The model for the evaluation runs is still open: Step B supports Gemini only for these two prompts, and the other upstream prompts (decomposition, action generation, conversation) have not been probed for any model.

REQUEST: Approval of this round. Halting; waiting for the Phase 6 specification.
