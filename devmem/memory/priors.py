"""
Stage 1: Personality Priors.
Loads permanent, pre-experience personality priors from configuration files,
formats prompt contexts for scoring and planning, and handles baseline fairness injection.
"""

from datetime import datetime
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import yaml

# Resolve default config directory: devmem/config/personas
DEFAULT_PERSONAS_DIR = Path(__file__).resolve().parent.parent / "config" / "personas"


class PersonaNotFoundError(FileNotFoundError):
    """Raised when an agent's persona prior YAML configuration file cannot be found."""
    pass


class PersonaSchemaError(ValueError):
    """Raised when a persona YAML configuration file fails schema validation."""
    pass


def _resolve_persona_file(agent_id: str, personas_dir: Path) -> Path:
    """
    Resolve agent_id to a specific YAML file path in personas_dir.
    Supports exact filename, lowercased snake_case filename, and scanning
    YAML files for matching 'agent_id' attribute.
    """
    if not personas_dir.exists() or not personas_dir.is_dir():
        raise PersonaNotFoundError(f"Personas configuration directory does not exist: {personas_dir}")

    # 1. Exact match on filename
    candidates = [
        personas_dir / f"{agent_id}.yaml",
        personas_dir / f"{agent_id}.yml",
        personas_dir / f"{agent_id.lower().replace(' ', '_')}.yaml",
        personas_dir / f"{agent_id.lower().replace(' ', '_')}.yml",
    ]
    for c in candidates:
        if c.exists() and c.is_file():
            return c

    # 2. Search all YAML files in personas_dir for matching 'agent_id' field
    for f in personas_dir.glob("*.y*ml"):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = yaml.safe_load(fp)
            if isinstance(data, dict):
                declared_id = data.get("agent_id")
                if declared_id and (
                    str(declared_id).strip() == agent_id.strip()
                    or str(declared_id).strip().lower() == agent_id.strip().lower()
                ):
                    return f
        except Exception:
            continue

    raise PersonaNotFoundError(
        f"No persona configuration file found for agent_id='{agent_id}' in directory '{personas_dir}'"
    )


def load_priors(agent_id: str, personas_dir: Optional[Union[str, Path]] = None) -> List[str]:
    """
    Load hand-authored priors from config/personas/{agent_id}.yaml.

    Args:
        agent_id: The unique identifier or full name of the agent (e.g. 'Isabella Rodriguez').
        personas_dir: Optional path to personas config directory. Defaults to devmem/config/personas.

    Returns:
        List of personality statements (strings).

    Raises:
        PersonaNotFoundError: If the YAML file for agent_id does not exist.
        PersonaSchemaError: If the YAML file is malformed or missing required keys.
    """
    p_dir = Path(personas_dir) if personas_dir else DEFAULT_PERSONAS_DIR
    file_path = _resolve_persona_file(agent_id, p_dir)

    try:
        with open(file_path, "r", encoding="utf-8") as fp:
            data = yaml.safe_load(fp)
    except Exception as e:
        raise PersonaSchemaError(f"Failed to parse YAML for '{agent_id}' at {file_path}: {e}") from e

    if not isinstance(data, dict):
        raise PersonaSchemaError(f"Persona file for '{agent_id}' must be a YAML dictionary mapping.")

    raw_priors = data.get("priors")
    if raw_priors is None:
        raise PersonaSchemaError(f"Persona file for '{agent_id}' is missing required 'priors' key.")

    if not isinstance(raw_priors, list):
        raise PersonaSchemaError(f"'priors' for '{agent_id}' must be a list of statements.")

    statements: List[str] = []
    for idx, item in enumerate(raw_priors):
        if isinstance(item, dict):
            stmt = item.get("statement")
            if not stmt or not isinstance(stmt, str):
                raise PersonaSchemaError(
                    f"Prior entry #{idx} for '{agent_id}' has a dictionary without a valid 'statement' string."
                )
            statements.append(stmt.strip())
        elif isinstance(item, str):
            if not item.strip():
                continue
            statements.append(item.strip())
        else:
            statements.append(str(item).strip())

    if not statements:
        raise PersonaSchemaError(f"Persona file for '{agent_id}' contains an empty list of priors.")

    return statements


