# DevMem-Agents: the Presentation Bible

For the panel presentation of **DevMem-Agents: A Staged Developmental Memory Architecture for Generative Agents Under a Zero-Cost Inference Constraint** (team: T. Umesh Chandra, P. Chethana Reddy, K. Harish; guide: Jagadeesh, Assistant Professor, Department of Computer Science and Engineering).

Written 2026-10-09 against the deck `DevMem_Agents_Mini_Project_Updated.pptx` (24 slides) and the repository state at that time. It is meant to let anyone on the presentation team, even without having built the project, explain it from A to Z and answer questions. Every number in this guide was checked against the project's result files; where the deck differs from the latest data, section 8 lists the exact fixes.

How to read it:
- **Part A (sections 1 to 4):** the story. Read this first: the pain point, where it applies in the real world, what the project did, and the 60-second version.
- **Part B (section 5):** the glossary: every keyword on the slides, explained in plain words.
- **Part C (section 6):** the slide-by-slide guide: what is on the slide, what to say, what each number means and why it came out that way, and the questions that slide invites.
- **Part D (sections 7 to 10):** all results in one place with "what" and "why", the corrections to make to the deck, the master question bank, and the rules for wording.

A plain-language rule for the whole team: **say what the data show and what they do not.** The project is strongest when it is honest. The result is "the mechanics work, the comparison is fair and documented, and no improvement is demonstrated at this scale." Do not oversell, and do not apologise for the null result: a carefully measured null result is a result.

---

## 1. The pain point (start here)

### 1.1 The setting in one paragraph
A *generative agent* is a software character driven by a large language model (LLM) that can live in a simulated world: it wakes up, plans its day, talks to others and remembers what happened. The best-known example is **Smallville** (Park et al., 2023, ACM UIST), a small town with 25 such characters. Their entire memory is one growing list of text records called the **memory stream**. Everything the agent has ever seen goes into that one list, and to decide what to do or say, the agent searches the list for the most relevant records and pastes them into the model's prompt.

### 1.2 The five pains (use these words)
1. **A flat list cannot tell "a glance" from "a pattern".** A customer who walks out once and a customer-type who walks out every day look the same unless the agent re-reads many records. The only thing that separates records is one importance score (1 to 10) set when the record is written. *Pain: importance is a single number, frozen at write time, the same for every character.*
2. **Patterns are rediscovered over and over.** There is no stored statement like "people often leave my cafe without ordering." To know it, the agent must retrieve many records and have the model work it out again, every time. The only built-in way to generalise is *periodic reflection*, which costs extra model calls and happens on a trigger, not by design. *Pain: repeated work, repeated cost, and answers that depend on which records were retrieved.*
3. **The prompt budget does not grow, but the memory does.** The model can only read a limited amount at once. After days of simulated life there are thousands of records; only a few dozen fit into any prompt. *Pain: records pile up while the prompt stays the same size, so more and more of what the agent lived through is unreachable.*
4. **Lasting traits look the same as passing moods.** "Isabella was irritated this morning" and "Isabella always avoids confrontation" are stored the same way. Nothing says which is a stable part of who she is. *Pain: no notion of identity that builds up slowly from experience and then colours later judgement.*
5. **It is expensive and fragile to study.** The original paper's two-day run with 25 agents cost thousands of dollars of model usage (as reported by the original authors). Running experiments is out of reach for students or small labs. And when we looked inside the original code under a different model we found hazards that quietly corrupt runs: a silent fallback when embeddings fail, and error messages such as "TOKEN LIMIT EXCEEDED" that get saved as if they were the agent's plan or memory. *Pain: results that cannot be reproduced or trusted, at a cost most people cannot pay.*

### 1.3 The one-sentence pain point
> "Agents that live for many days keep everything in one undifferentiated list, so they cannot turn repeated experience into stable knowledge about the world or about themselves, and studying any fix is expensive, unfair to compare and hard to trust."

### 1.4 The research question (slide 4)
"Does replacing Smallville's flat memory stream with a staged developmental memory change what agents remember, how consistently they describe themselves, and how many model calls they use, with everything else held fixed?"

---

## 2. Where this can be used in the real world

Be careful with the word "can": these are **applications the design is aimed at, not applications we tested.** For each, the thing to say is "this is where a memory that consolidates and keeps traceable summaries would matter; the next step would be to show a benefit there."

| Real-world area | Why flat memory hurts there | What the four stages would give | Honest status |
|---|---|---|---|
| **Game characters and interactive worlds (NPCs)** | A character who lives for weeks of play must stay consistent, remember patterns about the player and not cost a fortune per hour | Nightly consolidation turns many small encounters into short, source-linked beliefs; traits keep the character consistent | Mechanics shown in a town simulation; no player study |
| **Social-science and policy simulations (LLM "societies")** | Multi-day multi-agent runs are costly; results depend on opaque memory behaviour | Source-traceable memory plus a measured call ledger make runs auditable and cheaper to repeat; zero-cost mode opens access | Zero-cost three-day run completed; no policy result claimed |
| **Training and rehearsal role-play** (interview practice, hard conversations, customer-service training, classroom practice) | A practice partner must remember what happened in earlier sessions and keep a stable personality | Persona priors give a stable personality; summaries carry experience between sessions | Not tested with users |
| **Long-lived assistants, tutors and companions** | The conversation history outgrows the prompt; the assistant forgets or repeats itself | A nightly "sleep" job compresses the day's history into a few traceable summaries and keeps a short list of stable user or self traits | Same idea, different domain; not tested |
| **Customer-support or CRM agents** | Thousands of tickets: patterns (recurring bug, frequent complaint) are lost in the stream | Clustering similar episodes into one summary with links back to the original tickets (an audit trail) | Not tested |
| **Prototyping with synthetic users** (UX research, product testing) | Synthetic personas drift or contradict themselves over a multi-day session | Persona priors and identity traits as a consistency layer | Not tested |
| **Research tooling** | No one can compare memory designs fairly under the same model and budget | The router, call ledger, pinned model and pre-registered protocol are reusable | **Built and used in this project** |

The last row is the one that is already real: the infrastructure and method are reusable by others.

---

## 3. What this project did, and how it makes existing systems better

### 3.1 The contribution, in four layers (say it in this order)
**Layer 1: a better-organised memory (design).** Instead of one list, four stages: *priors* (who the agent is before experience), *episodic scoring* (how much each experience matters to this particular agent), *sleep consolidation* (many similar experiences become one summary that points back to its sources), *identity traits* (lasting traits promoted from repeated or pivotal experience and fed back into scoring). The world, agents and simulation loop are unchanged: only memory changes, so differences can be traced to memory.
- *Improvement over the existing system:* patterns are stored once instead of rediscovered every time; every summary is traceable to the original records; lasting traits are kept apart from passing moods.

**Layer 2: a fair, measured, honest way to test it (method).** A pre-registered protocol (predictions written before any data), the same model and embedding model for both conditions, a baseline that receives the same priors so it is not at an information disadvantage, call counts read from one ledger, bootstrap intervals and no significance claims. Every prediction is scored right, wrong or undecidable, whichever way it falls.
- *Improvement:* published agent-memory work rarely reports a controlled comparison with cost and a fairness control. Ours does.

**Layer 3: a zero-cost way to run it (infrastructure).** A custom *router* rotates many free-tier API keys, paces requests, caps each key at 450 requests per quota day, pins one model, logs every call, waits out outages and rate-limit waves, and a *supervisor* resumes the run from its last autosave after a crash. A three-day, three-agent comparison of two conditions finished with 0 router failures at $0 inference cost.
- *Improvement:* experiments that cost thousands of dollars in the original setting became possible on free keys, so students and small labs can repeat them.

