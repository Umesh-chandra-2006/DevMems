"""
Vector store / embedding layer (Phase 5, P5.0b).

Provides a configurable embedding path with:
  * fail-loud mode: any embedding failure raises EmbeddingError and is counted; the deterministic
    768-dim fallback exists only for offline unit tests (`allow_fallback=True`);
  * a persistent on-disk cache keyed by (embedding model, sha256 of the normalised text);
  * per-run statistics (`embedding_stats.json`): HTTP requests, cache hits, failures, fallbacks;
  * single and batch requests against the Gemini embedding endpoints.

The Gemini key is sent in the `x-goog-api-key` header (never in the URL) so that exceptions and logs
cannot leak it. This module is NOT yet wired into upstream `get_embedding` (that is a `reverie/` edit
awaiting checkpoint approval).
"""

import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import requests
import yaml

_DEVMEM_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = _DEVMEM_DIR / "config" / "embeddings.yaml"
FALLBACK_DIM = 768
_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


class EmbeddingError(RuntimeError):
    """Raised on any embedding failure in fail-loud mode (and on real/fallback mixing)."""


def normalize_text(text: str) -> str:
    """Same normalisation as upstream get_embedding."""
    text = (text or "").replace("\n", " ").strip()
    return text if text else "this is blank"


def text_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def deterministic_fallback_vector(text: str) -> List[float]:
    """Offline-test-only vector (768-dim, unit length), identical to upstream's fallback."""
    seed = int(hashlib.md5(normalize_text(text).encode("utf-8")).hexdigest()[:8], 16)
    vec = np.random.RandomState(seed).randn(FALLBACK_DIM).astype(float)
    return (vec / np.linalg.norm(vec)).tolist()


