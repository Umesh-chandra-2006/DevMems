"""
Stage 2: Episodic Memory.
Manages raw episodic memory logging, persona-conditioned importance scoring,
retrieval conditioning, and SQLite episodic mirroring.
"""

from datetime import datetime, date
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
from typing import Any, Dict, List, Optional, Union

from devmem.memory.priors import get_prompt_context
from devmem.router.llm_router import call_llm

logger = logging.getLogger(__name__)

# Default base directory for per-run storage
DEFAULT_STORAGE_ROOT = Path(__file__).resolve().parent.parent / "storage"
DEFAULT_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

# Upstream start date baseline: February 13, 2023
DEFAULT_SIM_START_DATE = date(2023, 2, 13)


def resolve_sim_code(sim_code: Optional[str] = None) -> str:
    """Resolve current simulation code from arg, env var, temp storage, or default."""
    if sim_code:
        return sim_code
    env_code = os.environ.get("SIM_CODE")
    if env_code:
        return env_code

    curr_sim_file = (
        Path(__file__).resolve().parent.parent.parent
        / "reverie"
        / "environment"
        / "frontend_server"
        / "temp_storage"
        / "curr_sim_code.json"
    )
    if curr_sim_file.exists():
        try:
            with open(curr_sim_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("sim_code"):
                    return str(data["sim_code"]).strip()
        except Exception:
            pass

    return "default_sim"


def get_db_path(sim_code: Optional[str] = None, storage_root: Optional[Union[str, Path]] = None) -> Path:
    """Get path to the SQLite database file for the given simulation run."""
    code = resolve_sim_code(sim_code)
    root = Path(storage_root) if storage_root else DEFAULT_STORAGE_ROOT
    db_dir = root / code
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "memory.db"


def init_episodic_db(db_path: Optional[Union[str, Path]] = None, sim_code: Optional[str] = None) -> Path:
    """Initialize episodic memory database and table schema if not already present."""
    target_path = Path(db_path) if db_path else get_db_path(sim_code=sim_code)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(target_path))
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS episodic_memory (
                entry_id            TEXT PRIMARY KEY,
                agent_id            TEXT NOT NULL,
                content             TEXT NOT NULL,
                sim_timestamp       TEXT NOT NULL,
                sim_day             INTEGER NOT NULL,
                recency_score       REAL,
                importance_score    REAL,
                relevance_score     REAL,
                consolidated        BOOLEAN DEFAULT FALSE,
                created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_episodic_agent_day 
            ON episodic_memory(agent_id, sim_day, consolidated);
        """)
        conn.commit()
    finally:
        conn.close()

    return target_path


def calculate_sim_day(sim_timestamp: Any, start_date: Optional[date] = None) -> int:
    """
    Calculate sim_day as days elapsed since fork's start date (Day 1 = start date).
    
    Definition:
        sim_day = max(1, (sim_date - start_date).days + 1)
        Default fork start date: February 13, 2023.
    """
    s_date = start_date or DEFAULT_SIM_START_DATE

    if isinstance(sim_timestamp, datetime):
        curr_d = sim_timestamp.date()
    elif isinstance(sim_timestamp, date):
        curr_d = sim_timestamp
    elif isinstance(sim_timestamp, str):
        # Attempt to parse standard datetime formats
        curr_d = None
        for fmt in (
            "%B %d, %Y, %H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%B %d, %Y",
            "%Y-%m-%d",
        ):
            try:
                curr_d = datetime.strptime(sim_timestamp.strip(), fmt).date()
                break
            except Exception:
                continue
        if curr_d is None:
            # Fallback if unparseable
            return 1
    else:
        return 1

    diff = (curr_d - s_date).days
    return max(1, diff + 1)


def get_upstream_prompt(
    agent_id: str,
    observation: str,
    kind: str = "event",
    persona: Any = None,
) -> str:
    """
    Build the exact byte-for-byte upstream importance scoring prompt.
    Matches poignancy_event_v1.txt or poignancy_chat_v1.txt.
    """
    agent_name = agent_id
    iss_str = ""

    if persona is not None and hasattr(persona, "scratch"):
        agent_name = getattr(persona.scratch, "name", agent_id)
        if getattr(persona.scratch, "curr_time", None) is None:
            # Set default simulation time if uninitialized in bootstrap state
            persona.scratch.curr_time = datetime(2023, 2, 13, 9, 0, 0)
        if hasattr(persona.scratch, "get_str_iss"):
            try:
                iss_str = persona.scratch.get_str_iss()
            except Exception:
                iss_str = ""

    if not iss_str:
        # Fallback: load scratch from storage/base_the_ville_n25 or base_the_ville_isabella_maria_klaus
        iss_str = _load_bootstrap_iss(agent_id)

    if kind == "chat":
        prompt = (
            f"Here is a brief description of {agent_name}. \n"
            f"{iss_str}\n\n"
            f"On the scale of 1 to 10, where 1 is purely mundane (e.g., routine morning greetings) "
            f"and 10 is extremely poignant (e.g., a conversation about breaking up, a fight), "
            f"rate the likely poignancy of the following conversation for {agent_name}.\n\n"
            f"Conversation: \n"
            f"{observation}\n\n"
            f"Rate (return a number between 1 to 10):"
        )
    else:
        prompt = (
            f"Here is a brief description of {agent_name}. \n"
            f"{iss_str}\n\n"
            f"On the scale of 1 to 10, where 1 is purely mundane (e.g., brushing teeth, making bed) "
            f"and 10 is extremely poignant (e.g., a break up, college acceptance), "
            f"rate the likely poignancy of the following event for {agent_name}.\n\n"
            f"Event: {observation}\n"
            f"Rate (return a number between 1 to 10):"
        )

    return prompt.strip()


def _load_bootstrap_iss(agent_id: str) -> str:
    """Load bootstrap identity stable set (ISS) string for agent_id from disk."""
    backend_storage = (
        Path(__file__).resolve().parent.parent.parent
        / "reverie"
        / "environment"
        / "frontend_server"
        / "storage"
    )
    candidate_folders = [
        backend_storage / "base_the_ville_n25" / "personas" / agent_id / "bootstrap_memory" / "scratch.json",
        backend_storage / "base_the_ville_isabella_maria_klaus" / "personas" / agent_id / "bootstrap_memory" / "scratch.json",
    ]

    for p in candidate_folders:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    s_data = json.load(f)
                name = s_data.get("name", agent_id)
                age = s_data.get("age", 30)
                innate = s_data.get("innate", "")
                learned = s_data.get("learned", "")
                currently = s_data.get("currently", "")
                lifestyle = s_data.get("lifestyle", "")
                daily_plan = s_data.get("daily_plan_req", "")
                curr_date = "Monday February 13"

                commonset = (
                    f"Name: {name}\n"
                    f"Age: {age}\n"
                    f"Innate traits: {innate}\n"
                    f"Learned traits: {learned}\n"
                    f"Currently: {currently}\n"
                    f"Lifestyle: {lifestyle}\n"
                    f"Daily plan requirement: {daily_plan}\n"
                    f"Current Date: {curr_date}\n"
                )
                return commonset
            except Exception:
                continue

    # Generic default if scratch file cannot be located
    return (
        f"Name: {agent_id}\n"
        f"Age: 30\n"
        f"Innate traits: observant, thoughtful\n"
        f"Learned traits: Local resident\n"
        f"Currently: Going about daily routine\n"
        f"Lifestyle: Regular schedule\n"
        f"Daily plan requirement: Standard activities\n"
        f"Current Date: Monday February 13\n"
    )


def build_staged_prompt(
    agent_id: str,
    observation: str,
    kind: str = "event",
    persona: Any = None,
    identity_context: str = "",
    personas_dir: Optional[Union[str, Path]] = None,
) -> str:
    """
    Build the staged importance scoring prompt.
    The staged prompt equals the upstream prompt PLUS the Stage 1 priors block.
    """
    upstream_prompt = get_upstream_prompt(agent_id, observation, kind=kind, persona=persona)
    priors_block = get_prompt_context(agent_id, personas_dir=personas_dir)

    if identity_context and identity_context.strip():
        staged_prompt = f"{upstream_prompt}\n\n{priors_block}\n\n{identity_context.strip()}"
    else:
        staged_prompt = f"{upstream_prompt}\n\n{priors_block}"

    return staged_prompt


def parse_importance_score(response_text: str, fail_safe: int = 4) -> int:
    """Extract an integer score between 1 and 10 from the LLM response."""
    if not response_text:
        return fail_safe

    cleaned = response_text.strip()
    # Match standalone digit or first integer
    match = re.search(r"\b(10|[1-9])\b", cleaned)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            pass

    return fail_safe


def score_importance_persona_conditioned(
    agent_id: str,
    observation: str,
    kind: str = "event",
    persona: Any = None,
    identity_context: str = "",
    personas_dir: Optional[Union[str, Path]] = None,
    config_path: Optional[Union[str, Path]] = None,
    db_path: Optional[Union[str, Path]] = None,
) -> int:
    """
    Stage 2: Score importance of an event or conversation conditioned on Stage 1 personality priors.
    Augments the upstream prompt with the agent's priors block.
    """
    prompt = build_staged_prompt(
        agent_id=agent_id,
        observation=observation,
        kind=kind,
        persona=persona,
        identity_context=identity_context,
        personas_dir=personas_dir,
    )

    kwargs: Dict[str, Any] = {
        "prompt": prompt,
        "tier": "fast",
        "purpose": "importance_scoring",
        "agent_id": agent_id,
        "condition": "staged",
    }
    if config_path is not None:
        kwargs["config_path"] = config_path
    if db_path is not None:
        kwargs["db_path"] = db_path

    try:
        raw_response = call_llm(**kwargs)
        return parse_importance_score(raw_response, fail_safe=4)
    except Exception as e:
        logger.error("Error scoring importance for '%s': %s. Using fail-safe 4.", agent_id, e)
        return 4


def log_episodic_memory(
    agent_id: str,
    content: str,
    sim_timestamp: Any,
    sim_day: Optional[int] = None,
    recency_score: Optional[float] = None,
    importance_score: Optional[float] = None,
    relevance_score: Optional[float] = None,
    entry_id: Optional[str] = None,
    consolidated: bool = False,
    db_path: Optional[Union[str, Path]] = None,
    sim_code: Optional[str] = None,
) -> str:
    """
    Mirror an episodic entry into SQLite episodic_memory table with consolidated=False.
    Idempotent: Uses INSERT OR IGNORE on entry_id primary key to prevent duplication on reload.
    """
    actual_db = init_episodic_db(db_path=db_path, sim_code=sim_code)

    if sim_day is None:
        sim_day = calculate_sim_day(sim_timestamp)

    if entry_id is None:
        timestamp_str = datetime.now().strftime("%Y%m%d%H%M%S%f")
        entry_id = f"{agent_id}:{timestamp_str}"

    ts_str = sim_timestamp.strftime("%Y-%m-%d %H:%M:%S") if isinstance(sim_timestamp, (datetime, date)) else str(sim_timestamp)

    conn = sqlite3.connect(str(actual_db))
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR IGNORE INTO episodic_memory (
                entry_id, agent_id, content, sim_timestamp, sim_day,
                recency_score, importance_score, relevance_score, consolidated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry_id,
                agent_id,
                content,
                ts_str,
                sim_day,
                recency_score,
                importance_score,
                relevance_score,
                1 if consolidated else 0,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return entry_id


def log_episodic_node(
    agent_id: str,
    node: Any,
    sim_time: Any = None,
    importance_score: Optional[float] = None,
    db_path: Optional[Union[str, Path]] = None,
    sim_code: Optional[str] = None,
) -> str:
    """Helper to log a ConceptNode into episodic_memory using standard entry_id = '<agent_id>:<node_id>'."""
    node_id = getattr(node, "node_id", "node_0")
    entry_id = f"{agent_id}:{node_id}"
    content = getattr(node, "description", str(node))
    ts = sim_time or getattr(node, "created", datetime.now())
    score = importance_score if importance_score is not None else getattr(node, "poignancy", 1)

    return log_episodic_memory(
        agent_id=agent_id,
        content=content,
        sim_timestamp=ts,
        importance_score=score,
        entry_id=entry_id,
        consolidated=False,
        db_path=db_path,
        sim_code=sim_code,
    )


def get_unconsolidated(
    agent_id: str,
    sim_day: Optional[int] = None,
    db_path: Optional[Union[str, Path]] = None,
    sim_code: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Retrieve all unconsolidated episodic memory records for an agent."""
    actual_db = init_episodic_db(db_path=db_path, sim_code=sim_code)

    query = "SELECT entry_id, agent_id, content, sim_timestamp, sim_day, recency_score, importance_score, relevance_score, consolidated, created_at FROM episodic_memory WHERE agent_id = ? AND consolidated = 0"
    params: List[Any] = [agent_id]

    if sim_day is not None:
        query += " AND sim_day = ?"
        params.append(sim_day)

    query += " ORDER BY sim_timestamp ASC"

    conn = sqlite3.connect(str(actual_db))
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def flag_consolidated(
    entry_ids: List[str],
    db_path: Optional[Union[str, Path]] = None,
    sim_code: Optional[str] = None,
) -> int:
    """Mark a list of episodic memory entry_ids as consolidated."""
    if not entry_ids:
        return 0

    actual_db = init_episodic_db(db_path=db_path, sim_code=sim_code)
    placeholders = ",".join("?" for _ in entry_ids)
    query = f"UPDATE episodic_memory SET consolidated = 1 WHERE entry_id IN ({placeholders})"

    conn = sqlite3.connect(str(actual_db))
    try:
        cursor = conn.cursor()
        cursor.execute(query, entry_ids)
        updated = cursor.rowcount
        conn.commit()
        return updated
    finally:
        conn.close()


def reconcile_mirror(
    agent_id: str,
    live_node_ids: Any,
    live_descriptions: Optional[Dict[str, str]] = None,
    db_path: Optional[Union[str, Path]] = None,
    sim_code: Optional[str] = None,
) -> Dict[str, Any]:
    """
    P5.0a: reconcile the SQLite mirror to the loaded upstream memory for one agent.

    Removes `episodic_memory` rows for `agent_id` whose node is not present in the
    loaded associative memory (`live_node_ids`, e.g. `persona.a_mem.id_to_node`).
    Idempotent: a second call with the same inputs removes nothing.

    If `live_descriptions` ({node_id: description}) is given, rows whose node exists
    but whose content differs are REPORTED (not modified) under `content_mismatch`.

    Extension point: semantic rows and sweep markers do not exist yet (Step 1, decision D7);
    they will be rolled back here by the same rule once approved.
    """
    actual_db = init_episodic_db(db_path=db_path, sim_code=sim_code)
    live_ids = {f"{agent_id}:{nid}" for nid in live_node_ids}

    conn = sqlite3.connect(str(actual_db))
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT entry_id, content FROM episodic_memory WHERE agent_id = ?", (agent_id,))
        rows = cursor.fetchall()
        orphans = sorted(eid for eid, _ in rows if eid not in live_ids)
        mismatch: List[str] = []
        if live_descriptions is not None:
            prefix = f"{agent_id}:"
            for eid, content in rows:
                if eid in live_ids and live_descriptions.get(eid[len(prefix):]) != content:
                    mismatch.append(eid)
        for eid in orphans:
            cursor.execute("DELETE FROM episodic_memory WHERE entry_id = ?", (eid,))
        conn.commit()
    finally:
        conn.close()

    return {
        "agent_id": agent_id,
        "rows_before": len(rows),
        "removed_orphans": orphans,
        "rows_after": len(rows) - len(orphans),
        "content_mismatch": sorted(mismatch),
    }


def reconcile_run(
    personas: Dict[str, Any],
    db_path: Optional[Union[str, Path]] = None,
    sim_code: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Reconcile the mirror for every persona of a loaded run and append one JSON line per
    agent to `reconcile_log.jsonl` beside the run's memory.db."""
    actual_db = init_episodic_db(db_path=db_path, sim_code=sim_code)
    results = []
    for name, persona in personas.items():
        a_mem = persona.a_mem
        results.append(
            reconcile_mirror(
                name,
                list(a_mem.id_to_node.keys()),
                live_descriptions={nid: n.description for nid, n in a_mem.id_to_node.items()},
                db_path=actual_db,
            )
        )
    with open(actual_db.parent / "reconcile_log.jsonl", "a", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")
    return results
