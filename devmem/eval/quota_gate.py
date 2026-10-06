"""
Quota pause for the long Phase 7 and 9 runs: when a daily quota is exhausted the process PAUSES until the provider's reset and then
resumes the SAME call; it does not crash and it never hands a call to another model (the router stays pinned; this module only waits
and retries the pinned call).

Cases (the router raises ModelPinnedError in all of them):
  * all arm keys at the per-key daily cap (450 requests, set as `rpd` in the arm's temporary provider config): the router finds no usable
    key and raises "failed across all configured keys" with no cooldown. The gate checks the ledger (quota day = DEVMEM_QUOTA_RESET_UTC_HOUR)
    and, if every key is at the cap, sleeps until the next reset hour (07:00 UTC = about 12:30 IST) plus a margin, then retries.
  * "exhausted or cooling down ... (in Ns)" with N above the router's own 90 s wait (a provider daily 429 lockout): sleep N seconds
    (at most one reset period) and retry.
  * any other pinned failure (for example a provider outage): retry after `generic_wait` seconds, at most `max_generic_retries` times, then
    re-raise (a real failure is not hidden).
Each pause is logged to quota_pauses.jsonl (start, reason, wake-up time). A file named ABORT in the run folder ends the wait with
`RunAborted`. `CapReached` (the call cap) is a BaseException and passes through untouched.
"""
import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable, Optional


class RunAborted(BaseException):
    """The operator created the ABORT file; the run stops at the next wait or step boundary."""


def next_reset(now: datetime, reset_hour: float = 7.0) -> datetime:
    base = now.replace(hour=int(reset_hour), minute=int((reset_hour % 1) * 60), second=0, microsecond=0)
    return base if base > now else base + timedelta(days=1)


class QuotaGate:
    def __init__(self, real_call: Callable[..., Any], keys: Iterable[str], model: str, cap: int, run_dir: Path, reset_hour: float = 7.0,
                 sleep: Callable[[float], None] = time.sleep, now: Callable[[], datetime] = datetime.utcnow,
                 usage: Optional[Callable[[str], int]] = None, generic_wait: float = 120.0, max_generic_retries: int = 20,
                 margin_seconds: float = 120.0, chunk_seconds: float = 30.0):
        self.real, self.keys, self.model, self.cap = real_call, list(keys), model, cap
        self.run_dir, self.reset_hour = Path(run_dir), reset_hour
        self.sleep, self.now, self.usage = sleep, now, usage
        self.generic_wait, self.max_generic, self.margin, self.chunk = generic_wait, max_generic_retries, margin_seconds, chunk_seconds
        self.pauses = 0

    # ---- helpers
    def _used(self, key: str) -> int:
        if self.usage is not None:
            return self.usage(key)
        from devmem.router import key_pool
        return key_pool.get_usage("gemini", key, model=self.model)

    def all_at_cap(self) -> bool:
        return bool(self.keys) and all(self._used(k) >= self.cap for k in self.keys)

    def _log(self, **rec) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        with open(self.run_dir / "quota_pauses.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"at": self.now().isoformat(), **rec}) + "\n")

    def wait(self, seconds: float, reason: str) -> None:
        wake = self.now() + timedelta(seconds=seconds)
        self.pauses += 1
        self._log(event="pause", reason=reason, seconds=round(seconds), wake=wake.isoformat())
        remaining = seconds
        while remaining > 0:
            if (self.run_dir / "ABORT").exists():
                self._log(event="abort", reason="ABORT file present during a pause")
                raise RunAborted("ABORT file present")
            step = min(self.chunk, remaining)
            self.sleep(step)
            remaining -= step
        self._log(event="resume", reason=reason)

    # ---- the wrapped call
    def __call__(self, *args, **kwargs):
        from devmem.router.providers import ModelPinnedError
        generic = 0
        while True:
            if (self.run_dir / "ABORT").exists():
                raise RunAborted("ABORT file present")
            try:
                return self.real(*args, **kwargs)
            except ModelPinnedError as exc:
                msg = str(exc)
                m = re.search(r"\(in (\d+)s\)", msg)
                if self.all_at_cap():
                    seconds = (next_reset(self.now(), self.reset_hour) - self.now()).total_seconds() + self.margin
                    self.wait(seconds, f"all {len(self.keys)} keys at the per-key daily cap {self.cap}")
                elif m and "exhausted or cooling down" in msg and int(m.group(1)) > 90:
                    self.wait(min(int(m.group(1)) + 5, 86400), "pinned model locked out by the provider (daily limit)")
                else:
                    generic += 1
                    if generic > self.max_generic:
                        raise
                    self.wait(self.generic_wait, f"pinned call failed (attempt {generic} of {self.max_generic}): {msg[:120]}")

    # ---- embeddings: the store raises EmbeddingError when all keys fail
    def wrap_embedding_store(self, store: Any, embed_keys: Iterable[str], rpd: int) -> None:
        from devmem.embeddings.vector_store import EmbeddingError
        real = store.embed_texts
        keys = list(embed_keys)

        def embed_texts(texts, batch=True):
            tries = 0
            while True:
                try:
                    return real(texts, batch=batch)
                except EmbeddingError as exc:
                    tries += 1
                    from devmem.router import key_pool
                    at_cap = all(key_pool.get_usage("gemini", k, model=store.model) >= rpd for k in keys) if keys else False
                    if at_cap:
                        seconds = (next_reset(self.now(), self.reset_hour) - self.now()).total_seconds() + self.margin
                        self.wait(seconds, "all embedding keys at the daily limit")
                    elif tries > self.max_generic:
                        raise
                    else:
                        self.wait(self.generic_wait, f"embedding failed (attempt {tries}): {str(exc)[:100]}")
        store.embed_texts = embed_texts
