"""
devmem/router/llm_router.py

LLM Router: Provider selection, multi-key rotation, RPM pacing, token budgeting,
and rate-limit classification across free-tier LLM providers (Groq, NVIDIA NIM, Google Gemini).
Enforces pre-emptive rate limits, logs calls to SQLite, and automatically fails over upon 429 rate limits.
Supports configurable timeouts per purpose, provider-level failure backoff, and evaluation model pinning.
"""

from datetime import date, datetime
import logging
import os
from pathlib import Path
import sqlite3
import time
from typing import Any, Dict, List, Optional, Union
import uuid
import yaml

from devmem.router.classifier import ClassificationResult, classify_429
from devmem.router.cooldown import CooldownManager, MAX_COOLDOWN_SECONDS
from devmem.router.key_pool import (
    DEFAULT_DB_PATH,
    get_db_connection,
    get_today_str,
    get_token_usage,
    get_usage,
    increment_token_usage,
    increment_usage,
    is_key_available,
    make_composite_key,
    mark_key_exhausted,
)
from devmem.router.providers import (
    AllProvidersExhaustedError,
    AuthOrBillingError,
    ModelPinnedError,
    ProviderError,
    ProviderResponse,
    ProviderTimeoutError,
    RateLimitError,
    send_request,
)

# Load environment variables from repo root .env if present
try:
    from dotenv import load_dotenv
    root_env = Path(__file__).resolve().parent.parent.parent / ".env"
    if root_env.exists():
        load_dotenv(dotenv_path=root_env)
except ImportError:
    pass

logger = logging.getLogger("devmem.router")

CONFIG_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "providers.yaml")

# Configurable default timeouts per purpose (Condition 4)
DEFAULT_PURPOSE_TIMEOUTS = {
    "importance_scoring": 15,
    "importance_score": 15,
    "poignancy": 15,
    "consolidation_summary": 30,
    "identity_summary": 30,
    "reflection": 45,
    "planning": 60,
    "dialogue": 20,
    "chat": 20,
    "m1_smoke_verification": 15,
    "m1_smoke": 15,
    "default": 30,
}

# Shared global cooldown manager instance
cooldown_manager = CooldownManager()


def load_providers_config(config_path: str = CONFIG_FILE_PATH) -> List[Dict[str, Any]]:
    """Load and return list of providers sorted by priority from providers.yaml."""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    providers = data.get("providers", [])
    # Sort providers by ascending priority (1 first, then 2, then 3)
    providers.sort(key=lambda p: p.get("priority", 999))
    return providers


def estimate_tokens(prompt: str, max_tokens: Optional[int] = None) -> int:
    """
    Estimate total token consumption (prompt + expected output).
    Uses a standard heuristic of ~1.35 tokens per word plus max output tokens.
    """
    words = len(prompt.split())
    prompt_tokens = int(words * 1.35) + 5
    out_tokens = max_tokens if max_tokens is not None else 500
    return max(1, prompt_tokens + out_tokens)


