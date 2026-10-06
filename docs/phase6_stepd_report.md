PHASE: 6, STEP D (natural live run on Gemini, staged, Stage 3 on, Stage 4 off)
STATUS: Complete as a PARTIAL run: it ended at its soft cap at simulated 13:45 on day 1, before any night. Halting for your decision on a follow-up (section 10).

Paths are relative to the repository root unless they start with `D:\DevMems_stepd` (the isolated worktree). Labels: **live** (the run), **offline-captured** (computed from the saved live artifacts, no network), **derived**. No em dashes are used in files added this round.

## 1. WHAT WAS RUN (**live**)

- Isolation: git worktree `D:\DevMems_stepd` detached at 9c60c86 (contains the Step D script), its own storage, a copy of `.env`, of the git-ignored upstream `utils.py` and of the embedding cache. Background process; the Stop 2 and Stop 3 work ran in the main tree meanwhile. The first launch failed at once with `No module named 'utils'` before any call (that file is git-ignored upstream config); copied and relaunched. Nothing was lost.
- Script `devmem/run_step_d.py` (committed 9c60c86): 3 agents (Isabella, Maria, Klaus), staged mode, `STAGE4_ENABLED` off, Stage 3 on, normalizer on, raw-reply log on, pinned `gemini-3.1-flash-lite`, start 2023-02-13 06:00, target 2023-02-14 08:00, autosave every 15 sim minutes, hard cap 1200 router calls, soft stop 900, per-key stop 380 (limit 400), real embeddings through the cache with a counted HTTP layer (soft 130, hard 150, fail loud). Chat keys 4, 5, 6 rotated.
- **Outcome:** `soft stop: 900 router calls reached at a step boundary` at simulated **2023-02-13 13:45:10** (step 2791), clean exit and final save, no upstream exception, so no resume was needed. Wall time 8,789 s (2.44 h).

## 2. COUNTS (**live**; artifacts `docs/phase6_stepd_artifacts/step_d_report_first.json`, `hourly_ledger.jsonl`, `raw_replies.jsonl`)

| Item | Value |
|---|---|
| Router-counted calls | **904** (cap 1200, soft 900): planning 410, importance scoring 445, other (object/action prompts) 49; equals the 904 records in the raw-reply log |
| Chat requests by key (router ledger) | GEMINI_KEY_4 314, GEMINI_KEY_5 297, GEMINI_KEY_6 293 (all under 400) |
| Embedding requests | **88** real requests (cap 150, soft 130), all HTTP 200, 18 cache hits, 106 texts; spread over keys 1, 3, 4, 5, 6 (18, 18, 18, 17, 17) |
| HTTP 429 | **none** |
| HTTP 503 (Gemini overload), each absorbed by the router | key 4: 21, key 5: 25, key 6: 33; timeouts (15 s): key 5: 5, key 6: 1, key 4: 1 (`stepd_analysis.json`) |
| Router failures (`ROUTER_FAILURES`) | **0** |
| Autosaves | 32 (every 90 steps), schedule scan `clean`, 0 findings |
| Normalizer | wake-up hour 4 applied / 4 changed; daily plan 3 / 3; hourly schedule 50 / 50; other call paths 837 applied / 149 changed; the 10 task-decomposition calls were vetoed (894 applied of 904) |
| Retries (upstream re-sends of the same prompt) | **1 in 904 calls**: Klaus's wake-up-hour prompt (first reply `7:00 AM (duration in minutes: 0, minutes left: 960)`, delivered `7:00 AM` after the normalizer, rejected by upstream's validator; the second attempt was accepted). Every other prompt type: 0 retries, 100 percent first-attempt acceptance (`step_c_analysis.md` in the artifact folder is the per-type table) |

## 3. COST PER PROMPT TYPE, PER SIMULATED HOUR, PER AGENT (**offline-captured** from the raw log aligned to the router ledger; alignment check passed for all 904 records)

Replaces the n=2 estimate. An agent-window is "sleeping" when more than half of its steps in that window were sleeping (steps counted by the script). Day-start planning (step 0) is reported separately. Full per-window per-agent per-type table: `stepd_analysis.json` (`windows`).

**Totals by prompt type** (calls; tokens in / out):

