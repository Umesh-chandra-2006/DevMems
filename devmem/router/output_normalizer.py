"""
Output normalizer (router/output layer). NOT wired into the router: it exists so that a replay can measure what it would
change. If it is ever adopted it must apply identically to baseline and staged and be reported as a disclosed deviation.

  normalize_unicode_spaces : maps every Unicode space separator (U+00A0 no-break space, U+2000 to U+200A, U+202F narrow
                             no-break space, U+205F, U+3000, U+1680) to a plain ASCII space.
  strip_duration_suffix    : removes a trailing "(duration in minutes: N, minutes left: M)" annotation.
                             HAZARD: upstream's task-decomposition prompt REQUIRES that annotation, so this step must only
                             ever be applied to the outputs of the wake-up, daily-plan and hourly-schedule prompts, never
                             globally.
"""
import re

_UNICODE_SPACES = "               　"
_SPACE_RE = re.compile("[" + _UNICODE_SPACES + "]")
_DURATION_RE = re.compile(r"\s*\(\s*duration in minutes\s*:\s*\d+\s*,\s*minutes left\s*:\s*\d+\s*\)", re.IGNORECASE)


def normalize_unicode_spaces(text: str) -> str:
    return _SPACE_RE.sub(" ", text)


def strip_duration_suffix(text: str) -> str:
    return _DURATION_RE.sub("", text)


def normalize_output(text: str, strip_duration: bool = False) -> str:
    out = normalize_unicode_spaces(str(text))
    return strip_duration_suffix(out) if strip_duration else out


def has_exotic_space(text: str) -> bool:
    return bool(_SPACE_RE.search(str(text)))


def has_duration_suffix(text: str) -> bool:
    return bool(_DURATION_RE.search(str(text)))


# ---------------------------------------------------------------------------------------------------------------------
# Router wiring (Phase 5, behind DEVMEM_OUTPUT_NORMALIZER; default OFF)
#
# The router calls `maybe_normalize(prompt, text)` on every reply. It does nothing unless DEVMEM_OUTPUT_NORMALIZER is "on"
# and the prompt is one of the three allow-listed upstream prompts below. It is an ALLOW-LIST: every other prompt (task
# decomposition, action generation, conversation, scoring, reflection, summaries) is left untouched, and two decomposition
# markers veto even an allow-listed match. The flag is process-wide, so it applies identically to baseline and staged.
# ---------------------------------------------------------------------------------------------------------------------
import os
from typing import Dict, Optional, Tuple

ENV_FLAG = "DEVMEM_OUTPUT_NORMALIZER"
STATS: Dict[str, Dict[str, int]] = {}  # kind -> {"applied": n, "changed": n}

# Fragments of the rendered upstream templates (wake_up_hour_v1, daily_planning_v6, generate_hourly_schedule_v2).
_KIND_MARKERS: Tuple[Tuple[str, str], ...] = (
    ("hourly_schedule", "Hourly schedule format:"),
    ("daily_plan", "plan today in broad-strokes"),
    ("wake_up_hour", "wake up hour:"),
)
# Fragments of the rendered decomposition templates (task_decomp_v3, new_decomp_schedule_v1). Their presence vetoes the match.
_VETO_MARKERS: Tuple[str, ...] = ("Describe subtasks in 5 min increments", "The revised schedule:")


def enabled() -> bool:
    return os.environ.get(ENV_FLAG, "off").strip().lower() == "on"


def prompt_kind(prompt: str) -> Optional[str]:
    """Which allow-listed prompt this is, or None. Decomposition prompts always return None."""
    text = str(prompt)
    if any(v in text for v in _VETO_MARKERS):
        return None
    for kind, marker in _KIND_MARKERS:
        if marker in text:
            return kind
    return None


def maybe_normalize(prompt: str, text: str) -> Tuple[str, Optional[str]]:
    """Returns (text, kind). `kind` is None when nothing was applied (flag off, or prompt not allow-listed)."""
    if not enabled():
        return text, None
    kind = prompt_kind(prompt)
    if kind is None:
        return text, None
    out = normalize_output(text, strip_duration=True)
    s = STATS.setdefault(kind, {"applied": 0, "changed": 0})
    s["applied"] += 1
    s["changed"] += 1 if out != text else 0
    return out, kind
