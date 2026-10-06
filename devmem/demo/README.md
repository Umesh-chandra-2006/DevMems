# Presentation mode: the memory inspector with the town replay (Phase 8)

This is the PRESENTATION ENTRY POINT. It replays a RECORDED run in upstream's town with a clock shared by two side-by-side panes, lets you click an
avatar to open that agent's memory panel at the replay time, and has a memory inspector tab and a cost view. It is READ ONLY: it never calls an LLM,
never writes to a run, needs no API key and sends nothing off the machine (React and Phaser are vendored; the town assets are served from
`reverie/environment/frontend_server/static_dirs/assets`). The Stage 3 replay further below stays as the SCRIPTED FALLBACK.

## One command (system Python with fastapi and uvicorn; versions in `devmem/api/REQUIREMENTS.md`)

Git Bash or PowerShell, from the repository root:

```bash
"/c/Users/H S R KRISHNA/AppData/Local/Programs/Python/Python313/python.exe" devmem/api/serve.py --a <left run> --b <right run> --open
```

`--a` and `--b` are run ids from `GET /runs` (a folder with a `memory.db`; a run ships `movement.zip` for the town). For the final demo they are the Phase 7/9
baseline and staged runs. Until those exist, the test recordings can be shown: `--a phase6_stepd_artifacts --b phase6_stepd_artifacts` (the natural Step D
run, partial, on both sides) or `--tab inspector --a phase6_stop3_artifacts` (the scripted Stop 3 run with all four stages). Other options: `--tab town|inspector|cost`,
`--t "2023-02-13 07:30:00"`, `--port 8765`. Stop it with Ctrl+C.

Make a recording replayable: `python -m devmem.api.movement_archive export <simulation folder> <run folder>/movement.zip` (one compressed archive with a loader;
a run that is still executing is read straight from its simulation folder, so the part already recorded can be replayed while it grows).

## What is on the screen
- **Label bar (always visible):** run id, recorded or live, scripted or natural, model, normalizer, stages, for each side. Fields the run did not declare say `unknown`.
- **Town replay:** left and right panes, one clock (play, pause, speed, scrubber). Click an avatar: its current action, where it is, dialogue lines, thoughts, and the four memory
  columns at that time (priors, episodic, semantic, identity); click a summary or a trait to highlight its sources. Drag to pan, scroll to zoom. A pane says so when its run has no
  frame at the clock time.
- **Memory inspector:** the Stop 1 timeline player and memory panel for one run.
- **Cost view:** calls and tokens by purpose per recorded ledger window (simulated hour), two runs side by side.
- **Live calls panel:** shows the router call counter of a run that is writing `run_status.json` (the arm runner does, about every simulated hour); otherwise it says no live segment is running.
It makes no claim about recall, coherence or efficiency, and it shows no score the recording does not contain.

## Rehearsal checklist (offline; run it the day before and again before the room opens)
1. `python devmem/api/serve.py --check --a <left> --b <right>` (standard library only) prints `rehearsal check: ok` and notes any missing movement or ledger for a run.
2. Start the server, open the printed URL, confirm the label bar names both runs, the clock moves when you press Play (the page must be the visible tab: browsers pause animation in a hidden tab).
3. Click one avatar in each pane; confirm the card shows an action and the four columns fill.
4. Open the Cost view and the Memory inspector tab; confirm no error banner.
5. Disconnect the network and repeat 2 to 4 (nothing may be requested outside `127.0.0.1`).
6. If anything fails: run the scripted fallback below (`devmem/demo/run_demo.py`), which also needs no network or key.
7. Optional live segment: start a short run that writes `run_status.json` into its run folder and watch the Live calls panel; a live segment uses live LLM calls (Groq keys are kept for this).

---

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