**Layer 4: reliability fixes to the existing system (engineering findings).** While running the original code under a free-tier model, we found and fixed or made visible several hazards: a silent fallback when embeddings fail (now fails loudly), failure messages saved as plans or memories (now counted, not stored), model outputs wrapped in code fences or annotations that broke the parsers (output normalizer: 0 usable daily plans in a 40-call probe without it, 6 of 6 with it on the pinned model), a location parser that rejected a correct answer and crashed a run (fixed identically in both conditions), and defaults that quietly replace model answers (conversation starts defaulted to "yes" in every call in both arms). 
- *Improvement:* anyone running the original code on a different model gets a more trustworthy run, and now knows which behaviours came from fallbacks, not from the model.

### 3.2 What the project did NOT show (say this yourselves)
- It did **not** show that staged memory improves recall, coherence or efficiency. Recall did not differ detectably; the staged condition used 23 percent fewer model calls, but a second difference (periodic reflection is off in the staged condition) means the saving cannot be credited to the stages.
- It did **not** show that the persona text affects an agent's own scoring more than another persona's text does.
- It is **one run per condition, three agents, three compressed days, one free-tier model.** That is enough to show the mechanics work and to describe what happened; it is not enough for statistics.

### 3.3 Why the honest version is still valuable (the answer to "so what did you achieve?")
1. A complete, working four-stage memory that plugs into an existing simulation without changing the world.
2. A reusable, documented, zero-cost experimental pipeline that other students can run.
3. A fair-comparison protocol with every prediction scored, including the wrong ones.
4. Traceable memories: each of the 16 summaries points back to its source records; 14 traits point back to their summaries or events.
5. Concrete defects found in the original system under a new model, with fixes.
6. A clear list of what to do next (several runs, ablations, persona-specific scoring), which is what a first controlled study should deliver.

---

## 4. The 60-second version and the numbers to memorise

### 4.1 The 60-second story (any team member can say this)
"Generative agents keep everything in one flat list, so they can't turn repeated experiences into lasting knowledge, and they are expensive to study. We replaced the list with a four-stage memory: seeded personality priors, importance scoring that depends on who the agent is, a nightly sleep step that clusters similar memories into source-linked summaries, and identity traits that are promoted from repeated or pivotal memories and fed back into scoring. Everything runs on free-tier models through a router that pins one model for both conditions. We compared our memory with the original flat stream over three simulated days with three agents and 27 injected events, with predictions written in advance. Both runs finished with zero router failures. The mechanics worked: 16 summaries and 14 traits were formed. Recall did not differ detectably, the staged condition made 23 percent fewer calls although a second change, reflection being off, means we don't credit the stages. So we claim a working, traceable, zero-cost architecture and a fair evaluation method, not an improvement."

### 4.2 Numbers to memorise
| Number | Meaning |
|---|---|
| 4 | stages: priors, episodic scoring, sleep consolidation, identity |
| 3 / 3 / 27 | agents / simulated days / injected events |
| 25,920 | simulation steps per condition (3 days x 8,640 steps of 10 simulated seconds) |
| 0 | router failures in either condition; $0 inference cost |
| 450 | requests per key per quota day (router cap) |
| 0.82 / 0.88 / 9 | clustering similarity threshold / trait reinforcement threshold / pivotal score |
| 11,858 vs 9,100 (deck: 9,112) | unique model calls up to the day-3 checkpoint, baseline vs staged (23 percent fewer) |
| 466.6 vs 608.4 | input tokens per scoring call, baseline vs staged |
| 589 of 5,822 (10.1 percent) | staged episodic entries consolidated into summaries |
| 16 / 14 | semantic summaries / identity traits formed |
| -0.039 | recall: staged minus baseline (95 percent interval -0.142 to 0.061): no detectable difference |
| 31 of 38 | questions where both conditions scored the same |
| 94.7 percent | agreement of the recall grader with 30 hand labels |
| 20 of 20 | judge calibration pairs correct |
| 1 of 18 vs 0 of 18 | contradictory day-1 vs day-3 answer pairs, baseline vs staged |
| 1 of 14 | traits closer to the priors than to their sources |

### 4.3 The five things never to say
1. "Our memory improves recall / coherence / efficiency." (Not shown.)
2. "The 23 percent saving is because of the stages." (Periodic reflection is also off in that arm.)
3. "The results are significant." (One run per condition; no tests.)
4. "It models human memory." (Cognitive-science ideas are design inspiration only.)
5. "Personality priors made agents behave more like their persona." (Only scores were measured, and the effect was not persona-specific.)

---

## 5. Glossary: every keyword, in plain words

Grouped by theme. Each entry: what it is, then why it matters here.

### 5.1 The base system
- **Generative agent:** a software character whose behaviour is produced by a large language model (LLM) together with a memory, a planner and a reflection step. It "lives" in a simulated world. *Here:* the three agents Isabella Rodriguez (cafe owner), Maria Lopez (student), Klaus Mueller (researcher).
- **LLM (large language model):** a model that reads text and writes text. *Here:* `gemini-3.1-flash-lite`, used for planning, dialogue, scoring and summaries.
- **Smallville:** the small simulated town (cafe, houses, library, park) from the original paper by Park et al. (2023), where 25 agents live. *Here:* we reuse it unchanged; "upstream" means the original code.
- **Upstream:** the original Generative Agents code that we built on. We only edited it at a small, listed set of points (hooks).
- **Memory stream:** the original single list of every observation, thought and conversation, each stored as a record (a *node*) with text, a time, an embedding and an importance score.
- **Node / record / entry:** one item in the memory (an event the agent saw, a thought, a conversation).
- **Simulation step:** one tick of the simulated clock: 10 simulated seconds. A day is 8,640 steps. *Here:* each condition ran 25,920 steps (3 days).
- **Compressed days:** our simulated days are authored: agents are awake 06:00 to 14:00 (the events happen there) and asleep afterwards. This lets three days fit in a few wall-clock hours of free-tier compute.
- **Injected events:** 27 small authored events we placed in the world on purpose (for example a man asks the price of a croissant and leaves). They give every question a known right answer. They are *persona-neutral*: not written to favour any agent's personality.
- **Perception / perceive:** the agent noticing events on nearby tiles and storing them as records.
- **Poignancy / importance:** a score from 1 (mundane) to 10 (life-changing) that an LLM prompt gives each record.
- **Retrieval:** choosing which records to paste into the prompt. Upstream ranks by a weighted sum of **recency** (newer is higher), **importance** and **relevance** (how close in meaning to the query). Weights in code: recency 0.5, relevance 3, importance 2.
- **Relevance / cosine similarity:** how close two pieces of text are in meaning, measured as the cosine of the angle between their embeddings (1 = same direction, 0 = unrelated).
- **Embedding:** a list of numbers (here 3,072 of them, from `gemini-embedding-001`) that represents the meaning of a text so that similar texts are close. *Cache:* each text is embedded once and stored; *fail loudly:* if embedding fails the run stops, instead of quietly using made-up vectors (the original code silently falls back to substitutes).
- **Periodic reflection:** the original way an agent generalises: when accumulated importance passes a threshold (150), the agent asks the model for "focal-point" questions and "insights" and stores the answers as new thoughts. It costs extra calls. *Here:* **off** in the staged condition, **on** in the baseline.
- **Post-conversation thoughts:** after a conversation the agent writes a planning thought and a memo. *Here:* these run in **both** conditions (they are not the same as periodic reflection).
- **Planning:** the agent's daily plan, hourly schedule, choosing where to go and which object to use.

