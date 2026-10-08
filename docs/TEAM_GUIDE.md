# DevMem-Agents: Team Guide (implementation A to Z, for the seminar panel)

Written 2026-10-08 (evening) for teammates who did not build the project. Read sections 1 to 3 first (ten minutes), then skim section 13 (the question bank). Everything here was checked against the code and the run logs in this repository on the day of writing; where a number is interim or still running, the text says so. Facts that are not in the repository (opinions, expectations) are marked as such. No API key value appears in this guide or anywhere in the repository; keys are referred to by name only.

---

## 1. The project in one minute

**What it is.** DevMem-Agents upgrades the memory of an existing, published research simulation: Stanford's *Generative Agents* ("Smallville", Park et al.), in which LLM-driven characters live in a small town. In the original, every thing an agent experiences goes into one flat list (the "memory stream"). We replace that flat list with a four-stage developmental memory:

| Stage | Name | One-line idea |
|---|---|---|
| 1 | Personality priors | Each character carries a few short, permanent, pre-experience statements about their disposition (for example "avoids confrontation"). |
| 2 | Episodic memory | Every observation is scored for importance by an LLM prompt that sees those priors, so the same event matters differently to different people. |
| 3 | Sleep-triggered consolidation | When an agent goes to sleep, related episodic entries are clustered by embedding similarity and each cluster is summarised into one semantic memory. |
| 4 | Identity memory | Repeated themes (over several nights) or single pivotal events are promoted into a few slow-changing identity traits, which are fed back into the scoring prompt. |

**What stays the same.** The town, the agents, the movement, the planning and the simulation loop are upstream's. Memory is the only variable. A switch, `MEMORY_MODE`, selects `baseline` (original behaviour) or `staged` (our four stages). The experiment compares the two as two *arms* of one run design.

**Hard constraint: zero API cost.** All language-model calls use free-tier keys only (Groq, Google Gemini, NVIDIA NIM), rotated by a custom router. OpenAI is never called (the legacy OpenAI code path is kept but disabled).

**What we are and are not claiming.** One run per arm, three agents, three compressed simulated days. We report differences as observations. We make no significance claims, no causal attribution to a single stage, and no claim about "behaviour" or human-like cognition (section 12 and `docs/phase9_claims_not_supported.md` are the guard-rails for wording).

**Who did what (project roles).** Project Owner (Umesh) approves; a Project Manager (a Claude session) writes specs and verdicts; the Senior Developer (Claude Code in this repo, after an earlier Gemini session) implements and reports; a Junior Developer role received small delegated tasks. The process rules are in `docs/PRD.md` and `CLAUDE.md`.

---

## 2. Vocabulary you will hear in the room

- **Smallville / Reverie / upstream:** the original Generative Agents code (in `reverie/`). "Upstream" means "the original code, not ours".
- **Persona / agent:** a simulated character. Evaluated agents: **Isabella Rodriguez** (cafe owner), **Maria Lopez** (student), **Klaus Mueller** (researcher). Three more persona files exist for controls and friction pairs (Giorgio Rossi, Sam Moore, Wolfgang Schulz).
- **Step:** one simulation tick = 10 simulated seconds. **Day** = 8,640 steps (24 simulated hours). The run starts 2023-02-13 00:00.
- **Poignancy / importance:** the 1 to 10 score the LLM gives a memory.
- **Associative memory:** upstream's store of nodes (events, thoughts, chats) with embeddings; this is the *live retrieval store* in both arms.
- **Mirror:** our SQLite copy of the memory entries (per run, `devmem/storage/<run>/memory.db`). Option A: upstream stays authoritative; SQLite mirrors it.
- **Arm B / baseline** and **Arm S / staged:** the two experimental conditions.
- **Router:** our module that sends every LLM call to a free-tier provider with key rotation and rate-limit handling.
- **Pinned model:** the run uses one fixed model for both arms (`gemini-3.1-flash-lite`) so the comparison is not confounded by model choice.
- **Ledger:** the router's SQLite table `llm_call_log` (one row per call: purpose, tokens, agent, condition, time). The efficiency numbers come from it.
- **Checkpoint:** a saved copy of a run at a given step. Registered checkpoints: end of the awake part of day 1 and of day 3 (first autosave at or after 14:15 simulated).
- **Interim:** any number taken before the run ended; always labelled with the step and simulated clock.
- **D1, D2 ...:** numbered design decisions approved by the PM (D1: periodic reflection off in the staged arm).
- **H1 to H29 (claims ledger):** numbered disclosures in `docs/CLAIMS_LEDGER.md` (what each artifact supports, deviations, incidents).

