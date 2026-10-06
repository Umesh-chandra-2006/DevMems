"""
Test-mode switch (import for its side effect at the top of a test module).

Default: offline. Embeddings come from the deterministic vectors, no network is used, so tests are
reproducible and cost nothing. DEVMEM_LIVE_TESTS=1 runs the same tests against the real embedding
endpoint (fail-loud, persistent cache) and enables the tests marked live.
"""
import os

LIVE = os.environ.get("DEVMEM_LIVE_TESTS") == "1"
os.environ["DEVMEM_EMBEDDING_MODE"] = "live" if LIVE else "offline"
