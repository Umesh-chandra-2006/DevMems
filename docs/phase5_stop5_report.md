PHASE: 5, erratum, model-qualification probe, demo hardening, claims ledger
STATUS: Complete as specified. No other live runs were made.

Paths are relative to the repository root. `ART/` = `docs/phase5_step4_artifacts/`. Everything from the probe is **live**; the post-processing is **offline-captured**.

## WHAT WAS BUILT

- **Erratum** appended to `docs/phase5_stop4_report.md` (no other number edited). The ledger shows 286 continuation calls (planning 253, dialogue 13, importance scoring 20), not 266. The 266 was my cap counter, which wraps `gpt_structure.call_llm`; the 20 staged importance-scoring calls go through `episodic.py`'s own `call_llm` import and bypassed it. It was not a step-boundary effect. Phase 1 (138 counted = 138 ledger) and the earlier smoke run (100 = 100) are unaffected. The cap rules were therefore enforced on non-scoring calls only; any further capped run should count at the router.
- **Model-qualification probe** (`devmem/memory/p5_model_probe.py`, post-processing `p5_model_probe_report.py`).
- **Demo hardening** (`devmem/demo/run_demo.py`, `devmem/demo/README.md`).
- **Claims ledger** (`docs/CLAIMS_LEDGER.md`): 7 sections (28 claim rows plus the not-demonstrated list) including the Stage 2 control results, the Stage 3 scripted sweep, the live hook observation, the recency finding, the capacity measurements, and a 12-item list of things NOT demonstrated.

## HOW IT MATCHES THE SPEC (compliance table)

| Item | Status | File | Proof |
|---|---|---|---|
| Erratum: state the ledger count, explain the difference, append only | Done | `docs/phase5_stop4_report.md` (end) | ledger rows in `docs/phase5_step3_artifacts/p5_staged_live_continue_hourly_ledger.jsonl` |
| Probe: real upstream prompt functions (wake-up hour, daily plan, hourly schedule), Isabella's saved state, 3 models pinned per call, up to 3 repeats, cap 40 | Done; stopped at **exactly 40 calls** during repeat 3 | `p5_model_probe.py` | `ART/model_probe.json` (live) |
| Probe: valid rate, echo rate, calls per valid result including upstream retries, tokens; no upstream edits | Done | `ART/model_probe_summary.json/.md` | `git status reverie` clean |
| Demo runs on Windows from a fresh shell without an encoding crash | Done: reproduced the crash, fixed it | `run_demo.py` (UTF-8 reconfigure) | two fresh PowerShell runs: exit 0, 280 lines each, identical, no traceback; one fresh Git Bash run: exit 0, 143 lines; `test_demo` 2 tests OK |
| `devmem/demo/README.md` with exact commands and expected headings | Done | `devmem/demo/README.md` | headings match the observed output |
| Claims ledger | Done | `docs/CLAIMS_LEDGER.md` | evidence paths in each row |
| No other live runs | Compliant | n/a | ledger: only the 40 probe calls |

## PROBE RESULTS (live; verbatim data in `ART/model_probe.json`)

Fixed inputs for all models: Isabella's saved fork state at 2023-02-13 00:00; wake-up and daily-plan prompts as upstream builds them (plan asked for wake hour 6); hourly schedule for the 07:00 AM slot with a reference plan (upstream's own default plan) and a prior schedule of 7 hours of "sleeping". Upstream's retry loop (up to 5 attempts) was left in place and every attempt counted. Coverage under the 40-call cap: wake-up 3 repeats per model, daily plan 2, hourly schedule 2 (a third daily-plan invocation for `gpt-oss-20b` was cut off by the cap after 2 calls and is excluded from the rates).

| Model | Wake-up valid (answers; calls) | Daily plan: validator passed / usable plan; calls | Hourly: valid / echo / "(duration in minutes...)" suffix / clean; calls | Tokens in / out |
|---|---|---|---|---|
| openai/gpt-oss-20b | 3/3 (6, 6, 6; 3 calls) | 1/2 / **0/2**; 7 calls | 2/2 / **2** / 0 / **0**; 5 calls | 9,760 / 17,532 |
| openai/gpt-oss-120b | 3/3 (6, 6, 6; 3 calls) | 1/2 / **0/2**; 10 calls | 2/2 / **1** / 0 / **1**; 2 calls | 7,760 / 18,693 |
| gemini-3.1-flash-lite | 3/3 (6, 6, 6; 4 calls) | 2/2 / **0/2**; 2 calls | 2/2 / **0** / **2** / **0**; 2 calls | 4,436 / 3,302 |