| Prompt type | Calls | Tokens in | Tokens out |
|---|---|---|---|
| staged importance scoring | 445 | 195,082 | 20,073 |
| generate hourly schedule | 50 | 71,033 | 21,882 |
| action location sector / object | 49 / 49 | 29,176 / 17,142 | 1,005 / 786 |
| action object | 49 | 16,051 | 199 |
| event triple / pronunciatio | 98 / 98 | 26,483 / 6,866 | 1,862 / 757 |
| object event | 49 | 6,356 | 554 |
| task decomposition | 10 | 9,880 | 2,688 |
| wake-up hour / daily plan | 4 / 3 | 1,146 / 1,082 | 842 / 888 |

**Day-start planning (step 0):** 85 calls, 83,316 in / 25,024 out (Isabella 29, Maria 26, Klaus 30).

**Awake versus sleeping, per agent (excluding step 0):**

| Agent | State | Agent-windows | Calls | Tokens in / out |
|---|---|---|---|---|
| Isabella | awake | 8 (7.75 simulated hours) | 804 | 291,572 / 25,955 |
| Isabella | sleeping | 0 | 0 | 0 |
| Maria | awake | 0 | 0 | 0 |
| Maria | sleeping | 8 | 2 | 831 / 8 |
| Klaus | awake | 1 (13:00 to 13:45) | 11 | 3,819 / 541 |
| Klaus | sleeping | 7 | 2 | 759 / 8 |

**Isabella awake, per simulated hour** (calls): 06 to 07: 2 (a long first action), 07 to 08: 126, 08 to 09: 157, 09 to 10: 128, 10 to 11: 55, 11 to 12: 101, 12 to 13: 92, 13:00 to 13:45: 143. Averages: about **104 calls per awake hour** over all 7.75 hours (37.6k tokens in, 3.3k out), about **119 per hour** over the 6.75 hours after the first. **Scoring is 49 percent of all calls** (445 of 904; per Isabella hour after the first, 23 to 94 scoring calls). A sleeping agent costs almost nothing (2 calls in 7 to 8 agent-hours). Klaus awake: 11 calls in 0.75 h (one window; not a rate). The sample is one awake agent over 7.75 hours; Maria and Klaus's awake rate is not measured.

## 4. WHAT RAN AND WHAT DID NOT

- **Conversations: none.** No persona-to-persona chat occurred (Maria and Klaus slept or were far away); the 4 mirror rows containing "chatting" are Isabella's own schedule action ("chatting with regulars about the upcoming Valentine's Day party"), not a conversation.
- **Reflections:** none, by design (decision D1: staged mode disables the importance-triggered reflection); no reflection prompt appears among the 904 classified calls (0 unclassified).
- **Sleep hook:** fired for Maria and Klaus twice: at 06:00 (night 0) and at 12:00 (night 1), each time with **0 entries considered**, no cluster, no LLM call (`consolidation_log.jsonl`). Isabella never slept in this window.
- **Consolidation sweep with content: did not happen**, so there are no entries per night, cluster sizes, summaries or merge cosines from Step D (your request to report Stage 3's real merge cosines "for information" cannot be met from this run; the only real ones are Stop 3's 0.889, 0.9134, 0.8949). Mirror: 608 rows (Isabella 585, Klaus 15, Maria 8), 0 semantic rows.

## 5. THE KLAUS WAKE 7 / ASLEEP AT 08:00 INCONSISTENCY (**observation only, no fix**)

Klaus's saved schedule (`D:\DevMems_stepd\reverie\environment\frontend_server\storage\p6_step_d_gemini\personas\Klaus Mueller\bootstrap_memory\scratch.json`) begins `['sleeping', 420]`, then his morning routine. His wake-up answer was 7 am. The run starts at 06:00, but upstream chooses the current schedule entry by minutes since midnight and then starts that entry NOW with its FULL duration (`plan.py:559-560` index from `get_f_daily_schedule_index`, `plan.py:618` takes `act_dura`, `plan.py:642` passes `int(act_dura)` to `add_new_action`). So at 06:00 the entry `sleeping 420` starts at 06:00 and lasts 420 minutes. The saved data agree: Klaus's sleeping-step fraction is 1.0 in every window up to 13:00 and 0.0 after (his first awake calls are in the 13:00 to 13:45 window), i.e. he woke at 13:00, 420 minutes after the start; Maria's entry is `sleeping 540` and she was still sleeping at the stop (15:00 would be her wake time). This is consistent with the explanation and I did not test it by any other means. It explains the Step C observation as well (Klaus "7 am" but asleep at 08:00). It is a property of starting at 06:00, not a model error.

