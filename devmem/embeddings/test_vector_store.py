"""
Offline tests for devmem.embeddings.vector_store (P5.0b). The HTTP layer is an injected fake
(`synthetic` responses, shaped like the documented Gemini embedContent / batchEmbedContents bodies);
the real endpoint is exercised separately by live_embedding_probe.py (label: live).
"""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from devmem.router.cooldown import CooldownManager
from devmem.embeddings.vector_store import (
    EmbeddingError,
    EmbeddingStore,
    FALLBACK_DIM,
    deterministic_fallback_vector,
    text_hash,
)

DIM = 8


class FakeResp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body or {}

    def json(self):
        return self._body


class FakePost:
    """Records calls; answers embedContent / batchEmbedContents with deterministic synthetic vectors."""

    def __init__(self, status=200, raise_exc=None):
        self.calls = []
        self.status = status
        self.raise_exc = raise_exc

    @staticmethod
    def _vec(text):
        base = float(len(text))
        return [base + i for i in range(DIM)]

    def __call__(self, url, headers=None, json=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "json": json})
        if self.raise_exc:
            raise self.raise_exc
        if self.status != 200:
            return FakeResp(self.status, {"error": {"message": "secret-bearing text would be here"}})
        if url.endswith(":batchEmbedContents"):
            texts = [r["content"]["parts"][0]["text"] for r in json["requests"]]
            return FakeResp(200, {"embeddings": [{"values": self._vec(t)} for t in texts]})
        text = json["content"]["parts"][0]["text"]
        return FakeResp(200, {"embedding": {"values": self._vec(text)}})


