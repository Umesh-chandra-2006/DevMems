# DevMem-Agents: Technical Implementation Plan

This document translates plan.md and the UML diagrams into concrete engineering steps: repo structure, data schemas, module specs, prompt templates, pseudocode for the non-trivial algorithms, and a build order. Treat this as the spec you hand to Antigravity one section at a time.

---

## 1. Repository Structure

Fork `generative_agents` first, then layer your additions on top rather than rewriting existing modules in place. This keeps diffs reviewable and makes it easy to prove to your guide exactly what you changed versus what you reused.

```
devmem-agents/
├── reverie/                          # forked base repo (environment, perception, action, planning)
│   ├── reverie/backend_server/      # actual upstream path is reverie/reverie/backend_server/ (kept as upstream lays it out)
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

**Pending decision (Phase 4 checkpoint):** run isolation (one memory DB file per simulation run vs. a `sim_code` column) and whether staged episodic entries mirror upstream memory nodes. Do not change this schema until that checkpoint is approved.

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

**Revision note (after Phase 2):** the yaml above is illustrative only. The repo's `devmem/config/providers.yaml` is the source of truth for models, priority order (currently Groq, then NVIDIA NIM, then Gemini) and quotas.

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

### 3.4 Rate-limit classification (added after Phase 3 review)

Two different things both arrive as HTTP 429: a transient per-minute limit (requests or tokens), and exhaustion of a daily quota. They need different handling, and the classifier must not depend on one hand-written substring.

1. The local usage ledger remains the first line of defense for daily limits (pre-emptive checks).
2. On a 429, classify using the provider's actual response: the retry-after value (header or body) and any quota identifiers in the body. Phrases indicating a per-day limit are expected signals, but the exact wording per provider must be taken from real captured payloads, not assumed.
3. A retry-after longer than a few minutes is treated as daily-style exhaustion until reset; a short one is treated as transient and the key is retried after that delay.
4. An unclassifiable 429 is treated as transient, with a per-key cooldown that escalates after consecutive 429s (circuit breaker), instead of disabling the key for the whole day.
5. Tests use fixtures built from real captured payloads from each provider, not invented error strings.

---

## 4. Integration Point with the Base Repo

`reverie/` (actual path `reverie/reverie/backend_server/`) is touched only at sanctioned points, each reported as such in the relevant phase report:

1. **LLM call sites** (Phase 2, done): OpenAI calls routed through the devmem router.
2. **Importance-scoring integration point in `perceive.py`** (scaffolded in Phase 2, wired in Phase 4): event and chat poignancy only, staged mode only.
3. **Persona initialization** (Phase 4): baseline-mode priors injection, idempotent on reload.
4. **Reflection replacement and sleep hook** (Phase 5).

Anything else is a deviation and must be reported as one.

Keep the original functions intact but unused (don't delete), so you can toggle between baseline and staged mode with a config flag rather than maintaining two separate codebases. This single toggle is what makes your side-by-side comparison runs trivial to execute.

Revision note: the original snippet here pointed at a scoring function in `spatial_memory.py`, which does not exist in upstream. Upstream scoring lives in the event and chat poignancy prompt functions called from the perceive module (exact names and call sites are confirmed in the Phase 4 report). The branch looks like this:

```python
# reverie/reverie/backend_server/persona/cognitive_modules/perceive.py (integration point)
if MEMORY_MODE == "staged":
    score = devmem.memory.episodic.score_importance_persona_conditioned(agent_id, description, kind)
else:
    score = <unchanged upstream call>
```

---

## 5. Stage 1: Priors Module

```python
# devmem/memory/priors.py

class PersonaNotFoundError(Exception): ...
class PersonaSchemaError(Exception): ...

def load_priors(agent_id: str, personas_dir=...) -> list[str]:
    """Load hand-authored priors from config/personas/. Raises PersonaNotFoundError
    if there is no file for the agent, PersonaSchemaError if the file is malformed."""
    ...

def get_prompt_context(agent_id: str, personas_dir=...) -> str:
    """Format priors into a block to inject into scoring/planning prompts."""
    priors = load_priors(agent_id)
    return "This agent's core personality traits:\n" + "\n".join(f"- {p}" for p in priors)

def inject_into_baseline(agent_id, persona, created_time=None, mode="atomic", personas_dir=...):
    """Fairness control: write the same priors into the baseline (flat-memory) agent's
    memory stream as one high-poignancy thought node per prior statement (mode="atomic",
    the default). mode="bundled" (one combined node) exists but is not used. Must be
    idempotent: reloading a saved simulation must not create duplicate prior nodes."""
    ...
