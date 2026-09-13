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
