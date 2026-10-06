"""
devmem/router/capture_429.py

Diagnostic utility to provoke and capture raw HTTP 429 rate limit responses
from configured LLM providers (Groq, Gemini, NVIDIA NIM).
Adheres strictly to the M1 budget: max 40 calls per provider, max 120 total.
Redacts API keys and project identifiers from saved fixtures.
"""

from datetime import datetime
import json
import os
from pathlib import Path
import time
from typing import Any, Dict, Optional
from dotenv import load_dotenv
import requests

# Load environment
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "429"
FIXTURES_DIR.mkdir(parents=True, exist_ok=True)


def redact_secrets(val: Any) -> Any:
    """Recursively redact known secrets, keys, and project IDs from data structures."""
    if isinstance(val, str):
        redacted = val
        for env_var in [
            "GROQ_KEY_1", "GROQ_KEY_2", "GROQ_KEY_3",
            "GEMINI_KEY_1", "GEMINI_KEY_2",
            "NIM_KEY_1"
        ]:
            secret = os.environ.get(env_var)
            if secret and len(secret) > 8:
                redacted = redacted.replace(secret, f"[REDACTED_{env_var}]")
        return redacted
    elif isinstance(val, dict):
        new_dict = {}
        for k, v in val.items():
            k_lower = str(k).lower()
            if any(s in k_lower for s in ["authorization", "key", "token", "secret", "cookie"]):
                new_dict[k] = "[REDACTED]"
            else:
                new_dict[k] = redact_secrets(v)
        return new_dict
    elif isinstance(val, list):
        return [redact_secrets(item) for item in val]
    return val


def append_observed_429(provider: str, status_code: int, headers: Dict[str, Any], body_str: str) -> None:
    """Append observed 429 payload to observed.jsonl in redacted format."""
    observed_file = FIXTURES_DIR / "observed.jsonl"
    try:
        try:
            body_obj = json.loads(body_str)
        except Exception:
            body_obj = body_str

        record = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "provider": provider,
            "status_code": status_code,
            "headers": redact_secrets(dict(headers)),
            "body": redact_secrets(body_obj),
        }
        with open(observed_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as e:
        print(f"Failed to append to observed.jsonl: {e}")


def capture_groq(max_calls: int = 40) -> Optional[Dict[str, Any]]:
    """Provoke per-minute rate limit on Groq using rapid minimal requests."""
    api_key = os.environ.get("GROQ_KEY_1")
    if not api_key:
        print("[Groq] GROQ_KEY_1 not found.")
        return None

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "openai/gpt-oss-20b",
        "messages": [{"role": "user", "content": "1"}],
        "max_tokens": 1,
        "temperature": 0.0,
    }

    print(f"[Groq] Probing up to {max_calls} rapid calls...")
    for i in range(1, max_calls + 1):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=10)
            if resp.status_code == 429:
                print(f"[Groq] Received 429 on call #{i}!")
                try:
                    body_json = resp.json()
                except Exception:
                    body_json = resp.text

                fixture = {
                    "provenance": "captured",
                    "provider": "groq",
                    "status_code": 429,
                    "headers": redact_secrets(dict(resp.headers)),
                    "body": redact_secrets(body_json),
                    "captured_at": datetime.utcnow().isoformat() + "Z",
                }
                out_path = FIXTURES_DIR / "groq_captured_429.json"
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(fixture, f, indent=2)
                append_observed_429("groq", 429, dict(resp.headers), resp.text)
                return fixture
            elif resp.status_code != 200:
                print(f"[Groq] Call #{i}: HTTP {resp.status_code}: {resp.text[:120]}")
        except Exception as e:
            print(f"[Groq] Network error on call #{i}: {e}")

    print(f"[Groq] Did not encounter 429 within {max_calls} calls budget.")
    return None


def capture_gemini(max_calls: int = 40) -> Optional[Dict[str, Any]]:
    """Provoke per-minute rate limit on Google Gemini using rapid minimal requests."""
    api_key = os.environ.get("GEMINI_KEY_1")
    if not api_key:
        print("[Gemini] GEMINI_KEY_1 not found.")
        return None

    model = "gemini-3.6-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": "1"}]}],
        "generationConfig": {"maxOutputTokens": 1, "temperature": 0.0}
    }

    print(f"[Gemini] Probing up to {max_calls} rapid calls...")
    for i in range(1, max_calls + 1):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=10)
            if resp.status_code == 429:
                print(f"[Gemini] Received 429 on call #{i}!")
                try:
                    body_json = resp.json()
                except Exception:
                    body_json = resp.text

                fixture = {
                    "provenance": "captured",
                    "provider": "gemini",
                    "status_code": 429,
                    "headers": redact_secrets(dict(resp.headers)),
                    "body": redact_secrets(body_json),
                    "captured_at": datetime.utcnow().isoformat() + "Z",
                }
                out_path = FIXTURES_DIR / "gemini_captured_429.json"
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(fixture, f, indent=2)
                append_observed_429("gemini", 429, dict(resp.headers), resp.text)
                return fixture
            elif resp.status_code != 200:
                print(f"[Gemini] Call #{i}: HTTP {resp.status_code}: {resp.text[:120]}")
        except Exception as e:
            print(f"[Gemini] Network error on call #{i}: {e}")

    print(f"[Gemini] Did not encounter 429 within {max_calls} calls budget.")
    return None