## 6. THE T RE-CHECK (pre-registered rule, section 8 of `docs/phase6_preregistration.md`, committed a28a44b before the run; **offline-captured**)

Population: LLM-scored events from Step D only, rule-assigned "is idle" rows excluded. Mirror 608 rows, 163 idle rows excluded, **445 LLM-scored events**; this equals the 445 staged scoring calls in the raw log. Artifact `stepd_analysis.json` (`T_recheck`).

| score | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| count | 238 | 183 | 17 | 5 | 0 | 2 | 0 | 0 | 0 | 0 |

By agent: Isabella 439, Klaus 4, Maria 2. Fraction reaching 8, 9 or 10: **0.0** for each. The unchanged rule (smallest integer in {8, 9, 10} with fewer than 5 percent reaching it) therefore gives **T = 8**, which differs from the frozen provisional **T = 9**. Per your D-rule: **reported, config NOT changed, the decision is yours.**

The three populations side by side (not pooled): Stop 1, 95 scores (friction experiment plus live runs, `gpt-oss-20b`): 8 of 95 (8.4 percent) reached 8, so T = 9. Step C rerun, 22 scores: provisional. Step D, 445 scores (Gemini): none reached even 7, T = 8 by the rule. What this does and does not show: the maximum observed score is 6, 421 of 445 scores are 1 or 2, and 439 of 445 are one agent (Isabella) doing routine cafe actions, so T = 8 comes from the absence of any high-scored event in this window, not from evidence that 8 is the better threshold; with these data neither 8 nor 9 would fire Path B. The Stop 3 live run, which used scripted high-importance events, scored a lease-ending notice 9, so Gemini can produce a 9 when the event is authored to be pivotal (a separate population, not used here).

## 7. CONDITIONS COMPLIANCE TABLE (PM verdict on the Step C rerun, Step D rules)

| Condition | Status | Evidence |
|---|---|---|
| Isolation in a worktree at committed HEAD, own storage, same `.env`, background | Done (worktree at 9c60c86, which is after b002969) | section 1 |
| Settings: 3 agents, staged, Stage 4 off, Stage 3 on, normalizer on, raw log on | Done | `devmem/run_step_d.py`; `step_d_report_first.json` |
| Start 06:00, run through the first night to 08:00 next day, or until a cap | Ended at a cap (soft 900 calls) at 13:45 day 1; the night was NOT reached | section 1 |
| Hard cap 1200, soft stop 900 at a step boundary | Respected (904 total, 4 over the soft threshold because the check runs at step boundaries) | `step_d_report_first.json` |
| Autosave every 15 sim minutes | Done (32 saves) | `autosave_steps` |
| Upstream exception: do not patch, save, resume once if not a code defect | No exception occurred | section 2 |
| Gemini keys only for chat; embeddings through the cache and embedding keys, up to 150, fail loud; no key over 400 | Done: chat 314/297/293, embeddings 88 | section 2 |
| Report: calls and tokens per prompt type and per simulated hour per agent, awake and sleeping separated | Done | section 3 |
| Report: retries per prompt type, router failures, normalizer hit counts | Done | section 2 |
| Report: conversations, reflections, sleep hook, sweep, entries per night, cluster sizes, summaries, merge cosines | Partly: conversations none, reflections none (design), sleep hook ran with 0 entries; no content sweep, so no cluster sizes, summaries or cosines | section 4 |
| Report: schedule scan and observation-only explanation of Klaus | Done (scan clean; explanation in section 5, no fix) | section 5 |
| T re-check: population committed BEFORE computing, rule unchanged, config unchanged if T would change, not used to tune REINFORCE_THRESHOLD | Done; T would be 8, config unchanged; nothing was tuned | section 6 |
| Commit locally, no push, key scan | Done at commit | see commit |

## 8. DEVIATIONS (complete)

