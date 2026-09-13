"""
Providers Adapter: Concrete client implementations for external LLM providers
(Groq, Google Gemini, NVIDIA NIM/Nemotron).
Thin adapters handling HTTP requests, response parsing, and error mapping.
"""

from dataclasses import dataclass
import json
import requests


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


def call_groq(prompt: str, model: str, api_key: str, timeout: int = 30) -> ProviderResponse:
    """Send prompt to Groq OpenAI-compatible API."""
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    except Exception as e:
        raise ProviderError(f"Groq network error: {e}") from e

    if response.status_code == 429:
        raise RateLimitError(f"Groq rate limit exceeded (429): {response.text}")
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


def call_gemini(prompt: str, model: str, api_key: str, timeout: int = 30) -> ProviderResponse:
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
            "temperature": 0.7
        }
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    except Exception as e:
        raise ProviderError(f"Gemini network error: {e}") from e

    if response.status_code == 429:
        raise RateLimitError(f"Gemini rate limit exceeded (429): {response.text}")
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


def call_nemotron(prompt: str, model: str, api_key: str, timeout: int = 30) -> ProviderResponse:
    """Send prompt to NVIDIA NIM (Nemotron) OpenAI-compatible API."""
    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7
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


def send_request(provider_name: str, model: str, api_key: str, prompt: str, timeout: int = 30) -> ProviderResponse:
    """Dispatch prompt request to the appropriate provider adapter."""
    adapter = PROVIDER_ADAPTERS.get(provider_name.lower())
    if not adapter:
        raise ProviderError(f"Unknown provider '{provider_name}'")
    return adapter(prompt=prompt, model=model, api_key=api_key, timeout=timeout)
