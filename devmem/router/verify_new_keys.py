"""Minimal key verification: one call per (key, endpoint), prints and saves ONLY key NAME and HTTP status.
LLM: max_tokens 5. Embeddings: one embedContent call. Keys are sent in headers, never printed or saved."""
import json, os, sys
from pathlib import Path
import requests
ROOT = Path(__file__).resolve().parent.parent.parent
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")
checks = []
def post(name, kind, url, headers, body):
    key_status = None
    try:
        r = requests.post(url, headers=headers, json=body, timeout=45)
        key_status = r.status_code
    except Exception as e:
        key_status = type(e).__name__
    checks.append({"key": name, "call": kind, "status": key_status})
    print(name, kind, key_status)
for name in sys.argv[1:]:
    k = os.environ.get(name)
    if not k:
        checks.append({"key": name, "call": "none", "status": "env var not set"}); print(name, "not set"); continue
    if name.startswith("GROQ"):
        post(name, "llm max_tokens=5 openai/gpt-oss-20b", "https://api.groq.com/openai/v1/chat/completions",
             {"Authorization": f"Bearer {k}"}, {"model": "openai/gpt-oss-20b", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 5})
    elif name.startswith("NIM"):
        post(name, "llm max_tokens=5 nemotron", "https://integrate.api.nvidia.com/v1/chat/completions",
             {"Authorization": f"Bearer {k}"}, {"model": "nvidia/nemotron-3.5-lightning-30b-a3b", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 5})
    elif name.startswith("GEMINI"):
        post(name, "llm maxOutputTokens=5 gemini-3.1-flash-lite",
             "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent",
             {"x-goog-api-key": k}, {"contents": [{"parts": [{"text": "hi"}]}], "generationConfig": {"maxOutputTokens": 5}})
        post(name, "embed gemini-embedding-001",
             "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent",
             {"x-goog-api-key": k}, {"content": {"parts": [{"text": "key verification"}]}})
out = ROOT / "docs/phase5_step2_artifacts/key_verification.json"
prev = json.loads(out.read_text()) if out.exists() else []
out.write_text(json.dumps(prev + checks, indent=1))
