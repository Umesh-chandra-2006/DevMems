# DevMem-Agents: Technical Implementation Plan

This document translates plan.md and the UML diagrams into concrete engineering steps: repo structure, data schemas, module specs, prompt templates, pseudocode for the non-trivial algorithms, and a build order. Treat this as the spec you hand to Antigravity one section at a time.

---

## 1. Repository Structure

Fork `generative_agents` first, then layer your additions on top rather than rewriting existing modules in place. This keeps diffs reviewable and makes it easy to prove to your guide exactly what you changed versus what you reused.

```
devmem-agents/
├── reverie/                          # forked base repo (environment, perception, action, planning)
│   ├── backend_server/
│   │   ├── persona/
│   │   │   ├── memory_structures/    # ORIGINAL flat memory stream lives here — do not delete, keep for baseline runs
│   │   │   └── cognitive_modules/    # perceive, plan, execute — reused as-is
│   │   └── ...
├── devmem/                           # your new code, entirely additive
│   ├── router/
│   │   ├── llm_router.py             # provider selection + fallback logic
│   │   ├── providers.py              # Groq / Gemini / Nemotron adapters
│   │   ├── key_pool.py               # multi-key rotation + usage tracking
│   │   └── usage_log.db              # local sqlite usage ledger
│   ├── memory/
│   │   ├── priors.py                 # Stage 1
│   │   ├── episodic.py               # Stage 2
│   │   ├── consolidation.py          # Stage 3
│   │   ├── identity.py               # Stage 4
│   │   └── schema.sql                # full DB schema for all memory tables
│   ├── embeddings/
│   │   └── vector_store.py           # Chroma/FAISS wrapper
│   ├── evaluation/
│   │   ├── recall_test.py
│   │   ├── coherence_tracker.py
│   │   └── efficiency_logger.py
│   ├── api/
│   │   └── main.py                   # FastAPI app, wraps simulation loop
│   └── config/
│       └── personas/                 # your 4-6 hand-written Stage 1 prior files (yaml/json)
├── frontend/
│   ├── src/
│   │   ├── components/TownView.jsx   # Three.js scene
│   │   ├── components/AgentPanel.jsx # per-agent memory inspector
│   │   └── ...
└── docs/
    ├── plan.md
    └── uml_diagrams.md
```

**Key principle:** `reverie/` stays a near-untouched fork except for one integration point (Section 4). Everything novel lives in `devmem/`, which makes "here's exactly what I built" trivial to demonstrate.

---

## 2. Database Schema

SQLite for development, portable to Postgres later if needed. This schema is the direct implementation of the class diagram from UML_diagrams.md.

```sql
-- Stage 1: Personality Priors (permanent, pre-experience)
CREATE TABLE priors (
    agent_id        TEXT NOT NULL,
    statement       TEXT NOT NULL,
    category        TEXT,            -- disposition, conflict_style, social_orientation, etc.
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (agent_id, statement)
);

-- Stage 2: Episodic Memory
CREATE TABLE episodic_memory (
    entry_id            TEXT PRIMARY KEY,
    agent_id            TEXT NOT NULL,
    content              TEXT NOT NULL,
    sim_timestamp        TEXT NOT NULL,       -- in-simulation time, not wall clock
    sim_day              INTEGER NOT NULL,
    recency_score        REAL,
    importance_score      REAL,
    relevance_score       REAL,
    consolidated          BOOLEAN DEFAULT FALSE,
    created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_episodic_agent_day ON episodic_memory(agent_id, sim_day, consolidated);

-- Stage 3: Semantic Memory
CREATE TABLE semantic_memory (
    entry_id             TEXT PRIMARY KEY,
    agent_id             TEXT NOT NULL,
    summary               TEXT NOT NULL,
    source_entry_ids      TEXT NOT NULL,       -- JSON array of episodic_memory.entry_id
    importance_score       REAL,
    times_reinforced        INTEGER DEFAULT 1,
    distinct_days_reinforced INTEGER DEFAULT 1, -- for the 3+ day promotion path
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_reinforced_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    graduated                BOOLEAN DEFAULT FALSE
);

-- Stage 4: Identity Memory
CREATE TABLE identity_memory (
    entry_id            TEXT PRIMARY KEY,
    agent_id            TEXT NOT NULL,
    trait_statement       TEXT NOT NULL,
    promotion_path         TEXT NOT NULL,      -- 'count_based' | 'same_day' | 'pivotal'
    source_references      TEXT NOT NULL,      -- JSON array of semantic_memory.entry_id or episodic_memory.entry_id
    graduated_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- LLM call/token usage log (also doubles as efficiency evaluation data)
CREATE TABLE llm_call_log (
    call_id          TEXT PRIMARY KEY,
    provider          TEXT NOT NULL,
    model             TEXT NOT NULL,
    purpose           TEXT NOT NULL,          -- 'importance_scoring' | 'consolidation_summary' | 'identity_summary' | 'reflection' | 'planning'
    tokens_in          INTEGER,
    tokens_out          INTEGER,
    sim_day             INTEGER,
    agent_id            TEXT,
    condition           TEXT,                 -- 'baseline' | 'staged'
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- API key usage tracking (router internals)
CREATE TABLE key_usage (
    provider          TEXT NOT NULL,
    key_id             TEXT NOT NULL,
    date                DATE NOT NULL,
    requests_used        INTEGER DEFAULT 0,
    PRIMARY KEY (provider, key_id, date)
);
```

