"""
Providers Adapter: Concrete client implementations for external LLM providers
(Groq, Google Gemini, NVIDIA NIM/Nemotron).
Thin adapters handling HTTP requests, response parsing, and error mapping.
Includes passive 429 capture for runtime rate-limit telemetry.
"""

from dataclasses import dataclass
import json
import logging
import os
import requests
import time
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger("devmem.router.providers")


class ProviderError(Exception):
    """Base class for all provider-side errors."""
    pass


class RateLimitError(ProviderError):
    """Raised when a provider returns HTTP 429 or quota exhaustion."""
    def __init__(
        self,
        message: str,
        status_code: int = 429,
        headers: Optional[Dict[str, Any]] = None,
        body: Optional[Union[str, Dict[str, Any]]] = None,
        provider: str = ""
    ):
        super().__init__(message)
        self.status_code = status_code
        self.headers = dict(headers) if headers else {}
        self.body = body if body is not None else message
        self.provider = provider


class AuthOrBillingError(ProviderError):
    """Raised on HTTP 401, 402, 403 auth or billing failure."""
    def __init__(
        self,
        message: str,
        status_code: int = 401,
        headers: Optional[Dict[str, Any]] = None,
        body: Optional[Union[str, Dict[str, Any]]] = None,
        provider: str = ""
    ):
        super().__init__(message)
        self.status_code = status_code
        self.headers = dict(headers) if headers else {}
        self.body = body if body is not None else message
        self.provider = provider


class AllProvidersExhaustedError(Exception):
    """Raised when all configured providers and keys fail or are exhausted."""
    pass


class ModelPinnedError(ProviderError):
    """Raised when a pinned model fails or rate-limits and fallback is prohibited."""
    pass


class ProviderNetworkError(ProviderError):
    """Raised when the request could not reach the provider (DNS failure, refused or reset connection, no route). Not an HTTP answer."""
    pass


class ProviderTimeoutError(ProviderError):
    """Raised when a provider request times out."""
    def __init__(self, message: str, provider: str = "", timeout: Optional[int] = None):
        super().__init__(message)
        self.provider = provider
        self.timeout = timeout


@dataclass
class ProviderResponse:
    text: str
    tokens_in: int
    tokens_out: int
    reasoning_tokens: Optional[int] = None

    def __str__(self) -> str:
        return self.text


def record_observed_429(provider: str, status_code: int, headers: Any, body_text: str) -> None:
    """Passively record any observed 429 response to observed.jsonl in redacted form."""
    try:
        from devmem.router.capture_429 import append_observed_429
        append_observed_429(provider, status_code, dict(headers), str(body_text))
    except Exception:
        pass


def call_groq(
    prompt: str,
    model: str,
    api_key: str,
    timeout: int = 30,
    system_prompt: Optional[str] = None,
    temperature: Optional[float] = None,
) -> ProviderResponse:
    """Send prompt to Groq OpenAI-compatible API."""
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature if temperature is not None else 0.1
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    except requests.exceptions.Timeout as te:
        raise ProviderTimeoutError(f"Groq request timed out after {timeout}s: {te}", provider="groq", timeout=timeout) from te
    except Exception as e:
        raise ProviderNetworkError(f"Groq network error: {e}") from e

    if response.status_code in [401, 402, 403]:
        raise AuthOrBillingError(
            f"Groq auth/billing error (HTTP {response.status_code}): {response.text}",
            status_code=response.status_code,
            headers=dict(response.headers),
            body=response.text,
            provider="groq"
        )

    if response.status_code == 429:
        record_observed_429("groq", response.status_code, response.headers, response.text)
        raise RateLimitError(
            f"Groq rate limit exceeded (429): {response.text}",
            status_code=429,
            headers=dict(response.headers),
            body=response.text,
            provider="groq"
        )

    if response.status_code != 200:
        raise ProviderError(f"Groq returned HTTP {response.status_code}: {response.text}")

    try:
        data = response.json()
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        tokens_in = usage.get("prompt_tokens", 0)
        tokens_out = usage.get("completion_tokens", 0)
        reasoning_tokens = usage.get("completion_tokens_details", {}).get("reasoning_tokens")
        return ProviderResponse(text=text, tokens_in=tokens_in, tokens_out=tokens_out, reasoning_tokens=reasoning_tokens)
    except Exception as e:
        raise ProviderError(f"Failed to parse Groq response: {e}") from e


