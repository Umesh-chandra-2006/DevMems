# Stage 3 demo

**Label: SCRIPTED.** The day shown is a hand-written set of 16 events for Isabella Rodriguez
(`devmem/memory/fixtures/scripted_day_isabella.json`), not a simulation run. Embeddings and summaries are real model outputs
that were saved earlier; the demo does not claim anything about recall quality, efficiency or coherence.

Run every command from the repository root `D:\DevMems`. The scripts set UTF-8 output themselves, so no
`PYTHONIOENCODING` setting is needed on Windows.

## Replay mode (default): no network, no API keys, no LLM calls

PowerShell:

```powershell
.\.venv\Scripts\python.exe devmem\demo\run_demo.py
```

Git Bash:

```bash
.venv/Scripts/python.exe devmem/demo/run_demo.py
```

Only one threshold run (the file contains two: 0.78 approved default, and 0.82 calibrated on this single day):

```powershell
.\.venv\Scripts\python.exe devmem\demo\run_demo.py --run 0.82
```

It reads `docs/phase5_step3_artifacts/demo_replay_data.json` (committed). Output is deterministic: two runs print identical
text (about 280 lines for both runs, about 140 for one).

### Expected output headings (in this order, once per threshold run)

```
STAGE 3 DEMO, REPLAY MODE: scripted day for Isabella Rodriguez (2023-02-13)
# RUN: threshold 0.78 (approved default)
1. EPISODIC ENTRIES AFTER THE SWEEP (...)      time, importance, consolidated yes/no, text
2. CLUSTERS  (threshold 0.78, single linkage; entries considered 12, flagged 11)
                                                cluster-size histogram, each cluster's entries, entries left raw and why
3. SEMANTIC MEMORIES (summary and the source entry ids it references)
                                                each summary, importance, source node ids and source texts, second-sweep result
4. RETRIEVAL RANKING (real new_retrieve; '*' = summary thought, 'c' = consolidated source entry)
                                                three focal points; columns consolidated_weight 0.5 | consolidated_weight 1.0
# RUN: threshold 0.82 (calibrated on this one day)
(the same four sections)
```

For the 0.78 run the header line of section 2 reports 11 entries flagged and a histogram of `{'1': 1, '4': 1, '7': 1}`; for
0.82, 9 flagged and `{'1': 3, '4': 1, '5': 1}`.

## Live mode: real embeddings and at most 4 LLM calls

Needs `.env` with working keys (Groq for the pinned model `openai/gpt-oss-20b`, Gemini for embeddings). One sweep at the
approved default threshold 0.78: 2 summaries + 2 importance scores = 4 calls. A guard raises if a 5th call is attempted.

```powershell
.\.venv\Scripts\python.exe devmem\demo\run_demo.py --live
```

Expected: a first line `STAGE 3 DEMO, LIVE MODE (at most 4 LLM calls; real embeddings; scripted events)`, then
`LLM calls made: 4 (cap 4)`, then the same four sections as replay (the retrieval ranking has no score column, and the events
table has no time column). The summaries differ from run to run because the model's wording varies.

## Regenerating the replay data (offline, no network)

```powershell
.\.venv\Scripts\python.exe devmem\demo\export_demo_data.py
```

Needs the local saved scripted-sweep databases and the embedding cache under `devmem/storage/` (git-ignored), so it only
works on the machine that ran the sweeps.

## Test

```powershell
.\.venv\Scripts\python.exe -m unittest devmem.demo.test_demo
```

Runs replay with network sockets blocked and checks the headings, every summary with its source texts, and both rankings.
