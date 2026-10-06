"""
Stage 4: identity memory (Phase 6, design approved at Stop 1, rules in docs/phase6_preregistration.md).

A slow-changing layer of traits that emerge from the agent's own experience. It runs inside the existing sleep hook,
after Stage 3 consolidation, as a second night-keyed step; it is a function of the run database (consolidation_events,
episodic rows, event_scoring_context) so that a crash between the two steps, a rerun and a reload all reproduce a clean run.

  * Reinforcement (spec 3.1): a night counts toward a semantic entry when Stage 3 created it or merged into it with a
    cosine at or above REINFORCE_THRESHOLD, and the guard (3.5, pre-registration section 3) passes.
  * Path A: distinct counted nights >= COUNT_THRESHOLD_DAYS (count_based) or same_day_max >= SAME_DAY_COUNT (same_day).
  * Path B: an event scored at or above PIVOTAL_THRESHOLD graduates, unless it was scored while a matching trait was in
    its identity_context (addendum A1). Path B is evaluated at the night step, not immediately (disclosed deviation).
  * Feed-forward: the active traits (at most MAX_IDENTITY_TRAITS, at most IDENTITY_TOKEN_CAP estimated tokens, whole
    traits only) become the identity_context of the Stage 2 scoring prompt, rendered by the scorer itself.
Everything is behind STAGE4_ENABLED (default false). With the flag off none of this code runs.
"""
import hashlib
import json
import logging
import os
import sqlite3
import time
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

import yaml

from devmem.memory import consolidation, episodic
from devmem.memory.priors import get_prompt_context
from devmem.router import llm_router
from devmem.router.llm_router import call_llm

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "identity.yaml"

IDENTITY_DDL = """
CREATE TABLE IF NOT EXISTS semantic_reinforcement (
    agent_id            TEXT NOT NULL,
    semantic_id         TEXT NOT NULL,
    day_set_json        TEXT NOT NULL,
    distinct_days       INTEGER NOT NULL,
    same_day_max        INTEGER NOT NULL,
    last_night          INTEGER NOT NULL,
    self_reinforced_json TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY (agent_id, semantic_id)
);
CREATE TABLE IF NOT EXISTS identity_traits (
    agent_id                 TEXT NOT NULL,
    trait_id                 TEXT NOT NULL,
    text                     TEXT NOT NULL,
    path                     TEXT NOT NULL,
    source_semantic_ids_json TEXT NOT NULL,
    source_event_ids_json    TEXT NOT NULL,
    created_night            INTEGER NOT NULL,
    created_sim_time         TEXT NOT NULL,
    active                   INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (agent_id, trait_id)
);
CREATE TABLE IF NOT EXISTS identity_sweeps (
    agent_id   TEXT NOT NULL,
    night      INTEGER NOT NULL,
    status     TEXT NOT NULL,
    sweep_time TEXT NOT NULL,
    attempts   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (agent_id, night)
);
CREATE TABLE IF NOT EXISTS consolidation_events (
    agent_id             TEXT NOT NULL,
    night                INTEGER NOT NULL,
    semantic_id          TEXT NOT NULL,
    action               TEXT NOT NULL,
    match_similarity     REAL,
    new_source_ids_json  TEXT NOT NULL,
    PRIMARY KEY (agent_id, night, semantic_id)
);
CREATE TABLE IF NOT EXISTS event_scoring_context (
    agent_id       TEXT NOT NULL,
    entry_id       TEXT NOT NULL,
    trait_ids_json TEXT NOT NULL,
    status         TEXT NOT NULL,
    PRIMARY KEY (agent_id, entry_id)
);
"""

TRAIT_PROMPT_PATTERN = """The following pattern was observed in {agent_name}'s experience {occurrence}:
{pattern}

Write ONE sentence, in the third person, that names {agent_name} and states the lasting personality trait this pattern shows about {agent_name}."""
TRAIT_PROMPT_EVENT = """The following single event was extremely important to {agent_name}:
{event_text}

Write ONE sentence, in the third person, that names {agent_name} and states the lasting trait or belief this event shows about {agent_name}."""
TRAIT_RETRY_SUFFIX = ("\n\nYour previous reply was: \"{previous}\"\nThat is not acceptable: it must be ONE sentence of at most "
                      "{max_words} words, written in the third person, naming {agent_name}. Reply with one corrected sentence only.")


