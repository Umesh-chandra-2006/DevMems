"""Current-agent context for LLM ledger tagging. The headless runner sets it around each persona's move() so every
router call made on that persona's behalf is logged with its agent_id, without touching upstream call sites."""
from contextvars import ContextVar
from typing import Optional

_current_agent: ContextVar[Optional[str]] = ContextVar("devmem_current_agent", default=None)


def set_current_agent(name: Optional[str]):
    return _current_agent.set(name)


def reset_current_agent(token) -> None:
    _current_agent.reset(token)


def get_current_agent() -> Optional[str]:
    return _current_agent.get()