---

## 3. How the upstream simulation works (you need this to explain our change)

Each agent has a cognitive loop run every step (files under `reverie/reverie/backend_server/persona/`):

1. **Perceive** (`cognitive_modules/perceive.py`): look at events on nearby tiles (vision radius, limited attention bandwidth, a retention filter that skips events seen very recently). Each new perceived event becomes a *node* in associative memory: a text description, keywords, an embedding, a poignancy score, timestamps. The poignancy score comes from an LLM prompt ("on the scale of 1 to 10 ... rate the likely poignancy").
2. **Retrieve** (`retrieve.py`): for a query, rank memory nodes by a weighted sum of recency, relevance (embedding cosine) and importance. Upstream weights are `[0.5, 3, 2]` for recency, relevance, importance.
3. **Plan** (`plan.py`): daily plan, hourly schedule, task decomposition, choosing a place (sector, then area, then object), deciding whether to talk or react.
4. **Execute / move:** pathfinding to the chosen tile.
5. **Reflect** (`reflect.py`): when accumulated importance since the last reflection crosses a threshold (150), the agent generates focal-point questions and insights from recent memories (upstream calls this *periodic reflection*). After a conversation it also writes a planning thought and a memo (post-conversation thoughts).
6. **Memory structures:** associative memory (nodes + embeddings + keyword strength), scratch (current state, schedule, clock), spatial memory (the town tree: world, sector, area, objects).

Two facts matter for our design: (a) the poignancy prompt is the only place importance is decided, so it is where personality can enter; (b) retrieval uses importance as one of three terms, so scores influence what an agent recalls and acts on.

---

## 4. Our architecture and data flow

```
 observation (perceive)                       sleep begins
        |                                           |
        v                                           v
 Stage 1 priors (YAML)  --block--> Stage 2 scorer   Stage 3 sweep (nightly, per agent)
                                     |                |  select unconsolidated entries (importance >= 3, not "idle")
                                     |                |  embed (gemini-embedding-001, cached)
        upstream node + our mirror   |                |  average-linkage clustering (cosine 0.82)
        (poignancy = persona-         |                |  one LLM sentence per cluster (max 6 / night, 12 sources each)
         conditioned score)           |                |  summary node (thought) + semantic row; sources flagged consolidated
                                     v                v
                          retrieval (upstream formula;   Stage 4 step (same sleep hook, after Stage 3)
                          consolidated sources x 0.5)      reinforcement counters -> Path A / Path B -> trait sentence
                                     ^                                 |
                                     +---- identity context (<= 5 traits, <= 120 tokens) appended to the scoring prompt
```

Switches: `MEMORY_MODE` (`baseline` or `staged`), `STAGE4_ENABLED`, `IDENTITY_FEEDBACK`, and config files under `devmem/config/`. In baseline mode none of our stage code runs except no-op helpers.

---

## 5. Stage by stage (what the code does)

### 5.1 Stage 1: personality priors (`devmem/memory/priors.py`, `devmem/config/personas/*.yaml`)
- Six YAML files, each with 4 to 6 short *behavioural* sentences (not adjectives) and a category tag, for example Isabella: "Avoids confrontation whenever possible", "Reacts to unexpected bad news by trying to immediately fix or soften the situation". The files are written with deliberate **friction pairs** (for example Isabella versus Wolfgang) and a "humanizing check" (no agent is purely positive or negative); see `devmem/config/personas/README.md`.
- `get_prompt_context(agent_id)` formats the priors into a block.
- **Staged mode:** priors are *not* put into the memory stream. They reach the agent only through the scoring prompt (and later through the identity context).
- **Baseline fairness injection:** so the baseline is not at an informational disadvantage, the same priors are injected into the baseline's memory as atomic thought nodes with poignancy 10 (idempotent). This is the Stage 1 "control".