def load_config(path: Path = CONFIG_PATH) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class EmbeddingStore:
    def __init__(
        self,
        model: Optional[str] = None,
        fail_loud: Optional[bool] = None,
        allow_fallback: bool = False,
        cache_path: Optional[Path] = None,
        stats_path: Optional[Path] = None,
        key_envs: Optional[Sequence[str]] = None,
        timeout: Optional[float] = None,
        post=requests.post,
    ):
        cfg = load_config()
        self.model = model or cfg["model"]
        self.fail_loud = cfg["fail_loud"] if fail_loud is None else fail_loud
        self.allow_fallback = allow_fallback
        self.key_envs = list(key_envs if key_envs is not None else cfg["key_envs"])
        self.timeout = timeout or cfg["timeout_seconds"]
        self.cache_path = Path(cache_path) if cache_path else _DEVMEM_DIR / cfg["cache_path"]
        self.stats_path = Path(stats_path) if stats_path else None
        self._post = post
        self._source: Optional[str] = None  # "real" or "fallback"; switching raises
        self._key_cursor = 0
        self.stats: Dict[str, Any] = {
            "model": self.model,
            "fail_loud": self.fail_loud,
            "http_requests": 0,
            "texts_requested": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "failures": 0,
            "fallbacks": 0,
            "http_status_counts": {},
            "requests_by_key_env": {},
            "dimensions_seen": [],
        }
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.cache_path))
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS embedding_cache ("
                "model TEXT NOT NULL, text_hash TEXT NOT NULL, dim INTEGER NOT NULL, vec BLOB NOT NULL, "
                "PRIMARY KEY (model, text_hash))"
            )
            conn.commit()
        finally:
            conn.close()

    # ---- cache -------------------------------------------------------------------------
    def _cache_get(self, hashes: List[str]) -> Dict[str, List[float]]:
        found: Dict[str, List[float]] = {}
        conn = sqlite3.connect(str(self.cache_path))
        try:
            for h in hashes:
                row = conn.execute(
                    "SELECT vec FROM embedding_cache WHERE model = ? AND text_hash = ?", (self.model, h)
                ).fetchone()
                if row:
                    found[h] = np.frombuffer(row[0], dtype=np.float32).astype(float).tolist()
        finally:
            conn.close()
        return found

    def _cache_put(self, h: str, vec: List[float]) -> None:
        conn = sqlite3.connect(str(self.cache_path))
        try:
            conn.execute(
                "INSERT OR IGNORE INTO embedding_cache (model, text_hash, dim, vec) VALUES (?, ?, ?, ?)",
                (self.model, h, len(vec), np.asarray(vec, dtype=np.float32).tobytes()),
            )
            conn.commit()
        finally:
            conn.close()

    # ---- http --------------------------------------------------------------------------
    def _next_key(self):
        keys = [(env, os.environ.get(env)) for env in self.key_envs]
        keys = [(e, v) for e, v in keys if v]
        if not keys:
            raise EmbeddingError(f"no embedding key set (looked for {self.key_envs})")
        env, val = keys[self._key_cursor % len(keys)]
        self._key_cursor += 1
        return env, val

    def _request(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        env, key = self._next_key()
        url = f"{_BASE_URL}/{self.model}:{endpoint}"
        self.stats["http_requests"] += 1
        self.stats["requests_by_key_env"][env] = self.stats["requests_by_key_env"].get(env, 0) + 1
        try:
            resp = self._post(
                url,
                headers={"Content-Type": "application/json", "x-goog-api-key": key},
                json=payload,
                timeout=self.timeout,
            )
        except Exception as exc:
            counts = self.stats["http_status_counts"]
            counts["exception"] = counts.get("exception", 0) + 1
            raise EmbeddingError(f"embedding request failed: {type(exc).__name__}") from None
        code = str(resp.status_code)
        counts = self.stats["http_status_counts"]
        counts[code] = counts.get(code, 0) + 1
        if resp.status_code != 200:
            raise EmbeddingError(f"embedding request returned HTTP {resp.status_code}")
        return resp.json()

    def _embed_real(self, texts: List[str], batch: bool) -> List[List[float]]:
        if batch:
            payload = {
                "requests": [
                    {"model": f"models/{self.model}", "content": {"parts": [{"text": t}]}} for t in texts
                ]
            }
            data = self._request("batchEmbedContents", payload)
            vecs = [e.get("values", []) for e in data.get("embeddings", [])]
        else:
            vecs = []
            for t in texts:
                data = self._request("embedContent", {"content": {"parts": [{"text": t}]}})
                vecs.append(data.get("embedding", {}).get("values", []))
        if len(vecs) != len(texts) or any(not v for v in vecs):
            raise EmbeddingError(f"embedding response incomplete: {len(vecs)} vectors for {len(texts)} texts")
        return vecs

    def _set_source(self, source: str) -> None:
        if self._source not in (None, source):
            raise EmbeddingError("refusing to mix real and fallback embeddings in one store")
        self._source = source

    # ---- public ------------------------------------------------------------------------
    def embed_texts(self, texts: Sequence[str], batch: bool = True) -> List[List[float]]:
        """Return raw (unnormalised) vectors in input order. Cache first; misses go to the provider
        in one batch request (batch=True) or one request per text. Duplicate texts are sent once."""
        norm = [normalize_text(t) for t in texts]
        hashes = [text_hash(t) for t in norm]
        self.stats["texts_requested"] += len(norm)
        cached = self._cache_get(sorted(set(hashes)))
        self.stats["cache_hits"] += sum(1 for h in hashes if h in cached)
        self.stats["cache_misses"] += sum(1 for h in hashes if h not in cached)
        misses: Dict[str, str] = {}
        for t, h in zip(norm, hashes):
            if h not in cached and h not in misses:
                misses[h] = t

        real_hit_hashes = set(cached.keys())  # vectors served from the on-disk (real) cache
        if misses:
            miss_hashes = list(misses.keys())
            vecs = None
            try:
                vecs = self._embed_real([misses[h] for h in miss_hashes], batch)
            except EmbeddingError:
                self.stats["failures"] += 1
                if self.fail_loud or not self.allow_fallback:
                    self.flush_stats()
                    raise
            if vecs is not None:
                self._set_source("real")
                for h, v in zip(miss_hashes, vecs):
                    cached[h] = v
                    self._cache_put(h, v)
                    if len(v) not in self.stats["dimensions_seen"]:
                        self.stats["dimensions_seen"].append(len(v))
            else:
                if real_hit_hashes & set(hashes):
                    self.flush_stats()
                    raise EmbeddingError("refusing to mix cached real embeddings with fallback vectors")
                self._set_source("fallback")
                self.stats["fallbacks"] += len(miss_hashes)
                for h in miss_hashes:  # fallback vectors are never cached
                    cached[h] = deterministic_fallback_vector(misses[h])
        elif self._source == "fallback" and real_hit_hashes & set(hashes):
            raise EmbeddingError("refusing to mix cached real embeddings with fallback vectors")
        self.flush_stats()
        return [cached[h] for h in hashes]

    def flush_stats(self) -> None:
        if self.stats_path:
            self.stats_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.stats_path, "w", encoding="utf-8") as f:
                json.dump(self.stats, f, indent=2)
