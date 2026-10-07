# Procedure (PREPARED, NOT RUN): moving both arms to a paid-tier key

Status: draft for the PM and the Owner. Nothing here has been executed and no code has been changed for it. It needs the PM's word. No em dashes, no key values.

## 0. Preconditions (all must hold before step 1)
1. The Owner has put two paid-tier test keys in `.env` under names the PM approves (for example `GEMINI_PAID_KEY_BASELINE` and `GEMINI_PAID_KEY_STAGED`), one per arm, so that the arms keep **disjoint** key sets. A single shared paid key would break the disjoint-pool rule and needs an explicit PM exception.
2. `python -m devmem.eval.latency_probe --paid <NAME> --free <free key NAME> --n 100 --embeddings 50` has been run for each paid key and the PM accepted its numbers (calls per minute, latency percentiles, 429, 503, timeouts against a free key in the same minute).
3. The paid limits are copied from the AI Studio console by the Owner: requests per minute, tokens per minute, requests per day (if any) for `gemini-3.1-flash-lite`, and the same for `gemini-embedding-001`. They are inputs; none is invented here.
4. The model stays `gemini-3.1-flash-lite`, the embedding model stays `gemini-embedding-001`, the output normalizer stays on, all other settings are unchanged.

## 1. What changes in the code (small, tested, identical for both arms)
- **Pool selection** (`devmem/eval/run_arm.py`): a file `paid_keys.json` in the run folder, `{"keys": [<one env name>], "rpm": <console value>, "rpd": <console value or null>, "mode": "paid_first"}`. `load_extra_keys` style loader: the name must be set in the environment, must not appear in the other arm's file, and is never printed (only its role, "paid", is logged).
- **Per-key caps adapted to the paid limits:** the free-tier per-key cap of 450 requests per quota day is replaced for the paid key by the console `rpd` (or no daily cap if none) and the router's RPM pacer reads the console `rpm` from the temporary provider configuration (`model_limits[model]["rpm"]`), the same mechanism the free keys use. The free keys keep 450.
- **Mode `paid_first` (recommended):** the paid key is tried first on every call and the free keys remain as spill-over, subject to the same rule as now (at most 3 keys per call on a 429, then backoff with jitter, no fail-safe). Alternative `paid_only`: the free keys are removed from the arm for the rest of the run; simpler to describe, but one outage or a paid 429 then pauses the arm.
- **Embeddings:** the paid key is added to the arm's embedding keys with the embedding console limits; the embedding cache is shared and unchanged.
- **Tests to add (offline, zero calls):** the paid key is first in the rotation; the free keys are still used after it fails; the paid limits reach the pacer; a paid key in both arms is refused; no key text appears in any log line; the disclosure line is written to `key_changes.jsonl`.

## 2. How it is applied (a supervisor restart at an autosave, no replay)
1. Commit and key-scan the code change; run the full suite and `test_run_arm_smoke`.
2. For each arm write `paid_keys.json` and the `KEY_CHANGE` marker in the run folder (no `PAUSE_FOR`, unless the PM wants a pause). The arm stops at its next autosave with outcome `key change restart ...`, the supervisor resumes it from that autosave (no crash count, no replay), and `code_version.jsonl` records the commit.
3. Check: `resume_log.jsonl` shows `key_change_resume`; `key_changes.jsonl` shows the arm and the role "paid"; `arm_health` is RUNNING; the first window after the restart shows the call rate.
4. The two arms switch at different clocks (each at its own next autosave). Both clocks are recorded.

## 3. Disclosure text (fill the clocks after the fact)
Claims ledger (next free id) and pre-registration deviation 7e:

"From simulated clock <baseline clock> (step <n>, <IST time>) the baseline arm, and from <staged clock> (step <n>, <IST time>) the staged arm, used one paid-tier Gemini key first for chat and embeddings, with the free keys as spill-over, on the same model and normalizer, because free-tier throttling (429, 503 and read timeouts) held the arms to about <measured> successful calls per minute. The paid limits used were <rpm> per minute and <rpd> per day from the console. The change is a run condition, not a design change: memory is still the only variable. The two arms switched at different simulated clocks, so wall-time and call-rate comparisons must carry that difference. Paid key identity and project are not recorded in any artifact."

## 4. Cost note
A paid-tier key spends the Owner's trial credits and breaks the zero-API-cost constraint in `CLAUDE.md`. That needs the Owner's and the PM's explicit decision before step 0 item 1.

## 5. Rollback
Write `paid_keys.json` with an empty key list and a `KEY_CHANGE` marker: the arm restarts at its next autosave on the free pool only.