### 5.2 Stage 2: episodic memory with persona-conditioned scoring (`devmem/memory/episodic.py`)
- **Staged prompt = upstream prompt + priors block (+ identity context when Stage 4 has traits), byte for byte** (`build_staged_prompt`). Augment, never replace.
- **Parser:** `parse_importance_score` reads the labelled value ("Rate: N"), ignores a "1 to 10" range phrase, strips markdown (`**7**`); fail-safe value 4. The same parser serves both conditions. (A parser bug that misread an echoed instruction as 1 was found and fixed before the full runs: claims ledger H10.)
- **Mirror (Option A):** each upstream node is written to SQLite `episodic_memory` with `entry_id = "<agent>:<node_id>"`, `INSERT OR IGNORE`. One database per run. `sim_day = max(1, (sim_date - 2023-02-13).days + 1)`.
- **Reconciliation:** upstream saves only at autosave; the mirror writes at once. On reload, mirror rows whose node is absent from the loaded memory are removed (`reconcile_mirror`), so a restart cannot leave orphans.
- **Schema** (`devmem/memory/schema.sql`): `priors`, `episodic_memory` (with `consolidated` flag), `semantic_memory`, `identity_memory`, `llm_call_log`, `key_usage`; Stage 3 and 4 add `consolidation_sweeps`, `semantic_reinforcement`, `identity_traits` and logs.

### 5.3 Stage 3: sleep-triggered consolidation (`devmem/memory/consolidation.py`, `devmem/config/consolidation.yaml`)
- **Trigger:** a hook in `persona.py` fires the first step an agent's new action contains "sleeping"/"asleep" (markers in config). One sweep per agent per *night*; night key = simulated day of the evening onset (a sleep signal before 12:00 belongs to the previous night). A marker row per (agent, night) is written in the same SQLite transaction as the results, so a crash cannot half-apply a night.
- **Selection:** unconsolidated entries up to the sweep time with importance at least 3, excluding descriptions containing "idle".
- **Embeddings:** `gemini-embedding-001` (3072 dimensions), cache first (`devmem/embeddings/vector_store.py`). One embedding model per run, identical for both arms; vectors from different models or the 768-dimension deterministic test fallback are never mixed (it refuses).
- **Clustering:** *average linkage* on cosine similarity with threshold **0.82**, minimum cluster size 3. (A single-linkage setting at 0.78 chained unrelated themes; average at 0.82 did not on the Stop 3 fixture. This is a design choice, not calibrated on natural data: ledger and config comments say so.)
- **Summaries:** the largest clusters first, at most 6 summaries a night, at most 12 source entries per prompt; one third-person sentence naming the agent, with one corrective retry. The summary is scored with the staged scorer, embedded, and written into upstream memory as a *thought node* (`consolidated` / `memory`) whose `filling` lists its sources, so it is retrievable and survives save/reload. If it matches an existing summary at cosine at least 0.80 it *reinforces* that one instead of creating a new one.
- **Flagging and retrieval:** sources get `consolidated = 1`; in staged mode retrieval multiplies their score by `consolidated_weight` = 0.5 (`apply_consolidated_weight`, called from `retrieve.py`).
- **Decision D1:** in staged mode periodic reflection (focal-point and insight generation) is switched off, because Stage 3 is designed to replace it (flag `staged_reflection: false`). The post-conversation planning-thought and memo calls inside `reflect()` are *outside* this gate and run in both arms (claims ledger H26).

### 5.4 Stage 4: identity memory (`devmem/memory/identity.py`, `devmem/config/identity.yaml`)
Runs inside the same sleep hook after Stage 3, as a second night-keyed step, computed from the run database (so a crash, rerun or reload reproduces the same state).
- **Reinforcement:** a night "counts" for a semantic entry when Stage 3 created it or merged into it at cosine at least 0.88, subject to a guard.
- **Path A (count based):** an entry counted on 3 distinct nights (including the birth night), or **same-day** reinforcement of 4 new source events in one night, graduates into a trait.
- **Path B (pivotal):** a single event whose importance is at least **T = 9** graduates. T was frozen at 9 by a PM override (the pre-registered rule would have given 8, which would have made all five authored significant events pivotal; 0 of 24 authored events misclassified at 9; margin one point; ledger H11). Path B is evaluated at the nightly step, not instantly (disclosed deviation). An event scored while a matching trait was already in its scoring context does not graduate (addendum A1, to avoid self-reinforcement).
- **Trait generation:** one third-person sentence of at most 35 words from the sources, one retry.
- **Feed-forward:** at most 5 active traits and at most 120 estimated tokens, whole traits only, appended as the *identity context* of the Stage 2 scoring prompt (`IDENTITY_FEEDBACK` flag; the ablation switch).