### 5.2 The four stages
- **Stage 1, persona priors:** 4 to 6 short, permanent, behavioural sentences per agent written before any experience, for example "avoids confrontation", "values harmony above honesty". Some pairs of agents are written to clash (a deliberate friction design). They reach the staged agent only through the scoring prompt. The *baseline* receives the same sentences as ordinary memories (a fairness control).
- **Stage 2, episodic memory with persona-conditioned scoring:** every observation is stored as an *episodic* record and scored with the original importance prompt **plus the agent's priors block** (and, later, its traits). The same event can then score differently for different agents. A test checks the staged prompt equals the original prompt plus the priors block and nothing else.
- **Episodic memory:** memory of specific events ("on day 1 a man left without ordering"). (Concept from Tulving, 1972.)
- **Semantic memory:** general knowledge distilled from many episodes ("people often leave the cafe without ordering").
- **Stage 3, sleep-triggered consolidation:** when an agent falls asleep, a nightly sweep takes its unconsolidated records with importance at least 3, clusters similar ones, and turns each cluster of 3 or more into one third-person summary that lists its source records.
- **Clustering / average linkage / threshold 0.82:** records are grouped by repeatedly merging the two groups whose *average* pairwise similarity is highest, stopping when it falls below 0.82. Average linkage resists "chaining" (one-by-one drifting into unrelated topics) better than single linkage. 0.82 is a design choice, not calibrated on natural data.
- **Importance floor of 3 / idle filter:** records below 3, and "idle" filler, are not clustered.
- **Summary with source ids:** every summary stores the ids of the records it came from, so you can always trace it back. If a new summary is at least 0.80 similar to an existing one, it is merged into it instead of creating a duplicate.
- **Flag as consolidated / weight 0.5:** source records are marked consolidated, and at retrieval their score is multiplied by 0.5, so the summary and its sources do not double count.
- **Once-per-night marker:** a record in the database that says "this agent's night N sweep is done", written together with the results so a crash cannot half-apply a night.
- **Sleep consolidation (inspiration):** the idea that sleep turns experiences into lasting memory (Diekelmann and Born, 2010; complementary learning systems, McClelland et al., 1995). Design inspiration only; we do not claim to model the brain.
- **Stage 4, identity traits:** a *trait* is a one-sentence, third-person statement of a stable tendency ("Isabella consistently avoids confrontation to preserve harmony"). Two ways to become one: **Path A** (reinforcement: a theme summary recurs on 3 different days, or 4 new entries land on one summary in one day) and **Path B** (pivotal: a single event scored at least 9). At most 5 traits are active and at most 120 tokens of them are appended to the scoring prompt (the *feed-forward* loop).
- **Reinforcement threshold 0.88:** a night's summary counts as reinforcing an existing entry only if its similarity is at least 0.88.
- **Pivotal threshold T = 9:** a single event scored 9 or 10 can become a trait at once. The rule chosen before the data would have given 8; the project manager set 9 on recorded evidence (an override, disclosed).
- **Idempotent:** doing it twice has the same effect as once (a second sweep on the same night changes nothing).
- **Provenance:** where a trait came from. We check whether a trait is more similar to the agent's *priors text* or to its *source memories*. If it were closer to the priors, it would suggest the model just echoed the priors instead of learning from experience.

### 5.3 The two conditions
- **Arm / condition / baseline / staged:** *Arm B (baseline)* = the original flat stream with periodic reflection on. *Arm S (staged)* = our four stages with periodic reflection off. "Arm" is just experiment jargon for a condition.
- **Everything else held fixed:** same world, schedules, events, model and embedding model.
- **Pinned model:** one fixed model for both arms, so the comparison is not confounded by switching models.

### 5.4 Infrastructure (the "zero-cost" part)
- **Free-tier API:** a provider's free usage allowance (here Google Gemini keys). Each key has daily and per-minute limits.
- **Router:** our component through which every model call passes. It rotates many keys, paces requests, caps each key at **450 requests per quota day**, pins the model, classifies rate-limit errors, waits out outages and logs every call.
- **Quota day / daily reset:** the provider's usage counters reset once a day (about 12:30 IST). When every key is at its cap the run pauses and resumes after the reset.
- **429 / rate-limit wave:** HTTP 429 means "too many requests". On the free tier these arrive in bursts shared across keys; the router backs off and retries. About 17 percent of wall time in each arm was spent waiting.
- **Call ledger:** a database table recording every model call (purpose, tokens, agent, time). Efficiency numbers come only from it; evaluation calls are kept out.
- **Autosave / supervisor / watchdog:** the run saves every 15 simulated minutes; a supervisor restarts it from the last save after a crash; a watchdog restarts it after a machine restart.
- **Output normalizer:** a small, identical-for-both-arms clean-up of model replies (removes code fences and annotation echoes) so that the original parsers accept them.
- **Fail-safe value:** the default the original code uses when a model reply is rejected after several tries (for example "yes" for "should I start a conversation?"). Not a model answer.
- **Inspector / viewer:** the read-only web page that replays the town, shows each memory stage, compares the two runs and shows the findings. It never calls a model and never changes a run.

### 5.5 Evaluation
- **Pre-registration:** writing the design, predictions and rules down and committing them before seeing the data, so the results cannot be bent to fit afterwards.
- **Prediction scorecard:** every prediction scored *right*, *wrong* or *undecidable* (when our own rules say the data cannot decide, for example fewer than 3 questions).
- **Recall questions:** 39 authored questions (27 about injected events, 3 about repeated themes, 9 about ordinary schedule entries). One question (about event I6) is excluded because the staged agent never perceived the event, leaving **38**. Answers are given through each agent's own retrieval and one fixed prompt.
- **Checkpoint:** a saved copy of a run at a given step. Questions are asked of copies, never of the live run.
- **Key-fact checklist grader:** a rule-based scorer that counts which required facts appear in an answer (no LLM judge). Score = items matched / items required (0 to 1). Validated against 30 hand-labelled answers: 94.7 percent item agreement.
- **Coherence / LLM judge:** the same probe questions are asked on day 1 and on day 3 and a judge labels each pair *consistent*, *contradictory* or *unrelated*. The judge must first score at least 80 percent on 20 authored pairs (it scored 20 of 20).
- **Confusion matrix:** a table of the judge's labels against the true labels, showing exactly which mistakes it makes.
- **Bootstrap and 95 percent interval:** resample the question-level differences many times to see how much the average could wobble. An interval that includes zero means "no detectable difference". We use it descriptively only.
- **Replay controls:** re-score the same 299 recorded events under different prompts: the plain baseline prompt, a length-matched neutral filler, another persona's priors, and the staged prompt. This isolates what the priors text does to scores, with the events held fixed.
- **Mismatch priors / neutral filler:** the "wrong persona" and "no information" controls in the replay.
- **Claim boundary:** the line between what the data support and what they do not. We keep a written list of claims we will not make.
- **Threats to validity:** the reasons the results might not mean what they seem (small sample, authored data, author-written labels, fallbacks).

---

## 6. Slide-by-slide guide

Format for each slide: **On the slide**, **Say** (a script you can read or paraphrase), **Numbers and keywords** (what and why), **Questions this slide invites**, **Watch out**. Suggested time: 20 to 25 minutes in total.

### Slide 1: Title and team (30 s)
**On the slide:** title, department, team (T. Umesh Chandra, P. Chethana Reddy, K. Harish), guide Jagadeesh.
**Say:** "Good morning. We present DevMem-Agents, a staged developmental memory for generative agents, built and evaluated under a zero-cost inference constraint. We thank our guide, Jagadeesh, Assistant Professor."
**Keywords in the title:** *staged developmental memory* = memory organised in stages that build on each other, like experience becoming knowledge becoming identity; *generative agents* = LLM-driven characters (section 5.1); *zero-cost inference constraint* = every model call uses a free tier, no paid usage.
**Question:** "What does 'developmental' mean?" Answer: the memory develops over time, from raw events to general summaries to stable traits. It is a design metaphor, not a claim about human development.