# ---------------------------------------------------------------------------------------------
# config and flags
# ---------------------------------------------------------------------------------------------
_CONFIG_CACHE: Dict[str, Any] = {}


def load_config(path: Optional[Path] = None) -> Dict[str, Any]:
    if path is not None:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    if not _CONFIG_CACHE:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            _CONFIG_CACHE.update(yaml.safe_load(f))
    return dict(_CONFIG_CACHE)


def _flag(env_name: str, default: bool) -> bool:
    v = os.environ.get(env_name)
    if v is None or not v.strip():
        return bool(default)
    return v.strip().lower() in ("1", "true", "on", "yes")


def stage4_enabled(config: Optional[Dict[str, Any]] = None) -> bool:
    return _flag("STAGE4_ENABLED", (config or load_config())["stage4_enabled"])


def feedback_active(config: Optional[Dict[str, Any]] = None) -> bool:
    cfg = config or load_config()
    return stage4_enabled(cfg) and _flag("IDENTITY_FEEDBACK", cfg["identity_feedback"])


def init_identity_db(db_path: Union[str, Path]) -> Path:
    path = consolidation.init_consolidation_db(db_path)
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(IDENTITY_DDL)
        conn.commit()
    finally:
        conn.close()
    return path


def _ts(t: Any) -> str:
    return t.strftime("%Y-%m-%d %H:%M:%S") if isinstance(t, datetime) else str(t)


def _trait_number(trait_id: str) -> int:
    return int(trait_id.rsplit("trait_", 1)[1])


def _connect(db: Union[str, Path]) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------------------------
# Stage 3 side: consolidation_events (written inside Stage 3's transaction)
# ---------------------------------------------------------------------------------------------
def record_consolidation_events(conn: sqlite3.Connection, agent: str, night: int, results: Sequence[Dict[str, Any]]) -> None:
    """One row per (agent, night, semantic entry): the action Stage 3 took, the match cosine and the NEW source ids it attached.
    Two clusters landing on the same entry in one night merge into one row (the first action is kept, the larger cosine wins)."""
    for res in results:
        new = list(res["sources"]) if res["action"] == "created" else list(res.get("sources_added", []))
        sim = res.get("match_similarity")
        row = conn.execute("SELECT action, match_similarity, new_source_ids_json FROM consolidation_events "
                           "WHERE agent_id = ? AND night = ? AND semantic_id = ?", (agent, night, res["entry_id"])).fetchone()
        if row is None:
            conn.execute("INSERT INTO consolidation_events (agent_id, night, semantic_id, action, match_similarity, "
                         "new_source_ids_json) VALUES (?,?,?,?,?,?)",
                         (agent, night, res["entry_id"], res["action"], sim, json.dumps(new)))
        else:
            merged = list(dict.fromkeys(json.loads(row[2]) + new))
            sims = [s for s in (row[1], sim) if s is not None]
            conn.execute("UPDATE consolidation_events SET match_similarity = ?, new_source_ids_json = ? "
                         "WHERE agent_id = ? AND night = ? AND semantic_id = ?",
                         (max(sims) if sims else None, json.dumps(merged), agent, night, res["entry_id"]))


# ---------------------------------------------------------------------------------------------
# scoring context (spec 3.5: record on the event whether it was scored with traits present)
# ---------------------------------------------------------------------------------------------
_PENDING: "OrderedDict[Tuple[str, str, str], Tuple[List[str], bool]]" = OrderedDict()
_PENDING_MAX = 5000


def _ctx_key(agent: str, sim_time: Any, text: str) -> Tuple[str, str, str]:
    norm = " ".join(str(text).split())
    return (agent, _ts(sim_time) if sim_time is not None else "", hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16])


def note_scoring_context(agent: str, sim_time: Any, text: str, trait_ids: Sequence[str], known: bool = True) -> None:
    """Called by the scorer when Stage 4 is on, before the scoring call. `known` is False when the traits could not be loaded."""
    _PENDING[_ctx_key(agent, sim_time, text)] = (list(trait_ids), bool(known))
    while len(_PENDING) > _PENDING_MAX:
        _PENDING.popitem(last=False)


