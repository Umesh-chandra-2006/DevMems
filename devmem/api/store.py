"""
Read-only data layer of the memory inspector (Phase 8). Standard library only, so it runs under any Python 3 and never imports the
simulation, the router or an LLM client.

Rules (spec section 0):
  * every SQLite connection is opened read-only (`mode=ro` plus `PRAGMA query_only`); nothing here writes to a run;
  * nothing here calls an LLM or the network (the embedding cache is read from disk for the provenance diagnostic only);
  * what is displayed is what was recorded: missing tables degrade to `available: false` with a reason, nothing is invented;
  * run labels come from the run's own `run_label.json` or recorded reports; unknown stays "unknown".

A "run" is a folder that holds a `memory.db` (a storage run under devmem/storage, or a saved artifacts folder such as the Step D
recording). Roots are searched in order; override with the environment variable DEVMEM_API_ROOTS (path-separator list).
"""
import array
import hashlib
import json
import math
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent.parent
IDENTITY_CONFIG = ROOT / "devmem" / "config" / "identity.yaml"
PERSONAS_DIR = ROOT / "devmem" / "config" / "personas"
EMBEDDING_CACHE = ROOT / "devmem" / "storage" / "embedding_cache.db"
EMBEDDING_MODEL = "gemini-embedding-001"
LIVE_WINDOW_SECONDS = 120


class NotFound(KeyError):
    pass


# ---------------------------------------------------------------------------------------------
# discovery and connections
# ---------------------------------------------------------------------------------------------
def roots() -> List[Path]:
    env = os.environ.get("DEVMEM_API_ROOTS")
    if env:
        return [Path(p) for p in env.split(os.pathsep) if p]
    return [ROOT / "devmem" / "storage", ROOT / "docs"]


def _is_run(c: Path) -> bool:
    """A run folder holds memory.db; the baseline arm writes no memory mirror, so a folder with run_label.json and run_status.json is a run too."""
    return (c / "memory.db").is_file() or ((c / "run_label.json").is_file() and (c / "run_status.json").is_file())


def discover() -> Dict[str, Path]:
    """run id -> folder. A root that itself holds memory.db is one run; otherwise each child folder with a memory.db is a run."""
    found: Dict[str, Path] = {}
    for root in roots():
        if not root.is_dir():
            continue
        candidates = [root] if _is_run(root) else sorted(c for c in root.iterdir() if c.is_dir() and _is_run(c))
        for c in candidates:
            rid, n = c.name, 2
            while rid in found and found[rid] != c:
                rid, n = f"{c.name}~{n}", n + 1
            found[rid] = c
    return found


def run_dir(run: str) -> Path:
    runs = discover()
    if run not in runs:
        raise NotFound(f"unknown run {run!r}")
    return runs[run]


