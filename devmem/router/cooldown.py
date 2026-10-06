"""
devmem/router/cooldown.py

Cooldown Management, RPM Pacing, Circuit Breaker, and Token Budgeting for LLM Router.
Persists runtime cooldown and token states across restarts in devmem/router/cooldown_state.json.
Uses atomic write operations and zoneinfo for Los Angeles reset timing.
"""

from datetime import date, datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger("devmem.router.cooldown")

STATE_FILE = Path(__file__).resolve().parent / "cooldown_state.json"

# Circuit breaker sequence for unknown 429 errors (seconds)
UNKNOWN_COOLDOWN_SEQUENCE = [30, 60, 120, 240, 480, 900]
MAX_COOLDOWN_SECONDS = 900  # 15 minutes cap for unknown 429s only


def get_seconds_until_utc_midnight() -> int:
    """Calculate seconds remaining until next 00:00:00 UTC (fallback daily reset)."""
    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).date()
    midnight = datetime.combine(tomorrow, datetime.min.time(), tzinfo=timezone.utc)
    diff = int((midnight - now).total_seconds())
    return max(60, diff)


def get_seconds_until_pt_midnight() -> int:
    """
    Calculate seconds remaining until next 00:00:00 Pacific Time (Gemini daily reset)
    using zoneinfo America/Los_Angeles (automatically accounting for PST/PDT).
    """
    tz_pt = ZoneInfo("America/Los_Angeles")
    now_pt = datetime.now(tz_pt)
    tomorrow_pt = (now_pt + timedelta(days=1)).date()
    midnight_pt = datetime.combine(tomorrow_pt, datetime.min.time(), tzinfo=tz_pt)
    diff = int((midnight_pt - now_pt).total_seconds())
    return max(60, diff)


