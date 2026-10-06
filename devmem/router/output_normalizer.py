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
# Router wiring (behind DEVMEM_OUTPUT_NORMALIZER; default OFF). REVISED RULE (PM verdict after Step C):
#
#   * Strip ONLY the exact annotation  "(duration in minutes: <n>, minutes left: <n>)"  (see STRICT_ANNOTATION), together with the
#     spaces or tabs directly before it. Nothing else is removed: text that does not contain that exact pattern comes back byte
#     for byte.
#   * Apply it to EVERY reply in the simulation call path EXCEPT the decomposition veto set (prompts whose parser needs the
#     annotation: task_decomp_v1/v2/v3 in both template folders, new_decomp_schedule_v1; found by code-reading
#     run_gpt_prompt.py: only the task-decomposition parser reads "(duration in minutes:" and "(total duration in minutes").
#   * Unicode-space mapping stays exactly as before: only for the three originally covered prompts (wake-up hour, daily plan,
#     hourly schedule). For every other prompt the only change ever made is removing the annotation.
#   * The flag is process-wide, so it applies identically to baseline and staged.
#
# Observed variants of the annotation that this rule handles (443 occurrences in 94 saved replies, Phase 5 probes and Step C).
# In every one the annotation is preceded by a single ASCII space and has exactly this text; what differs is what follows it:
#   V1 followed by a newline (end of line)      290      V4 at the very end of the reply          38
#   V2 followed by a space (mid line)             55      V5 followed by a period                  11
#   V3 followed by a comma                        47      V6 followed by a semicolon                2
# No non-exact lookalike (other wording, other case, missing "minutes left") occurred; any such text is left untouched.
# ---------------------------------------------------------------------------------------------------------------------
import os
import re
from typing import Dict, Optional, Tuple

ENV_FLAG = "DEVMEM_OUTPUT_NORMALIZER"
STATS: Dict[str, Dict[str, int]] = {}  # label -> {"applied": n, "changed": n}

STRICT_ANNOTATION = re.compile(r"[ \t]*\(duration in minutes: \d+, minutes left: \d+\)")

# Fragments of the rendered decomposition prompts. Their presence vetoes normalization of the reply.
#   "Describe subtasks in 5 min increments"  all six task_decomp templates (v2 and v3_ChatGPT folders)
#   "(total duration in minutes"              the task-decomposition question line the parser itself reads from the prompt
#   "The revised schedule:"                   new_decomp_schedule_v1
VETO_MARKERS: Tuple[str, ...] = ("Describe subtasks in 5 min increments", "(total duration in minutes", "The revised schedule:")

# The three prompts for which the Unicode-space mapping is also applied (scope unchanged from the first wiring).
_KIND_MARKERS: Tuple[Tuple[str, str], ...] = (
    ("hourly_schedule", "Hourly schedule format:"),
    ("daily_plan", "plan today in broad-strokes"),
    ("wake_up_hour", "wake up hour:"),
)


def enabled() -> bool:
    return os.environ.get(ENV_FLAG, "off").strip().lower() == "on"


def vetoed(prompt: str) -> bool:
    """True for the decomposition prompts, whose parser needs the annotation."""
    text = str(prompt)
    return any(v in text for v in VETO_MARKERS)


def prompt_kind(prompt: str) -> Optional[str]:
    """Which of the three space-mapped prompts this is, or None. Vetoed prompts always return None."""
    text = str(prompt)
    if vetoed(text):
        return None
    for kind, marker in _KIND_MARKERS:
        if marker in text:
            return kind
    return None


def strip_annotation_exact(text: str) -> str:
    return STRICT_ANNOTATION.sub("", text)


def maybe_normalize(prompt: str, text: str) -> Tuple[str, Optional[str]]:
    """Returns (text, label). label is None when nothing was applied (flag off, or a vetoed decomposition prompt); otherwise the
    prompt's kind for the three space-mapped prompts, or "call_path" for every other non-vetoed prompt."""
    if not enabled():
        return text, None
    if vetoed(prompt):
        return text, None
    kind = prompt_kind(prompt)
    out = normalize_unicode_spaces(text) if kind is not None else text
    out = strip_annotation_exact(out)
    label = kind or "call_path"
    s = STATS.setdefault(label, {"applied": 0, "changed": 0})
    s["applied"] += 1
    s["changed"] += 1 if out != text else 0
    return out, label