### 5.5 Where the upstream code was touched (the "sanctioned touch points")
| # | File | What |
|---|---|---|
| 1 | `prompt_template/gpt_structure.py` | All LLM call sites routed through our router; OpenAI path disabled; embeddings routed through `EmbeddingStore`; router failures counted; reply normalizer hook |
| 1b | `reverie.py` | one `os.makedirs` fix |
| 2 | `perceive.py` | poignancy branch on `MEMORY_MODE`; mirror write |
| 3 | `persona.py` | baseline priors injection at init |
| 4 | `persona.py`, `reflect.py` | sleep hook (Stage 3/4); D1 gate on periodic reflection |
| 5 | `retrieve.py` | `consolidated_weight` multiplier (staged only) |
| 6 | `prompt_template/run_gpt_prompt.py` | **added during the run (2026-10-08, ledger H28):** sector and arena validators ignore a comma after the first `}` when the text before it is an offered area |
Upstream functions are kept (unused paths are not deleted); behaviour is toggled by configuration, not forks.

---

## 6. The LLM router and why it is built the way it is (`devmem/router/`)

**Goal:** run a long multi-agent simulation on free tiers whose limits are low and unpredictable.
- **Providers/keys:** `devmem/config/providers.yaml` lists providers in priority order (Groq, NVIDIA Nemotron, Gemini), each with many keys (`GROQ_KEY_n`, `GEMINI_KEY_n`, `NIM_KEY_n` in a git-ignored `.env`). The full experiment pins one Gemini model and uses 33 verified Gemini chat keys split between the arms (baseline 17 chat/16 embedding keys, staged 16/16, disjoint). Each key is in its own project; each key is capped at 450 requests per quota day.
- **Entry point:** `call_llm(prompt, tier, purpose, agent_id, condition, ...)`. Every call is logged to the ledger with its purpose and condition.
- **Pinning:** `DEVMEM_PINNED_MODEL` forces both arms onto the same model: keys of that model are rotated, short cooldowns are waited out, and another model is never silently substituted.
- **429 handling** (`classifier.py`, `cooldown.py`): a rate-limit reply is classified (transient, daily, token-recoverable, unknown). In the full run Gemini returned many unrecognised "Resource has been exhausted" 429s (probably shared/IP-level), so the run-level gate (`devmem/eval/quota_gate.py`) tries at most 3 keys per call, then backs off with jitter (min(300, 20 x 2^n) seconds, no attempt limit). Outages (every key unreachable or HTTP 5xx) wait with backoff 20, 40, 80, 160, 300 s. Quota exhaustion pauses until the quota reset (07:00 UTC).
- **Timeouts:** importance-scoring read timeout was 15 s and was raised to 30 s during the run (claims ledger H20); a read timeout cools only the key that timed out, for 10 s.
- **Output normalizer** (`output_normalizer.py`): identical for both arms; strips JSON code fences and echoed annotations from replies so downstream parsers see clean text; per-arm strip counts are reported.
- **Zero cost** is enforced by configuration: only free-tier keys; the paid-tier move was prepared as a procedure but never run.

---

## 7. The headless runner and the experiment harness (`devmem/run_headless.py`, `devmem/eval/`)