- The run ended 4 calls over the 900 soft threshold (904): the soft stop is evaluated at step boundaries.
- Worktree copies of git-ignored local files (`.env`, upstream `utils.py`, embedding cache); the first launch failure described in section 1.
- Embedding requests used keys 1, 3, 4, 5 and 6 (the configured embedding keys), not only the chat keys; the 400-per-key limit applies to chat calls and no embedding key exceeded 18 requests.
- `devmem/memory/p6_stepd_analysis.py` re-runs the Step C prompt-type analysis on the Step D artifacts, so `step_c_analysis.json` and `step_c_analysis.md` in the Step D folder are Step D's (the file names come from the reused script).
- The run database `memory.db` is copied beside the artifacts but is not committed (`*.db` is git-ignored); the analysis reads it and every number from it is in `stepd_analysis.json`.
- The worktree `D:\DevMems_stepd` remains on disk with its saved simulation (autosave at step 2791) so a resume is possible.

## 9. TESTS

No code changed in the repository for Step D beyond the committed script and the new analysis script. The last full-suite run (Stop 3, 178 tests, 2 live-gated skipped) is in `docs/phase6_stop3_artifacts/full_suite_output.txt`; it has not been re-run for this report because no tested file changed.

## 10. OPEN QUESTIONS AND THE FOLLOW-UP PROPOSAL (for your call)

**The gap:** Step D never reached a night, so it produced no consolidation content, no cluster sizes, no merge cosines and no sleeping-hour cost beyond a few calls. Two facts shape any follow-up.

**Fact A (cost):** one awake agent costs about 104 to 119 calls per simulated hour (49 percent of them scoring). Estimating from the resume point (13:45) to 08:00 next day: Isabella awake until her evening sleep (roughly 6 hours, about 700 calls), Klaus awake from 13:00 and Maria from 15:00 (rates unmeasured; I assume 15 to 60 calls per hour each, about 200 to 800 calls), day-2 morning planning (about 85 calls per day start), plus nightly sweeps. **Roughly 1,300 to 2,000 calls, about 3.5 to 5.5 hours of wall time at the observed 6 calls per minute (904 calls in 146 minutes).** The three chat keys at 400 each allow 1,200.

**Fact B (a possible Stage 3 defect surfaced by the 06:00 start):** because the `sleeping` entries run their full duration from 06:00, Maria and Klaus were "sleeping" at 12:00, and the Stage 3 night key treats a sleep signal at or after `night_boundary_hour` = 12 as the evening night. The hook therefore wrote the night 1 marker (done, 0 entries) for both at 12:00. When they really go to sleep that evening, night 1 already has a `done` marker, so tonight's sweep would be skipped as "already swept". This is derived from the code and the consolidation log; I have not run it. It would also affect any natural run in which an agent is asleep at noon. Fixing it (for example a different boundary hour, or starting at 00:00) changes Phase 5 behavior and needs your checkpoint.

**Questions:**
1. Is the partial Step D enough for its cost purpose (section 3 replaces the n=2 estimate), with the night evidence left to a smaller dedicated run? Or do you want the full resume to 08:00?
2. If a follow-up: which option?
   - **(a) Resume to next 08:00** from the autosave at step 2791: about 1,300 to 2,000 calls, needs new caps (the 1,200 hard cap and the 400-per-key limit do not fit; five keys at 400 would, with keys 1 and 2 added for chat), 3.5 to 5.5 hours of wall time, and Fact B applies to Maria and Klaus.
   - **(b) Fresh short run starting at 20:00 on day 1** (all three awake, falling asleep by about 22:00, run to 08:00): about 85 day-start calls, a few hours of awake scoring (about 100 calls per hour per active agent) and a cheap night; around 600 to 1,000 calls. It yields the first sleep-hook sweeps and summaries, but each agent starts with no memory of the day, so the clusters will be small; entries come only from the run's evening.
   - **(c) Skip the natural night** and treat Stop 3 (scripted nights, real calls) as the only live consolidation evidence.
3. Fact B: authorize a design checkpoint on the night key (boundary hour or start-time handling) before any follow-up, or accept the risk and report what happens?
4. T: the rule gives 8 on 445 scores of which none reached 7 (section 6). Keep T = 9 provisional, or change it to 8, or specify a better population (for example a run with authored high-importance events, scored by the pinned model)? Config is unchanged.
5. Quota: by the ledger the three chat keys have already used about 330 requests each today (Step D plus Stop 3). Gemini's daily quota reset is at midnight Pacific as far as I know (not verified here, about 12:30 IST), so a follow-up should start after that. Confirm.

REQUEST: Your decisions on questions 1 to 5. Halting; no further live call will be made until you answer.
