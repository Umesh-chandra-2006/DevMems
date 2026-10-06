PHASE: 7, evaluation harness, STOP 1 (design only: no harness code, no live calls)
STATUS: Complete for Stop 1. Halting for approval. Stops 2 and 3 have not started; Phase 9 does not start before Stops 1 to 3 are approved.

Labels: **authored** (written by the Senior Developer as design data, committed before any harness output), **derived** (from reading code or from Step D numbers), **offline-captured** (computed from saved artifacts), **documented** (provider limits from `CLAUDE.md` and `providers.yaml`). No em dashes. No expected result is written into any report template.

Data files committed with this report (all **authored**): `docs/phase7_stop1_schedules.json` (authored schedules), `docs/phase7_stop1_events_questions.json` (27 events with fact sheets, 39 questions with key-fact checklists, probe questions), `docs/phase7_preregistration_draft.md`.

## 1. Experimental protocol

### 1.1 Arms
- **Arm B (baseline):** `MEMORY_MODE=baseline`, upstream memory, priors injected as atomic thought nodes (the disclosed asymmetry).
- **Arm S (staged):** `MEMORY_MODE=staged`, Stages 1 to 4 on (`STAGE4_ENABLED`, `IDENTITY_FEEDBACK` on), Stage 3 on, with the Phase 5 decision D1 as built: **staged mode disables upstream's importance-triggered reflection** (Stage 3 replaces it). This is a real asymmetry: Arm B keeps upstream reflection (extra planning-type calls and thought nodes), Arm S does not. It is disclosed, not removed (open question 1).
- Same router settings, same pinned model (`gemini-3.1-flash-lite`, normalizer on, `DEVMEM_PINNED_MODEL`), same embedding model (`gemini-embedding-001`, real, cache first), same keys policy, same authored schedules and events in both arms.
- Controls from Stage 2 run by replay (section 7), not as full simulations.

