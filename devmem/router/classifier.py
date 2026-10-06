"""
devmem/router/classifier.py

Unified HTTP 429 & Error Classifier for Multi-Provider LLM Router.
Parses raw HTTP status codes, response headers, and JSON/text bodies from
Groq, Google AI Studio (Gemini), and NVIDIA NIM to accurately classify
rate limits and transient vs. daily exhaustion without blind keyword guessing.
"""

from dataclasses import dataclass
import json
import re
from typing import Any, Dict, Optional, Tuple, Union


@dataclass
class ClassificationResult:
    kind: str  # 'transient_minute' | 'daily_requests' | 'tokens_recoverable' | 'unknown' | 'auth_billing_failure'
    retry_after: Optional[int]  # in seconds (capped at 900 for non-daily)
    raw_reason: str = ""

    def __iter__(self):
        """Allows unpacking as (kind, retry_after) for backward compatibility."""
        return iter((self.kind, self.retry_after))

    def __getitem__(self, index):
        return (self.kind, self.retry_after)[index]


def parse_retry_duration(duration_str: str) -> Optional[int]:
    """
    Parse a human-readable duration string into total seconds.
    Examples:
      '36s' -> 36
      '36.461687371s' -> 36
      '9m38s' -> 578
      '12h33m20s' -> 45200
      '578' -> 578
    """
    if not duration_str:
        return None
    duration_str = str(duration_str).strip()

    # Direct integer or float string
    try:
        val = float(duration_str)
        return max(0, int(val))
    except ValueError:
        pass

    # Pattern with optional hours, minutes, seconds
    pattern = r"^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s)?$"
    match = re.match(pattern, duration_str)
    if match:
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = float(match.group(3) or 0)
        total = int(hours * 3600 + minutes * 60 + seconds)
        return max(0, total)

    return None


def extract_groq_retry_seconds(headers: Dict[str, Any], msg: str) -> Optional[int]:
    """Extract retry seconds for Groq from headers or error message."""
    # 1. Header: retry-after
    if "retry-after" in headers:
        sec = parse_retry_duration(headers["retry-after"])
        if sec is not None:
            return sec

    # 2. Header: x-ratelimit-reset-requests / x-ratelimit-reset-tokens
    for h_key in ["x-ratelimit-reset-tokens", "x-ratelimit-reset-requests"]:
        if h_key in headers:
            sec = parse_retry_duration(headers[h_key])
            if sec is not None:
                return sec

    # 3. Message text: 'Please try again in 9m38s.' or 'try again in 2s.'
    msg_match = re.search(r"try again in ((?:\d+h)?(?:\d+m)?(?:\d+(?:\.\d+)?s?))", msg, re.IGNORECASE)
    if msg_match:
        sec = parse_retry_duration(msg_match.group(1))
        if sec is not None:
            return sec

    return None


def extract_gemini_retry_seconds(headers: Dict[str, Any], body_dict: Dict[str, Any]) -> Optional[int]:
    """Extract retry delay for Gemini from details[].retryDelay, headers, or error message."""
    # 1. Body: details[].retryDelay
    error_obj = body_dict.get("error", {})
    details = error_obj.get("details", [])
    if isinstance(details, list):
        for item in details:
            if isinstance(item, dict):
                # RetryInfo object
                if "retryDelay" in item:
                    sec = parse_retry_duration(item["retryDelay"])
                    if sec is not None:
                        return sec

    # 2. Header: retry-after
    if "retry-after" in headers:
        sec = parse_retry_duration(headers["retry-after"])
        if sec is not None:
            return sec

    # 3. Message text fallback: 'Please retry in 36.461687371s.'
    msg = error_obj.get("message", "")
    msg_match = re.search(r"retry in ((?:\d+h)?(?:\d+m)?(?:\d+(?:\.\d+)?s?))", msg, re.IGNORECASE)
    if msg_match:
        sec = parse_retry_duration(msg_match.group(1))
        if sec is not None:
            return sec

    return None