def write_scoring_context(db_path: Union[str, Path], agent: str, entry_id: str, content: str, sim_time: Any) -> str:
    """Called when an episodic row is mirrored (Stage 4 on). ok: scored with the listed traits (possibly none);
    rule: rule-assigned idle row (no scoring call, no traits); unknown: no scoring record found (treated as self-reinforced)."""
    key = _ctx_key(agent, sim_time, content)
    pending = _PENDING.pop(key, None)
    if pending is not None and pending[1]:
        status, ids = "ok", pending[0]
    elif "is idle" in content:
        status, ids = "rule", []
    else:
        status, ids = "unknown", []
    conn = sqlite3.connect(str(init_identity_db(db_path)))
    try:
        conn.execute("INSERT OR IGNORE INTO event_scoring_context (agent_id, entry_id, trait_ids_json, status) VALUES (?,?,?,?)",
                     (agent, entry_id, json.dumps(ids), status))
        conn.commit()
    finally:
        conn.close()
    return status


# ---------------------------------------------------------------------------------------------
# feed-forward
# ---------------------------------------------------------------------------------------------
def _active_rows(conn: sqlite3.Connection, agent: str) -> List[sqlite3.Row]:
    rows = conn.execute("SELECT * FROM identity_traits WHERE agent_id = ? AND active = 1", (agent,)).fetchall()
    return sorted(rows, key=lambda r: (-r["created_night"], -_reinforcement_count(conn, agent, r), -_trait_number(r["trait_id"])))


def _reinforcement_count(conn: sqlite3.Connection, agent: str, trait: sqlite3.Row) -> int:
    best = 0
    for sid in json.loads(trait["source_semantic_ids_json"]):
        r = conn.execute("SELECT distinct_days FROM semantic_reinforcement WHERE agent_id = ? AND semantic_id = ?",
                         (agent, sid)).fetchone()
        best = max(best, r[0] if r else 0)
    return best


def _fits(text: str, cap: int) -> bool:
    return llm_router.estimate_tokens(text, max_tokens=0) <= cap


def render_identity_context(trait_texts: Sequence[str], cfg: Optional[Dict[str, Any]] = None) -> Tuple[str, int]:
    """Header plus one `- trait` line per trait, newest first. Drops the OLDEST whole trait until the estimated token count
    (header included) is within the cap; never cuts a sentence. Returns (text, number of traits included)."""
    cfg = cfg or load_config()
    texts = list(trait_texts)[: cfg["max_identity_traits"]]
    while texts:
        out = cfg["identity_header"] + "\n" + "\n".join(f"- {t}" for t in texts)
        if _fits(out, cfg["identity_token_cap"]):
            return out, len(texts)
        texts.pop()
    return "", 0


def load_identity_context(agent: str, db_path: Union[str, Path], cfg: Optional[Dict[str, Any]] = None) -> Tuple[str, List[str]]:
    """The scorer's view: (identity_context, ids of the traits that made it into the text)."""
    cfg = cfg or load_config()
    if not Path(db_path).exists():
        return "", []
    conn = _connect(db_path)
    try:
        if conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='identity_traits'").fetchone() is None:
            return "", []
        rows = _active_rows(conn, agent)
    finally:
        conn.close()
    text, n = render_identity_context([r["text"] for r in rows], cfg)
    return text, [r["trait_id"] for r in rows[:n]]


_RENDERED: set = set()


def log_prompt_render(db_path: Union[str, Path], agent: str, sim_time: Any, prompt: str, trait_ids: Sequence[str]) -> bool:
    """One exact rendered scoring prompt per agent per night with identity context present (spec 3.4)."""
    night = consolidation.night_id(sim_time, consolidation.load_config()["night_boundary_hour"]) if isinstance(sim_time, datetime) else -1
    key = (str(db_path), agent, night)
    if key in _RENDERED:
        return False
    _RENDERED.add(key)
    with open(Path(db_path).parent / "identity_prompt_renders.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"agent": agent, "night": night, "sim_time": _ts(sim_time), "trait_ids": list(trait_ids),
                            "prompt": prompt}) + "\n")
    return True


# ---------------------------------------------------------------------------------------------
# the nightly identity step
# ---------------------------------------------------------------------------------------------
def _cos(a: Sequence[float], b: Sequence[float]) -> float:
    return consolidation._cos(a, b)