```

Persona file schema as delivered (agent_id is the exact upstream persona folder name; category is for traceability to plan.md Section 7 and is not required by the loader):
```yaml
# devmem/config/personas/isabella_rodriguez.yaml
agent_id: "Isabella Rodriguez"
priors:
  - statement: "Avoids confrontation whenever possible, prefers to smooth over disagreements rather than let them sit."
    category: conflict_style
  - statement: "Actively seeks out company and feels uneasy spending long stretches of time alone."
    category: social_orientation
```

**Revision note (after Phase 3 review):** baseline injection was amended from a single bundled entry to atomic entries. In the real-memory retrieval test, the bundled node scored a flat 0.500 relevance for a conflict-related focal point, while atomic nodes surfaced the conflict-relevant priors at 1.000 and 0.803. **Intended asymmetry to disclose:** baseline priors are ordinary memories subject to recency decay and competition in the flat stream; staged priors are permanent.

---

## 6. Stage 2: Episodic Memory with Persona-Conditioned Scoring

```python
# devmem/memory/episodic.py

def score_importance_persona_conditioned(agent_id: str, observation: str, kind: str,
                                         identity_context: str = "") -> int:
    """kind is "event" or "chat". The staged prompt is the upstream prompt for that kind
    PLUS the priors block from priors.get_prompt_context(agent_id). Augment, never replace,
    so the priors block is the only difference between the two conditions.
    identity_context stays an empty string until Stage 4 exists (Phase 6)."""
    ...

def log_episodic_memory(agent_id, content, sim_timestamp, sim_day, recency, importance, relevance):
    """Record the entry with consolidated=False. Storage design (mirror into SQLite vs.
    extend upstream node vs. SQLite only) is decided at the Phase 4 checkpoint.
    sim_day = days since the fork's start date (day 1 = start date)."""
    ...
```

Rules:
- Retrieval (recency + importance + relevance) is unchanged.
- Thought poignancy (reflection) is untouched in this stage; reflection is replaced in Stage 3.
- Pivotal-event detection (a score at the top of the scale triggers immediate identity promotion) is Stage 4 work. It was in the original pseudocode here but is deliberately not part of Stage 2 implementation. `PIVOTAL_THRESHOLD` is decided in Phase 6 after watching real score distributions.

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
| Stage 2 done | Two agents with different priors witnessing the same scripted event produce different importance scores, verified with repeated trials (raw scores reported, not a single call) |
| Stage 3 done | After a full simulated day + sleep, at least one semantic memory exists with correct source references, and `consolidated` flags flipped correctly |
| Stage 4 done | Manually force a semantic memory to reinforce 3+ days in a test, confirm it graduates and appears in the next scoring prompt |
| Evaluation harness done | Run baseline and staged side by side for a short test window (2-3 simulated days, 3 agents), confirm all three metrics produce non-trivial output |
| Visualization done | Live town view renders, clicking an agent shows its current memory state across all four tables |

---

## 11. Open Verification Items

**Resolved:**
- Upstream path layout is `reverie/reverie/backend_server/` (Phase 0). Keep real paths.
- Embeddings: Phase 2 replaced the OpenAI embedding call with a cached Gemini embedding model plus a deterministic fallback.

**Still open:**
- Exact internal representation of "agent is sleeping" (action string vs. object occupancy event vs. scratch memory field). Resolved at the start of Phase 5.
- Verbatim upstream event and chat poignancy prompts, their call sites, and what persona information they already receive. Phase 4, Task 1.
- Stage 3 clustering embeddings: reuse the provider-based embedding path (rate-limit and quota cost) or use a local model. Decision checkpoint in Phase 5.
- Rate-limit classification against real provider payloads (Section 3.4). Raised in the Phase 4 report, fixed in a follow-up task.
- Free-tier quotas change over time; `providers.yaml` is the source of truth and is re-verified before final experiment runs.

---

## 12. Revision Log

- **Rev 2 (after Phase 3 review):** repository paths corrected (Sections 1, 4); schema pending-decision note (Section 2); provider note and rate-limit classification added (Section 3); Section 4 rewritten with the list of sanctioned touch points and the incorrect scoring snippet removed; Section 5 updated to the delivered module API and persona schema, with atomic baseline injection; Section 6 rewritten to the augment-the-upstream-prompt design with pivotal detection moved to Stage 4; Section 11 updated.
