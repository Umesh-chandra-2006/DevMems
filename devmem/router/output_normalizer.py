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
