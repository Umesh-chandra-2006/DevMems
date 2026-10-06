"""
Stage 3: Sleep-Triggered Semantic Consolidation (Phase 5, decisions D1 to D7 as approved).

When an agent falls asleep, its unconsolidated episodic entries are clustered by embedding similarity
(single linkage over cosine), each multi-member cluster is summarized by the LLM into one semantic
memory that references its source entries, and the sources are flagged `consolidated`.

Design (approved at Stop 1):
  * D6: each summary is written into the live upstream AssociativeMemory as a thought node
        (s, p, o) = (agent, "consolidated", "memory"), `filling` = source node ids, so it is retrievable by
        new_retrieve and survives save/reload; it is mirrored to `semantic_memory` in SQLite.
        The live "consolidated" set is derived from the fillings of summary nodes.
  * D7: one marker row per (agent, night) in `consolidation_sweeps`, written in the same SQLite
        transaction as the semantic rows and flag flips. Night key = sim_day of the evening onset.
  * D3: summaries are scored with the staged event prompt (priors block included).
  * D2/D1: `apply_consolidated_weight` and `staged_reflection_disabled` are the two helpers the three small
        reverie/ hook points call; both are no-ops in baseline mode.
Baseline mode never reaches any of this code except through those no-op helpers.
"""

from datetime import datetime, timedelta
import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Union

import numpy as np
import yaml

from devmem.memory import episodic
from devmem.memory.priors import get_prompt_context
from devmem.router.llm_router import call_llm

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "consolidation.yaml"
SUMMARY_PREDICATE = "consolidated"
SUMMARY_OBJECT = "memory"

SUMMARIZATION_PROMPT_TEMPLATE = """{persona_context}

The following are related observations about {agent_name}, recorded today:
{cluster_entries}

Write ONE sentence, in the third person, that names {agent_name} and states the underlying pattern or takeaway
these related observations show about {agent_name}."""
SUMMARY_SYSTEM_PROMPT = ("Reply with exactly one sentence and nothing else: no preamble, no list, no explanation. "
                         "Write in the third person and use the person's name; never use I, me, my or we.")
SUMMARY_RETRY_SUFFIX = ("\n\nYour previous reply was: \"{previous}\"\nThat is not acceptable: it must be written in the "
                        "third person and name {agent_name}. Reply with one corrected sentence only.")

SEMANTIC_DDL = """
CREATE TABLE IF NOT EXISTS semantic_memory (
    entry_id             TEXT PRIMARY KEY,
    agent_id             TEXT NOT NULL,
    summary              TEXT NOT NULL,
    source_entry_ids     TEXT NOT NULL,
    importance_score     REAL,
    times_reinforced     INTEGER DEFAULT 1,
    distinct_days_reinforced INTEGER DEFAULT 1,
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_reinforced_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    graduated            BOOLEAN DEFAULT FALSE
);
CREATE TABLE IF NOT EXISTS consolidation_sweeps (
    agent_id     TEXT NOT NULL,
    night        INTEGER NOT NULL,
    sweep_time   TEXT NOT NULL,
    max_node_id  INTEGER NOT NULL,
    attempts     INTEGER NOT NULL DEFAULT 0,
    status       TEXT NOT NULL,
    PRIMARY KEY (agent_id, night)
);
"""


# ---------------------------------------------------------------------------------------------
# config and small helpers
# ---------------------------------------------------------------------------------------------
_CONFIG_CACHE: Dict[str, Any] = {}


def load_config(path: Optional[Path] = None) -> Dict[str, Any]:
    """Returns a copy of the config; the default file is read once per process (the sleep hook calls this
    every step)."""
    if path is not None:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    if not _CONFIG_CACHE:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            _CONFIG_CACHE.update(yaml.safe_load(f))
    return dict(_CONFIG_CACHE)


def init_consolidation_db(db_path: Union[str, Path]) -> Path:
    path = episodic.init_episodic_db(db_path=db_path)
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(SEMANTIC_DDL)
        conn.commit()
    finally:
        conn.close()
    return path


def night_id(sweep_time: datetime, boundary_hour: int = 12) -> int:
    """Night key: the sim_day of the evening onset. A signal before `boundary_hour` belongs to the
    previous night (the 00:00 carry-over sleep block). Day 1 at 00:00 is night 0."""
    day = episodic.calculate_sim_day(sweep_time)
    return day - 1 if sweep_time.hour < boundary_hour else day