class TestEmbeddingStore(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="p5_0b_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.cache = self.tmp / "cache.db"
        env = mock.patch.dict(os.environ, {"TEST_EMB_KEY_1": "KEY-ONE-SECRET", "TEST_EMB_KEY_2": "KEY-TWO-SECRET"})
        env.start()
        self.addCleanup(env.stop)

    def store(self, post, **kw):
        kw.setdefault("key_envs", ["TEST_EMB_KEY_1", "TEST_EMB_KEY_2"])
        kw.setdefault("cache_path", self.cache)
        kw.setdefault("db_path", str(self.tmp / "ledger.db"))
        kw.setdefault("cooldown_mgr", CooldownManager(state_file=self.tmp / f"cd_{id(post)}.json"))
        return EmbeddingStore(model="test-model", post=post, **kw)

    def test_batch_is_one_http_request_and_single_is_one_per_text(self):
        post = FakePost()
        s = self.store(post)
        out = s.embed_texts(["a", "bb", "ccc"], batch=True)
        self.assertEqual(len(post.calls), 1)
        self.assertTrue(post.calls[0]["url"].endswith(":batchEmbedContents"))
        self.assertEqual([v[0] for v in out], [1.0, 2.0, 3.0])
        post2 = FakePost()
        s2 = self.store(post2, cache_path=self.tmp / "other.db")
        s2.embed_texts(["a", "bb", "ccc"], batch=False)
        self.assertEqual(len(post2.calls), 3)

    def test_persistent_cache_across_instances_and_stats(self):
        post = FakePost()
        stats_file = self.tmp / "run" / "embedding_stats.json"
        s = self.store(post, stats_path=stats_file)
        s.embed_texts(["hello world", "second text"])
        self.assertEqual(len(post.calls), 1)
        post_b = FakePost()
        s_b = self.store(post_b, stats_path=stats_file)
        out = s_b.embed_texts(["hello world", "second text", "hello world"])
        self.assertEqual(len(post_b.calls), 0, "all served from the on-disk cache")
        self.assertEqual(len(out), 3)
        stats = json.loads(stats_file.read_text())
        self.assertEqual(stats["cache_hits"], 3)
        self.assertEqual(stats["http_requests"], 0)
        self.assertEqual(stats["failures"], 0)
        self.assertEqual(stats["fallbacks"], 0)

    def test_duplicates_sent_once_and_cache_keyed_by_model(self):
        post = FakePost()
        s = self.store(post)
        s.embed_texts(["same", "same", "same"])
        self.assertEqual(len(post.calls[0]["json"]["requests"]), 1)
        post_m = FakePost()
        other_model = EmbeddingStore(
            model="another-model", post=post_m, cache_path=self.cache, key_envs=["TEST_EMB_KEY_1"],
            db_path=str(self.tmp / "ledger.db"), cooldown_mgr=CooldownManager(state_file=self.tmp / "cd_m.json"))
        other_model.embed_texts(["same"])
        self.assertEqual(len(post_m.calls), 1, "same text, different model: cache miss")

    def test_text_normalisation_matches_upstream(self):
        self.assertEqual(text_hash("a\nb "), text_hash("a b"))
        self.assertEqual(text_hash(""), text_hash("this is blank"))

    def test_fail_loud_raises_counts_and_never_falls_back(self):
        for post in (FakePost(status=429), FakePost(status=500), FakePost(raise_exc=TimeoutError("t"))):
            with self.subTest(post=type(post).__name__, status=post.status):
                stats_file = self.tmp / f"stats_{post.status}.json"
                s = self.store(post, stats_path=stats_file, cache_path=self.tmp / f"c_{post.status}_{id(post)}.db")
                with self.assertRaises(EmbeddingError):
                    s.embed_texts(["x"])
                self.assertEqual(s.stats["failures"], 1)
                self.assertEqual(s.stats["fallbacks"], 0)
                self.assertEqual(json.loads(stats_file.read_text())["failures"], 1)

    def test_fallback_only_when_allowed_is_counted_and_not_cached_and_never_mixed(self):
        s = self.store(FakePost(status=500), fail_loud=False, allow_fallback=True)
        out = s.embed_texts(["offline text"])
        self.assertEqual(len(out[0]), FALLBACK_DIM)
        self.assertEqual(out[0], deterministic_fallback_vector("offline text"))
        self.assertEqual(s.stats["fallbacks"], 1)
        self.assertEqual(s._cache_get([text_hash("offline text")]), {}, "fallback vectors are never cached")
        # fail_loud=False without allow_fallback still raises
        s_strict = self.store(FakePost(status=500), fail_loud=False, allow_fallback=False,
                              cache_path=self.tmp / "strict.db")
        with self.assertRaises(EmbeddingError):
            s_strict.embed_texts(["x"])
        # a store that produced fallback vectors refuses to later return real ones
        s._post = FakePost()
        s.cooldown.reset_for_test()  # keys were put on cooldown by the failures above
        with self.assertRaises(EmbeddingError):
            s.embed_texts(["a brand new text"])

    def test_never_mixes_cached_real_vectors_with_fallback_in_one_call(self):
        self.store(FakePost()).embed_texts(["cached real"])  # real vector now on disk
        s = self.store(FakePost(status=500), fail_loud=False, allow_fallback=True)
        with self.assertRaises(EmbeddingError):
            s.embed_texts(["cached real", "needs provider"])
        self.assertEqual(s.stats["fallbacks"], 0)
        # a fully-missing call is still allowed to fall back
        self.assertEqual(len(s.embed_texts(["needs provider"])[0]), FALLBACK_DIM)

    def test_key_is_in_header_not_url_and_not_in_errors_or_stats(self):
        post = FakePost(status=429)
        stats_file = self.tmp / "s.json"
        s = self.store(post, stats_path=stats_file)
        with self.assertRaises(EmbeddingError) as cm:
            s.embed_texts(["x"])
        call = post.calls[0]
        self.assertNotIn("KEY-ONE-SECRET", call["url"])
        self.assertEqual(call["headers"]["x-goog-api-key"], "KEY-ONE-SECRET")
        self.assertNotIn("KEY-ONE-SECRET", str(cm.exception))
        self.assertNotIn("KEY-", stats_file.read_text())

    def test_keys_rotate_round_robin(self):
        post = FakePost()
        s = self.store(post)
        s.embed_texts(["one"], batch=False)
        s.embed_texts(["two"], batch=False)
        used = [c["headers"]["x-goog-api-key"] for c in post.calls]
        self.assertEqual(used, ["KEY-ONE-SECRET", "KEY-TWO-SECRET"])
        self.assertEqual(s.stats["requests_by_key_env"], {"TEST_EMB_KEY_1": 1, "TEST_EMB_KEY_2": 1})

    def test_403_skips_key_for_the_day_and_other_key_succeeds(self):
        class Post(FakePost):
            def __call__(inner, url, headers=None, json=None, timeout=None):
                if headers["x-goog-api-key"] == "KEY-ONE-SECRET":
                    inner.calls.append({"url": url, "headers": headers})
                    return FakeResp(403, {"error": {"message": "denied"}})
                return super().__call__(url, headers=headers, json=json, timeout=timeout)
        post = Post()
        s = self.store(post)
        out = s.embed_texts(["first"], batch=False)
        self.assertEqual(len(out), 1)  # key 1 failed (403), key 2 answered: no raise
        s.embed_texts(["second"], batch=False)
        used = [c["headers"]["x-goog-api-key"] for c in post.calls]
        self.assertEqual(used, ["KEY-ONE-SECRET", "KEY-TWO-SECRET", "KEY-TWO-SECRET"],
                         "key 1 is not retried after the 403")
        self.assertIn("TEST_EMB_KEY_1", s.stats["keys_skipped"])

    def test_requests_are_counted_in_router_ledger_with_composite_key(self):
        from devmem.router import key_pool
        s = self.store(FakePost())
        s.embed_texts(["a"], batch=False)
        s.embed_texts(["b"], batch=False)
        total = sum(key_pool.get_usage("gemini", env, model="test-model", db_path=str(self.tmp / "ledger.db"))
                    for env in ("TEST_EMB_KEY_1", "TEST_EMB_KEY_2"))
        self.assertEqual(total, 2)
        conn = key_pool.get_db_connection(str(self.tmp / "ledger.db"))
        ids = {r[0] for r in conn.execute("SELECT key_id FROM key_usage")}
        conn.close()
        self.assertEqual(ids, {"TEST_EMB_KEY_1#test-model", "TEST_EMB_KEY_2#test-model"})

    def test_per_key_daily_limit_skips_key_from_ledger(self):
        post = FakePost()
        s = self.store(post, rpd_per_key=1)
        s.embed_texts(["a"], batch=False)   # key 1 now at its limit
        s.embed_texts(["b"], batch=False)   # key 2
        self.assertEqual(len(post.calls), 2)
        with self.assertRaises(EmbeddingError):  # both keys at their limit: nothing usable
            s.embed_texts(["c"], batch=False)
        self.assertEqual(len(post.calls), 2, "no request was sent past the limit")

    def test_no_key_raises(self):
        s = self.store(FakePost(), key_envs=["DEFINITELY_UNSET_KEY_ENV"])
        with self.assertRaises(EmbeddingError):
            s.embed_texts(["x"])


@unittest.skipUnless(os.environ.get("DEVMEM_LIVE_TESTS") == "1", "live test: set DEVMEM_LIVE_TESTS=1")
class TestLiveEmbedding(unittest.TestCase):
    """live: 1 real embedding request (1 text) through the production configuration."""

    def test_real_endpoint_returns_3072_dim_vector(self):
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
        tmp = Path(tempfile.mkdtemp(prefix="p5_live_"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        s = EmbeddingStore(cache_path=tmp / "c.db", db_path=str(tmp / "l.db"),
                           cooldown_mgr=CooldownManager(state_file=tmp / "cd.json"))
        vec = s.embed_texts(["devmem live embedding test sentence"], batch=False)[0]
        self.assertEqual(len(vec), 3072)
        self.assertEqual(s.stats["http_requests"], 1)


if __name__ == "__main__":
    unittest.main()