### 1.2 Compressed day (authored schedules, `docs/phase7_stop1_schedules.json`)
- The run starts at **2023-02-13 00:00** (not 06:00) and lasts **3 compressed days** (nights 1, 2 and 3 are the three distinct nights Stage 4's count path needs), 3 agents: Isabella, Maria, Klaus.
- Each day, every agent: `sleeping` 00:00 to 06:00 (360 min), awake 06:00 to 14:00 (480 min, five authored entries), `sleeping` 14:00 to 24:00 (600 min). Each day sums to 1,440 minutes (checked: 1440 for all agents). Wake-up hour is 6 for all.
- Awake entries (minutes), identical on all three days:
  - Isabella: waking up and getting ready (60); preparing the counter and the morning pastries at Hobbs Cafe (60); serving morning customers at Hobbs Cafe (180); handling the lunch counter at Hobbs Cafe (120); closing the cafe and cleaning the tables (60).
  - Maria: waking up and getting ready (60); eating breakfast at Hobbs Cafe (60); studying physics at the Oak Hill College library (180); eating lunch at Hobbs Cafe (60); working on a physics problem set at Hobbs Cafe (120).
  - Klaus: waking up and getting ready (60); walking to the Oak Hill College library (60); reading research sources at the Oak Hill College library (180); eating lunch at Hobbs Cafe (60); writing his research paper at the Oak Hill College library (120).
- Authored `daily_req` strings per agent are in the file. The schedules are hand-written from each persona's existing bootstrap facts (job, place), not from the priors text and not tuned to any event; identical in both arms and on all days.
- **Mechanism (no upstream edit):** `plan._long_term_planning` (`plan.py:461-513`) calls the module-level functions `generate_wake_up_hour`, `generate_first_daily_plan` and `generate_hourly_schedule`, then stores `f_daily_schedule` (hourly compressed entries in minutes). The harness's runner replaces those three names in the `plan` module at run time (a runtime attribute assignment in the runner script, the same kind of touch as `_tag_agents`; no file under `reverie/` changes) with functions returning the authored values. Everything downstream is upstream's: task decomposition of entries of 60 minutes or more (LLM calls, both arms), action location prompts, `revise_identity` on days 2 and 3 (LLM calls, both arms). The simulation clock and the date rollover stay upstream's.
- **Disclosed deviation** from upstream's generated schedules (the daily-plan, wake-up and hourly-schedule prompts are not called). To go into the claims ledger and the paper.

### 1.3 Night-key interaction (checkpoint `docs/phase6_night_key_checkpoint.md`)
- A sleep signal at or after hour 12 is keyed as the evening night by the current rule. On THIS schedule that is correct: sleep begins at 14:00, so night 1 is keyed at 14:00 on day 1 and the after-midnight ticks of days 2 and 3 fall on existing markers (proven on the real hook with synthetic hourly ticks: `test_night_key.py::TestPhase7CompressedDay`; the proposed block-start rule gives identical keys).
- **Constraints the schedule must keep** (go into the Stop 2 schedule checker): (a) entries tile the clock, because upstream starts an entry now with its full duration; (b) no `sleeping` entry starts before 12:00 and runs past it, no nap between 12:00 and 14:00 (the schedules have none); (c) the run starts at 00:00 so no persona starts mid-`sleeping` (Klaus 07:00 versus 13:00 in Step D); (d) a run must not end with an awake final sweep after 12:00 unless the final-sweep rule of the checkpoint (4.3) is approved; the planned run end is a sleeping tick (day 3 at 14:00 or later).
- The night-key fix is pending its own approval and must be in and tested before any Phase 9 run.

## 2. Event injection (spec 1.3)

**Mechanism (no upstream edit, same code path in both arms):** a natural event is a tile event `(subject, predicate, object, description)` in `maze.tiles[y][x]["events"]` that `perceive` reads (`perceive.py:98-125`): it takes the events on tiles within the persona's vision radius and same arena, sorts by distance, keeps `att_bandwidth` of them, skips triples already among the last `retention` events, stores the text `f"{subject} is {description}"`, embeds it and scores it with `generate_poig_score` (baseline: upstream poignancy prompt; staged: the persona-conditioned scorer). The runner script adds the injected event to the persona's OWN current tile (`maze.add_event_from_tile`, the upstream method) at the first step boundary at or after the authored sim time, and removes it (`remove_event_from_tile`) 6 steps (one simulated minute) later. The event is perceived, stored, embedded and scored exactly as an object or agent event; the timing is the sim clock, so the injection step is identical in both arms; the tile is wherever the persona is at that step, so it is always in vision and arena.
- Nothing the persona does is changed. The events are persona-neutral third-person descriptions, each with a distinct subject so the retention filter cannot swallow a repeated theme.
- Risk stated: `att_bandwidth` limits perceived events per step; if the persona is surrounded by many object events the injected one could be crowded out. The Stop 2 injector therefore verifies, per event, that its text appears in the arm's memory (a pass/fail line per event in the artifact) and the report counts any event that was not perceived (the same count in both arms is expected but not assumed).

**Events (`docs/phase7_stop1_events_questions.json`, authored, committed before any harness output):** 9 per agent, 27 total, three per day, with types: mundane (6), repeated theme across the three days (9, i.e. three themes of three), social friction (6), pivotal (3), one-off (3). Times fall inside each agent's awake window and inside the authored entry that places the agent at the event's location. Example texts as stored in memory (full list in the file): "A blue delivery van is parked outside the entrance of Hobbs Cafe" (I1, day 1 08:20); "The department chair is telling Klaus Mueller at the cafe that his research funding will be cut at the end of the month" (K5, day 2 11:20, pivotal); "A physics professor is announcing in the hallway that the midterm exam moved up to this Friday" (M5, day 2 09:30, pivotal).
- **Persona-neutral check (offline, with the existing overlap script):** `check_overlap` from `devmem/memory/p6_t_calibration.py` (written for follow-up A4, content words of 4 or more letters against the persona's priors text) returns an EMPTY result for all 27 events (9 per agent; run once at this stop; the Stop 2 check script will enforce it permanently). One event was reworded during authoring because it shared the word "above" with a prior; no event was edited after scoring because nothing has been scored.
- **Fact sheets:** each event carries who, what, where, when and one key detail (in the data file).

## 3. Questions and grading (Metric 1, recall)

**Question set (authored with the events; 13 per agent, 39 total):** per agent: 9 injected-event questions (3 per day, i.e. distance 0, 1 and 2 days when asked), 1 theme-count question, and 3 natural-event questions. All are asked at the **end of day 3** (13:30, before the 14:00 sleep), so distance is 0 days (day 3 events, 12 questions), 1 day (day 2, 12 questions) and 2 days (day 1, 15 questions including the theme-count questions and natural questions on day 1). Natural-event questions ("What were you doing at 09:00 on day 2?", "Where did you have lunch on day 1?") take their ground truth from the AUTHORED schedule, which is the recorded plan in both arms; any further natural questions built from the recorded event stream are added at Stop 3 (a recorded stream exists only after a run), never altered afterward.
- **Answering path (same for both arms, no judge):** the agent's own retrieval (`new_retrieve` over its own memory, the same top-k) then one LLM call with one fixed prompt (purpose `eval_recall`). To avoid perturbing the run (upstream retrieval updates `last_accessed`), recall and probe questions are asked on a COPY of the saved state: the harness copies the saved simulation folder at the end of the awake window of each evaluated day and runs the questions against the copy, never against the live run. The Stage 3/4 hooks do not fire on the copy.
- **Primary score: automatic key-fact checklist.** Each question has 1 to 4 checklist items (names, objects, times), each with a list of acceptable surface forms (`any_of`), in the data file. Matching rule: lowercase, strip punctuation and the articles a, an, the, number words to digits ("three" and "3" both listed), simple plural folding, and substring match of each normalized form in the normalized answer. Per-question score = items matched / items; "strictly correct" = all items matched. An answer that says it does not remember scores 0. NO LLM judge for the primary score. Raw answers are saved verbatim.
- **Validation of the rule:** at least 30 hand-labelled answers (authored at Stop 2: 10 correct, 10 partial, 10 wrong, including paraphrases and near misses) with the label written before the rule is run; report the agreement (exact label agreement and the per-class confusion). A rule below 80 percent agreement is reported as such and the recall results are marked uninterpretable.
- Report: accuracy per arm, per distance, per agent, per question type, n shown everywhere.

## 4. Probe interviews and the judge (Metric 2, coherence)

- **Standard questions** (same for all agents, in the data file): P1 describe yourself in three sentences; P2 how do you react when someone is rude to you; P3 how do you feel about meeting new people; P4 what matters most to you in your daily life; P5 how would you describe your relationship with each of the other two residents you know; P6 how are you feeling about your work lately. Asked at the end of day 1 and of day 3 on checkpoint copies, through the same answering path (retrieval over the agent's own memory plus one fixed-prompt call, purpose `eval_probe`). 6 questions x 3 agents x 2 times = 36 answers per arm.
- **Pairs and judge:** the day-1 and day-3 answers to the same question form one pair (18 pairs per arm). The judge is the pinned model with a fixed rubric (consistent, contradictory, unrelated; one call per pair, purpose `eval_judge`, the rubric text is saved with the results). Output parsed by exact label match; anything else is a counted parse failure, never a guess.
- **Calibration:** at least 20 authored pairs with known labels (7 consistent, 7 contradictory, 6 unrelated, authored at Stop 2 and committed before the judge sees them); accuracy and the confusion matrix are printed next to EVERY coherence result. **If accuracy is below 80 percent the report states that coherence results are not interpretable** and shows them only as raw labels. Calibration pairs are run once (about 20 calls, not per arm).
- Natural dialogue is not used (absent in Step D).

## 5. Efficiency (Metric 3) and the ledger

- **One ledger** (the `db_path` forwarding is fixed, follow-up A1): per simulated day and per arm, calls and tokens by purpose (planning, decomposition, importance scoring, dialogue, reflection, consolidation, identity), and mean prompt tokens per call by purpose from the raw-reply log; evaluation purposes (`eval_recall`, `eval_probe`, `eval_judge`) are tagged at the call site and **excluded** from the per-day figures and reported separately.
- **Ledger splitter (design):** the runner records the ledger row window at every simulated hour (as the Step D script did); the splitter assigns rows to simulated days and hours by those windows and to arms by run folder. Retrieved-context tokens: simulation prompts in these runs contain little or no retrieved memory (Step D had no dialogue; staged reflection is off), so "mean retrieved-context tokens per call" is reported from the evaluation recall prompts and from any simulation prompt that includes retrieval, with the count of such prompts; this is stated up front so a zero is not misread.
- Supplementary (from the plan): the fraction of episodic entries consolidated over time (from `episodic_memory.consolidated` and the sweep log), and whether raw detail stays reachable when its summary is retrieved (a retrieval check over the evaluation copy). Differences are reported with both signs possible.

## 6. Diagnostics (zero LLM)
- **Trait provenance:** for each Stage 4 trait, cosine to its source events and to the agent's priors text (real embeddings, cache first); flag traits closer to the priors than to their sources; report the fraction flagged. (Motivation: Stop 3's pivotal trait contained content its source event lacked.)
- **Stage 3 cluster quality:** cluster size histogram, merge cosines, summaries verbatim, and the number of entries merged between 0.80 and 0.88.

## 7. Controls by replay (spec 1.4)
Record the full event stream of the Arm S run (events and sim times) from the mirror. Replay it through the scorer only, under (a) staged priors, (b) mismatch priors (another persona's), (c) neutral filler, (d) baseline scoring; one scoring call per event per condition, no planning calls, same pinned model. Measures scoring effects only. n equals the number of recorded events per agent (Step D had 445 scored events for one agent in 7.75 hours, so about 450 per condition per day is the working figure of the spec). No behavioral claim.

## 8. Budget table (**derived**; replace with measured at Stop 3)

Assumptions: about 110 calls per awake agent-hour (Step D, one awake agent: 104 averaged, 119 after the first hour; Maria's and Klaus's rates are NOT measured); 3 agents x 8 awake hours x 3 days = 72 awake agent-hours per arm; sleeping hours about free (Step D: 4 calls in 15 sleeping agent-windows); authored plans save about 20 calls per agent per day (no wake-up, daily plan, hourly schedule prompts); Stage 3 and 4 add about 10 calls per agent per night to Arm S; the observed throughput is about 6 calls per minute per process (904 calls in 146 minutes).

| Item | Calls |
|---|---|
| One arm, 3 agents, 3 days (110 per awake agent-hour, minus the replaced planning) | about 7,900 less 180 = about 7,700 |
| Arm S extras (Stage 3 and 4, about 10 per agent-night x 9) | about 90 |
| Two arms | about 15,500 |
| Replays (about 450 per condition per day x 4 conditions x 3 days) | about 5,400 |
| Evaluation per arm: recall 39 (cap 200), probe 36 (cap 150), judge 18 (cap 150) | about 93 per arm, about 190 for both arms |
| Judge calibration (once) | about 20 |
| Total | **about 21,100 calls** |

Per provider against current quota (**documented**; the model is pinned to Gemini by the Phase 5 decision, so other providers are listed for capacity only and are not used unless the model decision changes):

| Provider | Usable now | Capacity per day | Days for 21,100 calls |
|---|---|---|---|
| Gemini `gemini-3.1-flash-lite` (chat), 5 keys | keys 1, 2, 4, 5, 6 | 15 RPM and 500 RPD per key = 2,500 per day (2,000 per day at the 400-per-key demo limit) | about 8.5 days (about 10.5 at 400) |
| Gemini, plus about 10 incoming key sets (provider not stated; if all are Gemini at 500 per day) | not yet verified | up to about 7,500 per day with 15 keys | about 3 days |
| Groq, 9 keys | listed only | 1,000 RPD per key (gpt-oss) | not used (pinned model) |
| NVIDIA NIM | listed only | 40 RPM, RPD unknown | not used (pinned model) |
| Gemini embeddings (`gemini-embedding-001`) | keys 1, 3 to 6 | 100 RPM, 1,000 RPD per key | not a constraint (Step D used 88 requests; the trait provenance diagnostic and the cache add few) |

Wall time: one arm of about 7,800 calls at 6 calls per minute is about 22 hours; two arms in two parallel processes about 22 hours each; replays (single call per event) about 15 hours sequential. Caps for Stop 3 (validation on recorded data) are 80 router-counted calls, as in the spec; the Phase 9 caps will be set from the measured table.

## 9. Pre-registration draft
`docs/phase7_preregistration_draft.md` (metrics, comparisons, grader, judge, exclusion rules, directional predictions per persona). It becomes `docs/phase7_preregistration.md` and is committed before the first Phase 9 run.

## 10. COMPLIANCE TABLE (spec sections 1 to 7)

| Requirement | Status | Where |
|---|---|---|
| Protocol 1.2: authored schedules, start 00:00, awake 06:00 to 14:00, 3 days, 3 agents, edit schedule never clock, identical in both arms, not derived from priors, disclosed deviation | Designed; data authored and tiles to 1440 | section 1.2, `phase7_stop1_schedules.json` |
| Night-key checkpoint covers this schedule; fix before Phase 9 | Covered; fix awaiting approval | section 1.3, `phase6_night_key_checkpoint.md` |
| Event injection mechanism, no upstream edit, same path as a natural event, identical sim times | Designed (tile event on the persona's own tile through upstream methods) | section 2 |
| Events: 8 to 10 per agent, mixed significance, persona-neutral wording with an overlap check, fact sheets, committed before any harness output | 9 per agent; overlap check run, empty; fact sheets included | section 2, data file |
| Questions: at least 12 per agent at three distances, injected and natural, natural from the recorded stream | 13 per agent; natural questions use the authored schedule; stream-based natural questions deferred to Stop 3 | section 3 |
| Grader: key-fact checklist, no LLM judge, validated on 30 hand-labelled answers | Designed; labels authored at Stop 2 | section 3 |
| Judge: fixed rubric, calibrated on 20 authored pairs, accuracy beside every result, below 80 percent means not interpretable | Designed | section 4 |
| Efficiency from ONE ledger, evaluation purposes excluded, both signs possible | Designed; `db_path` fix done (A1) | section 5 |
| Diagnostics: trait provenance, Stage 3 cluster quality | Designed | section 6 |
| Controls by replay (a to d) | Designed | section 7 |
| Budget table per provider against quota | Given with assumptions | section 8 |
| Pre-registration draft with directional predictions | Written | `phase7_preregistration_draft.md` |
| No code, no live calls, no upstream edit | Compliant (data files and one existing offline script run) | n/a |

## 11. DEVIATIONS (complete)
- The overlap check reused `devmem/memory/p6_t_calibration.py::check_overlap` (written for A4) as a one-time offline validation; no new code was added for Phase 7.
- The data files were generated by a throwaway authoring script kept outside the repository (it only wrote the two JSON files); the files are the authoritative artifact.
- Arm S disables upstream reflection (decision D1) while Arm B keeps it (section 1.1).

## 12. OPEN QUESTIONS
1. **Reflection asymmetry:** keep D1 as built (Arm S without upstream reflection, Arm B with it, disclosed), or add an Arm S2 with reflection on (a third arm, about 7,700 more calls)? My recommendation: keep D1 and disclose; the efficiency difference then includes the removal of reflection calls, stated in the report.
2. **Evaluation on checkpoint copies** (so evaluation never perturbs the run) instead of asking questions inside the live run. This needs the saved state at the end of days 1 and 3 and means the evaluation cannot influence the simulation. Approve?
3. **Injection on the persona's own tile** at the first step boundary at or after the authored time (always perceived, same step in both arms) versus placing the event on a tile in the location where the schedule puts the persona. Approve the first?
4. **`revise_identity` on days 2 and 3** is an upstream LLM call that remains (both arms); it adds a few planning calls and may rewrite the persona's `learned` text from the day's events. Keep as upstream does?
5. **Provider capacity:** which providers are the about 10 incoming key sets, and are they usable with the pinned Gemini model? Until known, the table counts only the 5 Gemini keys.
6. **Questions about natural events from the recorded stream** are deferred to Stop 3. Acceptable?

REQUEST: Approval of Stop 1 and answers to questions 1 to 6. Halting.
