"""
LLM Router: Provider selection, multi-key rotation, and fallback logic across free-tier LLM providers.
Enforces pre-emptive rate limits, logs calls to SQLite, and automatically fails over upon 429 rate limits.
"""

from datetime import date
import logging
import os
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional, Union
import uuid
import yaml

from devmem.router.key_pool import (
    DEFAULT_DB_PATH,
    get_db_connection,
    get_today_str,
    get_usage,
    increment_usage,
    is_key_available,
    mark_key_exhausted,
)
from devmem.router.providers import (
    AllProvidersExhaustedError,
    ProviderError,
    ProviderResponse,
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
) -> Union[str, ProviderResponse]:
    """
    Route an LLM call across configured providers and keys.

    - Iterates providers by priority.
    - Iterates keys within a provider.
    - Pre-emptively checks daily limit before calling.
    - On RateLimitError (429), marks key exhausted and rotates to next key/provider.
    - On ProviderError, falls through to next key/provider.
    - On success, increments key usage, logs to llm_call_log, and returns response.
    """
    providers = load_providers_config(config_path)
    today = get_today_str()

    for provider in providers:
        p_name = provider.get("name", "").lower()
        models = provider.get("models", {})
        model = models.get(tier)
        if not model:
            logger.warning("Provider %s does not define a model for tier %s; skipping.", p_name, tier)
            continue

        limit_key = f"daily_limit_{tier}"
        daily_limit = provider.get(limit_key, 1000)
        keys = provider.get("keys", [])

        for key_entry in keys:
            key_env_var = key_entry.get("env")
            if not key_env_var:
                continue

            api_key = os.environ.get(key_env_var)
            if not api_key or not api_key.strip():
                logger.debug("Environment variable %s is empty; skipping.", key_env_var)
                continue

            # Pre-emptive check: local usage vs daily limit
            usage = get_usage(p_name, key_env_var, date_str=today, db_path=db_path)
            if usage >= daily_limit:
                logger.info("Key %s for provider %s reached daily limit (%d/%d); rotating.", key_env_var, p_name, usage, daily_limit)
                continue

            # Attempt provider request
            try:
                logger.debug("Attempting call to provider=%s model=%s key=%s", p_name, model, key_env_var)
                response = send_request(provider_name=p_name, model=model, api_key=api_key, prompt=prompt)

                # Successful request: update usage and call ledger
                increment_usage(p_name, key_env_var, date_str=today, count=1, db_path=db_path)
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
                logger.warning("Rate limit hit on %s (%s): %s. Marking exhausted and rotating.", p_name, key_env_var, rle)
                mark_key_exhausted(p_name, key_env_var, date_str=today, db_path=db_path)
                continue

            except ProviderError as pe:
                logger.warning("Provider error on %s (%s): %s. Falling through to next key/provider.", p_name, key_env_var, pe)
                continue

            except Exception as ex:
                logger.error("Unexpected error on %s (%s): %s. Falling through.", p_name, key_env_var, ex)
                continue

    raise AllProvidersExhaustedError("All configured LLM providers and keys have been exhausted or failed.")


# Alias for backward and forward compatibility with spec: llm_router.call(...)
call = call_llm