def _entry_vec(persona: Any, entry_id: str) -> Optional[Sequence[float]]:
    node = persona.a_mem.id_to_node.get(entry_id.split(":", 1)[1])
    return persona.a_mem.embeddings.get(node.embedding_key) if node is not None else None


def _state_from_row(row: Optional[sqlite3.Row]) -> Dict[str, Any]:
    if row is None:
        return {"day_set": [], "same_day_max": 0, "last_night": -1, "self": []}
    return {"day_set": json.loads(row["day_set_json"]), "same_day_max": row["same_day_max"], "last_night": row["last_night"],
            "self": json.loads(row["self_reinforced_json"])}


def run_identity_step(
    persona: Any,
    sweep_time: datetime,
    db_path: Optional[Union[str, Path]] = None,
    config: Optional[Dict[str, Any]] = None,
    embed_fn: Optional[Callable[[str], Sequence[float]]] = None,
    pinned_model: Optional[str] = None,
    log_dir: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Stage 4 for one agent and one night, after Stage 3's marker exists. Idempotent per (agent, night): a `done`
    identity marker makes a rerun a no-op. All SQLite effects (reinforcement rows, traits, the cap, the marker) commit in ONE
    transaction after every external call (LLM, embedding) has finished."""
    cfg = config or load_config()
    ccfg = consolidation.load_config()
    agent = persona.name
    embed = embed_fn or consolidation._default_embed
    db = init_identity_db(db_path or episodic.get_db_path())
    out_dir = Path(log_dir) if log_dir else db.parent
    night = consolidation.night_id(sweep_time, ccfg["night_boundary_hour"])
    t0 = time.time()
    thr = cfg["reinforce_threshold"]

    conn = _connect(db)
    try:
        marker = conn.execute("SELECT * FROM identity_sweeps WHERE agent_id = ? AND night = ?", (agent, night)).fetchone()
        if marker is not None:
            if marker["status"] == "done":
                return {"skipped": "already done", "night": night}
            if marker["attempts"] >= cfg["max_attempts_per_night"]:
                return {"skipped": "max attempts reached", "night": night}
        cons_marker = conn.execute("SELECT status FROM consolidation_sweeps WHERE agent_id = ? AND night = ?",
                                   (agent, night)).fetchone()
        if cons_marker is None or cons_marker["status"] != "done":
            return {"skipped": "consolidation not done", "night": night}
        events = conn.execute("SELECT * FROM consolidation_events WHERE agent_id = ? AND night = ? ORDER BY semantic_id",
                              (agent, night)).fetchall()
        reinf = {r["semantic_id"]: _state_from_row(r) for r in
                 conn.execute("SELECT * FROM semantic_reinforcement WHERE agent_id = ?", (agent,)).fetchall()}
        traits = [dict(r) for r in conn.execute("SELECT * FROM identity_traits WHERE agent_id = ? ORDER BY trait_id", (agent,)).fetchall()]
        ctx = {r["entry_id"]: (r["status"], json.loads(r["trait_ids_json"])) for r in
               conn.execute("SELECT * FROM event_scoring_context WHERE agent_id = ?", (agent,)).fetchall()}
        summaries = {r["entry_id"]: r["summary"] for r in
                     conn.execute("SELECT entry_id, summary FROM semantic_memory WHERE agent_id = ?", (agent,)).fetchall()}
        prev = conn.execute("SELECT MAX(sweep_time) FROM identity_sweeps WHERE agent_id = ? AND status = 'done' AND night < ?",
                            (agent, night)).fetchone()[0]
        sql = ("SELECT entry_id, content, sim_timestamp, importance_score FROM episodic_memory WHERE agent_id = ? "
               "AND importance_score >= ? AND sim_timestamp <= ?")
        args: List[Any] = [agent, cfg["pivotal_threshold"], _ts(sweep_time)]
        if prev:
            sql += " AND sim_timestamp > ?"
            args.append(prev)
        pivotal_rows = conn.execute(sql + " ORDER BY sim_timestamp, entry_id", args).fetchall()
        attempts = (marker["attempts"] if marker else 0) + 1
    finally:
        conn.close()

    trait_by_id = {t["trait_id"]: t for t in traits}
    vec_cache: Dict[str, Sequence[float]] = {}

    def trait_vec(t: Dict[str, Any]) -> Sequence[float]:
        if t["trait_id"] not in vec_cache:
            vec_cache[t["trait_id"]] = list(embed(t["text"]))
        return vec_cache[t["trait_id"]]

    def trait_matches_entry(t: Dict[str, Any], sid: str, e_vec: Sequence[float]) -> bool:
        sems = json.loads(t["source_semantic_ids_json"])
        if sid in sems:
            return True
        for s in sems:
            v = _entry_vec(persona, s)
            if v is not None and _cos(e_vec, v) >= thr:
                return True
        if not sems:
            return _cos(e_vec, trait_vec(t)) >= thr
        return False

    decisions: List[Dict[str, Any]] = []
    # ---- reinforcement (3.1) with the guard (3.5)
    for ev in events:
        sid, new_src = ev["semantic_id"], json.loads(ev["new_source_ids_json"])
        st = reinf.get(sid) or _state_from_row(None)
        rec: Dict[str, Any] = {"kind": "reinforcement", "agent": agent, "night": night, "semantic_id": sid, "stage3_action": ev["action"],
                               "cosine": ev["match_similarity"], "threshold": thr, "new_sources": len(new_src)}
        if ev["action"] == "reinforced" and ev["match_similarity"] < thr:
            rec["decision"] = "merged_by_stage3_below_stage4_threshold"
            decisions.append(rec)
            continue
        e_vec = _entry_vec(persona, sid)
        qualifying, unknown, with_match = 0, 0, 0
        for s in new_src:
            status, ids = ctx.get(s, ("ok", []))
            if status == "unknown":
                unknown += 1
                continue
            present = [trait_by_id[i] for i in ids if i in trait_by_id]
            if e_vec is not None and any(trait_matches_entry(t, sid, e_vec) for t in present):
                with_match += 1
            else:
                qualifying += 1
        rec.update({"sources_scored_without_matching_trait": qualifying, "sources_scored_with_matching_trait": with_match,
                    "sources_unknown_context": unknown})
        if qualifying > 0:
            if night not in st["day_set"]:
                st["day_set"].append(night)
            st["same_day_max"] = max(st["same_day_max"], len(new_src))
            rec["decision"] = "born" if ev["action"] == "created" else "counted"
        else:
            if night not in st["self"]:
                st["self"].append(night)
            rec["decision"] = "self_reinforced"
        st["last_night"] = max(st["last_night"], night)
        reinf[sid] = st
        decisions.append(rec)

    # ---- graduation candidates: Path A then Path B (deterministic order)
    have_sem = {s for t in traits for s in json.loads(t["source_semantic_ids_json"])}
    have_evt = {e for t in traits for e in json.loads(t["source_event_ids_json"])}
    candidates: List[Dict[str, Any]] = []
    for sid in sorted(reinf):
        st = reinf[sid]
        if sid in have_sem or sid not in summaries:
            continue
        days = len(st["day_set"])
        if days >= cfg["count_threshold_days"]:
            candidates.append({"path": "count_based", "semantic_id": sid, "text": summaries[sid],
                               "occurrence": f"on {days} different days"})
        elif st["same_day_max"] >= cfg["same_day_count"]:
            candidates.append({"path": "same_day", "semantic_id": sid, "text": summaries[sid],
                               "occurrence": f"{st['same_day_max']} times on one day"})
    pivotal_self = 0
    for r in pivotal_rows:
        if r["entry_id"] in have_evt:
            continue
        status, ids = ctx.get(r["entry_id"], ("ok", []))
        rec = {"kind": "pivotal", "agent": agent, "night": night, "event_id": r["entry_id"], "importance": r["importance_score"],
               "threshold": cfg["pivotal_threshold"], "scoring_status": status}
        present = [trait_by_id[i] for i in ids if i in trait_by_id]
        e_vec = _entry_vec(persona, r["entry_id"])
        match = None
        if status != "unknown" and present:
            if e_vec is None:
                raise ValueError(f"no embedding for pivotal event {r['entry_id']}")
            for t in present:
                c = _cos(e_vec, trait_vec(t))
                if c >= thr:
                    match = {"trait_id": t["trait_id"], "cosine": round(c, 4)}
                    break
        if status == "unknown" or match:
            pivotal_self += 1
            rec.update({"decision": "self_reinforced_pivotal", "matching_trait": match})
            decisions.append(rec)
            continue
        rec["decision"] = "graduates"
        decisions.append(rec)
        candidates.append({"path": "pivotal", "event_id": r["entry_id"], "text": r["content"]})

    # ---- trait text (external calls, none inside the transaction)
    priors_ctx = get_prompt_context(agent)
    sim_day = episodic.calculate_sim_day(sweep_time)
    new_traits, failures, retries_used = [], [], 0
    for c in candidates:
        if c["path"] == "pivotal":
            body = TRAIT_PROMPT_EVENT.format(agent_name=agent, event_text=c["text"])
        else:
            body = TRAIT_PROMPT_PATTERN.format(agent_name=agent, occurrence=c["occurrence"], pattern=c["text"])
        prompt = f"{priors_ctx}\n\n{body}"
        try:
            current, retries = prompt, 0
            while True:
                raw = call_llm(current, tier=cfg["trait_tier"], purpose="identity_trait", agent_id=agent, condition="staged",
                               sim_day=sim_day, system_prompt=consolidation.SUMMARY_SYSTEM_PROMPT, pinned_model=pinned_model)
                text = consolidation.parse_summary(raw)
                if text and consolidation.is_third_person(text, agent) and len(text.split()) <= cfg["trait_max_words"]:
                    break
                if retries >= cfg["trait_retries"]:
                    raise ValueError(f"trait not one third-person sentence within {cfg['trait_max_words']} words: {text[:80]!r}")
                retries += 1
                retries_used += 1
                current = prompt + TRAIT_RETRY_SUFFIX.format(previous=text[:200], max_words=cfg["trait_max_words"], agent_name=agent)
        except Exception as exc:  # counted, never silent
            failures.append({"candidate": c.get("semantic_id") or c.get("event_id"), "path": c["path"], "error": f"{type(exc).__name__}: {str(exc)[:120]}"})
            continue
        new_traits.append({**c, "trait_text": text, "prompt": prompt})

    # ---- one transaction: reinforcement rows, traits, the cap, the marker
    conn = _connect(db)
    created: List[Dict[str, Any]] = []
    try:
        conn.execute("BEGIN")
        for sid, st in reinf.items():
            if not any(e["semantic_id"] == sid for e in events) and conn.execute(
                    "SELECT 1 FROM semantic_reinforcement WHERE agent_id = ? AND semantic_id = ?", (agent, sid)).fetchone():
                continue
            conn.execute(
                "INSERT INTO semantic_reinforcement (agent_id, semantic_id, day_set_json, distinct_days, same_day_max, last_night, "
                "self_reinforced_json) VALUES (?,?,?,?,?,?,?) ON CONFLICT(agent_id, semantic_id) DO UPDATE SET "
                "day_set_json = excluded.day_set_json, distinct_days = excluded.distinct_days, same_day_max = excluded.same_day_max, "
                "last_night = excluded.last_night, self_reinforced_json = excluded.self_reinforced_json",
                (agent, sid, json.dumps(sorted(st["day_set"])), len(st["day_set"]), st["same_day_max"], st["last_night"],
                 json.dumps(sorted(st["self"]))))
        n = max([_trait_number(r[0]) for r in conn.execute("SELECT trait_id FROM identity_traits WHERE agent_id = ?", (agent,))] or [0])
        for nt in new_traits:
            n += 1
            tid = f"{agent}:trait_{n}"
            sems = [nt["semantic_id"]] if "semantic_id" in nt else []
            evts = [nt["event_id"]] if "event_id" in nt else []
            conn.execute("INSERT INTO identity_traits (agent_id, trait_id, text, path, source_semantic_ids_json, "
                         "source_event_ids_json, created_night, created_sim_time, active) VALUES (?,?,?,?,?,?,?,?,1)",
                         (agent, tid, nt["trait_text"], nt["path"], json.dumps(sems), json.dumps(evts), night, _ts(sweep_time)))
            created.append({"trait_id": tid, "path": nt["path"], "text": nt["trait_text"], "source_semantic_ids": sems,
                            "source_event_ids": evts, "prompt": nt["prompt"]})
        evicted = apply_cap(conn, agent, cfg)
        status = "failed" if failures else "done"
        conn.execute("INSERT INTO identity_sweeps (agent_id, night, status, sweep_time, attempts) VALUES (?,?,?,?,?) "
                     "ON CONFLICT(agent_id, night) DO UPDATE SET status = excluded.status, sweep_time = excluded.sweep_time, "
                     "attempts = excluded.attempts", (agent, night, status, _ts(sweep_time), attempts))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    counts: Dict[str, int] = {}
    for d in decisions:
        counts[d["decision"]] = counts.get(d["decision"], 0) + 1
    with open(out_dir / "reinforcement_decisions.jsonl", "a", encoding="utf-8") as f:
        for d in decisions:
            f.write(json.dumps({**d, "attempt": attempts}) + "\n")
    # PM condition on design detail 1: events lost to Path B after the last allowed attempt are counted and named, never silent
    pivotal_lost = ([f["candidate"] for f in failures if f["path"] == "pivotal"]
                    if status == "failed" and attempts >= cfg["max_attempts_per_night"] else [])
    record = {"agent": agent, "night": night, "sim_time": _ts(sweep_time), "status": status, "attempts": attempts,
              "decision_counts": counts, "self_reinforced_pivotal": pivotal_self, "pivotal_lost": len(pivotal_lost),
              "pivotal_lost_events": pivotal_lost,
              "traits_created": [{k: v for k, v in c.items() if k != "prompt"} for c in created], "evicted": evicted,
              "trait_retries": retries_used, "failures": failures, "seconds": round(time.time() - t0, 2)}
    with open(out_dir / "identity_log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({**record, "trait_prompts": [c["prompt"] for c in created]}) + "\n")
    return record


def apply_cap(conn: sqlite3.Connection, agent: str, cfg: Dict[str, Any]) -> List[str]:
    """Deactivate the oldest active traits beyond MAX_IDENTITY_TRAITS (ties: lower reinforcement count first, then creation order).
    Deterministic given the table contents, so reconcile can recompute it."""
    rows = conn.execute("SELECT * FROM identity_traits WHERE agent_id = ? AND active = 1", (agent,)).fetchall()
    order = sorted(rows, key=lambda r: (r["created_night"], _reinforcement_count(conn, agent, r), _trait_number(r["trait_id"])))
    evicted = []
    for r in order[: max(0, len(rows) - cfg["max_identity_traits"])]:
        conn.execute("UPDATE identity_traits SET active = 0 WHERE agent_id = ? AND trait_id = ?", (agent, r["trait_id"]))
        evicted.append(r["trait_id"])
    return evicted


# ---------------------------------------------------------------------------------------------
# reload reconciliation
# ---------------------------------------------------------------------------------------------
def reconcile_identity(persona: Any, db_path: Union[str, Path], config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """After loading a saved run (and after reconcile_mirror and reconcile_consolidation), roll Stage 4 back to the loaded state.
    One rule, idempotent: drop consolidation_events whose entry or Stage 3 marker is gone; drop identity markers recorded after
    the loaded clock or without a Stage 3 marker; drop traits created after the loaded clock or whose source entry or event is
    gone; rebuild every semantic_reinforcement row from the surviving rows (nights kept only if their identity marker survives,
    same_day_max recomputed from the surviving consolidation_events); delete scoring-context rows whose episodic entry is gone;
    recompute the cap (so traits evicted only by a deleted newer trait become active again)."""
    cfg = config or load_config()
    agent = persona.name
    db = init_identity_db(db_path)
    loaded = persona.scratch.curr_time
    loaded_s = _ts(loaded) if loaded is not None else None
    conn = _connect(db)
    report: Dict[str, Any] = {"agent_id": agent}
    try:
        conn.execute("BEGIN")
        sem_alive = {r[0] for r in conn.execute("SELECT entry_id FROM semantic_memory WHERE agent_id = ?", (agent,))}
        cons_nights = {r[0] for r in conn.execute(
            "SELECT night FROM consolidation_sweeps WHERE agent_id = ? AND status = 'done'", (agent,))}
        ev_rows = conn.execute("SELECT night, semantic_id FROM consolidation_events WHERE agent_id = ?", (agent,)).fetchall()
        dropped_ev = [(r["night"], r["semantic_id"]) for r in ev_rows if r["semantic_id"] not in sem_alive or r["night"] not in cons_nights]
        for n, s in dropped_ev:
            conn.execute("DELETE FROM consolidation_events WHERE agent_id = ? AND night = ? AND semantic_id = ?", (agent, n, s))
        report["removed_consolidation_events"] = len(dropped_ev)

        dropped_sweeps = []
        for m in conn.execute("SELECT night, sweep_time FROM identity_sweeps WHERE agent_id = ?", (agent,)).fetchall():
            if m["night"] not in cons_nights or (loaded_s is not None and m["sweep_time"] > loaded_s):
                conn.execute("DELETE FROM identity_sweeps WHERE agent_id = ? AND night = ?", (agent, m["night"]))
                dropped_sweeps.append(m["night"])
        report["removed_identity_markers"] = sorted(dropped_sweeps)
        kept_nights = {r[0] for r in conn.execute("SELECT night FROM identity_sweeps WHERE agent_id = ?", (agent,))}

        epi_alive = {r[0] for r in conn.execute("SELECT entry_id FROM episodic_memory WHERE agent_id = ?", (agent,))}
        dropped_traits = []
        for t in conn.execute("SELECT * FROM identity_traits WHERE agent_id = ?", (agent,)).fetchall():
            sems, evts = json.loads(t["source_semantic_ids_json"]), json.loads(t["source_event_ids_json"])
            gone = (loaded_s is not None and t["created_sim_time"] > loaded_s) or t["created_night"] not in kept_nights \
                or any(s not in sem_alive for s in sems) or any(e not in epi_alive for e in evts)
            if gone:
                conn.execute("DELETE FROM identity_traits WHERE agent_id = ? AND trait_id = ?", (agent, t["trait_id"]))
                dropped_traits.append(t["trait_id"])
        report["removed_traits"] = sorted(dropped_traits)

        rebuilt = 0
        for r in conn.execute("SELECT * FROM semantic_reinforcement WHERE agent_id = ?", (agent,)).fetchall():
            sid = r["semantic_id"]
            if sid not in sem_alive:
                conn.execute("DELETE FROM semantic_reinforcement WHERE agent_id = ? AND semantic_id = ?", (agent, sid))
                continue
            days = sorted(n for n in json.loads(r["day_set_json"]) if n in kept_nights)
            selfn = sorted(n for n in json.loads(r["self_reinforced_json"]) if n in kept_nights)
            per_night = {e["night"]: len(json.loads(e["new_source_ids_json"])) for e in conn.execute(
                "SELECT night, new_source_ids_json FROM consolidation_events WHERE agent_id = ? AND semantic_id = ?", (agent, sid))}
            same = max([per_night.get(n, 0) for n in days] or [0])
            last = max(days + selfn or [-1])
            if (days, selfn, same, last) != (json.loads(r["day_set_json"]), json.loads(r["self_reinforced_json"]),
                                              r["same_day_max"], r["last_night"]):
                rebuilt += 1
            conn.execute("UPDATE semantic_reinforcement SET day_set_json = ?, distinct_days = ?, same_day_max = ?, last_night = ?, "
                         "self_reinforced_json = ? WHERE agent_id = ? AND semantic_id = ?",
                         (json.dumps(days), len(days), same, last, json.dumps(selfn), agent, sid))
        report["rebuilt_reinforcement_rows"] = rebuilt

        gone_ctx = [r[0] for r in conn.execute("SELECT entry_id FROM event_scoring_context WHERE agent_id = ?", (agent,))
                    if r[0] not in epi_alive]
        for e in gone_ctx:
            conn.execute("DELETE FROM event_scoring_context WHERE agent_id = ? AND entry_id = ?", (agent, e))
        report["removed_scoring_context"] = len(gone_ctx)

        conn.execute("UPDATE identity_traits SET active = 1 WHERE agent_id = ?", (agent,))
        report["evicted_after_recompute"] = apply_cap(conn, agent, cfg)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return report


def reconcile_run_identity(personas: Dict[str, Any], db_path: Union[str, Path]) -> List[Dict[str, Any]]:
    return [reconcile_identity(p, db_path) for p in personas.values()]