---

## 3. LLM Router (build this first, week 1)

### 3.1 Config structure

```yaml
# devmem/config/providers.yaml
providers:
  - name: groq
    priority: 1
    models:
      fast: "llama-3.1-8b-instant"      # high daily quota, used for Stage 2 scoring
      strong: "llama-3.3-70b-versatile" # lower daily quota, used for Stage 3/4
    keys:
      - env: GROQ_KEY_1
      - env: GROQ_KEY_2
      - env: GROQ_KEY_3
    daily_limit_fast: 14400
    daily_limit_strong: 1000

  - name: gemini
    priority: 2
    models:
      fast: "gemini-1.5-flash"
      strong: "gemini-1.5-flash"
    keys:
      - env: GEMINI_KEY_1
      - env: GEMINI_KEY_2
    daily_limit_fast: 1500
    daily_limit_strong: 1500

  - name: nemotron
    priority: 3
    models:
      fast: "nvidia/nemotron-mini"
      strong: "nvidia/nemotron-4-340b-instruct"
    keys:
      - env: NIM_KEY_1
    daily_limit_fast: 5000
    daily_limit_strong: 40
```

Verify actual current quotas for each provider before locking these numbers, free-tier limits change. Treat the yaml values as configuration, not hardcoded assumptions, so updating them later doesn't touch code.

### 3.2 Router logic (pseudocode)

```
function call_llm(prompt, tier, purpose, agent_id, condition):
    for provider in providers sorted by priority:
        for key in provider.keys:
            usage = key_usage_tracker.get(provider, key, today)
            limit = provider.daily_limit[tier]
            if usage < limit:
                try:
                    response = send_request(provider, key, tier, prompt)
                    key_usage_tracker.increment(provider, key, today)
                    log_call(provider, model, purpose, tokens, agent_id, condition)
                    return response
                except RateLimitError:
                    mark_key_exhausted(provider, key, today)
                    continue
                except ProviderError:
                    continue  # try next key/provider
    raise AllProvidersExhaustedError
```