def call_gemini(
    prompt: str,
    model: str,
    api_key: str,
    timeout: int = 30,
    system_prompt: Optional[str] = None,
    temperature: Optional[float] = None,
) -> ProviderResponse:
    """Send prompt to Google Gemini API (generateContent)."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    headers = {
        "Content-Type": "application/json"
    }
    payload = {
        "contents": [
            {
                "parts": [{"text": prompt}]
            }
        ],
        "generationConfig": {
            "temperature": temperature if temperature is not None else 0.1
        }
    }
    if system_prompt:
        payload["system_instruction"] = {
            "parts": [{"text": system_prompt}]
        }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    except requests.exceptions.Timeout as te:
        raise ProviderTimeoutError(f"Gemini request timed out after {timeout}s: {te}", provider="gemini", timeout=timeout) from te
    except Exception as e:
        raise ProviderNetworkError(f"Gemini network error: {e}") from e

    if response.status_code in [401, 402, 403]:
        raise AuthOrBillingError(
            f"Gemini auth/billing error (HTTP {response.status_code}): {response.text}",
            status_code=response.status_code,
            headers=dict(response.headers),
            body=response.text,
            provider="gemini"
        )

    if response.status_code == 429:
        record_observed_429("gemini", response.status_code, response.headers, response.text)
        raise RateLimitError(
            f"Gemini rate limit exceeded (429): {response.text}",
            status_code=429,
            headers=dict(response.headers),
            body=response.text,
            provider="gemini"
        )

    if response.status_code != 200:
        raise ProviderError(f"Gemini returned HTTP {response.status_code}: {response.text}")

    try:
        data = response.json()
        candidates = data.get("candidates", [])
        if not candidates:
            raise ProviderError(f"Gemini response has no candidates: {data}")
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(part.get("text", "") for part in parts)
        usage = data.get("usageMetadata", {})
        tokens_in = usage.get("promptTokenCount", 0)
        tokens_out = usage.get("candidatesTokenCount", 0)
        return ProviderResponse(text=text, tokens_in=tokens_in, tokens_out=tokens_out)
    except Exception as e:
        raise ProviderError(f"Failed to parse Gemini response: {e}") from e


def call_nemotron(
    prompt: str,
    model: str,
    api_key: str,
    timeout: int = 30,
    system_prompt: Optional[str] = None,
    temperature: Optional[float] = None,
) -> ProviderResponse:
    """Send prompt to NVIDIA NIM (Nemotron) OpenAI-compatible API."""
    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature if temperature is not None else 0.1
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    except requests.exceptions.Timeout as te:
        raise ProviderTimeoutError(f"Nemotron request timed out after {timeout}s: {te}", provider="nemotron", timeout=timeout) from te
    except Exception as e:
        raise ProviderNetworkError(f"Nemotron network error: {e}") from e

    if response.status_code in [401, 402, 403]:
        raise AuthOrBillingError(
            f"Nemotron auth/billing error (HTTP {response.status_code}): {response.text}",
            status_code=response.status_code,
            headers=dict(response.headers),
            body=response.text,
            provider="nemotron"
        )

    if response.status_code == 429:
        record_observed_429("nemotron", response.status_code, response.headers, response.text)
        raise RateLimitError(
            f"Nemotron rate limit exceeded (429): {response.text}",
            status_code=429,
            headers=dict(response.headers),
            body=response.text,
            provider="nemotron"
        )

    if response.status_code != 200:
        raise ProviderError(f"Nemotron returned HTTP {response.status_code}: {response.text}")

    try:
        data = response.json()
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        tokens_in = usage.get("prompt_tokens", 0)
        tokens_out = usage.get("completion_tokens", 0)
        return ProviderResponse(text=text, tokens_in=tokens_in, tokens_out=tokens_out)
    except Exception as e:
        raise ProviderError(f"Failed to parse Nemotron response: {e}") from e


PROVIDER_ADAPTERS = {
    "groq": call_groq,
    "gemini": call_gemini,
    "nemotron": call_nemotron,
}


def send_request(
    provider_name: str,
    model: str,
    api_key: str,
    prompt: str,
    timeout: int = 30,
    system_prompt: Optional[str] = None,
    temperature: Optional[float] = None,
) -> ProviderResponse:
    """Dispatch prompt request to the appropriate provider adapter."""
    adapter = PROVIDER_ADAPTERS.get(provider_name.lower())
    if not adapter:
        raise ProviderError(f"Unknown provider '{provider_name}'")
    return adapter(
        prompt=prompt,
        model=model,
        api_key=api_key,
        timeout=timeout,
        system_prompt=system_prompt,
        temperature=temperature,
    )