### Slide 2: Abstract (1 min)
**Say:** read the three ideas: (1) the problem (flat stream, importance only by a number), (2) our four-stage memory and zero-cost infrastructure, (3) the pre-registered comparison and the honest result: both arms completed; 10.1 percent of staged memories consolidated into 16 summaries and 14 traits; recall not detectably different; 23 percent fewer calls but reflection was off, so no credit to the stages; persona text shifts scores but not specifically for the agent's own persona; no improvement claimed.
**Numbers:**
- *10.1 percent* = 589 of 5,822 staged episodic entries were folded into summaries.
- *Recall -0.039 (95 percent interval -0.142 to 0.061)*: average staged-minus-baseline checklist score across 38 questions (pooled mean -0.0395). The interval comes from resampling the questions within each agent (that resampling's own mean is -0.044; use "about -0.04"). Because the interval includes zero we say "no detectable difference"; a small decline cannot be ruled out.
- *23 percent fewer calls*: 9,100 versus 11,858 unique model calls (deck shows 9,112, see section 8).
**Keywords:** pre-registered, bootstrap interval, persona-conditioned (section 5).
**Watch out:** do not read "no claim" as a weakness; it is the main discipline of the study.

### Slide 3: Introduction (1 min)
**On the slide:** four boxes: background, domain/technology, motivation, real-world relevance.
**Say:** background: Park et al. combine an LLM with a memory stream, reflection and planning; retrieval ranks records by recency, importance and relevance. Technology: LLM-based agent simulation, embeddings, similarity clustering, the free-tier Gemini API. Motivation: a flat stream treats a glance and a repeated argument alike; inspiration from episodic/semantic memory and sleep consolidation. Real-world relevance: believable game characters, social prototyping, rehearsal spaces; multi-day simulations are costly, so a zero-cost design widens access.
**Questions:** "Why sleep?" Because in the simulation each agent has a natural pause (sleep) when nothing new arrives, a convenient moment to organise the day, and sleep consolidation is the best-known biological analogy (Diekelmann and Born). It is inspiration, not a brain model. "Real-world use?" See section 2.

### Slide 4: Problem statement (1 min)
**On the slide:** the research question; existing problem; challenges; need.
**Say:** the question is deliberately a controlled comparison: only memory changes. Existing problem: one flat stream, records differ only by importance; no way to turn many similar episodes into a general statement. Challenges: records grow while the prompt budget does not; lasting traits look like moods; a fair comparison on free-tier quotas is hard. Need: store experiences faithfully, then distill them; measure cost; give honest, pre-registered evidence.
**Question:** "Why is a fair comparison hard on free tiers?" Quotas cap each key, rate limits arrive in shared waves, models differ in behaviour. So we pinned one model, rotated keys, logged every call and removed evaluation calls from the efficiency numbers.

### Slide 5: Existing system, Smallville (1 min)
**On the slide:** observation, flat stream, retrieval (recency + importance + relevance), periodic reflection; limitations; problems.
**Say:** the existing system is the published Smallville architecture. Limitations are structural: importance is a single number set at write time; generalisation only happens through periodic reflection; agents change only by accumulating records. Problems: retrieval must rediscover patterns each time; the original paper reports thousands of dollars of tokens for 25 agents over two days; and we found hazards in the upstream code: a silent embedding fallback and errors saved as "TOKEN LIMIT EXCEEDED".
**Numbers:** "thousands of dollars for 25 agents over 2 days" is the original authors' own cost statement, not ours. Present it as "reported by the original paper".
**Keywords:** silent embedding fallback = if the embedding service failed, the original code quietly used stand-in vectors, so retrieval would run on meaningless numbers without anyone noticing; "TOKEN LIMIT EXCEEDED" = a fixed error string returned on failure that the original code then saved as if it were a real model answer (a plan or a memory).
**Question:** "Did you verify those hazards?" Yes: we found them reading and running the code, made the embedding failure loud, and count failures instead of storing them.

### Slide 6: Proposed system (1 min)
**On the slide:** four numbered stages; proposed solution; key features; advantages "by design".
**Say:** replace the flat stream with four stages; the world is unchanged and our edits are additive hooks; free-tier APIs through a router with a call ledger. Features: seeded priors, persona-conditioned scoring, nightly clusters becoming source-linked summaries, traits from reinforcement or pivotal events. Advantages: patterns stored once, summaries trace to sources, lasting traits kept apart from moods, costs measured and reproducible.
**Watch out:** the slide says "by design": these are properties of the design. What the data later show is separate (slides 16 to 19). Say that explicitly.
**Question:** "What does 'additive hooks' mean?" We did not rewrite the simulation; we added small calls at a few points (where an event is scored, where the agent falls asleep, where retrieval ranks) and kept the original functions in place.

### Slide 7: Literature survey (2 min)
**On the slide:** table of related work.
**Say (row by row):**
- *Park et al., 2023 (ACM UIST), Generative Agents:* memory stream, scored retrieval, reflection; believable behaviour; but retrieval failures, embellishment and high cost. Our base.
- *Packer et al., 2023 (arXiv), MemGPT:* treats the LLM like an operating system, paging information in and out of a limited context; goes beyond the context window; does not form traits.
- *Zhong et al., 2024 (AAAI), MemoryBank:* summarises dialogue and lets memory strength decay over time (forgetting curve); adapts, but is dialogue-centred.
- *Shinn et al., 2023 (NeurIPS), Reflexion:* the agent writes verbal feedback on its failures in an episodic buffer and does better next time; per-task, not long-term identity.
- *Zhang et al., 2024 (arXiv), survey:* catalogues memory designs; notes there are no standard evaluations.
- *This work:* priors, episodic, consolidation, identity; source-tracked, free-tier, with a fair baseline; no gain shown at this scale.
**The research gap (say this):** combining seeded priors, nightly consolidation with source tracking and identity feedback, tested against the flat stream under a pinned model and a pre-registered protocol.
**Question:** "How is yours different from MemGPT?" MemGPT solves *where information lives* (context versus external storage); we address *how experience is organised and generalised* (summaries, traits). They are complementary.

### Slide 8: Software requirements (30 s)
**Say:** Python for the code; Smallville with its Phaser web front end; `gemini-3.1-flash-lite` pinned for both arms; `gemini-embedding-001` with 3,072-dimension vectors and a persistent cache; memory stores and average-linkage clustering; an offline test suite that needs no network; VS Code and GitHub; local runs with a supervisor that resumes from the last autosave.
**Numbers:** "100+ tests": the repository has about 420 test functions; "over 100" is true, "over 400" is also true (see section 8).
**Keywords:** pinned; 3,072-d; cache; supervisor (section 5).
**Question:** "Why this model?" It is free-tier, fast, and many keys were available, which the zero-cost constraint requires. The original study used another model; we say so as a disclosed difference.

### Slide 9: Hardware requirements (30 s)
**Say:** an ordinary laptop (i5 or equivalent, 8 GB RAM, SSD); no GPU, because all model and embedding work goes to free-tier APIs; the run pauses when every key hits its cap and resumes after the daily reset; a stable internet connection with backoff on failures.
**Numbers:** $0 inference cost; 450 requests per key per quota day (enforced by the router); 0 local GPUs.
**Why 450:** it keeps each key safely below the provider's daily limit (we observed a key hit the provider limit at 279 once, so the cap protects against surprises); the router also marks keys that hit a real limit earlier.
**Question:** "Is zero cost really zero?" Inference was zero; the laptop and electricity are ours. No paid key or credit was used.

### Slide 10: System architecture (1 to 2 min)
**On the slide:** diagram: Smallville world, Stage 1 priors (fixed), Stage 2 episodic store, Stage 3 consolidation (sleep-triggered), Stage 4 identity traits (at most 5, at most 120 tokens, appended to scoring in the staged arm only), infrastructure for both arms.
**Say:** walk left to right. The unchanged world feeds the episodic store. When an agent falls asleep a sweep clusters records into semantic summaries. Summaries that recur become traits. Traits return to the scoring prompt (the feedback loop). Priors are permanent. Infrastructure is identical for both conditions: router with key rotation and a pinned model, embedding cache, call ledger, autosave runner, read-only inspector.
**Question:** "Where is the feedback loop and why does it matter?" Traits are appended to the scoring prompt, so what the agent has become changes how it scores new events. This is what makes it "developmental": experience shapes identity, identity shapes how later experience is valued.

### Slide 11: Implementation / methodology (2 min)
**Say, by stage:**
1. *Priors:* 4 to 6 permanent behavioural statements per agent, with friction between some pairs (for example Isabella versus Wolfgang). The baseline gets the same statements as ordinary memories, so it is not disadvantaged.
2. *Episodic store and scoring:* the original importance prompt plus the priors block; a test checks nothing else differs. Consolidated entries get retrieval weight 0.5.
3. *Sleep consolidation:* at sleep start, cluster entries with importance at least 3 by average linkage at cosine 0.82; clusters of 3 or more become third-person summaries with source ids; a once-per-night marker.
4. *Identity traits:* reinforce at cosine at least 0.88; promote after 3 days or 4 same-day entries; pivotal path: score at least 9; at most 5 traits, fed back into scoring.
**Why these numbers:** 3 (floor) removes trivial records; 0.82 and 0.88 are design choices (the first from a fixture where single linkage at 0.78 merged unrelated themes and average at 0.82 did not; the second tuned once on a scripted fixture); 4 and 3 days are design choices; T = 9 was fixed by an explicit override because the pre-set rule gave 8 and would have called all five authored significant events pivotal. None is calibrated on natural data, and slide 20 shows one consequence.
**Question:** "Why 0.5 for consolidated records?" So that when a summary and its sources are both retrieved they do not crowd the prompt twice; it still lets raw detail appear when it is highly relevant. It is a design parameter, not tuned.

### Slide 12: Algorithm (2 min)
**On the slide:** input/process/output; dataset and setup; the retrieval score formula; the nightly sweep pseudocode.
**Retrieval score:** score(m) = w_r r̂ + w_i î + w_v v̂, where r̂, î, v̂ are the recency, importance and relevance of memory m, each scaled to 0 to 1 (min-max). The relevance term v̂ is the cosine similarity between the query and the memory. This is the original formula (code weights: recency 0.5, importance 2, relevance 3); our only change is multiplying the score of consolidated entries by 0.5.
**Pseudocode, line by line:**
- E ← unconsolidated entries with importance at least 3: the candidates for tonight.
- C ← average-linkage clusters of E at cosine at least 0.82: group similar memories.
- For each cluster of size at least 3: write a third-person summary; find the nearest existing semantic entry x; if cosine(s, x) is at least 0.80 merge s into x, else write s as a new entry with source ids; flag the cluster's sources as consolidated.
- If cosine(s, x) is at least 0.88, reinforce x (counts as another night of evidence).
- Promote reinforced x when seen on 3 days or 4 same-day; promote any entry scored at least T = 9 (pivotal).
**Dataset and setup:** Smallville, 3 agents, 3 compressed days, 27 injected persona-neutral events, same pinned model in both arms.
**Question:** "Why are there two thresholds, 0.80 and 0.88?" 0.80 decides whether a new summary is basically a repeat of an old one (merge it); 0.88 is stricter, deciding that the repeat is strong enough to count as another night of evidence for a trait.

### Slide 13: Implementation and screenshots (2 min, needs your screenshots)
**On the slide:** three placeholders ("Insert screenshot": replay view, side-by-side runs, cost view) and four component bullets (router, embeddings, runner, inspector).
**Action needed:** replace the placeholders with screenshots from the viewer. Start it with `python devmem/api/serve.py --a p7_staged --b p7_baseline --tab town --port 8765` and open `http://127.0.0.1:8765/ui/index.html`. Capture: (1) **Town replay**: click "Day 2", click an avatar so its memory panel opens, both panes visible; (2) **Side by side**: choose an agent and a morning range so the "first step where the action text differs" banner shows; (3) **Cost view**: the calls-by-class stacked bars for both arms. A fourth useful screenshot is the **Findings** scorecard.
**Say:** the router rotates free-tier keys, paces tokens and logs every call; embeddings use one model, are cached and fail loudly; the runner autosaves every 15 simulated minutes and resumes after a reload; the inspector is read-only and labelled "FULL RUN, 3 simulated days".
**Question:** "Is the viewer showing real data?" Yes: it reads the saved run files and the final results file; it makes no model calls.

### Slide 14: Evaluation protocol (2 min)
**Say, by box:**
1. *Design:* Arm B = flat stream, periodic reflection on; Arm S = Stages 1 to 4, periodic reflection off; 3 agents, 3 compressed days, 27 injected events.
2. *Recall:* 38 questions at the day-3 checkpoint, answered through each agent's own retrieval; scored by a key-fact checklist (no LLM judge); the checklist scorer agrees with 30 hand labels on 94.7 percent of items (54 of 57).
3. *Coherence and efficiency:* day-1 versus day-3 answers judged by an LLM judge that must first reach 80 percent on 20 authored pairs; calls are read from one ledger with evaluation calls excluded.
4. *Pre-registration and fairness:* predictions and exclusion rules committed before the full runs; same model, embeddings and schedules; bootstrap intervals; no significance claims.
**Why a checklist and not an LLM judge for recall:** it is rule-based, repeatable and cannot be swayed by fluent wording. **Why a judge for coherence:** comparing two free-text answers for consistency cannot be done by keywords, so we calibrated a judge first.
**Why periodic reflection is off in Arm S:** the design says Stage 3 replaces it (consolidation does the generalising). But it makes Arm S differ in two ways, which is why we do not credit stages for any difference (a limitation we state on slide 21).
**Question:** "Isn't turning reflection off unfair?" It is a disclosed design difference, chosen because the staged memory is meant to replace it; the fair reading is "staged memory with no periodic reflection against the original with it". A future ablation (reflection on in both) is listed as future work.

### Slide 15: Run completion (1 to 2 min)
**On the slide:** both arms finished all 3 days (25,920 steps each), 7 to 9 October 2026; unique calls to day 3: baseline 11,858, staged 9,112; events perceived 27 of 27 baseline and 26 of 27 staged (I6 excluded); disruptions; tiles: 2 arms completed, 0 router failures, 17 percent of wall time lost to rate-limit waves.
**Say:** running a three-day agent simulation on free keys was its own engineering problem. Disruptions: rate-limit waves, an application restart, a battery shutdown (the arms resumed from autosave); an upstream location parser stopped the staged arm twice; we fixed it identically in both arms; the scoring timeout was raised from 15 to 30 seconds in both arms.
**Numbers and why:**
- *Unique calls:* repeated steps after a restart are counted once. Staged is 9,100 in the final regenerated file (the deck's 9,112 predates removing one more replayed stretch; section 8).
- *I6:* the injected event "the wall clock over the register is stopped at ten past twelve" was not stored by the staged agent (Isabella stood still on a busy tile where several events compete for her limited attention; this explanation is plausible but unverified because attention internals are not logged). The pre-registered rule excludes the event's question from both arms.
- *17 percent:* about 373 minutes (baseline) and 368 minutes (staged) of waiting for rate limits over roughly 37 and 32 hours of running time; free-tier waves came in bursts shared across keys.
- *Why the parser stopped the arm:* the model's location reply began with the right area but continued with a list; the original validator rejects any reply containing a comma, tried five times (identical each time), then used its own default location "kitchen", which does not exist in the cafe; the lookup crashed. We changed the validator to accept an offered area followed by extra text, in both arms. In the recorded logs the change would have altered 5 area choices (2 staged, 3 baseline).
**Question:** "If you changed code mid-run, is the comparison still fair?" The change applies to both arms from their restarts, is disclosed, and the three affected baseline calls before the change stay as run.

### Slide 16: Results: recall and model calls (2 min)
**On the slide:** recall difference -0.039 (95 percent interval -0.142 to 0.061), equal scores on 31 of 38 questions; staged 23.2 percent fewer calls (9,112 vs 11,858), opposite to prediction E1; staged scoring prompts longer (608.4 vs 466.6 tokens), as predicted.
**What:**
- *Recall:* score by distance (baseline / staged): same day 0.83 / 0.79 (12 questions), one day 1.00 / 1.00 (11), two days 0.75 / 0.75 (12), theme counts 0.83 / 0.50 (3). By agent: Isabella 0.875 / 0.667, Maria 0.962 / 0.885, Klaus 0.731 / 0.885. Of 38 questions, 31 scored the same, staged was lower on 5 (Q_I2, Q_I_theme, Q_M_theme, N_I3, N_M3) and higher on 2 (Q_K7, N_K2).
- *Calls:* staged made 2,758 fewer calls. Where the gap sits (staged minus baseline): periodic reflection -425, importance scoring -1,235, action and object description -1,106, planning -32, dialogue -25, post-conversation memo -4; and staged added +54 consolidation and +15 identity calls.
- *Prompt length:* the priors block and trait block make each staged scoring prompt longer, as predicted.
**Why (honest):**
- *Why recall did not differ much:* the questions are mostly about recent, distinct events that both retrieval methods can reach; the staged changes mainly touch repeated patterns. Only 3 questions test repeated patterns, so that is where a difference would show and where we have least power.
- *Why staged lost on specific questions (hypotheses, not tested):* in Q_I2 ("what did a man ask about before leaving without ordering?") the baseline answered correctly and the staged agent said "I do not remember": the answer harness logs how many memories were retrieved but not which ones, so we cannot say whether the memory was missed by retrieval or ranked lower. One pre-registered reason: consolidated source records have their retrieval weight halved, so raw detail may rank lower. The theme-count questions are exactly where summaries (which describe a pattern, not a count) could drop details.
- *Why staged won on two:* for Q_K7 and N_K2 the baseline said "I do not remember", staged recalled. Randomness in what retrieval returns is a sufficient explanation; with one run we cannot separate it from a real effect.
- *Why 23 percent fewer calls (not explained, not credited):* about 15 percent of the gap is the missing periodic reflection; the largest parts are fewer scoring calls and fewer action-description calls, which means the staged agents perceived and acted less (a different trajectory), the cause of which we did not isolate. Staged also adds consolidation and identity calls but they are few (69).
**Questions:** "So did your memory work?" The mechanics worked; recall is not detectably different. "Why is E1 'wrong'?" We predicted staged would make slightly more calls; it made fewer. We report the prediction as wrong without re-explaining it away.
**Watch out:** the theme bar rests on three questions. Say so.

### Slide 17: Results: persona scoring (1 to 2 min)
**On the slide (deck wording):** neutral filler left friction scores at 3.0 to 3.5; another persona's priors raised them to 7.0 to 8.0; persona text shifts importance strongly but not specifically for the agent's own persona; "own-priors replay is being re-run, so four scoring-direction predictions are pending".
**Update (the re-run finished; use these numbers):** replaying the staged scoring prompt (with the agent's own priors and any traits it had at that time) on the same 299 events gives, for the social-friction events (2 per agent): Isabella 5.0, Klaus 6.0, Maria 3.0, against baseline 3.0, 3.5, 3.0 and mismatch (another persona's priors) 7.0, 7.0, 8.0. Whole-sample mean importance over 299 events: baseline 1.98, filler 1.94, staged 2.41, mismatch 2.47.
**What it means:** adding persona text moves scores up; adding a different persona's text moves friction scores up more than the agent's own text does. So persona text matters, but not in a persona-specific way: the model reacts to *any* personality block describing friction or sensitivity.
**Why (hypothesis):** the model reads "this person is sensitive to conflict" and raises scores for conflict events whichever persona it describes; to make scoring truly persona-specific you would need priors that differ in what they imply for the same event (future work).
**Prediction outcomes:** Isabella right (staged higher), Maria wrong (no difference), Klaus wrong (staged higher; predicted lower), filler right (filler stays near baseline), mismatch undecidable (no sign was registered). Each persona has only 2 friction events: small samples.
**Earlier experiment:** a separate earlier test (8 events, another model) found staged versus mismatch +0.25, not distinguishable from zero: the same conclusion.
**Question:** "Is a 7 versus 5 difference important?" It is a large shift in the score scale but based on two events per persona, so we describe it, not generalise it.
**Why the re-run:** the first replay reused the staged agent's recorded in-run scores, and the pre-registration says all conditions are replays. We corrected it (one verdict, Maria, flipped) and disclosed it in the ledger.

### Slide 18: Results: memory and identity (2 min)
**On the slide:** every nightly sweep completed for all 3 agents; 589 of 5,822 episodic entries consolidated (baseline 0 by design); only 1 of 14 traits closer to the priors than to its sources (predicted at least a third: wrong, in the good direction); coherence: judge calibrated 20 of 20; contradictory pairs baseline 1 of 18, staged 0 of 18; tiles 16 summaries, 14 traits, 10 percent consolidated.
**What and why:**
- *16 summaries:* nightly sweeps wrote 4 (Isabella), 4 (Klaus) and 8 (Maria) new summaries in total; most of what happened on nights 2 and 3 matched an existing summary at 0.80 or more and was merged into it (reinforced) rather than creating a new one. That is the design working: the same themes recur, so the memory stays small.
- *589 of 5,822 (10.1 percent):* the sweeps only consolidate records of importance at least 3, in clusters of 3 or more, at most 6 summaries a night with at most 12 sources each, so most single or unrelated records stay as they are.
- *14 traits:* 12 formed by the same-day path (4 or more entries added to one summary in one night), 2 by the pivotal path (Isabella trait 3, Klaus trait 5), and none by the three-different-days path. The same-day path fires easily; the 3-day path needs reinforcement on three separate days, which a 3-day run barely allows.
- *1 of 14 closer to priors than to sources:* we feared the model would just paraphrase the priors; cosine similarity of each trait to the priors text versus to its best source shows 13 of 14 sit closer to their sources. The prediction "at least a third" is scored wrong, which is the reassuring direction.
- *Coherence:* the same probe questions asked on day 1 and day 3 got consistent answers in 17 of 18 (baseline) and 18 of 18 (staged) pairs. One contradiction is not a difference.
**Questions:** "Are the traits sensible?" We show provenance and sources for each trait in the viewer (Memory inspector, staged run). The 0.88 reinforcement threshold has a known weakness (slide 20). "Why no 3-day traits?" see above.

### Slide 19: Prediction scorecard (2 min)
**On the slide:** the table of all registered predictions with outcomes. The deck shows persona predictions as "pending". Use the final table:

| ID | Prediction | Outcome | Numbers |
|---|---|---|---|
| E1 | Staged makes more calls, by under 10 percent | Wrong | staged 9,100 vs baseline 11,858 (-23.3 percent) |
| E2 | Longer scoring prompts in staged | Right | 608.4 vs 466.6 tokens |
| E3 | Consolidated fraction above 0 only in staged | Right | 0.101 vs 0 |
| R1 | Isabella's theme count: staged no worse | Undecidable | n = 1 (< 3); staged 0.0, baseline 0.5 |
| R2 | Klaus's theme count: staged no worse | Undecidable | n = 1 (< 3); 1.0 vs 1.0 |
| R3 | Pivotal events at 2 days within 0.2 | Undecidable | the registered definition matches no question (pivotal events happen on day 2, so they are 1 day old at day 3) |
| R4 | Mundane events at 2 days: staged at or below baseline | Right | n = 3; 0.833 vs 0.833 |
| R5 | Same-day questions within 0.1 | Right | n = 12; 0.792 vs 0.833 |
| S-Isabella | Own priors raise friction scores | Right | +2.0 over baseline |
| S-Maria | Own priors raise friction scores | Wrong | 0.0 (no change) |
| S-Klaus | Own priors lower friction scores | Wrong | +2.5 (went up) |
| S-filler | Neutral filler stays near baseline | Right | filler 1.94, baseline 1.98 |
| S-mismatch | Mismatch moves toward that persona | Undecidable | no sign was registered; mean 2.47 |
| D-1 | At least one third of traits closer to priors than to sources | Wrong | 1 of 14 |
| D-2 | Merges in the 0.80 to 0.88 band above 0 | Right | weak by design |
| M2 | Coherence (no prediction) | None | baseline 1 of 18, staged 0 of 18 contradictory |

**Tally (use this instead of the deck's):** 7 right, 4 wrong, 4 undecidable, 0 pending, 1 with no prediction (16 rows).
**Why "undecidable" exists:** our pre-registered rule says a prediction needs at least 3 questions (R1, R2 have one each) and a definition that matches real questions (R3). We did not redefine the prediction after seeing data. This is a strength.
**Why D-2 is "weak by design":** with the clustering threshold at 0.82, nearly every merge falls in the band 0.80 to 0.88, so a count above zero was almost certain.
**Question:** "Isn't 4 wrong a failure?" A pre-registered prediction being wrong is a finding. Reporting the wrong ones as plainly as the right ones is what pre-registration is for.

### Slide 20: Testing (1 to 2 min)
**On the slide:** table of test cases.
**Say:** these are the mechanics tests behind the claims. Explain each:
- *Prompt equivalence:* baseline and staged scoring prompts must be identical except the priors block: Pass.
- *Idempotent sweep:* a second sweep on the same night changes nothing: Pass (protects against double-consolidating after a restart).
- *Scripted-day consolidation:* a day of 16 scripted events, including idle ones and ones below the importance floor; only eligible entries were summarised and flagged: Pass.
- *Night key:* the first design keyed each sleeping tick by its own clock, which mislabeled 136 of 408 keys for sleep blocks that span noon; the rule was replaced to key by the start of the sleep block: Pass (fixed).
- *Full-run injection:* 27 injected events: 27 of 27 perceived in baseline, 26 of 27 in staged (I6 excluded): Partial.
- *Reinforcement threshold:* summaries of *other* themes should not reinforce an entry (cosine below 0.88) but did at 0.889 and 0.913: Fail (known limitation). It means the 0.88 threshold, tuned on a small scripted fixture, is not strict enough on real embeddings: traits can be reinforced by loosely related summaries.
**The footer:** an offline suite of over 100 tests (about 420 test functions in the repository), no network needed. The output-validity probe: without the router's normalizer the daily-plan outputs were unusable (0 usable in the 40-call probe across three models and three prompts), with it 6 of 6 daily plans from the pinned model were usable. (If asked for detail: the probe is described in `docs/phase5_stop5_report.md` and ledger entries D5 and D6.)
**Question:** "Why leave a failed test in the table?" Because hiding it would be misleading; it is a disclosed limitation of one of our design thresholds.

### Slide 21: Limitations and threats to validity (2 min)
**Say, three columns:**
- *What we cannot claim:* no significance tests (one run per arm); no stage-level cause (periodic reflection also off); no claim to model human memory.
- *Disclosed deviations:* router normalizer and fence rule; arena (location) validator fix; scoring timeout 15 to 30 seconds; resume from autosave; the pinned model differs from the original study's.
- *Other threats:* grader labels and judge pairs written by the authors (so they are not independent of the rubric); authored, compressed schedules and events; conversation starts defaulted to "yes" in both arms (the original "should I talk" function always fell back to its default "yes" in 14 of 14 calls, so the model did not decide who starts a conversation); also schedule revision fell back to the unchanged schedule in 38 to 39 percent of calls.
**Why a resumed run is not identical to an uninterrupted one:** after a restart the arm re-runs steps since the last save and the model's answers can differ; the replayed calls are counted once, but the paths are not guaranteed to match.
**Question:** "Does the default 'yes' invalidate the dialogue results?" It means conversation initiation was the same fallback in both arms, so it cannot differ between them, and we make no claim about conversation initiation.

### Slide 22: Conclusion and future scope (1 to 2 min)
**Say:** achievements: a four-stage memory built additively on Smallville; a pre-registered three-day comparison completed in both arms on free-tier compute. Outcome: every nightly sweep worked (16 summaries, 14 traits, 13 of 14 closer to their sources than to the priors); recall not detectably different (-0.039); no improvement claimed. Benefits: traceable memories, measured costs (23 percent fewer calls, reflection also off), every prediction scored. Future scope: (1) several runs per arm and more agents for statistics; (2) ablate each stage and turn periodic reflection on in both arms; (3) make persona-conditioned scoring persona-specific, test across models; (4) longer simulations and independent grader and judge labels.
**The honest summary:** the architecture worked as designed and runs on free-tier compute; this study does not show that staged memory improves recall, coherence or efficiency.
**Question:** "What is the single most important next experiment?" Several runs per arm with reflection on in both, so a difference can be tested and attributed.

### Slide 23: References (30 s)
**Say:** cite the base paper [1] first. [2] to [6] are cognitive-science references (Tulving on episodic/semantic memory; McClelland et al. and Kumaran et al. on complementary learning systems; Diekelmann and Born on sleep and memory; Spelke and Kinzler on core knowledge): design inspiration only. [7] to [11] are the closest memory systems and background (MemGPT, MemoryBank, Reflexion, retrieval-augmented generation, and the survey by Zhang et al.).
**Question:** "Which reference is closest to yours?" Park et al. (base) then MemoryBank and MemGPT.

### Slide 24: Queries (close)
**Say:** restate the claim boundary: the mechanics are demonstrated; the comparison shows no detectable recall difference and no demonstrated improvement. Thank the guide and the panel.

---

## 7. Results master table: what, why, and what it means

Keep every answer in the shape: **what we measured, what came out, why (or "we do not know why"), what it means.** Items marked *hypothesis* were not tested.

| Result | What | Why it came out so | What it means |
|---|---|---|---|
| Both arms finished | 25,920 steps each, 0 router failures, $0 | Router key rotation, pinned model, autosave and supervisor | The zero-cost pipeline works for a three-day, three-agent comparison |
| Recall -0.039 (interval -0.142 to 0.061) | Staged minus baseline checklist score over 38 questions | Questions mostly concern distinct recent events both retrievals reach; only 3 test repeated patterns | No detectable difference; a small decline cannot be ruled out |
| 31 of 38 equal | Same score on 31 questions; staged lower on 5, higher on 2 | Retrieval randomness plus possibly halved weight on consolidated sources (*hypothesis*) | Differences are few and run both ways |
| 23 percent fewer calls | 9,100 vs 11,858 unique calls | Periodic reflection off (about 425 calls) plus fewer scoring and action calls (different trajectory, cause not isolated) | Opposite to prediction E1; cannot be credited to the stages |
| 608.4 vs 466.6 tokens | Input tokens per scoring call | Priors and trait blocks are added to the prompt | Staged scoring costs more per call; as predicted |
| 589 of 5,822 (10.1 percent) | Entries folded into summaries | Importance floor 3, clusters of 3 or more, caps of 6 summaries and 12 sources a night | Consolidation is selective and works |
| 16 summaries | New summaries written (4, 4, 8) | Later nights mostly merged into existing summaries (0.80 rule) | Memory stays compact because themes recur |
| 14 traits | 12 same-day path, 2 pivotal, 0 three-day path | Same-day rule fires easily; three-day rule needs three separate days | Traits form, but the three-day path is barely testable in 3 days |
| 1 of 14 closer to priors | Trait text nearer to priors than to sources | Traits are written from the summaries, not the priors | Traits are not just echoes of priors (prediction D-1 wrong, in the good direction) |
| Persona scoring | Own priors: Isabella 5.0, Klaus 6.0, Maria 3.0; mismatch 7.0, 7.0, 8.0; baseline 3.0, 3.5, 3.0 (friction events) | The model reacts to any personality block about friction | Priors move scores but not persona-specifically |
| Coherence | Contradictory pairs: baseline 1 of 18, staged 0 of 18 | Both answer consistently; the judge was calibrated 20 of 20 | No difference |
| Scorecard | 7 right, 4 wrong, 4 undecidable, 0 pending, 1 no prediction | Rules fixed before the data | Honest accounting, wrong ones included |
| Reinforcement test failure | Other-theme summaries reinforced at 0.889 and 0.913 | 0.88 tuned on a small scripted fixture | Known limitation; traits may be reinforced by loosely related summaries |
| Fail-safe findings | "Should I talk" fell back to "yes" in 14 of 14 calls; schedule revision fell back in 38 to 39 percent | Replies rejected by the original parsers, then the default is used | Conversation starts are not a model decision in either arm; no dialogue claims |

---

## 8. Corrections to apply to the deck before presenting

The data were regenerated after the deck was written. Make these edits (or say them aloud):

1. **Slides 15 and 16: staged unique calls 9,112 -> 9,100;** the reduction becomes 23.3 percent (2,758 fewer). "23 percent" stays correct. If you cannot edit, say "about 9,100".
2. **Slide 17: replace "pending"** with the own-priors numbers (Isabella 5.0, Klaus 6.0, Maria 3.0 versus mismatch 7.0, 7.0, 8.0 and baseline or filler 3.0 to 3.5). Remove the sentence that the re-run is in progress.
3. **Slide 19 (and the scoring mention on slides 2 and 22): resolve the pending rows:** S-Isabella right, S-Maria wrong, S-Klaus wrong, S-filler right. The tally line becomes **7 right, 4 wrong, 4 undecidable, 0 pending, 1 no prediction**.
4. **Slide 2 and 16 recall interval:** the point value -0.039 is the pooled question mean; the interval comes from an agent-averaged bootstrap (mean -0.044). Say "about -0.04, interval -0.14 to 0.06, includes zero".
5. **Slide 13: add real screenshots** (Town replay, Side by side, Cost view, optionally Findings) from `http://127.0.0.1:8765/ui/index.html`.
6. **Slide 8: "100+ tests"** is true (about 420 test functions); you may say "over 400".
7. **Slide 20:** the "40 calls" probe is 40 calls across three models and three prompts, not 40 on the pinned model; the pinned-model figure is 6 of 6. The night-key figure "136 of 408" refers to keys of sleep blocks that span noon.
8. **Slide 18:** provenance is fine as written (1 of 14).

---

## 9. Master question bank

**Pain point and purpose**
- *What problem are you solving?* Flat memory cannot turn repeated experience into stable knowledge or identity, and studying fixes is costly and hard to trust (section 1).
- *Who benefits?* Game and simulation builders, role-play training, long-lived assistants, and researchers comparing memory designs (section 2). Only the research tooling was exercised here.
- *What is new?* Combination of priors, nightly source-linked consolidation and identity feedback, tested against the flat stream under a pinned model and a pre-registered protocol, on free tiers.
- *What did you improve in existing systems?* Organisation (patterns stored once, traceable), method (fair controlled comparison), cost (free-tier pipeline), reliability (fixes to silent fallbacks, saved error strings, parsers).

**Results**
- *Did it work?* The mechanics did; no recall or coherence improvement was shown.
- *Then why is the project worthwhile?* Section 3.3: working architecture, reusable pipeline, honest protocol, traceability, found defects, clear next steps.
- *Why fewer calls?* Reflection is off, and staged agents did fewer scoring and action calls; we did not isolate the cause.
- *Why is recall the same?* Mostly distinct, recent events; low power on pattern questions (only 3).
- *Is -0.039 significant?* No claim of significance; the interval includes zero.
- *Why 38 and not 39 questions?* The staged agent never perceived event I6; the pre-registered rule removes its question from both arms.
- *Why are 4 predictions undecidable?* Our own rules require at least 3 questions (R1, R2) or a matching definition (R3), and S-mismatch registered no sign.

**Method**
- *Why a baseline that receives priors?* So any difference is not due to the baseline lacking information.
- *Why pin one model?* Different models behave differently; pinning removes that confound.
- *Why free tier only?* Cost constraint, and to show access for small teams.
- *Why a key-fact checklist?* Rule-based, repeatable; validated at 94.7 percent item agreement on 30 hand labels (labels written by the developers).
- *Why only three agents and days?* Free-tier quotas and compute time; hence no statistics.
- *Is the data real?* Simulation data are produced by the real run; the 27 events and questions are authored by us, which we list as a threat.
- *Why did you change code mid-run?* The location parser crashed the run; fix applied identically to both arms and disclosed (touch point 6).

**Concept**
- *Is this like human memory?* Inspired by episodic versus semantic memory and sleep consolidation; no claim of modelling the brain.
- *Why average linkage?* Resists chaining of unrelated topics; single linkage at 0.78 merged unrelated themes in a fixture.
- *Where do thresholds come from?* Design choices, not calibrated on natural data; the 0.88 failure shows a weakness.
- *Could the model have copied priors into traits?* We checked: 13 of 14 traits are closer to their sources.
- *What if someone asks for the data?* All numbers sit in `docs/phase9_results_export_day3.json` and `.md`.

**Hard questions (answer plainly)**
- *"Your hypothesis failed."* We pre-registered both directions and report wrong predictions; the finding is a null result at this scale.
- *"Why not run longer?"* Free-tier quotas; longer runs and repeats are the first future step.
- *"The dialogue part is a fallback."* Yes, we state it (slide 21); it is identical in both arms and we make no dialogue claim.

---

## 10. Wording rules and file map

**Say:** "no detectable difference", "the data show", "pre-registered", "in this run", "hypothesis, not tested". **Avoid:** "proves", "significant", "improves", "because of the stages", "like the human brain".

**Label every figure:** captured (from a real run file), documented, synthetic, scripted, or live.

**Where to look**
| Topic | File |
|---|---|
| Everything about the project | `docs/TEAM_GUIDE.md` |
| Final numbers | `docs/phase9_results_export_day3.md` and `.json` |
| Claims we will not make | `docs/phase9_claims_not_supported.md` |
| Rulings and decisions | `docs/phase9_rulings.md`, `docs/CLAIMS_LEDGER.md` |
| Pre-registration | `docs/phase7_preregistration.md` |
| Fail-safe counts | `docs/phase9_failsafe_count.json` |
| Viewer (live demo) | `python devmem/api/serve.py --a p7_staged --b p7_baseline --tab town --port 8765`, then `http://127.0.0.1:8765/ui/index.html` |
| Plan, spec | `docs/PRD.md`, `docs/technical_implementation_plan.md` |
