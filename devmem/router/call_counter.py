"""Router-level LLM call counter and cap.

`llm_router.call_llm` calls `record_call` as its first action, so EVERY call is counted regardless of how the caller imported it
(`gpt_structure`, `episodic`, `consolidation`, scripts). A call is counted when it is attempted, before any provider work, whether
it later succeeds or fails. `CapReached` derives from BaseException on purpose: upstream's `except Exception` retry loops cannot
swallow it, so a hard cap really stops the run.
"""
import threading
from typing import Any, Dict, Optional


class CapReached(BaseException):
    pass


_lock = threading.Lock()
_state: Dict[str, Any] = {"count": 0, "cap": None, "by_purpose": {}, "by_agent": {}}


def set_cap(cap: Optional[int]) -> None:
    """Hard cap on the number of call_llm attempts counted from now (None removes the cap)."""
    with _lock:
        _state["cap"] = cap


def reset() -> None:
    with _lock:
        _state.update({"count": 0, "cap": None, "by_purpose": {}, "by_agent": {}})


def snapshot() -> Dict[str, Any]:
    with _lock:
        return {"count": _state["count"], "cap": _state["cap"],
                "by_purpose": dict(_state["by_purpose"]), "by_agent": dict(_state["by_agent"])}


def record_call(purpose: Optional[str], agent_id: Optional[str]) -> None:
    with _lock:
        if _state["cap"] is not None and _state["count"] >= _state["cap"]:
            raise CapReached(f"router call cap {_state['cap']} reached")
        _state["count"] += 1
        p = purpose or "none"
        a = agent_id or "none"
        _state["by_purpose"][p] = _state["by_purpose"].get(p, 0) + 1
        _state["by_agent"][a] = _state["by_agent"].get(a, 0) + 1
