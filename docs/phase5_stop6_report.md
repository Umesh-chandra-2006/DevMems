PHASE: 5, router-level cap counting and probe Step A (offline replay)
STATUS: Complete. Step A done with zero live calls. **Halted before Step B**, which waits for your go (reasons in "Open questions").

Paths are relative to the repository root. Labels: **live** (verification calls only this round), **offline-captured** (saved live replies replayed through the real upstream functions with the model call stubbed; zero network, zero LLM calls), **synthetic** (stubbed provider in tests).

## 1. New keys (names only; verification calls reported separately from every cap)

Env var names in `.env`: `GROQ_KEY_1` to `GROQ_KEY_9`, `GEMINI_KEY_1` to `GEMINI_KEY_7`, `NIM_KEY_1` to `NIM_KEY_6`. New this round: `GROQ_KEY_7`, `GROQ_KEY_8`, `GROQ_KEY_9`, `GEMINI_KEY_6`, `GEMINI_KEY_7`, `NIM_KEY_5`, `NIM_KEY_6`. One minimal call each (LLM `max_tokens` 5; for each Gemini key also one embed call). Status codes only (`docs/phase5_step2_artifacts/key_verification.json`, **live**):

| Key | Call | Status |
|---|---|---|
| GROQ_KEY_7 | LLM, 5 tokens | 200 |
| GROQ_KEY_8 | LLM, 5 tokens | 200 |
| GROQ_KEY_9 | LLM, 5 tokens | 200 |
| GEMINI_KEY_6 | LLM, 5 tokens | 200 |
| GEMINI_KEY_6 | embed | 200 |
| GEMINI_KEY_7 | LLM, 5 tokens | **403** |
| GEMINI_KEY_7 | embed | **403** |
| NIM_KEY_5 | LLM, 5 tokens | 200 |
| NIM_KEY_6 | LLM, 5 tokens | 200 |