- **Headless runner:** drives upstream's server without the Django frontend, autosaves every 15 simulated minutes (90 steps), and reconciles the mirror on load.
- **Arm runner (`eval/run_arm.py`):** one process per arm; hard cap 16,500 router calls per arm (soft stop 15,500); writes heartbeats, hourly ledger windows, run status, checkpoints; refuses unsafe states (canary checks A1 to A6, for example calls per awake agent-hour: warn above 165, abort above 260).
- **Supervisor (`eval/supervisor.py`):** restarts an arm from its last autosave after a crash or kill (at most 3 crash resumes per simulated day); if the same step crashes twice it writes an ABORT file and stops; it never resumes over an ABORT.
- **Watchdog (`eval/watchdog.py`):** a 5-minute scheduled task that restarts an arm whose process died (for example after the laptop was shut down), with an exclusive lock and a restart-per-hour limit. Processes are launched through WMI so they survive the desktop app restarting.
- **Event injector (`eval/injector.py`):** adds the 27 authored events to a persona's own tile for six steps, through the same code path as a natural event (the same in both arms) and logs whether each was perceived and stored (PASS or FAIL).
- **Authored plan (`eval/authored_plan.py`, `docs/phase7_stop1_schedules.json`):** the three days' schedules are authored so both arms face the same situations; each simulated day has an awake window (06:00 to 14:00) followed by sleep, which is why a "compressed day" takes a few hours of wall time.
- **Health tools:** `arm_health.py` (verdicts RUNNING, FINISHED, DEAD, ABORTED, PAUSED, WAITING), `event_monitor.py`, `rate_sampler.py`, `eta_analysis.py`, `wave_report.py`, `step_cost_analysis.py`.
- **Process rule:** every commit goes through `eval/safe_commit.py`, which byte-compiles changed files and runs the covering tests before committing; any changed script needs a test that runs it.

---

## 8. The experiment design (pre-registered, `docs/phase7_preregistration.md`)

- **Two arms**, same pinned model, same three agents, same authored three-day schedule, same 27 injected events. Arm S differs from B by the staged memory **and by decision D1**: periodic reflection (focal-point and insight generation) is off in S and on in B; the post-conversation planning-thought and memo calls run in both. So any difference mixes the four stages with that reflection difference. There is no ablation arm.
- **Injected events (27):** nine per agent across days, in classes mundane, repeated theme, friction, one-off and pivotal (`docs/phase7_stop1_events_questions.json`). One event (I6) was not perceived in the staged arm and is excluded from both arms.
- **Questions (39):** 27 about injected events, 3 theme-count questions, 9 about natural (unauthored) schedule events; plus 6 probe interview questions asked of each agent at day 1 and day 3 (18 pairs per arm).
- **Metrics:**
  - **Efficiency:** E1 calls (unique, replays removed), E2 mean prompt tokens per scoring call, E3 consolidated fraction.
  - **Recall (M1):** key-fact checklist score per question, graded by an automatic rule-based grader validated on 30 developer-authored labels (94.7 percent item agreement); strict correctness as secondary.
  - **Coherence (M2):** day-1 versus day-3 answers judged consistent, contradictory or unrelated by an LLM judge calibrated on 20 authored pairs; only interpretable if calibration accuracy is at least 80 percent.
  - **Diagnostics:** D-1 trait provenance (closer to the priors text than to its sources?), D-2 merge heights of Stage 3 entries, replay controls for the Stage 2 scoring effect (see below).
- **Registered directional predictions** (scored right, wrong or undecidable regardless of direction): E1 staged more calls than baseline by under 10 percent; E2 higher tokens in staged; E3 above 0 in staged and 0 in baseline; R1 to R5 recall relations (theme counts, pivotal events, mundane events, same-day questions); persona-specific scoring directions (Isabella and Maria higher on friction events, Klaus lower). Rules: undecidable when the relevant n is below 3 questions or a validator fails.
- **Replay controls:** on a fixed stratified sample of 300 events (all 27 injected plus 273 natural, seed 20261008), re-score with (a) another persona's priors, (b) a neutral filler block, (c) the baseline prompt, to see what the priors do to scores. Scoring only; says nothing about behaviour.
- **Exclusion and flagging rules:** runs not completing three days are interim, never silently dropped; a run with more than 1 percent fail-safe calls is flagged; no post hoc exclusions.

---

## 9. The evaluation pipeline (Phase 9, `devmem/eval/phase9/`)

Runs after an arm finishes, on that arm's own key pool only (`eval_keys.py` refuses to use a key of an arm that is still running or any paid key):
1. answer harness: for each question, retrieve the top 30 memories from a checkpoint copy using the agent's own retrieval with real embeddings, then one fixed-prompt answer call;
2. grader (offline rules), judge (LLM), ledger splitter (evaluation calls excluded from efficiency), diagnostics;
3. two **chains** (`run_staged_chain.py`, `run_baseline_chain.py`) that wait for an arm to finish and run the steps in a fixed order, stopping at the first failure and writing to `devmem/storage/phase9_eval/chain_status.jsonl`;
4. `results_export.py` writes one readable file and one JSON with every paper number and every prediction scored (`docs/phase9_results_export_*.md|json`); an interim dry run on the day-2 copies already exists.
Per-call classes (planning, action/object description, dialogue, importance, periodic reflection, post-conversation memo, consolidation, identity) are assigned from the prompts by `purpose_classes.py`, because the router's keyword tag is unreliable (73 to 78 percent false matches for "dialogue"; claims ledger H25).