### 3.3 Build/test order
1. Single-provider, single-key call working (Groq only)
2. Add key rotation within Groq
3. Add fallback to Gemini, then Nemotron
4. Add local usage tracking table and pre-emptive limit checks (don't wait for 429)
5. Load-test with a burst of dummy calls to confirm rotation actually triggers correctly

---

## 4. Integration Point with the Base Repo

The only place `reverie/` gets touched directly: the original `memory_structures/` and `cognitive_modules/` call sites where the base code (a) computes importance scores and (b) triggers reflection. Both get redirected to your `devmem/memory/` modules instead of the original flat logic.

- Base repo's importance-scoring function call → replaced with a call into `devmem/memory/episodic.py`'s persona-conditioned scorer
- Base repo's reflection trigger (currently importance-threshold based) → replaced with your sleep-action listener that calls `devmem/memory/consolidation.py`

Keep the original functions intact but unused (don't delete), so you can toggle between baseline and staged mode with a config flag rather than maintaining two separate codebases. This single toggle is what makes your side-by-side comparison runs trivial to execute.

```python
# reverie/backend_server/persona/cognitive_modules/perceive.py (integration point)
if config.MEMORY_MODE == "staged":
    from devmem.memory.episodic import score_importance_persona_conditioned as score_fn
else:
    from persona.memory_structures.spatial_memory import score_importance as score_fn
```

---

## 5. Stage 1: Priors Module

```python
# devmem/memory/priors.py

def load_priors(agent_id: str) -> list[str]:
    """Load hand-authored priors from config/personas/{agent_id}.yaml"""
    ...

def get_prompt_context(agent_id: str) -> str:
    """Format priors into a block to inject into scoring/planning prompts."""
    priors = load_priors(agent_id)
    return "This agent's core personality traits:\n" + "\n".join(f"- {p}" for p in priors)

def inject_into_baseline(agent_id: str):
    """Fairness control: write the same priors as a single initial memory
    stream entry for baseline (flat-memory) condition agents."""
    ...
```

Persona files, one per agent, e.g.:
```yaml
# devmem/config/personas/isabella.yaml
agent_id: isabella
priors:
  - "Assumes new people are trustworthy until proven otherwise, opens up quickly."
  - "Actively seeks out company, feels uncomfortable being alone for long."
  - "Values harmony above honesty, avoids saying something upsetting even if true."
  - "Deliberates carefully before acting on anything uncertain."
```

---

## 6. Stage 2: Episodic Memory with Persona-Conditioned Scoring

```python
# devmem/memory/episodic.py

IMPORTANCE_PROMPT_TEMPLATE = """
{persona_context}
{identity_context}

On a scale of 1 to 10, rate how important the following event is
to this specific agent, given who they are:

Event: "{observation}"

Respond with only a single number.
"""

def score_importance_persona_conditioned(agent_id: str, observation: str) -> float:
    persona_context = priors.get_prompt_context(agent_id)
    identity_context = identity.get_prompt_context(agent_id)  # empty until Stage 4 has graduated entries
    prompt = IMPORTANCE_PROMPT_TEMPLATE.format(
        persona_context=persona_context,
        identity_context=identity_context,
        observation=observation
    )
    response = llm_router.call(prompt, tier="fast", purpose="importance_scoring", agent_id=agent_id)
    score = parse_float(response)

    if score >= PIVOTAL_THRESHOLD:  # e.g. 9.5+
        flag_for_pivotal_promotion(agent_id, observation, score)

    return score

def log_episodic_memory(agent_id, content, sim_timestamp, sim_day, recency, importance, relevance):
    """Insert into episodic_memory table with consolidated=False"""
    ...
```

**Threshold to decide during implementation, not now:** `PIVOTAL_THRESHOLD`. Start high (9.5/10) so pivotal promotion stays genuinely rare, tune after watching real score distributions from a test run.

---

## 7. Stage 3: Sleep-Triggered Consolidation

```python
# devmem/memory/consolidation.py

SUMMARIZATION_PROMPT_TEMPLATE = """
{persona_context}

The following are related observations this agent experienced today:
{cluster_entries}

Write ONE sentence capturing the underlying pattern or takeaway
this agent would form from these related experiences.
"""

def run_nightly_sweep(agent_id: str, sim_day: int):
    entries = episodic.get_unconsolidated(agent_id, sim_day)
    if not entries:
        return

    embeddings = vector_store.embed_batch([e.content for e in entries])
    clusters = cluster_by_similarity(embeddings, threshold=SIMILARITY_THRESHOLD)

    for cluster in clusters:
        if len(cluster) < 2:
            continue  # isolated memory, stays as raw episodic entry
        summary = llm_router.call(
            SUMMARIZATION_PROMPT_TEMPLATE.format(
                persona_context=priors.get_prompt_context(agent_id),
                cluster_entries="\n".join(f"- {e.content}" for e in cluster)
            ),
            tier="strong", purpose="consolidation_summary", agent_id=agent_id
        )
        importance = episodic.score_importance_persona_conditioned(agent_id, summary)
        semantic_id = semantic_memory.create_or_reinforce(
            agent_id, summary, source_ids=[e.entry_id for e in cluster], importance=importance
        )
        episodic.flag_consolidated([e.entry_id for e in cluster])
        identity.check_promotion(semantic_id)

def cluster_by_similarity(embeddings, threshold):
    """Simple approach: pairwise cosine similarity, union-find or
    single-linkage clustering above threshold. Start simple, don't
    reach for a heavy clustering library unless simple grouping
    proves insufficient on real data."""
    ...
```

**Trigger wiring:** in the simulation loop, after an agent's action for the hour resolves to sleep (confirm exact representation in the forked repo, likely `agent.scratch.act_description` containing "sleeping" or similar, or a bed object occupancy flag), call `consolidation.run_nightly_sweep(agent_id, current_sim_day)` once per agent per day, guarded so it only fires once even if the agent remains asleep for multiple hourly ticks.

**Tuning note:** `SIMILARITY_THRESHOLD` is a knob you will need to empirically tune. Start around 0.75-0.8 cosine similarity, log cluster sizes during test runs, adjust if everything clusters into one giant blob (threshold too low) or nothing ever clusters (threshold too high).

---

## 8. Stage 4: Identity Promotion

```python
# devmem/memory/identity.py

COUNT_THRESHOLD_DAYS = 3
SAME_DAY_THRESHOLD = 5
PIVOTAL_THRESHOLD = 9.5  # shared with episodic.py, keep in one config location

def check_promotion(semantic_entry_id: str):
    entry = semantic_memory.get(semantic_entry_id)

    if entry.distinct_days_reinforced >= COUNT_THRESHOLD_DAYS:
        graduate(entry, path="count_based")
    elif entry.times_reinforced_today >= SAME_DAY_THRESHOLD:
        graduate(entry, path="same_day")

def flag_for_pivotal_promotion(agent_id, observation, score):
    """Called directly from episodic.py, bypasses consolidation entirely."""
    trait = summarize_pivotal_event(agent_id, observation)
    write_identity_entry(agent_id, trait, path="pivotal", source=[observation])

def graduate(semantic_entry, path):
    trait_statement = llm_router.call(
        TRAIT_SUMMARY_PROMPT.format(pattern=semantic_entry.summary),
        tier="strong", purpose="identity_summary", agent_id=semantic_entry.agent_id
    )
    write_identity_entry(semantic_entry.agent_id, trait_statement, path, source=[semantic_entry.entry_id])
    semantic_memory.mark_graduated(semantic_entry.entry_id)

def get_prompt_context(agent_id: str) -> str:
    """Feeds into the SAME prompt slot used by priors.get_prompt_context,
    called alongside it in episodic.py's scoring prompt builder."""
    entries = get_identity_entries(agent_id)
    if not entries:
        return ""
    return "Traits this agent has developed through experience:\n" + \
           "\n".join(f"- {e.trait_statement}" for e in entries)
```

---

## 9. Evaluation Harness

### 9.1 Recall accuracy
```
For each of N ground-truth events injected during a run:
    at time T+1day, T+3days, T+7days:
        query agent: "Do you remember anything about {event_topic}?"
        LLM-judge: does response correctly reference the event? score 0/1
    compute accuracy curve: baseline vs staged, at each time distance
```

### 9.2 Behavioral coherence
```
Periodically sample agent statements/beliefs about self and others
Store as (agent_id, subject, statement, sim_day)
At evaluation time, for each pair of statements about the same subject:
    LLM-judge: "Are these two statements consistent or contradictory?"
    flag contradictions, compute contradiction rate over time: baseline vs staged
```

### 9.3 Efficiency
```
Already logged continuously via llm_call_log table.
At evaluation time: SELECT sim_day, condition, COUNT(*), SUM(tokens_in+tokens_out)
    FROM llm_call_log GROUP BY sim_day, condition
Plot calls/tokens per simulated day, baseline vs staged.
```

---

## 10. Build Order (maps to the timeline in plan.md, now with concrete checkpoints)

| Checkpoint | What "done" looks like |
|---|---|
| Router working | A test script makes 50 dummy calls, exhausts one key, rotates automatically, logs usage correctly |
| Baseline running | Forked repo runs end-to-end on Groq instead of OpenAI, produces normal Smallville output |
| Config toggle works | Flipping `MEMORY_MODE` between `baseline` and `staged` actually changes which scoring function executes |
| Stage 1 done | Every agent's priors load correctly and appear in the scoring prompt (verify by logging the actual prompt sent) |
| Stage 2 done | Two agents with different priors witnessing the same scripted event produce different importance scores, verify this explicitly with a test case |
| Stage 3 done | After a full simulated day + sleep, at least one semantic memory exists with correct source references, and `consolidated` flags flipped correctly |
| Stage 4 done | Manually force a semantic memory to reinforce 3+ days in a test, confirm it graduates and appears in the next scoring prompt |
| Evaluation harness done | Run baseline and staged side by side for a short test window (2-3 simulated days, 3 agents), confirm all three metrics produce non-trivial output |
| Visualization done | Live town view renders, clicking an agent shows its current memory state across all four tables |

---

## 11. Things to Verify Once Inside the Actual Repo (not guessable from outside)

- Exact internal representation of "agent is sleeping" (action string vs. object occupancy event vs. scratch memory field)
- Exact function signature and call site for the existing importance-scoring logic, so the integration point in Section 4 attaches cleanly
- Whether the base repo's embedding calls (used for its own relevance scoring) are already wired to an embedding provider you can reuse, or whether you need to add a separate embedding call for Stage 3 clustering
- Confirm current free-tier daily limits for Groq/Gemini/Nemotron directly from each provider's docs before finalizing `providers.yaml`, these change over time and the plan should not silently rely on stale numbers