def log_llm_call(
    provider: str,
    model: str,
    purpose: str,
    tokens_in: int,
    tokens_out: int,
    agent_id: Optional[str] = None,
    sim_day: Optional[int] = None,
    condition: Optional[str] = "staged",
    db_path: str = DEFAULT_DB_PATH,
) -> str:
    """Log an LLM call record into the llm_call_log SQLite table."""
    call_id = str(uuid.uuid4())
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute("""
                INSERT INTO llm_call_log (
                    call_id, provider, model, purpose,
                    tokens_in, tokens_out, sim_day, agent_id, condition
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                call_id, provider, model, purpose,
                tokens_in, tokens_out, sim_day, agent_id, condition
            ))
        return call_id
    finally:
        conn.close()


def call_llm(
    prompt: str,
    tier: str = "fast",
    purpose: str = "general",
    agent_id: Optional[str] = None,
    condition: Optional[str] = "staged",
    sim_day: Optional[int] = None,
    config_path: str = CONFIG_FILE_PATH,
    db_path: str = DEFAULT_DB_PATH,
    return_obj: bool = False,
    system_prompt: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    pinned_model: Optional[str] = None,
    timeout: Optional[int] = None,
    cooldown_mgr: Optional[CooldownManager] = None,
) -> Union[str, ProviderResponse]:
    """
    Route an LLM call across configured providers and keys.

    - Iterates providers by priority.
    - Iterates keys within a provider.
    - Model Pinning: If pinned_model is specified, strictly restricts execution to that model.
      Rotates across all keys of the pinned model. Waits if keys are in cooldown <= 90s.
      Raises ModelPinnedError if all keys fail or exhaust without silent fallback.
    - Configurable Timeouts: Computes timeout based on purpose. Treats timeout as transient
      provider failure with 30s provider-level cooldown.
    - Pre-check: Estimates token size. Re-routes if Groq TPM (8,000) exceeded.
    - Pre-check: Checks daily request quota (RPD) and daily token budget (TPD).
    - Pre-check: Checks active cooldown on key/model or provider.
    - RPM Pacer: Automatically paces calls to observe provider RPM constraints.
    - On 429: Classifies error using classify_429, applies circuit-breaker escalating cooldown
      or reset-time lockout, and fails over to next key.
    - On All Cooling Down: If shortest cooldown <= 90s, sleeps and retries.
    """
    if agent_id is None:  # ledger tagging: the headless runner sets the current agent around persona.move()
        from devmem.router.agent_context import get_current_agent
        agent_id = get_current_agent()
    from devmem.router.call_counter import record_call  # counts every attempt, whatever the import path
    record_call(purpose, agent_id)
    providers = load_providers_config(config_path)
    today = get_today_str()
    cm = cooldown_mgr or cooldown_manager

    active_pinned = pinned_model or os.environ.get("DEVMEM_PINNED_MODEL")
    estimated_req_tokens = estimate_tokens(prompt, max_tokens=max_tokens)
    actual_timeout = timeout or DEFAULT_PURPOSE_TIMEOUTS.get(purpose, DEFAULT_PURPOSE_TIMEOUTS.get("default", 30))

    # Maximum 2 retry rounds if all keys cooling down with wait <= 90s
    for wait_attempt in range(2):
        cooldown_durations: List[float] = []

        for provider in providers:
            p_name = provider.get("name", "").lower()
            models = provider.get("models", {})
            model = models.get(tier)

            if not model:
                # If tier not directly in models map, check model_limits or emergency models
                if active_pinned and active_pinned in provider.get("model_limits", {}):
                    model = active_pinned
                else:
                    logger.debug("Provider %s does not define a model for tier %s; skipping.", p_name, tier)
                    continue

            # Model Pinning filter
            if active_pinned and model != active_pinned:
                # If pinned model matches a different tier or model in this provider, adjust
                if active_pinned in models.values() or (provider.get("model_limits") and active_pinned in provider.get("model_limits")):
                    model = active_pinned
                else:
                    logger.debug("Provider %s model %s does not match pinned model %s; skipping.", p_name, model, active_pinned)
                    continue

            # Check provider-level cooldown (e.g. recent timeout)
            p_cooling, p_rem = cm.is_provider_cooling_down(p_name)
            if p_cooling:
                cooldown_durations.append(p_rem)
                logger.debug("Provider %s is in provider-level cooldown (%.1fs remaining); skipping.", p_name, p_rem)
                continue

            # Provider-specific RPM, RPD, TPM, TPD configuration
            model_limits = provider.get("model_limits", {}).get(model, {})
            rpm = model_limits.get("rpm", provider.get("rpm"))
            rpd = model_limits.get("rpd", provider.get(f"daily_limit_{tier}", provider.get("rpd")))
            tpm = model_limits.get("tpm", provider.get("tpm"))
            tpd = model_limits.get("tpd", provider.get("tpd"))

            # 1. TPM Pre-Check: If request exceeds TPM cap (e.g. Groq 8,000 TPM), skip provider
            if tpm is not None and estimated_req_tokens > tpm:
                if active_pinned:
                    raise ModelPinnedError(
                        f"Request ({estimated_req_tokens} est. tokens) exceeds TPM limit ({tpm}) "
                        f"for pinned model '{active_pinned}' on provider {p_name}."
                    )
                logger.warning(
                    "Request estimated at %d tokens exceeds %s TPM cap (%d); skipping to next provider.",
                    estimated_req_tokens, p_name, tpm
                )
                continue

            keys = provider.get("keys", [])

            for key_entry in keys:
                key_env_var = key_entry.get("env")
                if not key_env_var:
                    continue

                api_key = os.environ.get(key_env_var)
                if not api_key or not api_key.strip():
                    logger.debug("Environment variable %s is empty; skipping.", key_env_var)
                    continue

                # 2. Cooldown check
                is_cooling, remaining_sec = cm.is_cooling_down(p_name, key_env_var, model)
                if is_cooling:
                    cooldown_durations.append(remaining_sec)
                    logger.debug("Key %s for %s (%s) is cooling down (%.1fs remaining); skipping.", key_env_var, p_name, model, remaining_sec)
                    continue

                # 3. Pre-emptive check: Daily request quota (RPD) in SQLite
                if rpd is not None and rpd > 0:
                    usage = get_usage(p_name, key_env_var, date_str=today, model=model, db_path=db_path)
                    if usage >= rpd:
                        logger.info("Key %s on %s reached daily limit (%d/%d) for model %s; rotating.", key_env_var, p_name, usage, rpd, model)
                        continue

                # 4. Pre-emptive check: Daily token budget (TPD)
                if tpd is not None and tpd > 0:
                    if not cm.check_token_budget(p_name, key_env_var, model, estimated_req_tokens, tpd):
                        logger.info("Key %s on %s would exceed daily token budget (%d TPD) for model %s; rotating.", key_env_var, p_name, tpd, model)
                        continue

                # 5. RPM Pacing: Observe per-minute rate limit before sending
                cm.pace_request(p_name, key_env_var, model, rpm)

                # 6. Sliding-window TPM Pacing (Condition M1.2): Observe rolling 60s TPM limit
                cm.pace_tpm_window(p_name, key_env_var, model, estimated_req_tokens, tpm)

                # Attempt provider request
                try:
                    logger.debug("Attempting call to provider=%s model=%s key=%s (timeout=%ds)", p_name, model, key_env_var, actual_timeout)
                    response = send_request(
                        provider_name=p_name,
                        model=model,
                        api_key=api_key,
                        prompt=prompt,
                        timeout=actual_timeout,
                        system_prompt=system_prompt,
                        temperature=temperature,
                    )

                    # Successful request: reset circuit-breaker consecutive counter
                    cm.record_success(p_name, key_env_var, model)

                    # Record tokens and increment usage
                    tokens_used = (response.tokens_in or 0) + (response.tokens_out or 0)
                    if tokens_used > 0:
                        cm.record_token_usage(p_name, key_env_var, model, tokens_used)
                        increment_token_usage(p_name, key_env_var, tokens_used, model=model, date_str=today, db_path=db_path)

                    increment_usage(p_name, key_env_var, date_str=today, count=1, model=model, db_path=db_path)

                    log_llm_call(
                        provider=p_name,
                        model=model,
                        purpose=purpose,
                        tokens_in=response.tokens_in,
                        tokens_out=response.tokens_out,
                        agent_id=agent_id,
                        sim_day=sim_day,
                        condition=condition,
                        db_path=db_path,
                    )
                    return response if return_obj else response.text

                except RateLimitError as rle:
                    # Classify rate limit response with provider-specific logic
                    result = classify_429(
                        provider=p_name,
                        status=rle.status_code,
                        headers=rle.headers,
                        body=rle.body,
                    )
                    logger.warning(
                        "429 RateLimit on %s (%s, model=%s): kind=%s, retry_after=%s, reason=%s",
                        p_name, key_env_var, model, result.kind, result.retry_after, result.raw_reason
                    )

                    # Apply cooldown based on classified kind
                    cooldown_sec = cm.set_cooldown(
                        provider=p_name,
                        key_env=key_env_var,
                        model=model,
                        kind=result.kind,
                        retry_after=result.retry_after,
                        reason=result.raw_reason,
                    )
                    cooldown_durations.append(cooldown_sec)

                    # Handle daily quota lockout and ledger reconciliation
                    if result.kind == "daily_requests":
                        current_cnt = get_usage(p_name, key_env_var, date_str=today, model=model, db_path=db_path)
                        configured_limit = rpd or 1000
                        if current_cnt < (configured_limit * 0.7):
                            logger.warning(
                                "LEDGER RECONCILIATION: Provider %s key %s encountered daily 429 at usage count %d, "
                                "far below configured limit of %d! Recording observed limit.",
                                p_name, key_env_var, current_cnt, configured_limit
                            )
                            cm.record_observed_limit(p_name, key_env_var, model, current_cnt)

                        mark_key_exhausted(p_name, key_env_var, date_str=today, model=model, db_path=db_path)

                    # Pinned mode rotates to next key of pinned model, rather than immediately failing
                    continue

                except ProviderTimeoutError as pte:
                    logger.warning("Timeout (%ds) on provider %s (%s): %s. Setting 30s provider-level cooldown.", actual_timeout, p_name, key_env_var, pte)
                    p_cooldown = cm.set_provider_cooldown(p_name, duration=30.0, reason=str(pte))
                    cooldown_durations.append(p_cooldown)
                    continue

                except AuthOrBillingError as abe:
                    logger.warning("Auth/Billing error (HTTP %d) on %s (%s): %s. Disabling key for today.", abe.status_code, p_name, key_env_var, abe)
                    cooldown_sec = cm.set_cooldown(
                        provider=p_name,
                        key_env=key_env_var,
                        model=model,
                        kind="auth_billing_failure",
                        reason=str(abe),
                    )
                    cooldown_durations.append(cooldown_sec)
                    mark_key_exhausted(p_name, key_env_var, date_str=today, model=model, db_path=db_path)
                    continue

                except ProviderError as pe:
                    logger.warning("Provider error on %s (%s): %s. Falling through to next key/provider.", p_name, key_env_var, pe)
                    continue

                except Exception as ex:
                    logger.error("Unexpected error on %s (%s): %s. Falling through.", p_name, key_env_var, ex)
                    continue

        # If all keys are currently cooling down, check if the shortest wait is <= 90s
        if cooldown_durations:
            shortest_wait = min(cooldown_durations)
            if shortest_wait <= 90.0 and wait_attempt == 0:
                logger.info(
                    "All providers in cooldown, shortest wait is %.1fs (<= 90s). Waiting to retry...",
                    shortest_wait
                )
                time.sleep(shortest_wait + 0.5)
                continue
            else:
                earliest_time = datetime.fromtimestamp(time.time() + shortest_wait).isoformat()
                if active_pinned:
                    raise ModelPinnedError(
                        f"Pinned model '{active_pinned}' exhausted or cooling down across all keys. "
                        f"Earliest available key at {earliest_time} (in {int(shortest_wait)}s)."
                    )
                raise AllProvidersExhaustedError(
                    f"All configured LLM providers and keys are exhausted or cooling down. "
                    f"Earliest available key at {earliest_time} (in {int(shortest_wait)}s)."
                )

    if active_pinned:
        raise ModelPinnedError(f"Pinned model '{active_pinned}' failed across all configured keys.")
    raise AllProvidersExhaustedError("All configured LLM providers and keys have been exhausted or failed.")


# Alias for backward and forward compatibility with spec: llm_router.call(...)
call = call_llm