---

## 10. The viewer (`devmem/api/`)

A read-only inspector: a FastAPI server plus a web UI (React and Phaser vendored, no CDN). It replays a recorded run (a town view with the agents moving), shows an agent's memory by stage, supports a side-by-side comparison of the two arms and a Findings tab with the reported results and where they differ and why. It never calls an LLM and never writes to a run. Start it with `python devmem/api/serve.py --a <staged run> --b <baseline run> --open` (system Python with fastapi and uvicorn; see `devmem/api/REQUIREMENTS.md`). The Findings text must use the corrected D1 wording; its data file (`web/data/findings.json`) is rebuilt after the arms finish.

---

## 11. What actually happened during the run (honest timeline)

Launch: 2026-10-07 15:57:47 IST, both arms, supervised. The key events, all disclosed in `docs/CLAIMS_LEDGER.md` and `docs/phase7_preregistration.md` section 7:
- **Free-tier 429 "Resource has been exhausted" waves** hit both arms in short, often simultaneous bursts all along; handled by the 3-key limit and backoff (H18). Waves faded in the evening of Oct 8 (5 to 13 percent of wall time versus about 40 to 46 percent overnight).
- **Read-timeout change 15 s to 30 s** (H20): before it, up to 31 percent (baseline) and 28 percent (staged) of scoring calls had a timeout retry.
- **External kill at about 00:10 IST Oct 8** (cause not established) and **laptop power-off at 14:56:53** (critical battery); the watchdog restarted both arms from the last autosave (H19, H22). Replayed steps are counted once in unique figures.
- **Torn checkpoint copies** (found Oct 8): the external copier copied while upstream was still saving (upstream writes `meta.json` first), so some day-2 copies had truncated embedding files; fixed in the copier, repaired copies are used and labelled (H23).
- **Staged crash on an invalid area** (Oct 8, 19:23 onward): the model's area reply contained a run-on list; upstream rejected it five times (identical replies at temperature 0) and returned its own fail-safe area "kitchen", which does not exist in the cafe sector, so the run raised `KeyError`. The same step crashed twice and the supervisor wrote ABORT. With PM approval a minimal validator change (touch point 6) was applied to both arms (staged resumed at step 20,790 at 20:01 IST; baseline restarted at step 19,980 at 20:10); the staged arm then passed the step (H27, H28).
- **Upstream fail-safes** reached the simulation in both arms (H29): the "decide to talk" function fell back to "yes" in 14 of 14 calls in each arm, so conversation starts were not decided by the model; about 38 to 39 percent of schedule revisions fell back to the unchanged schedule. Totals are 0.65 percent (baseline) and 0.44 percent (staged) of upstream function calls, under the 1 percent flag.

---

## 12. Results so far and what you may and may not say

**Status on 2026-10-08 evening:** both arms are still running day 3 (staged slightly ahead). No day-3 answer, judge result or replay result exists yet; the final comparison depends on the arms finishing (see the status report in the chat/`docs`). Everything below is **interim**, from day-2 copies (step 13,770, simulated 2023-02-14 14:15):
- **E1 unique calls:** baseline 7,302; staged 6,008 (staged about 18 percent fewer). The registered prediction (staged more by under 10 percent) is scored **wrong** so far. Do **not** say the stages make the system cheaper: periodic reflection is off in the staged arm (D1), so the gap cannot be credited to the stages. By class the gap sits mainly in action/object description calls, and we make no attribution.
- **E2 mean prompt tokens per scoring call:** baseline 418.5; staged 572.3 (right).
- **E3 consolidated fraction:** staged 0.0974 (380 of 3,901 entries), baseline 0 by construction (right). Stage 3 produced 14 summaries and Stage 4 13 traits across the three agents by that checkpoint.
- **D-2** reproduced exactly offline for all six consolidating nights and scores right, but it was weak by design (at threshold 0.82 nearly every merge falls in the 0.80 to 0.88 band).
- Recall, coherence, replay and D-1 results do not exist yet.