def is_sleeping(description: Optional[str], markers: Sequence[str]) -> bool:
    d = (description or "").lower()
    return any(m in d for m in markers)


def _is_summary_node(node: Any) -> bool:
    return (getattr(node, "type", None) == "thought" and getattr(node, "predicate", None) == SUMMARY_PREDICATE
            and getattr(node, "object", None) == SUMMARY_OBJECT)


def consolidated_node_ids(a_mem: Any) -> set:
    """Live-memory view of the `consolidated` flag: union of `filling` over summary thought nodes."""
    out = set()
    for node in a_mem.id_to_node.values():
        if _is_summary_node(node) and node.filling:
            out.update(node.filling)
    return out


def _normalize(m: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(m, axis=-1, keepdims=True)
    n[n == 0] = 1.0
    return m / n


def cluster_by_similarity(embeddings: Sequence[Sequence[float]], threshold: float, linkage: str = "single"
                          ) -> List[List[int]]:
    """Cluster by cosine similarity >= threshold. Deterministic: members sorted ascending, clusters ordered by
    their smallest member. Isolated points come back as singleton clusters. Raises ValueError on mixed vector
    lengths or an unknown linkage.

    linkage="single" (default): union-find; any pair at or above the threshold joins two clusters (chaining possible).
    linkage="average": agglomerative; repeatedly merge the two clusters with the highest mean pairwise similarity
    while that mean is >= threshold (ties: lowest member indices first). Resists chaining."""
    n = len(embeddings)
    if n == 0:
        return []
    dims = {len(v) for v in embeddings}
    if len(dims) != 1:
        raise ValueError(f"embeddings have mixed dimensions {sorted(dims)}; refusing to cluster")
    if linkage not in ("single", "average"):
        raise ValueError(f"unknown linkage {linkage!r}")
    m = _normalize(np.asarray(embeddings, dtype=float))
    sim = m @ m.T
    if linkage == "average":
        clusters = [[i] for i in range(n)]
        while len(clusters) > 1:
            best, best_pair = None, None
            for x in range(len(clusters)):
                for y in range(x + 1, len(clusters)):
                    mean = float(sim[np.ix_(clusters[x], clusters[y])].mean())
                    if mean >= threshold and (best is None or mean > best + 1e-12):
                        best, best_pair = mean, (x, y)
            if best_pair is None:
                break
            x, y = best_pair
            clusters[x] = sorted(clusters[x] + clusters[y])
            del clusters[y]
        return sorted(clusters, key=lambda c: c[0])
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(n):
        for j in range(i + 1, n):
            if sim[i, j] >= threshold:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[max(ri, rj)] = min(ri, rj)
    groups: Dict[int, List[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return [sorted(g) for _, g in sorted(groups.items(), key=lambda kv: min(kv[1]))]


def _cos(a: Sequence[float], b: Sequence[float]) -> float:
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if a.shape != b.shape:
        raise ValueError("refusing to compare embeddings of different dimension")
    d = np.linalg.norm(a) * np.linalg.norm(b)
    return float(a @ b / d) if d else 0.0


def parse_summary(text: Any) -> str:
    """First non-empty line of the model reply with list/markdown/quote decoration removed."""
    import re
    for line in str(text or "").splitlines():
        line = re.sub(r"^\s*(?:[-*•]+|\d+[.)])\s+", "", line).strip("*_`\"' 	")
        if line:
            return line
    return ""


def is_third_person(summary: str, agent_name: str) -> bool:
    """True when the summary names the agent (full name or first name) and has no first-person words."""
    import re
    low = summary.lower()
    names = {agent_name.lower(), agent_name.split()[0].lower()}
    if not any(n in low for n in names):
        return False
    if re.search(r"\bI\b|\bI'(?:m|ve|ll|d)\b", summary):
        return False
    return not re.search(r"\b(?:my|me|mine|myself|we|our|ours)\b", low)


def _default_embed(text: str) -> List[float]:
    from persona.prompt_template.gpt_structure import get_embedding  # upstream path -> EmbeddingStore
    return get_embedding(text)


def _ledger_tokens(ledger_db: Optional[str], agent: str, since_utc: str) -> Dict[str, int]:
    from devmem.router import key_pool
    conn = key_pool.get_db_connection(ledger_db or key_pool.DEFAULT_DB_PATH)
    try:
        rows = conn.execute(
            "SELECT purpose, COUNT(*) c, COALESCE(SUM(tokens_in),0) ti, COALESCE(SUM(tokens_out),0) tout "
            "FROM llm_call_log WHERE agent_id = ? AND created_at >= ? AND purpose IN "
            "('consolidation_summary','importance_scoring') GROUP BY purpose", (agent, since_utc)).fetchall()
        return {r["purpose"]: {"calls": r["c"], "tokens_in": r["ti"], "tokens_out": r["tout"]} for r in rows}
    finally:
        conn.close()


# ---------------------------------------------------------------------------------------------
# sweep
# ---------------------------------------------------------------------------------------------
def _marker(conn: sqlite3.Connection, agent: str, night: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM consolidation_sweeps WHERE agent_id = ? AND night = ?",
                        (agent, night)).fetchone()


def _select_entries(conn, agent: str, sweep_time: datetime, cfg: Dict[str, Any]) -> List[sqlite3.Row]:
    rows = conn.execute(
        "SELECT entry_id, content, sim_timestamp, sim_day, importance_score FROM episodic_memory "
        "WHERE agent_id = ? AND consolidated = 0 AND sim_timestamp <= ? AND importance_score >= ? "
        "ORDER BY sim_timestamp, entry_id",
        (agent, sweep_time.strftime("%Y-%m-%d %H:%M:%S"), cfg["importance_floor"])).fetchall()
    ex = [s.lower() for s in cfg["exclude_description_substrings"]]
    return [r for r in rows if not any(s in r["content"].lower() for s in ex)]


def _apply_cluster(conn, persona, agent, plan, cfg) -> Dict[str, Any]:
    """create_or_reinforce for one planned summary (no external calls). Returns a record."""
    a_mem = persona.a_mem
    summary, importance, emb, sources, sweep_time = (plan["summary"], plan["importance"], plan["embedding"],
                                                    plan["sources"], plan["sweep_time"])
    source_nodes = [e.split(":", 1)[1] for e in sources]
    candidates = list(conn.execute(
        "SELECT entry_id, source_entry_ids FROM semantic_memory WHERE agent_id = ?", (agent,)).fetchall())
    best, best_sim = None, -1.0
    for row in candidates:
        node = a_mem.id_to_node.get(row["entry_id"].split(":", 1)[1])
        vec = a_mem.embeddings.get(node.embedding_key) if node is not None else None
        if vec is None or len(vec) != len(emb):
            continue
        s = _cos(emb, vec)
        if s > best_sim:
            best, best_sim = row, s
    now = sweep_time.strftime("%Y-%m-%d %H:%M:%S")
    if best is not None and best_sim >= cfg["match_threshold"]:
        existing = json.loads(best["source_entry_ids"])
        merged = existing + [e for e in sources if e not in existing]
        days = conn.execute(
            f"SELECT COUNT(DISTINCT sim_day) FROM episodic_memory WHERE entry_id IN ({','.join('?' * len(merged))})",
            merged).fetchone()[0]
        conn.execute(
            "UPDATE semantic_memory SET source_entry_ids = ?, times_reinforced = times_reinforced + 1, "
            "distinct_days_reinforced = ?, last_reinforced_at = ? WHERE entry_id = ?",
            (json.dumps(merged), days, now, best["entry_id"]))
        node = a_mem.id_to_node[best["entry_id"].split(":", 1)[1]]
        node.filling = list(dict.fromkeys(list(node.filling or []) + source_nodes))
        return {"action": "reinforced", "entry_id": best["entry_id"], "match_similarity": round(best_sim, 4),
                "sources_added": [e for e in sources if e not in existing], "distinct_days": days}

    keywords = set()
    for nid in source_nodes:
        n = a_mem.id_to_node.get(nid)
        if n is not None:
            keywords.update(k for k in n.keywords if k and "idle" not in k.lower())
    keywords = set(sorted(keywords)[:12]) | {"consolidated memory"}
    node = a_mem.add_thought(sweep_time, sweep_time + timedelta(days=30), agent, SUMMARY_PREDICATE, SUMMARY_OBJECT,
                             summary, keywords, importance, (summary, emb), source_nodes)
    entry_id = f"{agent}:{node.node_id}"
    days = conn.execute(
        f"SELECT COUNT(DISTINCT sim_day) FROM episodic_memory WHERE entry_id IN ({','.join('?' * len(sources))})",
        sources).fetchone()[0]
    conn.execute(
        "INSERT OR IGNORE INTO semantic_memory (entry_id, agent_id, summary, source_entry_ids, importance_score, "
        "times_reinforced, distinct_days_reinforced, created_at, last_reinforced_at) VALUES (?,?,?,?,?,1,?,?,?)",
        (entry_id, agent, summary, json.dumps(sources), importance, days, now, now))
    return {"action": "created", "entry_id": entry_id, "node_id": node.node_id, "distinct_days": days}


def run_nightly_sweep(
    persona: Any,
    sweep_time: datetime,
    db_path: Optional[Union[str, Path]] = None,
    force: bool = False,
    pinned_model: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
    embed_fn: Optional[Callable[[str], Sequence[float]]] = None,
    ledger_db: Optional[str] = None,
    log_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Consolidate one agent's unconsolidated episodic entries up to `sweep_time`.

    Idempotent per (agent, night): returns {"skipped": ...} if a `done` marker exists (unless force).
    All SQLite effects (semantic rows, consolidated flags, marker) commit in ONE transaction after every
    external call (LLM, embedding) has finished; a sweep whose clusters all fail leaves no `done` marker."""
    cfg = config or load_config()
    agent = persona.name
    embed = embed_fn or _default_embed
    db = init_consolidation_db(db_path or episodic.get_db_path())
    from devmem.memory import identity  # Stage 4 (Phase 6); lazy because identity imports this module
    stage4 = identity.stage4_enabled()
    if stage4:
        identity.init_identity_db(db)
    log_file = Path(log_path) if log_path else db.parent / "consolidation_log.jsonl"
    night = night_id(sweep_time, cfg["night_boundary_hour"])
    sim_day = episodic.calculate_sim_day(sweep_time)
    since = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    t0 = time.time()

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        marker = _marker(conn, agent, night)
        if marker is not None and not force:
            if marker["status"] == "done":
                return {"skipped": "already swept", "night": night}
            if marker["attempts"] >= cfg["max_attempts_per_night"]:
                return {"skipped": "max attempts reached", "night": night}
        entries = _select_entries(conn, agent, sweep_time, cfg)
    finally:
        conn.close()

    record: Dict[str, Any] = {"agent": agent, "sim_time": sweep_time.strftime("%Y-%m-%d %H:%M:%S"), "night": night,
                              "entries_considered": len(entries), "threshold": cfg["cluster_similarity"], "linkage": cfg.get("linkage", "single"),
                              "min_cluster_size": cfg["min_cluster_size"], "importance_floor": cfg["importance_floor"],
                              "pinned_model": pinned_model, "failures": [], "fallbacks": 0}
    a_mem = persona.a_mem
    usable, vectors = [], []
    for r in entries:
        node = a_mem.id_to_node.get(r["entry_id"].split(":", 1)[1])
        vec = a_mem.embeddings.get(node.embedding_key) if node is not None else None
        if vec is None:
            record["failures"].append(f"no embedding for {r['entry_id']}")
            continue
        usable.append(r)
        vectors.append(vec)
    clusters = (cluster_by_similarity(vectors, cfg["cluster_similarity"], cfg.get("linkage", "single"))
                if vectors else [])
    hist: Dict[int, int] = {}
    for c in clusters:
        hist[len(c)] = hist.get(len(c), 0) + 1
    record["cluster_size_histogram"] = {str(k): v for k, v in sorted(hist.items())}

    multi = [c for c in clusters if len(c) >= cfg["min_cluster_size"]]
    multi.sort(key=lambda c: (-len(c), -sum(usable[i]["importance_score"] or 0 for i in c), c[0]))
    multi = multi[: cfg["max_summaries_per_night"]]

    plans, llm_failed = [], 0
    priors_ctx = get_prompt_context(agent)
    for c in multi:
        members = sorted(c, key=lambda i: (-(usable[i]["importance_score"] or 0), usable[i]["sim_timestamp"]))
        members = sorted(members[: cfg["max_entries_per_prompt"]])
        prompt = SUMMARIZATION_PROMPT_TEMPLATE.format(
            persona_context=priors_ctx, agent_name=agent,
            cluster_entries="\n".join(f"- {usable[i]['content']}" for i in members))
        try:
            retries = 0
            current = prompt
            while True:
                raw = call_llm(current, tier=cfg["summary_tier"], purpose="consolidation_summary", agent_id=agent,
                               condition="staged", sim_day=sim_day, system_prompt=SUMMARY_SYSTEM_PROMPT,
                               pinned_model=pinned_model)
                summary = parse_summary(raw)
                if summary and is_third_person(summary, agent):
                    break
                if retries >= cfg.get("summary_retries", 1):
                    raise ValueError(f"summary not third person naming the agent after {retries} retries: {summary[:80]!r}")
                retries += 1
                record["summary_retries"] = record.get("summary_retries", 0) + 1
                current = prompt + SUMMARY_RETRY_SUFFIX.format(previous=summary[:200], agent_name=agent)
            importance = episodic.score_importance_persona_conditioned(agent, summary, kind="event", persona=persona)
            emb = list(embed(summary))
        except Exception as exc:  # counted, never silent
            llm_failed += 1
            record["failures"].append(f"{type(exc).__name__}: {str(exc)[:120]}")
            continue
        plans.append({"summary": summary, "importance": importance, "embedding": emb,
                      "sources": [usable[i]["entry_id"] for i in members], "sweep_time": sweep_time,
                      "prompt_entries": [usable[i]["content"] for i in members]})

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    results = []
    try:
        conn.execute("BEGIN")
        for plan in plans:
            res = _apply_cluster(conn, persona, agent, plan, cfg)
            res["summary"] = plan["summary"]
            res["sources"] = plan["sources"]
            res["source_contents"] = plan["prompt_entries"]
            res["importance"] = plan["importance"]
            results.append(res)
        if stage4:  # Phase 6: the per-night record the identity step reads, written in this same transaction
            identity.record_consolidation_events(conn, agent, night, results)
        flagged = sorted({e for p in plans for e in p["sources"]})
        if flagged:
            conn.execute(f"UPDATE episodic_memory SET consolidated = 1 WHERE entry_id IN ({','.join('?' * len(flagged))})",
                         flagged)
        failed_all = bool(multi) and not plans
        prev = _marker(conn, agent, night)
        attempts = (prev["attempts"] if prev else 0) + 1
        conn.execute(
            "INSERT INTO consolidation_sweeps (agent_id, night, sweep_time, max_node_id, attempts, status) "
            "VALUES (?,?,?,?,?,?) ON CONFLICT(agent_id, night) DO UPDATE SET sweep_time = excluded.sweep_time, "
            "max_node_id = excluded.max_node_id, attempts = excluded.attempts, status = excluded.status",
            (agent, night, record["sim_time"], len(a_mem.id_to_node), attempts, "failed" if failed_all else "done"))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    record.update({"summaries_written": sum(1 for r in results if r["action"] == "created"),
                   "summaries_reinforced": sum(1 for r in results if r["action"] == "reinforced"),
                   "entries_flagged": len(flagged), "status": "failed" if failed_all else "done",
                   "llm_tokens": _ledger_tokens(ledger_db, agent, since), "seconds": round(time.time() - t0, 1)})
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    record["results"] = results
    return record


def force_sweep(persona: Any, sweep_time: Optional[datetime] = None, **kwargs: Any) -> Dict[str, Any]:
    """Sweep regardless of any sleep signal (tests and end-of-run). Still idempotent per night unless force=True."""
    t = sweep_time or persona.scratch.curr_time
    res = run_nightly_sweep(persona, t, **kwargs)
    ident = _run_identity_after(persona, t, res, kwargs)
    if ident is not None:
        res["identity"] = ident
    return res


def _run_identity_after(persona: Any, sweep_time: datetime, res: Dict[str, Any], kwargs: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Phase 6 hook: the Stage 4 step that follows consolidation (None when STAGE4_ENABLED is off)."""
    from devmem.memory import identity
    if not identity.stage4_enabled():
        return None
    if res.get("status") == "failed":
        return {"skipped": "consolidation failed", "night": res.get("night")}
    return identity.run_identity_step(persona, sweep_time, db_path=kwargs.get("db_path"), embed_fn=kwargs.get("embed_fn"),
                                      pinned_model=kwargs.get("pinned_model"))


def maybe_sweep_on_sleep(persona: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
    """The sleep hook (called from persona.move in staged mode). Fires once per agent per night: an
    in-memory set short-circuits after a success; the SQLite marker makes it idempotent across reload.
    A failing sweep is logged and retried on later ticks up to `max_attempts_per_night`; it never raises."""
    cfg = kwargs.get("config") or load_config()
    t = persona.scratch.curr_time
    if t is None or not is_sleeping(persona.scratch.act_description, cfg["sleep_markers"]):
        return None
    night = night_id(t, cfg["night_boundary_hour"])
    done = persona.__dict__.setdefault("_devmem_swept_nights", set())
    if night in done:
        return None
    try:
        res = run_nightly_sweep(persona, t, **kwargs)
    except Exception as exc:
        logger.error("sleep sweep failed for %s: %s", persona.name, exc)
        return {"error": f"{type(exc).__name__}: {exc}"[:200]}
    if "skipped" in res or res.get("status") == "done":
        identity_ok = True
        try:
            ident = _run_identity_after(persona, t, res, kwargs)
        except Exception as exc:
            logger.error("identity step failed for %s: %s", persona.name, exc)
            res["identity"] = {"error": f"{type(exc).__name__}: {exc}"[:200]}
            identity_ok = False
        else:
            if ident is not None:
                res["identity"] = ident
                identity_ok = "skipped" in ident or ident.get("status") == "done"
        if identity_ok:
            done.add(night)
    return res


def reconcile_consolidation(persona: Any, db_path: Union[str, Path]) -> Dict[str, Any]:
    """P5.0a extension (D6/D7): after loading a saved run, roll the Stage 3 mirror back to the loaded memory.
    Removes semantic rows whose summary node is absent, removes sweep markers recorded after the loaded
    state (more nodes than loaded, or sweep_time later than the loaded clock), and recomputes the mirror's
    `consolidated` flags from the surviving semantic rows. Idempotent."""
    agent = persona.name
    db = init_consolidation_db(db_path)
    live_nodes = set(persona.a_mem.id_to_node.keys())
    loaded_clock = persona.scratch.curr_time
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("BEGIN")
        sem = conn.execute("SELECT entry_id, source_entry_ids FROM semantic_memory WHERE agent_id = ?", (agent,)).fetchall()
        dropped_sem = sorted(r["entry_id"] for r in sem if r["entry_id"].split(":", 1)[1] not in live_nodes)
        for eid in dropped_sem:
            conn.execute("DELETE FROM semantic_memory WHERE entry_id = ?", (eid,))
        dropped_markers = []
        for m in conn.execute("SELECT night, sweep_time, max_node_id FROM consolidation_sweeps WHERE agent_id = ?",
                              (agent,)).fetchall():
            later = loaded_clock is not None and m["sweep_time"] > loaded_clock.strftime("%Y-%m-%d %H:%M:%S")
            if m["max_node_id"] > len(live_nodes) or later:
                conn.execute("DELETE FROM consolidation_sweeps WHERE agent_id = ? AND night = ?", (agent, m["night"]))
                dropped_markers.append(m["night"])
        conn.execute("UPDATE episodic_memory SET consolidated = 0 WHERE agent_id = ?", (agent,))
        keep = set()
        for r in conn.execute("SELECT source_entry_ids FROM semantic_memory WHERE agent_id = ?", (agent,)).fetchall():
            keep.update(json.loads(r["source_entry_ids"]))
        if keep:
            conn.execute(f"UPDATE episodic_memory SET consolidated = 1 WHERE entry_id IN ({','.join('?' * len(keep))})",
                         sorted(keep))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {"agent_id": agent, "removed_semantic": dropped_sem, "removed_markers": sorted(dropped_markers),
            "consolidated_after": len(keep)}


# ---------------------------------------------------------------------------------------------
# hooks for the three small reverie/ touch points (both no-ops in baseline mode)
# ---------------------------------------------------------------------------------------------
def _staged() -> bool:
    import utils
    return getattr(utils, "MEMORY_MODE", "baseline") == "staged"


def staged_reflection_disabled(config: Optional[Dict[str, Any]] = None) -> bool:
    """D1 Option A: True when staged mode replaces upstream importance-triggered reflection."""
    if not _staged():
        return False
    return not (config or load_config())["staged_reflection"]


def apply_consolidated_weight(persona: Any, master_out: Dict[str, float], config: Optional[Dict[str, Any]] = None
                              ) -> Dict[str, float]:
    """D2 (ii): scale the retrieval score of consolidated source nodes by `consolidated_weight`
    (staged mode only; the same dict is returned untouched in baseline)."""
    if not _staged():
        return master_out
    weight = (config or load_config())["consolidated_weight"]
    consolidated = consolidated_node_ids(persona.a_mem)
    if not consolidated or weight == 1.0:
        return master_out
    return {k: (v * weight if k in consolidated else v) for k, v in master_out.items()}
