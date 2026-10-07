# Phase 9 evaluation plan (PREPARED, not started): steps, calls, and time at the measured rate

Source: `docs/phase7_spec_evaluation_harness.md`, `docs/phase7_stop1_report.md`, `docs/phase7_stop1_events_questions.json`, `docs/phase7_preregistration.md`. Evaluation calls carry their own ledger purposes (`eval_recall`, `eval_probe`, `eval_judge`) and are never included in the per-day efficiency figures. All answers run on the checkpoint copies, never on the live runs.

## What exists and what does not
- **Exists (committed):** authored events, 39 questions with key-fact checklists, 6 probe questions, schedule and event checkers, the arm runner that makes the checkpoint copies (steps 5,130 and 22,410), the ledger windows, the viewer.
- **Not built yet (Phase 7 Stop 2b, the offline build that was to follow launch):** the answer harness over a checkpoint copy, the key-fact grader with its 30-label hand validation, the judge prompt with 20 authored calibration pairs, the ledger splitter, the provenance and cluster diagnostics, the replay-controls runner. None of these needs a live call to build. **Recommendation: build them now, offline, while the arms run, so that the day-3 end is the only wait.** This needs the PM's word.

## Steps, calls and time

Rates used: measured after the 429 change, 4.3 and 4.9 successful calls per minute per arm (about 9 per minute with both pools in parallel). Evaluation can use both arms' pools in parallel once the runs have ended. These are estimates from an 8-minute window and will move.

| Step | Calls (live) | Per arm | At the measured rate (both pools in parallel) |
|---|---|---|---|
| 1. Recall answers on the day-3 checkpoint copy (39 questions per arm, one call each, `eval_recall`) | 78 | 39 | about 9 minutes |
| 2. Probe interviews, 6 questions x 3 agents x 2 checkpoints (day 1 and day 3), `eval_probe` | 72 | 36 | about 8 minutes |
| 3. Judge, 18 day-1 against day-3 answer pairs per arm, `eval_judge` | 36 | 18 | about 4 minutes |
| 4. Judge calibration on 20 authored pairs (once; can run before the day-3 end, on the free pool or the paid key) | 20 | none | about 3 minutes |
| 5. Grader validation on 30 hand-labelled answers | 0 (offline) | none | none |
| 6. Diagnostics: provenance cosines (cached embeddings), Stage 3 cluster quality, ledger splitter | 0 live | none | minutes of CPU |
| **Steps 1 to 4 total** | **about 206** | | **about 25 minutes** (below the spec caps of 200 recall, 150 probe, 150 judge per arm) |
| 7. Replay controls (scorer only, no planning): conditions mismatch priors, neutral filler, baseline scoring (the staged condition reuses the run's own scores); one call per event per condition | 3 x N events | | see below |

**Replay size (decision for the PM).** N is the number of importance-scoring events of the staged arm. From the pilot, staged scoring was about 79 calls per awake agent-hour, so a full 72 awake agent-hours gives N of about 5,700 and about 17,000 replay calls: roughly 31 hours at 9 calls per minute, which does not fit. Options: (a) a fixed stratified sample of 300 events per condition (900 calls, about 1.7 hours), chosen by a stated rule before looking at any score (for example every k-th event per agent, stratified by authored event type); (b) the events within the three authored days' injected-event windows only; (c) the full replay on a paid key. N is measured exactly from the staged `llm_call_log` at the run end; the table above is re-issued then.

## Order after the day-3 end (start within 30 minutes)
1. Confirm both arms `finished` and both checkpoint copies exist (`checkpoints_made` in `run_status.json`); run the canary evaluation on each arm.
2. Steps 1 to 3 in this order per arm (recall, probe, judge), each with the fixed prompts saved beside the results; parse failures counted, never guessed.
3. Step 7 on the PM's chosen sample, after the answers (so the pools are not shared with the arms).
4. Reports: efficiency from one ledger (evaluation excluded), recall and coherence with the grader and judge accuracy printed beside every result, diagnostics, and the directional-prediction table of the pre-registration, right or wrong, labelled with the run conditions (the 429 change, the pause, the key counts, the clocks).