**Never say:** that the result is significant; that a difference is caused by Stage 2, 3 or 4 alone; that the system models human memory, development or cognition; that agent behaviour improved; that staged memory is cheaper or more efficient because of the stages; that either arm ran unmodified upstream code. **Do say:** single run per arm, three agents, descriptive; every number labelled live/interim/derived; periodic reflection (focal-point and insight generation) is off in staged and on in baseline, the post-conversation memo calls run in both.

---

## 13. Question bank for the panel (short, defensible answers)

**Motivation and design**
1. *Why change memory at all?* The original stores everything in one stream, retrieved by recency, relevance and importance; importance is persona-blind and nothing is ever abstracted, so memory grows and has no notion of identity. We test whether staged, developmental memory helps.
2. *Why four stages?* Each maps to a separable mechanism: who you are before experience (priors), what mattered to you (conditioned scoring), what you keep after sleep (consolidation), and who you become (identity). Each can be switched off by a flag (ablation hooks exist for identity feedback and for reflection).
3. *Is this a model of human memory?* No. The stage names are design inspiration only; we make no cognitive claims.
4. *Why not change the simulation?* Keeping Smallville unchanged makes memory the only variable.
5. *What is novel?* Persona-conditioned importance scoring through priors, sleep-triggered clustering into semantic summaries inside the live retrieval store, and identity promotion with two paths feeding back into scoring, evaluated as a pre-registered two-arm comparison.

**Implementation**
6. *How are priors used?* As a text block appended to the scoring prompt; the staged prompt is the upstream prompt plus that block, byte for byte.
7. *Why is the baseline given the priors too?* Fairness control: otherwise the staged arm would simply know more. The baseline gets them as high-importance thought nodes.
8. *Where does consolidation run?* In a hook triggered when an agent's action becomes sleeping; once per agent per night; atomic with a marker so crashes are safe.
9. *Why average linkage at 0.82?* Single linkage chained unrelated themes in a fixture; average at 0.82 kept themes apart. It is a design choice, not calibrated on natural data, and we say so.
10. *How are summaries retrieved?* They are written as thought nodes into upstream memory, so the unchanged retrieval finds them; source entries are down-weighted by 0.5 so summaries and sources do not double count.
11. *How does an identity trait form?* Path A: a theme reinforced on 3 distinct nights (or 4 events in one night); Path B: a single event scored at least 9. Then one sentence is generated and fed back (at most 5 traits, 120 tokens).
12. *Why T = 9?* The pre-registered rule gave 8, which would make all five authored significant events pivotal; the PM froze 9 (0 of 24 authored events misclassified; margin one point). Disclosed as a deviation.
13. *Which embedding model?* `gemini-embedding-001` (3072 dimensions) for both arms; vectors from different models are never compared.
14. *How is the zero-cost constraint met?* Only free-tier keys, many rotated by the router; no OpenAI calls; the paid-tier move was prepared but not used.
15. *How do you rotate keys and handle limits?* The router keeps a per-key usage ledger, classifies 429s, applies cooldowns, caps each key at 450 a day, limits attempts per call, and backs off with jitter; the run-level gate pauses for quota or outages.
16. *Why one pinned model?* So the two arms differ only in memory; otherwise key rotation across models would confound the comparison.