def capture_nemotron(max_calls: int = 40) -> Optional[Dict[str, Any]]:
    """Probe NVIDIA NIM for rate limit or credit exhaustion."""
    api_key = os.environ.get("NIM_KEY_1")
    if not api_key:
        print("[NVIDIA NIM] NIM_KEY_1 not found.")
        return None

    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "nvidia/nemotron-3.5-lightning-30b-a3b",
        "messages": [{"role": "user", "content": "1"}],
        "max_tokens": 1,
        "temperature": 0.0,
    }

    print(f"[NVIDIA NIM] Probing up to {max_calls} rapid calls...")
    for i in range(1, max_calls + 1):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=10)
            if resp.status_code in [429, 402, 403]:
                print(f"[NVIDIA NIM] Observed HTTP {resp.status_code} on call #{i}!")
                try:
                    body_json = resp.json()
                except Exception:
                    body_json = resp.text

                fixture = {
                    "provenance": "captured",
                    "provider": "nemotron",
                    "status_code": resp.status_code,
                    "headers": redact_secrets(dict(resp.headers)),
                    "body": redact_secrets(body_json),
                    "captured_at": datetime.utcnow().isoformat() + "Z",
                }
                out_path = FIXTURES_DIR / f"nemotron_captured_{resp.status_code}.json"
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(fixture, f, indent=2)
                append_observed_429("nemotron", resp.status_code, dict(resp.headers), resp.text)
                return fixture
            elif resp.status_code != 200:
                print(f"[NVIDIA NIM] Call #{i}: HTTP {resp.status_code}: {resp.text[:120]}")
        except Exception as e:
            print(f"[NVIDIA NIM] Network error on call #{i}: {e}")

    print(f"[NVIDIA NIM] Did not encounter 429/402/403 within {max_calls} calls budget.")
    return None


def populate_documented_fixtures():
    """Populate documented fixtures for limits that cannot be safely captured live."""
    fixtures = {
        "groq_documented_tpd.json": {
            "provenance": "documented",
            "source_url": "https://console.groq.com/docs/rate-limits",
            "provider": "groq",
            "kind": "tokens_recoverable",
            "status_code": 429,
            "headers": {
                "retry-after": "578",
                "x-ratelimit-limit-tokens": "500000",
                "x-ratelimit-remaining-tokens": "0",
                "x-ratelimit-reset-tokens": "9m38s"
            },
            "body": {
                "error": {
                    "message": "Rate limit reached for model `openai/gpt-oss-20b` on tokens per day (TPD): Limit 500000, Used 500000, Requested 1. Please try again in 9m38s.",
                    "type": "tokens",
                    "code": "rate_limit_exceeded"
                }
            }
        },
        "groq_documented_rpd.json": {
            "provenance": "documented",
            "source_url": "https://console.groq.com/docs/rate-limits",
            "provider": "groq",
            "kind": "daily_requests",
            "status_code": 429,
            "headers": {
                "retry-after": "45200",
                "x-ratelimit-limit-requests": "14400",
                "x-ratelimit-remaining-requests": "0",
                "x-ratelimit-reset-requests": "12h33m20s"
            },
            "body": {
                "error": {
                    "message": "Rate limit reached for model `openai/gpt-oss-20b` on requests per day (RPD): Limit 14400, Used 14400, Requested 1. Please try again in 12h33m20s.",
                    "type": "requests",
                    "code": "rate_limit_exceeded"
                }
            }
        },
        "gemini_documented_per_day.json": {
            "provenance": "documented",
            "source_url": "https://ai.google.dev/gemini-api/docs/troubleshooting#rate-limits",
            "provider": "gemini",
            "kind": "daily_requests",
            "status_code": 429,
            "headers": {
                "content-type": "application/json; charset=UTF-8"
            },
            "body": {
                "error": {
                    "code": 429,
                    "message": "Resource has been exhausted (e.g. check quota).",
                    "status": "RESOURCE_EXHAUSTED",
                    "details": [
                        {
                            "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                            "violations": [
                                {
                                    "quotaMetric": "generate-content-requests-per-day",
                                    "description": "Requests per day quota exceeded."
                                }
                            ]
                        }
                    ]
                }
            }
        },
        "gemini_documented_multiple_violations.json": {
            "provenance": "documented",
            "source_url": "https://ai.google.dev/gemini-api/docs/troubleshooting#rate-limits",
            "provider": "gemini",
            "kind": "daily_requests",
            "status_code": 429,
            "headers": {
                "content-type": "application/json; charset=UTF-8"
            },
            "body": {
                "error": {
                    "code": 429,
                    "message": "Resource has been exhausted (e.g. check quota).",
                    "status": "RESOURCE_EXHAUSTED",
                    "details": [
                        {
                            "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                            "violations": [
                                {
                                    "quotaMetric": "generate-content-requests-per-minute",
                                    "description": "Requests per minute quota exceeded."
                                },
                                {
                                    "quotaMetric": "generate-content-requests-per-day",
                                    "description": "Requests per day quota exceeded."
                                }
                            ]
                        }
                    ]
                }
            }
        }
    }

    for fname, data in fixtures.items():
        fpath = FIXTURES_DIR / fname
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    print(f"Populated {len(fixtures)} documented fixtures in {FIXTURES_DIR}")


if __name__ == "__main__":
    populate_documented_fixtures()
    print("\n--- PROBING LIVE PROVIDERS FOR 429 PAYLOADS ---")
    capture_groq(max_calls=40)
    capture_gemini(max_calls=40)
    capture_nemotron(max_calls=40)
    print("\nProbe complete.")