def connect(run: str) -> sqlite3.Connection:
    path = run_dir(run) / "memory.db"
    if not path.is_file():                      # a run without a memory database (the baseline arm): an empty read-only view, nothing is created on disk
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        return conn
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def tables(conn: sqlite3.Connection) -> set:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _json(path: Path) -> Optional[Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _jsonl(path: Path) -> List[Dict[str, Any]]:
    try:
        return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    except (OSError, ValueError):
        return []


def norm_t(t: Optional[str]) -> Optional[str]:
    """Accept '2023-02-13 09:30', '2023-02-13T09:30:00' and return 'YYYY-MM-DD HH:MM:SS' (lexicographic order = time order)."""
    if t is None or t == "":
        return None
    s = t.strip().replace("T", " ")
    if len(s) == 10:
        s += " 23:59:59"
    elif len(s) == 16:
        s += ":00"
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", s):
        raise ValueError(f"time must look like 2023-02-13 09:30:00, got {t!r}")
    return s


def slug(agent: str) -> str:
    return agent.lower().replace(" ", "_")


# ---------------------------------------------------------------------------------------------
# labels (spec 3.5: nothing may look like a result the data does not support)
# ---------------------------------------------------------------------------------------------
FULL_RUNS = ("p7_baseline", "p7_staged")


def full_run_mode(run: str, state: Optional[str]) -> Optional[str]:
    """The label of a full Phase 7 run is rendered from its run_status.json state, not from run_label.json (which was written at launch and still says "live run in progress"): the
    run folder is never edited. Pilot runs (p7pilot_*) and every other run keep their declared label."""
    if run not in FULL_RUNS:
        return None
    st = str(state or "")
    return "FULL RUN, 3 simulated days, " + ("finished" if st.startswith("finished") else ("running" if st.startswith(("running", "starting")) else "state not recorded"))


def run_label(run: str) -> Dict[str, Any]:
    d = run_dir(run)
    declared = _json(d / "run_label.json") or {}
    report = _json(d / "step_d_report_first.json") or _json(d / "stop3_report.json") or {}
    mdb = d / "memory.db"
    age = time.time() - (mdb if mdb.is_file() else d / "run_status.json").stat().st_mtime
    # A label that DECLARES the run recorded wins (a fresh copy or checkout of a recording must not look live). Without a declaration, a
    # database written in the last LIVE_WINDOW_SECONDS is labelled live; a run that is writing run_status.json with a running state is live.
    status_live = False
    sf = d / "run_status.json"
    if sf.is_file() and time.time() - sf.stat().st_mtime < LIVE_WINDOW_SECONDS:
        status_live = str((_json(sf) or {}).get("state", "")).startswith(("running", "starting"))
    live_hint = status_live or (age < LIVE_WINDOW_SECONDS and declared.get("mode") != "recorded")
    full_mode = full_run_mode(run, (_json(sf) or {}).get("state") if sf.is_file() else None)
    return {
        "run": run,
        "mode": full_mode or ("live (database written in the last %d s)" % LIVE_WINDOW_SECONDS if live_hint else declared.get("mode", "recorded (inferred: the database was not written in the last %d s)" % LIVE_WINDOW_SECONDS)),
        "origin": declared.get("origin", "unknown"),
        "model": declared.get("model", report.get("model", "unknown")),
        "normalizer": declared.get("normalizer", "unknown"),
        "stages": declared.get("stages", "unknown"),
        "note": declared.get("note", ""),
        "label_source": "run_label.json" if declared else ("recorded report" if report else "none (fields left unknown)"),
    }


# ---------------------------------------------------------------------------------------------
# runs and agents
# ---------------------------------------------------------------------------------------------
def list_runs() -> List[Dict[str, Any]]:
    out = []
    for rid in sorted(discover()):
        try:
            conn = connect(rid)
        except (sqlite3.Error, OSError):
            continue
        try:
            t = tables(conn)
            agents: List[str] = []
            lo = hi = None
            if "episodic_memory" in t:
                agents = [r[0] for r in conn.execute("SELECT DISTINCT agent_id FROM episodic_memory ORDER BY 1")]
                row = conn.execute("SELECT MIN(sim_timestamp), MAX(sim_timestamp) FROM episodic_memory").fetchone()
                lo, hi = row[0], row[1]
            out.append({"run": rid, "agents": agents, "sim_time_min": lo, "sim_time_max": hi,
                        "stages_present": {"stage1_priors": bool(agents), "stage2_episodic": "episodic_memory" in t,
                                           "stage3_semantic": "semantic_memory" in t and conn.execute("SELECT COUNT(*) FROM semantic_memory").fetchone()[0] > 0,
                                           "stage4_identity": "identity_traits" in t},
                        "label": run_label(rid)})
        finally:
            conn.close()
    return out


def priors_for(agent: str) -> List[Dict[str, str]]:
    """Stage 1 priors from the persona file (parsed without a YAML library: `- statement: "..."` then `category: ...`)."""
    path = PERSONAS_DIR / f"{slug(agent)}.yaml"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    out = []
    for m in re.finditer(r'-\s*statement:\s*"((?:[^"\\]|\\.)*)"\s*\n\s*category:\s*([\w\-]+)', text):
        out.append({"statement": m.group(1).replace('\\"', '"'), "category": m.group(2)})
    return out


# ---------------------------------------------------------------------------------------------
# baseline arm: it writes no memory mirror, so its memory panel is read, read-only, from upstream's own associative memory node file
# (reverie/environment/frontend_server/storage/<run>/personas/<agent>/bootstrap_memory/associative_memory/nodes.json, as of its last autosave)
# ---------------------------------------------------------------------------------------------
def _node_root(run: str) -> Path:
    from devmem.api.movement_archive import SIM_STORAGE
    return SIM_STORAGE / run / "personas"


def _node_agents(run: str) -> List[str]:
    root = _node_root(run)
    return sorted(c.name for c in root.iterdir() if (c / "bootstrap_memory" / "associative_memory" / "nodes.json").is_file()) if root.is_dir() else []


def _nodes(run: str, agent: str) -> List[Dict[str, Any]]:
    f = _node_root(run) / agent / "bootstrap_memory" / "associative_memory" / "nodes.json"
    if not f.is_file():
        return []
    rows = []
    for nid, n in json.loads(f.read_text(encoding="utf-8")).items():
        rows.append({"node_id": nid, "type": n.get("type"), "created": n.get("created"), "description": n.get("description") or "",
                     "poignancy": float(n.get("poignancy") or 0)})
    rows.sort(key=lambda r: (r["created"], int(r["node_id"].split("_")[-1]) if r["node_id"].split("_")[-1].isdigit() else 0))
    return rows


def _state_from_nodes(run: str, agent: str, t: Optional[str]) -> Dict[str, Any]:
    t = norm_t(t) or "9999-12-31 23:59:59"
    nodes = _nodes(run, agent)
    entries = [{"entry_id": f"{agent}:{n['node_id']}", "text": n["description"], "sim_time": n["created"], "sim_day": None, "importance": n["poignancy"],
                "is_idle_text": "idle" in n["description"].lower(), "consolidated_into": None, "consolidated_now": False,
                "scoring": {"status": "baseline (upstream scoring); node type " + str(n["type"])}} for n in nodes if n["created"] <= t]
    return {"run": run, "agent": agent, "sim_time": t, "label": run_label(run),
            "stage1_priors": {"statements": priors_for(agent), "source": f"devmem/config/personas/{slug(agent)}.yaml (the baseline injects them as atomic thought nodes of importance 10, listed below)"},
            "stage2_episodic": {"entries": entries, "entries_total_up_to_t": len(entries), "returned": len(entries),
                                "idle_text_entries": sum(1 for e in entries if e["is_idle_text"]),
                                "source_note": "read-only from the baseline's own associative memory node file (flat memory stream: events, thoughts and chats), as of its last autosave; the baseline arm writes no memory database"},
            "stage3_semantic": {"available": False, "summaries": [], "sweeps": []},
            "stage4_identity": {"available": False, "traits": []},
            "identity_context_at_t": {"text": "", "note": "baseline arm: no Stage 3 or Stage 4"}}


def list_agents(run: str) -> List[Dict[str, Any]]:
    conn = connect(run)
    try:
        t = tables(conn)
        names = set()
        for table in ("episodic_memory", "semantic_memory", "identity_traits"):
            if table in t:
                names.update(r[0] for r in conn.execute(f"SELECT DISTINCT agent_id FROM {table}"))
        if not names:
            names.update(_node_agents(run))
        return [{"agent": a, "persona": a, "priors_count": len(priors_for(a)), "priors_file": f"devmem/config/personas/{slug(a)}.yaml"}
                for a in sorted(names)]
    finally:
        conn.close()


# ---------------------------------------------------------------------------------------------
# identity context rendering (mirrors devmem.memory.identity.render_identity_context; a test asserts they agree)
# ---------------------------------------------------------------------------------------------
def identity_settings() -> Dict[str, Any]:
    text = IDENTITY_CONFIG.read_text(encoding="utf-8") if IDENTITY_CONFIG.is_file() else ""

    def val(key, cast, default):
        m = re.search(rf"^{key}:\s*(.+?)\s*$", text, re.M)
        return cast(m.group(1).strip().strip('"')) if m else default
    return {"max_identity_traits": val("max_identity_traits", int, 5), "identity_token_cap": val("identity_token_cap", int, 120),
            "identity_header": val("identity_header", str, "Traits this agent has developed through experience:")}


def estimate_prompt_tokens(text: str) -> int:
    return max(1, int(len(text.split()) * 1.35) + 5)  # same heuristic as the router's estimate_tokens(max_tokens=0)


def render_identity_context(trait_texts: List[str], cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = cfg or identity_settings()
    texts = list(trait_texts)[: cfg["max_identity_traits"]]
    while texts:
        out = cfg["identity_header"] + "\n" + "\n".join(f"- {t}" for t in texts)
        if estimate_prompt_tokens(out) <= cfg["identity_token_cap"]:
            return {"text": out, "traits_included": len(texts), "traits_dropped_by_caps": len(trait_texts) - len(texts),
                    "estimated_tokens": estimate_prompt_tokens(out)}
        texts.pop()
    return {"text": "", "traits_included": 0, "traits_dropped_by_caps": len(trait_texts), "estimated_tokens": 0}


# ---------------------------------------------------------------------------------------------
# embedding cache (read-only, for the provenance diagnostic; never a network request)
# ---------------------------------------------------------------------------------------------
def _norm_text(text: str) -> str:
    text = (text or "").replace("\n", " ").strip()
    return text if text else "this is blank"


def _cached_vec(text: str) -> Optional[List[float]]:
    if not EMBEDDING_CACHE.is_file():
        return None
    h = hashlib.sha256(_norm_text(text).encode("utf-8")).hexdigest()
    conn = sqlite3.connect(EMBEDDING_CACHE.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        row = conn.execute("SELECT vec FROM embedding_cache WHERE model = ? AND text_hash = ?", (EMBEDDING_MODEL, h)).fetchone()
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    if not row:
        return None
    a = array.array("f")
    a.frombytes(row[0])
    return list(a)


def _cos(a: List[float], b: List[float]) -> float:
    d = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b)) / d if d else 0.0


def provenance(trait_text: str, source_texts: List[str], priors_text: str) -> Dict[str, Any]:
    """Cosine of a trait to each of its source texts and to the agent's priors text, from CACHED real embeddings only.
    A vector that is not in the cache makes the diagnostic unavailable (never computed, never estimated)."""
    tv = _cached_vec(trait_text)
    if tv is None:
        return {"available": False, "reason": "trait text embedding is not in the embedding cache"}
    pv = _cached_vec(priors_text)
    if pv is None:
        return {"available": False, "reason": "priors text embedding is not in the embedding cache"}
    per_source, missing = [], 0
    for s in source_texts:
        sv = _cached_vec(s)
        if sv is None:
            missing += 1
            continue
        per_source.append({"text": s, "cosine": round(_cos(tv, sv), 4)})
    if not per_source:
        return {"available": False, "reason": "no source text embedding is in the embedding cache"}
    best = max(p["cosine"] for p in per_source)
    to_priors = round(_cos(tv, pv), 4)
    return {"available": True, "model": EMBEDDING_MODEL, "cosine_to_priors_text": to_priors, "cosine_to_sources": per_source,
            "sources_missing_from_cache": missing, "closer_to_priors_than_to_best_source": to_priors > best,
            "note": "cosines of cached real embeddings; a diagnostic, not a judgement of the trait"}


# ---------------------------------------------------------------------------------------------
# agent state at a simulated time
# ---------------------------------------------------------------------------------------------
def _trait_order(rows: List[sqlite3.Row], reinforcement: Dict[str, int]) -> List[sqlite3.Row]:
    def count(r):
        sems = json.loads(r["source_semantic_ids_json"])
        return max([reinforcement.get(s, 0) for s in sems] or [0])
    return sorted(rows, key=lambda r: (-r["created_night"], -count(r), -int(r["trait_id"].rsplit("trait_", 1)[1])))


def agent_state(run: str, agent: str, t: Optional[str] = None, diagnostics: bool = False, limit: int = 3000) -> Dict[str, Any]:
    t = norm_t(t)
    conn = connect(run)
    try:
        tb = tables(conn)
        if "episodic_memory" not in tb:
            raise NotFound("run has no episodic_memory table")
        if not conn.execute("SELECT 1 FROM episodic_memory WHERE agent_id = ? LIMIT 1", (agent,)).fetchone():
            if agent in _node_agents(run) and not conn.execute("SELECT 1 FROM episodic_memory LIMIT 1").fetchone():
                return _state_from_nodes(run, agent, t)          # a run with no mirror rows at all: the baseline arm
            known = list_agents(run)
            if agent not in [a["agent"] for a in known]:
                raise NotFound(f"unknown agent {agent!r} in run {run!r}")
        if t is None:
            t = conn.execute("SELECT MAX(sim_timestamp) FROM episodic_memory").fetchone()[0] or "9999-12-31 23:59:59"
        ctx: Dict[str, Any] = {}
        if "event_scoring_context" in tb:
            ctx = {r["entry_id"]: (r["status"], json.loads(r["trait_ids_json"])) for r in
                   conn.execute("SELECT * FROM event_scoring_context WHERE agent_id = ?", (agent,))}
        semantic = []
        if "semantic_memory" in tb:
            semantic = conn.execute("SELECT * FROM semantic_memory WHERE agent_id = ? AND created_at <= ? ORDER BY created_at, rowid",
                                    (agent, t)).fetchall()
        in_summary: Dict[str, str] = {}
        for s in semantic:
            for e in json.loads(s["source_entry_ids"]):
                in_summary.setdefault(e, s["entry_id"])
        total = conn.execute("SELECT COUNT(*) FROM episodic_memory WHERE agent_id = ? AND sim_timestamp <= ?", (agent, t)).fetchone()[0]
        rows = conn.execute("SELECT entry_id, content, sim_timestamp, sim_day, importance_score, consolidated FROM episodic_memory "
                            "WHERE agent_id = ? AND sim_timestamp <= ? ORDER BY sim_timestamp, rowid LIMIT ?", (agent, t, limit)).fetchall()
        episodic = []
        for r in rows:
            status, trait_ids = ctx.get(r["entry_id"], (None, []))
            episodic.append({
                "entry_id": r["entry_id"], "text": r["content"], "sim_time": r["sim_timestamp"], "sim_day": r["sim_day"],
                "importance": r["importance_score"], "is_idle_text": "idle" in r["content"].lower(),
                "consolidated_into": in_summary.get(r["entry_id"]),
                "consolidated_now": bool(r["consolidated"]),
                "scoring": ({"status": status, "trait_ids_in_prompt": trait_ids} if "event_scoring_context" in tb
                            else {"status": "not recorded"})})
        reinforcement = {}
        if "semantic_reinforcement" in tb:
            reinforcement = {r["semantic_id"]: dict(r) for r in conn.execute("SELECT * FROM semantic_reinforcement WHERE agent_id = ?", (agent,))}
        summaries = []
        for s in semantic:
            known_sources = [e for e in json.loads(s["source_entry_ids"])
                             if (conn.execute("SELECT sim_timestamp FROM episodic_memory WHERE entry_id = ?", (e,)).fetchone() or ["9"])[0] <= t]
            r = reinforcement.get(s["entry_id"])
            summaries.append({"entry_id": s["entry_id"], "summary": s["summary"], "source_entry_ids": known_sources,
                              "sources_total_in_record": len(json.loads(s["source_entry_ids"])), "importance": s["importance_score"],
                              "created_at": s["created_at"], "times_reinforced": s["times_reinforced"],
                              "distinct_days_reinforced": s["distinct_days_reinforced"],
                              "stage4_reinforcement": ({"day_set": json.loads(r["day_set_json"]), "same_day_max": r["same_day_max"],
                                                        "self_reinforced_nights": json.loads(r["self_reinforced_json"])} if r else None)})
        sweeps = []
        if "consolidation_sweeps" in tb:
            sweeps = [{"night": r["night"], "sweep_time": r["sweep_time"], "status": r["status"]} for r in
                      conn.execute("SELECT * FROM consolidation_sweeps WHERE agent_id = ? AND sweep_time <= ? ORDER BY sweep_time", (agent, t))]
        traits, trait_rows = [], []
        stage4 = {"available": "identity_traits" in tb}
        if "identity_traits" in tb:
            trait_rows = conn.execute("SELECT * FROM identity_traits WHERE agent_id = ? AND created_sim_time <= ?", (agent, t)).fetchall()
            sem_text = {s["entry_id"]: s["summary"] for s in conn.execute("SELECT entry_id, summary FROM semantic_memory WHERE agent_id = ?", (agent,))} \
                if "semantic_memory" in tb else {}
            counts = {k: v["distinct_days"] for k, v in reinforcement.items()}
            priors_text = " ".join(p["statement"] for p in priors_for(agent))
            for r in _trait_order(trait_rows, counts):
                sems, evts = json.loads(r["source_semantic_ids_json"]), json.loads(r["source_event_ids_json"])
                src_texts = [sem_text.get(s, "") for s in sems]
                for e in evts:
                    row = conn.execute("SELECT content FROM episodic_memory WHERE entry_id = ?", (e,)).fetchone()
                    src_texts.append(row[0] if row else "")
                traits.append({"trait_id": r["trait_id"], "text": r["text"], "path": r["path"], "source_semantic_ids": sems,
                               "source_event_ids": evts, "created_night": r["created_night"], "created_sim_time": r["created_sim_time"],
                               "active_now": bool(r["active"]),
                               "active_at_t": "unknown (evictions are not timestamped; `active_now` is the recorded flag)",
                               "provenance": (provenance(r["text"], [s for s in src_texts if s], priors_text) if diagnostics
                                              else {"available": False, "reason": "not requested (add diagnostics=true)"})})
        active = [tr["text"] for tr in traits if tr["active_now"]]
        stage4["traits"] = traits
        return {
            "run": run, "agent": agent, "sim_time": t, "label": run_label(run),
            "stage1_priors": {"statements": priors_for(agent), "source": f"devmem/config/personas/{slug(agent)}.yaml"},
            "stage2_episodic": {"entries": episodic, "entries_total_up_to_t": total, "returned": len(episodic),
                                "idle_text_entries": sum(1 for e in episodic if e["is_idle_text"])},
            "stage3_semantic": {"available": "semantic_memory" in tb, "summaries": summaries, "sweeps": sweeps},
            "stage4_identity": stage4,
            "identity_context_at_t": ({**render_identity_context(active), "traits_considered": "active_now traits created at or before t, newest first"}
                                      if "identity_traits" in tb else {"text": "", "note": "no Stage 4 tables in this run"})}
    finally:
        conn.close()


# ---------------------------------------------------------------------------------------------
# timeline and ledger
# ---------------------------------------------------------------------------------------------
STAGE_OF_KIND = {"priors": 1, "episodic": 2, "sweep": 3, "summary": 3, "identity_sweep": 4, "trait": 4, "sleep_state": 0, "ledger_window": 0}


def timeline(run: str) -> Dict[str, Any]:
    conn = connect(run)
    d = run_dir(run)
    events: List[Dict[str, Any]] = []
    try:
        tb = tables(conn)
        first = {}
        if "episodic_memory" in tb:
            for r in conn.execute("SELECT agent_id, entry_id, content, sim_timestamp, importance_score FROM episodic_memory ORDER BY sim_timestamp, rowid"):
                first.setdefault(r["agent_id"], r["sim_timestamp"])
                events.append({"t": r["sim_timestamp"], "agent": r["agent_id"], "kind": "episodic", "stage": 2, "id": r["entry_id"],
                               "text": r["content"], "importance": r["importance_score"], "idle_text": "idle" in r["content"].lower()})
        if not first:                                                   # no mirror rows: the baseline arm, from its node files
            for a in _node_agents(run):
                for n in _nodes(run, a):
                    first.setdefault(a, n["created"])
                    events.append({"t": n["created"], "agent": a, "kind": "episodic", "stage": 2, "id": f"{a}:{n['node_id']}", "text": n["description"],
                                   "importance": n["poignancy"], "idle_text": "idle" in n["description"].lower()})
        for a, t0 in first.items():
            events.append({"t": t0, "agent": a, "kind": "priors", "stage": 1, "id": f"{a}:priors", "text": f"Stage 1 priors ({len(priors_for(a))} statements) in force"})
        if "consolidation_sweeps" in tb:
            for r in conn.execute("SELECT * FROM consolidation_sweeps"):
                events.append({"t": r["sweep_time"], "agent": r["agent_id"], "kind": "sweep", "stage": 3, "id": f"sweep:{r['agent_id']}:{r['night']}",
                               "text": f"consolidation sweep, night {r['night']}, status {r['status']}"})
        if "semantic_memory" in tb:
            for r in conn.execute("SELECT * FROM semantic_memory"):
                events.append({"t": r["created_at"], "agent": r["agent_id"], "kind": "summary", "stage": 3, "id": r["entry_id"], "text": r["summary"]})
        if "identity_sweeps" in tb:
            for r in conn.execute("SELECT * FROM identity_sweeps"):
                events.append({"t": r["sweep_time"], "agent": r["agent_id"], "kind": "identity_sweep", "stage": 4, "id": f"isweep:{r['agent_id']}:{r['night']}",
                               "text": f"identity step, night {r['night']}, status {r['status']}"})
        if "identity_traits" in tb:
            for r in conn.execute("SELECT * FROM identity_traits"):
                events.append({"t": r["created_sim_time"], "agent": r["agent_id"], "kind": "trait", "stage": 4, "id": r["trait_id"],
                               "text": r["text"], "path": r["path"]})
    finally:
        conn.close()
    windows = _jsonl(d / "hourly_ledger.jsonl")
    for w in windows:
        for a, frac in (w.get("sleeping_step_fraction") or {}).items():
            events.append({"t": w["sim_clock"], "agent": a, "kind": "sleep_state", "stage": 0, "id": f"sleep:{a}:{w['label']}",
                           "text": f"fraction of steps asleep in this window: {frac}", "fraction_asleep": frac})
        events.append({"t": w["sim_clock"], "agent": None, "kind": "ledger_window", "stage": 0, "id": f"ledger:{w['label']}",
                       "text": f"{w['calls']} router calls in window {w['label']}", "calls": w["calls"]})
    events.sort(key=lambda e: (e["t"], e["stage"], str(e["id"])))
    times = [e["t"] for e in events]
    return {"run": run, "label": run_label(run), "events": events, "count": len(events), "t_min": times[0] if times else None,
            "t_max": times[-1] if times else None,
            "notes": ["sleep_state and ledger_window events come from hourly_ledger.jsonl when the run has one (window ends, not exact wake or sleep instants)",
                      "individual router calls carry no simulated time in the logs, so they appear only as per-window counts"]}


def ledger_summary(run: str) -> Dict[str, Any]:
    d = run_dir(run)
    windows = _jsonl(d / "hourly_ledger.jsonl")
    if not windows:
        return {"run": run, "available": False, "reason": "no hourly_ledger.jsonl in this run folder"}
    analysis = _json(d / "stepd_analysis.json") or {}
    detail = {w["window"]: w["by_agent_and_prompt_type"] for w in analysis.get("windows", [])}
    out = []
    for w in windows:
        out.append({"window": w["label"], "sim_clock_end": w["sim_clock"], "calls": w["calls"], "tokens_in": w["tokens_in"], "tokens_out": w["tokens_out"],
                    "by_purpose": w.get("by_purpose", {}), "by_agent": w.get("by_agent", {}),
                    "by_agent_and_prompt_type": detail.get(w["label"]), "sleeping_step_fraction": w.get("sleeping_step_fraction")})
    return {"run": run, "available": True, "label": run_label(run), "windows": out,
            "totals": {"calls": sum(w["calls"] for w in windows), "tokens_in": sum(w["tokens_in"] for w in windows),
                       "tokens_out": sum(w["tokens_out"] for w in windows)},
            "sources": ["hourly_ledger.jsonl"] + (["stepd_analysis.json (offline-captured per-window per-agent per-prompt-type split)"] if detail else []),
            "note": "evaluation calls, if any, are not in these windows"}


def compare(a: str, b: str, agent: str, t: Optional[str] = None) -> Dict[str, Any]:
    return {"agent": agent, "t": norm_t(t), "a": agent_state(a, agent, t), "b": agent_state(b, agent, t)}


# ---------------------------------------------------------------------------------------------
# town replay support (Phase 8 Stop 2): movement frames, thoughts, live status
# ---------------------------------------------------------------------------------------------
def _movement(run: str):
    from devmem.api.movement_archive import MovementSource
    src = MovementSource.open(run_dir(run), run)
    return src


def movement_meta(run: str) -> Dict[str, Any]:
    src = _movement(run)
    if src is None:
        return {"run": run, "available": False,
                "reason": "no movement.zip in the run folder and no simulation folder with movement files for this run"}
    return {"run": run, "available": True, **src.describe()}


def movement_frames(run: str, from_step: int, to_step: int, stride: int = 1) -> Dict[str, Any]:
    src = _movement(run)
    if src is None:
        raise NotFound("no movement recorded for this run")
    if to_step < from_step:
        raise ValueError("to_step must not be below from_step")
    return {"run": run, **src.frames(from_step, to_step, stride)}


def agent_thoughts(run: str, agent: str, t: Optional[str] = None) -> Dict[str, Any]:
    src = _movement(run)
    if src is None:
        return {"run": run, "agent": agent, "available": False, "reason": "no saved memory with thought nodes is available for this run"}
    return {"run": run, "available": True, **src.thoughts(agent, norm_t(t) if t else None)}


def run_status(run: str) -> Dict[str, Any]:
    """The live call counter of a run that is writing run_status.json (the arm runner does). `fresh` means the file changed in the
    last LIVE_WINDOW_SECONDS; otherwise no live segment is running and the numbers are the last recorded ones."""
    f = run_dir(run) / "run_status.json"
    data = _json(f)
    if data is None:
        return {"run": run, "available": False, "fresh": False, "reason": "this run folder has no run_status.json"}
    age = time.time() - f.stat().st_mtime
    return {"run": run, "available": True, "fresh": age < LIVE_WINDOW_SECONDS and str(data.get("state", "")).startswith(("running", "starting")),
            "age_seconds": round(age), "status": data}