def classify_429(
    provider: str,
    status: int,
    headers: Optional[Dict[str, Any]] = None,
    body: Union[str, Dict[str, Any], None] = None,
) -> ClassificationResult:
    """
    Classify an HTTP response from an LLM provider into an actionable rate-limit kind.

    Parameters:
      provider: 'groq' | 'gemini' | 'nemotron' | etc.
      status: HTTP response status code (e.g. 429, 401, 402, 403, 500)
      headers: dictionary of HTTP headers (case-insensitive)
      body: JSON body dictionary or raw text

    Returns:
      ClassificationResult with:
        kind: 'transient_minute' | 'daily_requests' | 'tokens_recoverable' | 'unknown' | 'auth_billing_failure'
        retry_after: seconds to cool down (capped at 900 for non-daily kinds)
        raw_reason: explanation string
    """
    prov = (provider or "").lower().strip()
    raw_headers = headers or {}
    h_lower: Dict[str, Any] = {str(k).lower(): v for k, v in raw_headers.items()}

    # Parse body into dictionary if provided as string
    body_dict: Dict[str, Any] = {}
    body_text = ""
    if isinstance(body, dict):
        body_dict = body
        body_text = json.dumps(body)
    elif isinstance(body, str):
        body_text = body
        try:
            body_dict = json.loads(body)
        except Exception:
            body_dict = {}

    # Check for authentication or billing failures (401, 402, 403)
    if status in [401, 402, 403]:
        return ClassificationResult(
            kind="auth_billing_failure",
            retry_after=None,
            raw_reason=f"Auth/Billing failure (HTTP {status}) on {prov}: {body_text[:120]}"
        )

    # If status is not 429, return unknown
    if status != 429:
        return ClassificationResult(
            kind="unknown",
            retry_after=None,
            raw_reason=f"Non-429 HTTP status ({status}) on {prov}"
        )

    # -------------------------------------------------------------
    # 1. GROQ CLASSIFICATION
    # -------------------------------------------------------------
    if prov == "groq":
        error_info = body_dict.get("error", {})
        msg = str(error_info.get("message", body_text))
        retry_sec = extract_groq_retry_seconds(h_lower, msg)

        # Check named limits in message
        is_rpd = bool(
            re.search(r"requests per day|\(RPD\)", msg, re.IGNORECASE) or
            (h_lower.get("x-ratelimit-remaining-requests") == "0" and "day" in msg.lower())
        )
        is_tpd = bool(re.search(r"tokens per day|\(TPD\)", msg, re.IGNORECASE))
        is_rpm = bool(re.search(r"requests per minute|\(RPM\)", msg, re.IGNORECASE))
        is_tpm = bool(re.search(r"tokens per minute|\(TPM\)", msg, re.IGNORECASE))

        if is_rpd:
            return ClassificationResult(
                kind="daily_requests",
                retry_after=retry_sec,
                raw_reason=f"Groq RPD daily quota exhausted: {msg[:100]}"
            )
        elif is_tpd:
            # TPD is tokens per day: recovers dynamically in minutes.
            # CRITICAL SPEC: Must NOT lock key for the day!
            # Honor retry-after beyond 15 minutes for known kinds.
            sec = retry_sec if retry_sec is not None else 600
            return ClassificationResult(
                kind="tokens_recoverable",
                retry_after=sec,
                raw_reason=f"Groq TPD token limit (recoverable in {sec}s): {msg[:100]}"
            )
        elif is_rpm or is_tpm:
            sec = retry_sec if retry_sec is not None else 60
            return ClassificationResult(
                kind="transient_minute",
                retry_after=sec,
                raw_reason=f"Groq transient per-minute limit (wait {sec}s): {msg[:100]}"
            )

        # If unnamed or unrecognized, check if retry_after exists
        if retry_sec is not None:
            return ClassificationResult(
                kind="transient_minute",
                retry_after=retry_sec,
                raw_reason=f"Groq 429 with retry-after {retry_sec}s: {msg[:100]}"
            )

        return ClassificationResult(
            kind="unknown",
            retry_after=None,
            raw_reason=f"Unrecognized Groq 429 payload: {msg[:100]}"
        )

    # -------------------------------------------------------------
    # 2. GOOGLE GEMINI CLASSIFICATION
    # -------------------------------------------------------------
    elif prov == "gemini":
        error_info = body_dict.get("error", {})
        details = error_info.get("details", [])
        retry_sec = extract_gemini_retry_seconds(h_lower, body_dict)

        # Collect all violations across all QuotaFailure details
        all_violations = []
        if isinstance(details, list):
            for item in details:
                if isinstance(item, dict):
                    v_list = item.get("violations", [])
                    if isinstance(v_list, list):
                        all_violations.extend(v_list)

        has_per_day = False
        has_per_minute = False

        for v in all_violations:
            quota_id = str(v.get("quotaId", ""))
            quota_metric = str(v.get("quotaMetric", ""))
            combined = (quota_id + " " + quota_metric).lower()

            # Check case-insensitive signals for PerDay and PerMinute
            if "perday" in combined or "per-day" in combined or "requests-per-day" in combined:
                has_per_day = True
            if "perminute" in combined or "per-minute" in combined or "requests-per-minute" in combined:
                has_per_minute = True

        # Rule: If ANY violation contains PerDay, it is daily_requests (daily wins!)
        if has_per_day:
            return ClassificationResult(
                kind="daily_requests",
                retry_after=retry_sec,
                raw_reason="Gemini QuotaFailure contains PerDay violation"
            )
        elif has_per_minute:
            sec = retry_sec if retry_sec is not None else 60
            return ClassificationResult(
                kind="transient_minute",
                retry_after=sec,
                raw_reason=f"Gemini transient PerMinute violation (retry {sec}s)"
            )

        # Fallback to message text if details[] was missing or unpopulated
        msg = str(error_info.get("message", body_text))
        if re.search(r"per-day|perday|requests per day", msg, re.IGNORECASE):
            return ClassificationResult(
                kind="daily_requests",
                retry_after=retry_sec,
                raw_reason="Gemini 429 message indicates daily quota"
            )
        elif re.search(r"per-minute|perminute|requests per minute|limit: 5|limit: 15", msg, re.IGNORECASE):
            sec = retry_sec if retry_sec is not None else 60
            return ClassificationResult(
                kind="transient_minute",
                retry_after=sec,
                raw_reason=f"Gemini 429 message indicates per-minute limit (retry {sec}s)"
            )

        # If retryDelay was provided, treat as transient
        if retry_sec is not None:
            return ClassificationResult(
                kind="transient_minute",
                retry_after=retry_sec,
                raw_reason=f"Gemini 429 with retry delay {retry_sec}s"
            )

        return ClassificationResult(
            kind="unknown",
            retry_after=None,
            raw_reason=f"Unrecognized Gemini 429 payload: {body_text[:100]}"
        )

    # -------------------------------------------------------------
    # 3. NVIDIA NEMOTRON CLASSIFICATION
    # -------------------------------------------------------------
    elif prov in ["nemotron", "nvidia"]:
        retry_header = h_lower.get("retry-after")
        retry_sec = parse_retry_duration(retry_header) if retry_header else None
        if retry_sec is not None:
            return ClassificationResult(
                kind="transient_minute",
                retry_after=retry_sec,
                raw_reason=f"Nemotron 429 with retry-after header ({retry_sec}s)"
            )
        return ClassificationResult(
            kind="unknown",
            retry_after=None,
            raw_reason=f"Nemotron 429 rate limit: {body_text[:100]}"
        )

    # -------------------------------------------------------------
    # 4. GENERIC / UNKNOWN PROVIDER
    # -------------------------------------------------------------
    else:
        retry_header = h_lower.get("retry-after")
        retry_sec = parse_retry_duration(retry_header) if retry_header else None
        if retry_sec is not None:
            sec = min(retry_sec, 900)  # cap unknown at 900s
            return ClassificationResult(
                kind="unknown",
                retry_after=sec,
                raw_reason=f"Provider {prov} 429 with retry-after header ({sec}s)"
            )
        return ClassificationResult(
            kind="unknown",
            retry_after=None,
            raw_reason=f"Unknown provider {prov} 429: {body_text[:100]}"
        )