Added to `providers.yaml`: `GROQ_KEY_7` to `_9`, `NIM_KEY_5`, `NIM_KEY_6`, `GEMINI_KEY_6`; `GEMINI_KEY_6` also to `embeddings.yaml` (now `GEMINI_KEY_1`, `_3`, `_4`, `_5`, `_6`). **`GEMINI_KEY_7` stays out** (403 on both chat and embeddings; a different account is a different project, so this is that project's key, not a shared one). Verification calls this round: **9**. No other live call was made.

## 2. WHAT WAS BUILT

**Router-level cap counting (approved).** `devmem/router/call_counter.py`: `record_call`, `set_cap`, `reset`, `snapshot`, and `CapReached` (a `BaseException`, so upstream's `except Exception` retry loops cannot swallow it). `llm_router.call_llm` calls `record_call` as its first action (2 added lines in `devmem/router/llm_router.py`, after the `agent_id` default), so every attempt is counted whatever the import path (`gpt_structure`, `episodic`, `consolidation`, scripts), whether it later succeeds or fails; a call refused by the cap is not counted. `devmem/run_live_staged.py` now uses it for all future capped runs (it reports `router_counter` next to its own counts). The earlier probe and smoke scripts keep their old wrappers (legacy; no past number was changed).
**Test** `devmem/router/test_call_counter.py` (4 tests, provider layer stubbed, `call_llm` itself real): a call made through `episodic.py`'s own import path is counted (it asserts `episodic.call_llm is llm_router.call_llm`, the by-value import the old wrapper missed) together with a direct call and a call through upstream's `GPT_request` (total 3, by purpose and by agent); failed attempts are counted; a hard cap raises out of `episodic`'s `except Exception` (not swallowed, refused call not counted); counting without a cap and reset.

**Probe Step A.**
- `devmem/router/output_normalizer.py` (not wired into the router): maps U+00A0, U+1680, U+2000 to U+200A, U+202F, U+205F, U+3000 to a plain space; optionally strips a trailing `(duration in minutes: N, minutes left: M)`. Tests: `devmem/router/test_output_normalizer.py` (4 tests). Hazard recorded in the module: upstream's task-decomposition prompt **requires** that annotation, so the suffix strip may only be applied to the wake-up, daily-plan and hourly-schedule outputs, never globally.
- `devmem/memory/p5_probe_replay.py`: runs the **real upstream prompt functions** on the same Isabella state and inputs as the live probe, with only `gpt_structure.call_llm` replaced by a stub that returns the saved raw replies of each invocation in order. GPT_request's cleanup, `safe_generate_response` (retry loop, 5-attempt limit) and each prompt's own validator and clean-up function are upstream's own code. The normalizer is applied to the stub's output (the router/output layer), never inside upstream. Three variants: `none`, `spaces`, `spaces+duration`. A network path raises. Raw: `docs/phase5_step4_artifacts/probe_replay.json`, table `probe_replay_summary.md`.

## 3. STEP A RESULTS (offline-captured; zero live calls)

**Fidelity of the replay.** Variant `none` reproduced the live outcome (same output and same validator results) in **19 of 21** invocations. The 2 that did not (`gemini-3.1-flash-lite` daily plan repeat 1, `gpt-oss-120b` hourly repeat 2) are listed in the artifact. **Limitation that bounds every result below:** the live probe saved each raw reply truncated to its first 500 characters (my script's choice); all daily-plan replies were exactly 500 characters long, so every daily-plan replay parses truncated text. The `gpt-oss-120b` hourly repeat 2 live result was clean ("having breakfast and reviewing the day’s schedule") but its truncated replay is not; that live result stands and the replay for it is not trusted.

Valid / clean counts (valid = upstream validator passed and a non-trivial result; clean = valid, not echo by the `schedule_check` rule, no duration suffix, no exotic space). Format `valid / clean of n`; "faithful only" excludes the 2 non-faithful invocations:

| Model | Prompt | none | spaces | spaces + duration strip | faithful only (none / spaces / spaces+duration) |
|---|---|---|---|---|---|
| gpt-oss-20b | wake-up | 3 / 3 of 3 | 3 / 3 of 3 | 3 / 3 of 3 | same |
| gpt-oss-20b | daily plan | 0 / 0 of 2 | 0 / 0 of 2 | 0 / 0 of 2 | same |
| gpt-oss-20b | hourly | 2 / 0 of 2 | 2 / 0 of 2 | 2 / 0 of 2 | same |
| gpt-oss-120b | wake-up | 3 / 3 of 3 | 3 / 3 of 3 | 3 / 3 of 3 | same |
| gpt-oss-120b | daily plan | 0 / 0 of 2 | 0 / 0 of 2 | 0 / 0 of 2 | same |
| gpt-oss-120b | hourly | 2 / 0 of 2 | 2 / 0 of 2 | 2 / 0 of 2 | 1 / 0 of 1 for all three |
| gemini-3.1-flash-lite | wake-up | 3 / 3 of 3 | 3 / 3 of 3 | 3 / 3 of 3 | same |
| gemini-3.1-flash-lite | daily plan | 0 / 0 of 2 | 0 / 0 of 2 | **2 / 2 of 2** | 0 / 0 of 1, 0 / 0 of 1, **1 / 1 of 1** |
| gemini-3.1-flash-lite | hourly | 2 / 0 of 2 | 2 / 0 of 2 | **2 / 2 of 2** | 2 / 0, 2 / 0, **2 / 2** of 2 |

What the data shows:
1. **Mapping Unicode spaces to a plain space changed no outcome** in any of the 21 invocations.
2. **Adding the duration-suffix strip made Gemini valid and clean** on both prompts it affected: daily plan 0 of 2 to 2 of 2 (the parsed plans are real items, for example "prepare breakfast and have coffee at 6:30 am"; 1 of the 2 is a faithful replay, the other was truncated), hourly 0 of 2 to 2 of 2 (2 of 2 faithful).
3. **Neither normalizer variant changed anything for `gpt-oss-20b` or `gpt-oss-120b`.** Their hourly outputs are echo-format (the suffix strip does not address that), and their daily-plan replays stay at 0 usable. **That daily-plan result is inconclusive**, not negative: the replies were truncated at 500 characters, so these replays parse partial text; the effect on full replies is unknown.
4. Wake-up is unaffected for all models (9 of 9 valid).

I make no claim about why the models produce these formats; the system prompt of the repo's `GPT_request` was not varied (not run, as instructed).

## 4. COMPLIANCE TABLE

| Item | Status | File | Proof |
|---|---|---|---|
| Router-level counting, every import path | Done | `devmem/router/call_counter.py`; `llm_router.py` (2 lines in `call_llm`) | `test_call_counter.py` (4 tests) |
| Test that a call via `episodic.py`'s import path is counted | Done | `devmem/router/test_call_counter.py` | `test_calls_through_every_import_path_are_counted` |
| Use it for all future capped runs; change no past number | Done for `run_live_staged.py`; past artifacts and reports untouched | `devmem/run_live_staged.py` | `git diff` shows only that script and the router |
| Step A: replay saved raw replies through upstream's parsers, with and without the normalizer | Done, zero live calls | `p5_probe_replay.py`, `output_normalizer.py` | `docs/phase5_step4_artifacts/probe_replay.json` |
| Report valid and clean per model and prompt | Done | Section 3 | `probe_replay_summary.md` |
| Normalizer at the router/output layer, not in upstream; identical for both conditions; disclosed deviation if adopted | Honored (not adopted, not wired) | `output_normalizer.py` | no `reverie/` change |
| No other live runs; quota kept for the demo | Compliant: only 9 key-verification calls | n/a | n/a |
| Commit locally, no push | Done (hash in my message) | n/a | n/a |

## 5. DEVIATIONS (complete)

- New files: `devmem/router/call_counter.py`, `test_call_counter.py`, `output_normalizer.py`, `test_output_normalizer.py`, `devmem/memory/p5_probe_replay.py`, `docs/phase5_step5_artifacts/`, `docs/phase5_step4_artifacts/probe_replay*`. Edited: `llm_router.py` (2 lines), `run_live_staged.py` (counter), `providers.yaml`, `embeddings.yaml`, `docs/CLAIMS_LEDGER.md` (new row D5, a note on F4, and not-demonstrated item 13).
- A forced-abort check of `run_live_staged.py` overwrote the tracked artifact `docs/phase5_step3_artifacts/p5_staged_live_soft_budget.json`; I restored it from git, so no past number changed.
- The replay's "faithful" split is my construction, stated in the artifact; the `all` columns include 2 invocations whose replay is not trusted.
- The earlier probe's 500-character truncation of saved replies is a flaw of my script; it limits Step A.

## 6. TESTS

Full suite, offline default (`docs/phase5_step5_artifacts/full_suite_output_offline_default.txt`), verbatim:

```
=== devmem.router.test_router
Ran 33 tests in 4.120s
OK
=== devmem.router.test_call_counter
Ran 4 tests in 1.661s
OK
=== devmem.router.test_output_normalizer
Ran 4 tests in 0.000s
OK
=== devmem.memory.test_priors
Ran 9 tests in 2.333s
OK
=== devmem.memory.test_episodic
Ran 10 tests in 1.748s
OK
=== devmem.memory.test_reconcile
Ran 10 tests in 43.280s
OK
=== devmem.memory.test_gpt_structure_touch
Ran 5 tests in 0.041s
OK
=== devmem.memory.test_consolidation
Ran 27 tests in 7.349s
OK (skipped=1)
=== devmem.embeddings.test_vector_store
Ran 14 tests in 1.267s
OK (skipped=1)
=== devmem.demo.test_demo
Ran 2 tests in 0.045s
OK
```
118 tests (up from 110), 2 live-gated skipped.

## 7. OPEN QUESTIONS (Step B is held)

Your condition for Step B was "only if Step A shows the normalizer fixes validity", and Step B was specified for pinned `openai/gpt-oss-20b`. Step A shows the suffix strip fixes validity for **Gemini only**; for `gpt-oss-20b` it fixes nothing (hourly stays echo-format) and the daily-plan result is inconclusive because of my truncation. So the condition is met for a different model than the one Step B names. Options:
1. Run Step B on `gemini-3.1-flash-lite` instead (pinned, same prompts, hard cap 30 counted at the router), with the suffix strip applied at the output layer, saving **full** (untruncated) replies. That would confirm or refute the Gemini finding on fresh replies.
2. Run Step B as specified on `gpt-oss-20b` with full replies saved, mainly to resolve the truncated daily-plan question for the gpt-oss models (the normalizer is expected, from Step A, not to help its hourly echo format).
3. Skip Step B to keep quota for the demo.
I recommend option 1 or 2 only with full-reply saving; I will not run either until you say go.

REQUEST: Approval of this round and a decision on Step B. Halting here.