def get_prompt_context(agent_id: str, personas_dir: Optional[Union[str, Path]] = None) -> str:
    """
    Format loaded priors into a prompt-injection block to inject into scoring/planning prompts.

    Args:
        agent_id: The unique identifier or full name of the agent.
        personas_dir: Optional directory containing persona YAML files.

    Returns:
        A standardized multi-line string block representing the agent's core personality traits.
    """
    priors = load_priors(agent_id, personas_dir=personas_dir)
    return "This agent's core personality traits:\n" + "\n".join(f"- {p}" for p in priors)


def inject_into_baseline(
    agent_id: str,
    persona: Any,
    created_time: Optional[datetime] = None,
    mode: str = "atomic",
    personas_dir: Optional[Union[str, Path]] = None,
) -> Any:
    """
    Fairness control: writes the agent's priors into the baseline (flat-memory) condition's
    original upstream memory structure (AssociativeMemory) so baseline agents start with
    the same personality grounding as staged-condition agents.

    Plan Amendment:
        Default mode is 'atomic' (one ConceptNode per prior statement) rather than 'bundled'.
        Rationale: Bundled embeddings dilute cosine similarity against specific situational
        focal points, which would handicap the baseline condition during retrieval.

    Args:
        agent_id: Identifier of the agent.
        persona: Upstream Persona instance (or object with .a_mem: AssociativeMemory).
        created_time: Timestamp for memory creation. Defaults to persona.scratch.curr_time or 2023-02-13 00:00:00.
        mode: Injection format mode ("atomic" for individual thoughts, "bundled" for single combined thought).
              Default is "atomic".
        personas_dir: Optional path to personas config directory.

    Returns:
        List of ConceptNode instances (if atomic) or the created ConceptNode instance (if bundled).
    """
    priors = load_priors(agent_id, personas_dir=personas_dir)

    if not hasattr(persona, "a_mem"):
        raise AttributeError(f"Target persona object for '{agent_id}' has no 'a_mem' (AssociativeMemory) attribute.")

    a_mem = persona.a_mem

    if created_time is None:
        if hasattr(persona, "scratch") and getattr(persona.scratch, "curr_time", None):
            created_time = persona.scratch.curr_time
        else:
            created_time = datetime(2023, 2, 13, 0, 0, 0)

    # Import embedding generator from upstream prompt structure
    try:
        from reverie.backend_server.persona.prompt_template.gpt_structure import get_embedding
    except ImportError:
        try:
            import sys
            p_root = Path(__file__).resolve().parent.parent.parent / "reverie" / "reverie" / "backend_server"
            if str(p_root) not in sys.path:
                sys.path.insert(0, str(p_root))
            from persona.prompt_template.gpt_structure import get_embedding
        except Exception:
            # Fallback embedding if running in detached environment
            def get_embedding(text):
                import hashlib
                import numpy as np
                seed = int(hashlib.md5(text.encode("utf-8")).hexdigest()[:8], 16)
                rng = np.random.RandomState(seed)
                v = rng.randn(768).astype(float)
                return (v / np.linalg.norm(v)).tolist()

    agent_name = getattr(persona, "name", agent_id)

    if mode == "bundled":
        # Option A: Single combined thought entry
        bundled_desc = f"{agent_name}'s core personality traits: " + " ".join(priors)
        embedding = get_embedding(bundled_desc)
        node = a_mem.add_thought(
            created=created_time,
            expiration=None,
            s=agent_name,
            p="has personality trait",
            o="core priors",
            description=bundled_desc,
            keywords=["personality", "core", "priors", "traits"],
            poignancy=10,
            embedding_pair=(bundled_desc, embedding),
            filling=None,
        )
        return node
    elif mode == "atomic":
        # Option B: Individual atomic thought entries (one per prior statement)
        nodes = []
        for idx, prior_stmt in enumerate(priors):
            desc = f"{agent_name}: {prior_stmt}"
            embedding = get_embedding(desc)
            words = [w.strip(".,;:\"'()").lower() for w in prior_stmt.split() if len(w) > 4]
            node = a_mem.add_thought(
                created=created_time,
                expiration=None,
                s=agent_name,
                p="has personality trait",
                o=f"prior_{idx+1}",
                description=desc,
                keywords=list(set(["personality", "trait"] + words[:4])),
                poignancy=10,
                embedding_pair=(desc, embedding),
                filling=None,
            )
            nodes.append(node)
        return nodes
    else:
        raise ValueError(f"Unknown injection mode: '{mode}'. Must be 'bundled' or 'atomic'.")