**Experiment and evaluation**
17. *How big is it?* Two arms, three agents, three simulated days (8,640 steps each), 27 injected events, 39 recall questions, 18 coherence pairs per arm, about 8,000 router calls per arm so far.
18. *Why only three agents and one run per arm?* Free-tier quotas and wall time; hence no significance claims.
19. *How is recall graded?* By a rule-based key-fact checklist grader, validated against 30 developer-authored labels (94.7 percent item agreement; the disagreements are listed). No LLM judge for the primary score.
20. *How is coherence judged?* An LLM judge with a fixed rubric, calibrated on 20 authored pairs; interpretable only at 80 percent accuracy or better; parse failures are counted, never guessed.
21. *What are the predictions?* Written before data: staged more calls (under 10 percent), higher prompt tokens, consolidated fraction above zero, recall relations R1 to R5, persona-specific scoring directions, D-1 and D-2. Each is scored right, wrong or undecidable and reported either way. So far E1 is wrong, E2 and E3 right.
22. *Why is E1 wrong and does that mean your system is cheaper?* Staged made fewer calls so far, but periodic reflection is off in staged by decision D1, so the difference cannot be credited to the stages. We report it as registered and make no efficiency claim.
23. *What do the replay controls show?* How the scoring prompt variants score the same recorded events (priors, another persona's priors, filler, none). They say nothing about behaviour.
24. *Is there a control for the priors?* Yes: the mismatch-persona and neutral-filler conditions in the replay, plus baseline injection of the same priors as thoughts.
25. *What about statistics?* Bootstrap intervals over questions within agents are descriptive only; with three agents and one seed there are no p-values.

**Problems and honesty**
26. *Did anything go wrong?* Yes; all of it is disclosed: 429 waves, a timeout change, an external kill, a laptop power-off, torn checkpoint copies, a crash on an invalid area (fixed with a validator change applied to both arms), and fail-safe values that reached the simulation (section 11). Replayed stretches are counted once in unique figures.
27. *Do both arms run the same code?* Yes, except the staged-only stages; but from the restart on, the area parsing differs from upstream in both arms (touch point 6), and we say so.
28. *Why did conversations not depend on the model?* In this setup upstream's "decide to talk" fell back to its fail-safe "yes" every time in both arms (14 of 14), because the model's answer format was rejected by upstream's validator. We report it and make no claim about conversation initiation.
29. *Is the staged arm's lower call count an artefact?* Possibly partly; by class the gap is mainly in action/object description calls. We do not attribute it.
30. *What is excluded?* Injected event I6 in both arms (not perceived in staged; probably attention crowding on a busy tile, unverified).
31. *Could the result be a fluke of the free tier?* Quota and rate-limit waits changed wall time, not simulated content; replayed steps are removed from unique counts; the arms ran on disjoint key pools.
32. *What would you do next?* More agents and seeds, an ablation arm with reflection on in the staged arm, a validated behavioural measure, and a human evaluation of recall and coherence.

**If asked something not covered:** say what the data show and what they do not; point to `docs/CLAIMS_LEDGER.md` and `docs/phase9_claims_not_supported.md`; never extrapolate.

---

## 14. Where to find things

| Need | Where |
|---|---|
| Process rules, roles | `CLAUDE.md`, `docs/PRD.md` |
| Binding technical spec | `docs/technical_implementation_plan.md` |
| Pre-registered design and predictions | `docs/phase7_preregistration.md` |
| Every disclosure and what each artifact supports | `docs/CLAIMS_LEDGER.md` |
| What the data cannot support | `docs/phase9_claims_not_supported.md` |
| PM rulings | `docs/phase9_rulings.md` |
| Evaluation plan, chains | `docs/phase9_evaluation_plan.md`, `docs/phase9_pipelined_evaluation_plan.md` |
| Interim analysis and export | `docs/phase9_interim_day2.md`, `docs/phase9_results_export_interim_day2.md` |
| Per-phase reports with raw artifacts | `docs/phase*_report.md` |
| Code: memory stages | `devmem/memory/` |
| Code: router | `devmem/router/` |
| Code: experiment harness | `devmem/eval/`, `devmem/eval/phase9/` |
| Config | `devmem/config/` |
| Viewer | `devmem/api/` |

**Run the tests** (repository root, venv Python): `export PYTHONPATH="reverie/reverie/backend_server;."` then `.venv/Scripts/python.exe -m unittest discover -s devmem -p "test_*.py" -t .`.

**Open the viewer** (recorded runs, read only): `python devmem/api/serve.py --a p7pilot_staged --b p7pilot_baseline --open`.

---

## 15. Limits to state before the panel does

One run per arm; three agents; three compressed days; one free-tier model; authored events and questions; a developer-authored grader validation set and judge calibration set; interim figures only until the arms finish; the staged arm differs by more than the memory stages (periodic reflection off); upstream fail-safes shaped parts of both arms' behaviour; the area parsing was relaxed mid-run in both arms; some checkpoint copies were repaired. These are reported, not hidden, and every one has an entry in the claims ledger.