Definitions: *valid* = upstream's own validator accepted some attempt (a fail-safe return is not valid; for the plan and hourly prompts also a non-trivial result); *echo* = the `schedule_check` rule (configured marker, or a leading `[... Activity:`); *usable plan* = at least 2 non-empty items after the prepended wake-up line; *clean hourly* = valid, not echo, no duration suffix. Calls per valid result including retries, all prompts together: `gpt-oss-20b` 3.0 (15 calls, 5 valid), `gpt-oss-120b` 3.0 (15, 5), `gemini-3.1-flash-lite` 1.14 (8, 7). The live script's own summary (`ART/model_probe.json`) uses upstream-validity only; the table above adds the stricter columns from the same recorded outputs.

What the data shows, and what it does not:
- Wake-up hour: all three models answered "6" in 9 of 9 invocations (Gemini needed one retry once).
- Daily plan: **no model produced a usable plan** under upstream's parser in any of the 6 completed invocations. The raw replies are sensible plan text (verbatim samples in the artifact, for example "1) Wake up and complete morning routine at 6:00 am ..."). Upstream's parser rejects replies in formats such as narrow no-break spaces (U+202F) in "6:00 am" or "(duration in minutes: 30, minutes left: 990)" suffixes: the gpt-oss models fell back to upstream's fail-safe plan in 1 of 2 repeats and in the other passed the validator with only the prepended wake-up line; Gemini passed the validator in both repeats but yielded only empty items. The cause of those formats was **not tested** (no run without the repo's system prompt that asks for the duration format), so I make no claim about it.
- Hourly schedule: both gpt-oss models produced the echo format ("[(ID:ABCDEF) Monday February 13 -- 07:00 AM] Activity: Isabella ...") in 3 of 4 outputs; Gemini produced no echo but appended "(duration in minutes: 60, minutes left: 0)" to both outputs, which `schedule_check` does not flag (it would become activity text). Only one of the six hourly outputs (`gpt-oss-120b`, repeat 2: "having breakfast and reviewing the day’s schedule") was clean.
- No model "cannot plan" is shown. This is 40 calls, 2 to 3 repeats, three prompts, one persona state.

## DEVIATIONS (complete)

- New files: `devmem/memory/p5_model_probe.py`, `p5_model_probe_report.py`, `devmem/demo/README.md`, `docs/CLAIMS_LEDGER.md`, `docs/phase5_step4_artifacts/`. Edited: `devmem/demo/run_demo.py` (stdout and stderr reconfigured to UTF-8 with `errors="replace"`), `docs/phase5_stop4_report.md` (erratum appended only).
- The probe sets `utils.FAIL_LOUD_LLM` true and wraps `gpt_structure.call_llm` and the run_gpt_prompt module's `safe_generate_response` in memory (spies); no upstream file was edited. Models were pinned per call through `DEVMEM_PINNED_MODEL`.
- The router's passive 429 capture appended to the tracked fixture `devmem/router/fixtures/429/observed.jsonl` during the live probe (captured real 429s); committed as captured.
- The probe's hourly-schedule inputs (reference plan and prior schedule) are fixed test inputs, not the live run's state.

## TESTS

Full suite, offline default (`ART/full_suite_output_offline_default.txt`), verbatim:

```
=== devmem.router.test_router
Ran 33 tests in 3.865s
OK
=== devmem.memory.test_priors
Ran 9 tests in 2.840s
OK
=== devmem.memory.test_episodic
Ran 10 tests in 1.540s
OK
=== devmem.memory.test_reconcile
Ran 10 tests in 38.592s
OK
=== devmem.memory.test_gpt_structure_touch
Ran 5 tests in 0.055s
OK
=== devmem.memory.test_consolidation
Ran 27 tests in 15.562s
OK (skipped=1)
=== devmem.embeddings.test_vector_store
Ran 14 tests in 1.697s
OK (skipped=1)
=== devmem.demo.test_demo
Ran 2 tests in 0.052s
OK
```
110 tests, 2 live-gated skipped (unchanged from the previous round).

## OPEN QUESTIONS

1. The probe suggests the blocker for usable schedules is output format versus upstream's parsers, not model capability, but that is a hypothesis. Do you want a controlled follow-up (same prompts with and without the repo's system prompt), which needs a fresh call budget?
2. Counting caps at the router instead of at `gpt_structure.call_llm` would make caps exact; it is a small router change. Approve for future runs?

REQUEST: Approval of this round. Halting here.
