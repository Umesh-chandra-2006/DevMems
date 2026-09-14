"""
Providers Adapter: Concrete client implementations for external LLM providers
(Groq, Google Gemini, NVIDIA NIM/Nemotron).
Thin adapters handling HTTP requests, response parsing, and error mapping.
"""

from dataclasses import dataclass
import json
import requests


import time
from typing import Any, Dict, List, Optional


class RateLimitError(Exception):
    """Raised when a provider returns HTTP 429 or quota exhaustion."""
    pass


class ProviderError(Exception):
    """Raised on provider-side errors (5xx, bad request, network failure)."""
    pass


class AllProvidersExhaustedError(Exception):
    """Raised when all configured providers and keys fail or are exhausted."""
    pass


@dataclass
class ProviderResponse:
    text: str
    tokens_in: int
    tokens_out: int

    def __str__(self) -> str:
        return self.text


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

    for attempt in range(5):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        except Exception as e:
            raise ProviderError(f"Groq network error: {e}") from e

        if response.status_code == 429:
            err_text = response.text
            retry_sec = None
            if "retry-after" in response.headers:
                try:
                    retry_sec = float(response.headers["retry-after"])
                except Exception:
                    pass
            if retry_sec is None and "Please try again in " in err_text:
                try:
                    part = err_text.split("Please try again in ")[1].split("s")[0].strip()
                    retry_sec = float(part)
                except Exception:
                    pass

            if attempt < 4 and (retry_sec is not None or "tokens per minute" in err_text.lower() or "tpm" in err_text.lower() or "rate_limit_exceeded" in err_text.lower()):
                sleep_duration = (retry_sec + 1.0) if (retry_sec is not None and retry_sec <= 30) else 6.0
                time.sleep(sleep_duration)
                continue

            raise RateLimitError(f"Groq rate limit exceeded (429): {err_text}")
        break

    if response.status_code != 200:
        raise ProviderError(f"Groq returned HTTP {response.status_code}: {response.text}")

    try:
        data = response.json()
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        tokens_in = usage.get("prompt_tokens", 0)
        tokens_out = usage.get("completion_tokens", 0)
        return ProviderResponse(text=text, tokens_in=tokens_in, tokens_out=tokens_out)
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

    for attempt in range(4):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        except Exception as e:
            raise ProviderError(f"Gemini network error: {e}") from e

        if response.status_code == 429:
            if attempt < 3:
                time.sleep(5.0)
                continue
            raise RateLimitError(f"Gemini rate limit exceeded (429): {response.text}")
        break

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
    except Exception as e:
        raise ProviderError(f"Nemotron network error: {e}") from e

    if response.status_code == 429:
        raise RateLimitError(f"Nemotron rate limit exceeded (429): {response.text}")
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