class CooldownManager:
    """
    Manages rate-limiting state, circuit breaker cooldowns, RPM pacing,
    provider-level transient cooldowns, and daily token usage per key and model.
    """

    def __init__(self, state_file: Optional[Path] = None):
        self.state_file = state_file or STATE_FILE
        self.state: Dict[str, Any] = {
            "date": date.today().isoformat(),
            "cooldowns": {},             # key_id -> {"cooldown_until": float, "consecutive_unknown": int, "reason": str}
            "provider_cooldowns": {},    # provider -> {"cooldown_until": float, "reason": str}
            "token_usage": {},           # key_id -> int
            "last_call_timestamps": {},  # key_id -> float
            "tpm_sliding_windows": {},   # key_id -> list of [timestamp, tokens]
            "observed_limits": {},       # key_id -> int
        }
        self.load_state()

    def _make_key_id(self, provider: str, key_env: str, model: Optional[str] = None) -> str:
        """Construct composite key identifier."""
        p = provider.lower().strip()
        k = key_env.strip()
        m = (model or "").strip()
        if m:
            return f"{p}:{k}#{m}"
        return f"{p}:{k}"

    def load_state(self) -> None:
        """
        Load state from JSON file if present, resetting daily counters if date changed.
        A missing or corrupt file starts clean.
        """
        if not self.state_file.exists():
            self.reset_for_test()
            return

        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                saved = json.load(f)

            today_str = date.today().isoformat()
            saved_date = saved.get("date", today_str)

            self.state["date"] = today_str
            self.state["cooldowns"] = saved.get("cooldowns", {})
            self.state["provider_cooldowns"] = saved.get("provider_cooldowns", {})
            self.state["observed_limits"] = saved.get("observed_limits", {})

            # If date changed, reset token usage; otherwise keep
            if saved_date == today_str:
                self.state["token_usage"] = saved.get("token_usage", {})
            else:
                self.state["token_usage"] = {}

            # Prune expired cooldowns
            now = time.time()
            to_delete = []
            for kid, info in self.state["cooldowns"].items():
                if info.get("cooldown_until", 0) <= now:
                    to_delete.append(kid)
            for kid in to_delete:
                self.state["cooldowns"][kid]["cooldown_until"] = 0

            # Prune expired provider cooldowns
            for p, p_info in list(self.state["provider_cooldowns"].items()):
                if p_info.get("cooldown_until", 0) <= now:
                    del self.state["provider_cooldowns"][p]

        except Exception as e:
            logger.warning("Could not read cooldown state file (%s) due to error (%s); starting clean.", self.state_file, e)
            self.reset_for_test()

    def save_state(self) -> None:
        """
        Persist state to JSON file using an atomic write pattern
        (write to .json.tmp in same directory, then rename/replace).
        """
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            temp_file = self.state_file.with_suffix(".json.tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_file, self.state_file)
        except Exception as e:
            logger.warning("Could not atomically save cooldown state file (%s): %s", self.state_file, e)

    def is_cooling_down(self, provider: str, key_env: str, model: Optional[str] = None) -> Tuple[bool, float]:
        """
        Check if key/model (or provider) is in cooldown.
        Returns: (is_in_cooldown, remaining_seconds)
        """
        # First check provider-level cooldown (e.g. timeout failure)
        p_is_cooling, p_rem = self.is_provider_cooling_down(provider)
        if p_is_cooling:
            return True, p_rem

        key_id = self._make_key_id(provider, key_env, model)
        info = self.state["cooldowns"].get(key_id, {})
        cooldown_until = info.get("cooldown_until", 0.0)
        now = time.time()
        remaining = cooldown_until - now
        if remaining > 0:
            return True, remaining
        return False, 0.0

    def set_provider_cooldown(self, provider: str, duration: float = 30.0, reason: str = "") -> float:
        """Set a transient provider-level cooldown (e.g. upon timeout or network failure)."""
        p = provider.lower().strip()
        now = time.time()
        self.state["provider_cooldowns"][p] = {
            "cooldown_until": now + duration,
            "reason": reason
        }
        logger.info("Set provider-level cooldown on %s: duration=%.1fs, reason=%s", p, duration, reason)
        self.save_state()
        return duration

    def is_provider_cooling_down(self, provider: str) -> Tuple[bool, float]:
        """Check if provider is in provider-level cooldown."""
        p = provider.lower().strip()
        p_info = self.state["provider_cooldowns"].get(p, {})
        cooldown_until = p_info.get("cooldown_until", 0.0)
        now = time.time()
        rem = cooldown_until - now
        if rem > 0:
            return True, rem
        return False, 0.0

    def set_cooldown(
        self,
        provider: str,
        key_env: str,
        model: Optional[str],
        kind: str,
        retry_after: Optional[int] = None,
        reason: str = ""
    ) -> float:
        """
        Set cooldown on a key based on classification kind.
        - Groq daily_requests: honors retry_after (now + x-ratelimit-reset-requests), not fixed midnight UTC.
        - Gemini daily_requests: honors retry_after or calculates Los Angeles midnight.
        - Known kinds: honors retry_after beyond 15 minutes.
        - Unknown kind: caps at 15 minutes (900s) or escalates [30, 60, 120, 240, 480, 900].
        """
        key_id = self._make_key_id(provider, key_env, model)
        info = self.state["cooldowns"].setdefault(key_id, {
            "cooldown_until": 0.0,
            "consecutive_unknown": 0,
            "reason": ""
        })

        prov = provider.lower()
        now = time.time()
        duration = 30.0

        if kind == "daily_requests":
            if prov == "groq":
                # Condition 1: lock until now + x-ratelimit-reset-requests (or retry-after), not 00:00 UTC
                if retry_after is not None and retry_after > 0:
                    duration = float(retry_after)
                else:
                    duration = float(get_seconds_until_utc_midnight())
            elif prov == "gemini":
                # Condition 6: Los Angeles midnight
                if retry_after is not None and retry_after > 0:
                    duration = float(retry_after)
                else:
                    duration = float(get_seconds_until_pt_midnight())
            else:
                duration = float(retry_after if retry_after is not None and retry_after > 0 else get_seconds_until_utc_midnight())
            info["consecutive_unknown"] = 0

        elif kind == "tokens_recoverable":
            # Condition 2: Honor known-kind retry-after beyond 15 minutes
            duration = float(retry_after if retry_after is not None else 600)
            info["consecutive_unknown"] = 0

        elif kind == "transient_minute":
            # Condition 2: Honor known-kind retry-after beyond 15 minutes
            duration = float(retry_after if retry_after is not None else 60)
            info["consecutive_unknown"] = 0

        elif kind == "unknown":
            # Condition 2: Cap only unknown 429s
            if retry_after is not None and retry_after > 0:
                duration = float(min(retry_after, MAX_COOLDOWN_SECONDS))
            else:
                consecutive = info.get("consecutive_unknown", 0)
                idx = min(consecutive, len(UNKNOWN_COOLDOWN_SEQUENCE) - 1)
                duration = float(UNKNOWN_COOLDOWN_SEQUENCE[idx])
                info["consecutive_unknown"] = consecutive + 1

        elif kind == "auth_billing_failure":
            duration = float(get_seconds_until_utc_midnight())
            info["consecutive_unknown"] = 0

        info["cooldown_until"] = now + duration
        info["reason"] = f"[{kind}] {reason} (cooldown: {int(duration)}s)"
        logger.info("Set cooldown on %s: duration=%.1fs, reason=%s", key_id, duration, info["reason"])
        self.save_state()
        return duration

    def record_success(self, provider: str, key_env: str, model: Optional[str] = None) -> None:
        """Reset consecutive circuit-breaker counter on success."""
        key_id = self._make_key_id(provider, key_env, model)
        if key_id in self.state["cooldowns"]:
            self.state["cooldowns"][key_id]["consecutive_unknown"] = 0
            self.state["cooldowns"][key_id]["cooldown_until"] = 0.0
            self.save_state()

    def pace_request(self, provider: str, key_env: str, model: Optional[str], rpm: Optional[int]) -> float:
        """
        Enforce RPM pacing per (provider, key, model).
        Sleeps if time since last call is less than 60 / rpm.
        Returns the sleep duration (in seconds).
        """
        if not rpm or rpm <= 0:
            return 0.0

        key_id = self._make_key_id(provider, key_env, model)
        last_call = self.state["last_call_timestamps"].get(key_id, 0.0)
        interval = 60.0 / float(rpm)
        now = time.time()
        elapsed = now - last_call
        slept = 0.0

        if elapsed < interval:
            slept = interval - elapsed
            logger.debug("Pacing %s: sleeping %.2fs to observe %d RPM limit", key_id, slept, rpm)
            time.sleep(slept)

        self.state["last_call_timestamps"][key_id] = time.time()
        return slept

    def pace_tpm_window(
        self,
        provider: str,
        key_env: str,
        model: Optional[str],
        estimated_tokens: int,
        tpm: Optional[int],
        window_seconds: float = 60.0
    ) -> float:
        """
        Enforce a sliding-window TPM pacer per (provider, key, model).
        Maintains a rolling 60-second window of [timestamp, tokens].
        If adding estimated_tokens would breach tpm, sleeps until older tokens
        fall outside the sliding window.
        Returns the duration slept (in seconds).
        """
        if not tpm or tpm <= 0 or estimated_tokens <= 0:
            return 0.0

        key_id = self._make_key_id(provider, key_env, model)
        if "tpm_sliding_windows" not in self.state:
            self.state["tpm_sliding_windows"] = {}
        window = self.state["tpm_sliding_windows"].setdefault(key_id, [])

        now = time.time()
        cutoff = now - window_seconds
        window[:] = [entry for entry in window if entry[0] > cutoff]

        current_tokens = sum(entry[1] for entry in window)
        total_slept = 0.0

        while (current_tokens + estimated_tokens) > tpm and window:
            oldest_ts, oldest_tok = window.pop(0)
            sleep_needed = (oldest_ts + window_seconds) - time.time()
            if sleep_needed > 0:
                logger.debug(
                    "TPM sliding window on %s would reach %d/%d; sleeping %.2fs for window clearance.",
                    key_id, current_tokens + estimated_tokens, tpm, sleep_needed
                )
                time.sleep(sleep_needed + 0.05)
                total_slept += (sleep_needed + 0.05)
            current_tokens -= oldest_tok

        window.append([time.time(), estimated_tokens])
        return total_slept

    def check_token_budget(
        self,
        provider: str,
        key_env: str,
        model: Optional[str],
        estimated_tokens: int,
        tpd_limit: Optional[int]
    ) -> bool:
        """
        Check if adding estimated_tokens would exceed TPD limit.
        Returns True if within budget, False if budget exceeded.
        """
        if not tpd_limit or tpd_limit <= 0:
            return True

        key_id = self._make_key_id(provider, key_env, model)
        used = self.state["token_usage"].get(key_id, 0)
        return (used + estimated_tokens) <= tpd_limit

    def record_token_usage(
        self,
        provider: str,
        key_env: str,
        model: Optional[str],
        tokens: int
    ) -> int:
        """Record tokens consumed by a successful call."""
        key_id = self._make_key_id(provider, key_env, model)
        current = self.state["token_usage"].get(key_id, 0)
        updated = current + tokens
        self.state["token_usage"][key_id] = updated
        self.save_state()
        return updated

    def record_observed_limit(self, provider: str, key_env: str, model: Optional[str], observed_count: int) -> None:
        """Record an observed daily limit when 429 arrives earlier than configured."""
        key_id = self._make_key_id(provider, key_env, model)
        self.state["observed_limits"][key_id] = observed_count
        self.save_state()

    def reset_for_test(self) -> None:
        """Reset all in-memory and persisted cooldown/token states for clean test isolation."""
        self.state = {
            "date": date.today().isoformat(),
            "cooldowns": {},
            "provider_cooldowns": {},
            "token_usage": {},
            "last_call_timestamps": {},
            "tpm_sliding_windows": {},
            "observed_limits": {},
        }
        if self.state_file.exists():
            try:
                self.state_file.unlink()
            except Exception:
                pass
