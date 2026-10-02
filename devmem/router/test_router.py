"""
Standalone test suite for devmem LLM Router.
Tests:
1. SQLite usage tracking and pre-emptive limit enforcement.
2. In-provider multi-key rotation upon limit exhaustion.
3. 429 RateLimitError dynamic key exhaustion and immediate failover.
4. Multi-provider priority fallback (Groq -> Gemini -> Nemotron).
5. Logging accuracy in llm_call_log table.
6. Live provider invocation if keys are present in environment.
"""

from datetime import date
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import sys
from pathlib import Path
import yaml

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from devmem.router.key_pool import (
    get_db_connection,
    get_today_str,
    get_usage,
    increment_usage,
    is_key_available,
    mark_key_exhausted,
)
from devmem.router.llm_router import (
    AllProvidersExhaustedError,
    call_llm,
    load_providers_config,
    log_llm_call,
)
from devmem.router.providers import (
    ProviderError,
    ProviderResponse,
    RateLimitError,
    send_request,
)


class TestKeyPool(unittest.TestCase):
    """Test SQLite-based key usage tracking and exhaustion."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_usage.db")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_increment_and_get_usage(self):
        self.assertEqual(get_usage("groq", "KEY_1", db_path=self.db_path), 0)
        increment_usage("groq", "KEY_1", count=1, db_path=self.db_path)
        self.assertEqual(get_usage("groq", "KEY_1", db_path=self.db_path), 1)
        increment_usage("groq", "KEY_1", count=4, db_path=self.db_path)
        self.assertEqual(get_usage("groq", "KEY_1", db_path=self.db_path), 5)

    def test_key_availability_limit(self):
        increment_usage("groq", "KEY_A", count=3, db_path=self.db_path)
        self.assertTrue(is_key_available("groq", "KEY_A", limit=5, db_path=self.db_path))
        self.assertFalse(is_key_available("groq", "KEY_A", limit=3, db_path=self.db_path))

    def test_mark_key_exhausted(self):
        mark_key_exhausted("groq", "KEY_B", db_path=self.db_path)
        usage = get_usage("groq", "KEY_B", db_path=self.db_path)
        self.assertGreaterEqual(usage, 9999999)
        self.assertFalse(is_key_available("groq", "KEY_B", limit=10000, db_path=self.db_path))


class TestRouterRotationAndFallback(unittest.TestCase):
    """Test router multi-key rotation and multi-provider fallback logic."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_router.db")
        self.config_path = os.path.join(self.temp_dir, "test_providers.yaml")

        # Create a test providers config with low limits for testing
        test_config = {
            "providers": [
                {
                    "name": "groq",
                    "priority": 1,
                    "models": {"fast": "llama-3.1-8b-instant", "strong": "llama-3.3-70b-versatile"},
                    "keys": [{"env": "MOCK_GROQ_KEY_1"}, {"env": "MOCK_GROQ_KEY_2"}],
                    "daily_limit_fast": 2,  # Limit is 2 calls for quick rotation test
                    "daily_limit_strong": 2,
                },
                {
                    "name": "gemini",
                    "priority": 2,
                    "models": {"fast": "gemini-1.5-flash", "strong": "gemini-1.5-flash"},
                    "keys": [{"env": "MOCK_GEMINI_KEY_1"}],
                    "daily_limit_fast": 5,
                    "daily_limit_strong": 5,
                },
            ]
        }
        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.dump(test_config, f)

        # Set mock env vars
        os.environ["MOCK_GROQ_KEY_1"] = "groq-key-1"
        os.environ["MOCK_GROQ_KEY_2"] = "groq-key-2"
        os.environ["MOCK_GEMINI_KEY_1"] = "gemini-key-1"

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        for k in ["MOCK_GROQ_KEY_1", "MOCK_GROQ_KEY_2", "MOCK_GEMINI_KEY_1"]:
            os.environ.pop(k, None)

    @patch("devmem.router.llm_router.send_request")
    def test_key_rotation_within_provider(self, mock_send):
        """Verify calls rotate to Key 2 after Key 1 reaches its daily limit."""
        mock_send.side_effect = [
            ProviderResponse(text="Resp 1", tokens_in=10, tokens_out=5),
            ProviderResponse(text="Resp 2", tokens_in=10, tokens_out=5),
            ProviderResponse(text="Resp 3 from Key 2", tokens_in=10, tokens_out=5),
        ]

        # Call 1 -> Uses Groq Key 1 (usage becomes 1/2)
        res1 = call_llm("test prompt 1", tier="fast", config_path=self.config_path, db_path=self.db_path)
        self.assertEqual(res1, "Resp 1")
        self.assertEqual(get_usage("groq", "MOCK_GROQ_KEY_1", db_path=self.db_path), 1)

        # Call 2 -> Uses Groq Key 1 (usage becomes 2/2 -> reached limit)
        res2 = call_llm("test prompt 2", tier="fast", config_path=self.config_path, db_path=self.db_path)
        self.assertEqual(res2, "Resp 2")
        self.assertEqual(get_usage("groq", "MOCK_GROQ_KEY_1", db_path=self.db_path), 2)

        # Call 3 -> Groq Key 1 is at limit (2 >= 2). Must automatically rotate to Groq Key 2!
        res3 = call_llm("test prompt 3", tier="fast", config_path=self.config_path, db_path=self.db_path)
        self.assertEqual(res3, "Resp 3 from Key 2")
        self.assertEqual(get_usage("groq", "MOCK_GROQ_KEY_2", db_path=self.db_path), 1)

        # Check mock calls to confirm key rotation
        self.assertEqual(mock_send.call_args_list[0].kwargs["api_key"], "groq-key-1")
        self.assertEqual(mock_send.call_args_list[1].kwargs["api_key"], "groq-key-1")
        self.assertEqual(mock_send.call_args_list[2].kwargs["api_key"], "groq-key-2")

    @patch("devmem.router.llm_router.send_request")
    def test_429_rate_limit_marks_exhausted_and_fails_over(self, mock_send):
        """Verify dynamic 429 marks key exhausted and immediately rotates to next key."""
        mock_send.side_effect = [
            RateLimitError("429 Too Many Requests: daily_limit reached"),
            ProviderResponse(text="Success from Key 2", tokens_in=12, tokens_out=6),
        ]

        res = call_llm("prompt on 429", tier="fast", config_path=self.config_path, db_path=self.db_path)
        self.assertEqual(res, "Success from Key 2")

        # Key 1 must now be marked exhausted in database
        usage_key_1 = get_usage("groq", "MOCK_GROQ_KEY_1", db_path=self.db_path)
        self.assertGreaterEqual(usage_key_1, 9999999)
        # Key 2 should have recorded 1 successful request
        self.assertEqual(get_usage("groq", "MOCK_GROQ_KEY_2", db_path=self.db_path), 1)

    @patch("devmem.router.llm_router.send_request")
    def test_provider_fallback(self, mock_send):
        """Verify that when all keys of Groq are exhausted, router falls back to Gemini."""
        # Key 1 at limit, Key 2 at limit
        increment_usage("groq", "MOCK_GROQ_KEY_1", count=2, db_path=self.db_path)
        increment_usage("groq", "MOCK_GROQ_KEY_2", count=2, db_path=self.db_path)

        mock_send.return_value = ProviderResponse(text="Gemini Response", tokens_in=20, tokens_out=15)

        res = call_llm("prompt for gemini", tier="fast", config_path=self.config_path, db_path=self.db_path)
        self.assertEqual(res, "Gemini Response")

        # Gemini key should have incremented
        self.assertEqual(get_usage("gemini", "MOCK_GEMINI_KEY_1", db_path=self.db_path), 1)
        # Mock call must be to gemini
        self.assertEqual(mock_send.call_args.kwargs["provider_name"], "gemini")
        self.assertEqual(mock_send.call_args.kwargs["api_key"], "gemini-key-1")

    @patch("devmem.router.llm_router.send_request")
    def test_all_providers_exhausted_raises_exception(self, mock_send):
        """Verify AllProvidersExhaustedError is raised when no keys/providers remain."""
        increment_usage("groq", "MOCK_GROQ_KEY_1", count=2, db_path=self.db_path)
        increment_usage("groq", "MOCK_GROQ_KEY_2", count=2, db_path=self.db_path)
        increment_usage("gemini", "MOCK_GEMINI_KEY_1", count=5, db_path=self.db_path)

        with self.assertRaises(AllProvidersExhaustedError):
            call_llm("prompt when all dead", tier="fast", config_path=self.config_path, db_path=self.db_path)

    @patch("devmem.router.llm_router.send_request")
    def test_call_log_recording(self, mock_send):
        """Verify successful call logs accurate entry into llm_call_log table."""
        mock_send.return_value = ProviderResponse(text="Answer", tokens_in=25, tokens_out=8)

        call_llm(
            prompt="Evaluate event",
            tier="fast",
            purpose="importance_scoring",
            agent_id="isabella",
            condition="staged",
            sim_day=1,
            config_path=self.config_path,
            db_path=self.db_path,
        )

        conn = get_db_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM llm_call_log")
            rows = cursor.fetchall()
            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row["provider"], "groq")
            self.assertEqual(row["model"], "llama-3.1-8b-instant")
            self.assertEqual(row["purpose"], "importance_scoring")
            self.assertEqual(row["tokens_in"], 25)
            self.assertEqual(row["tokens_out"], 8)
            self.assertEqual(row["agent_id"], "isabella")
            self.assertEqual(row["condition"], "staged")
            self.assertEqual(row["sim_day"], 1)
        finally:
            conn.close()


def run_controlled_burst_demonstration():
    """
    Demonstrate controlled burst testing satisfying Task 6:
    Fires a burst of calls against low-limit keys, proves rotation to next key
    and fallback to next provider, and prints ledger entries.
    """
    print("\n" + "=" * 70)
    print("DEMONSTRATION: Controlled Burst Test (Key Rotation & Provider Fallback)")
    print("=" * 70)

    temp_dir = tempfile.mkdtemp()
    demo_db = os.path.join(temp_dir, "burst_demo.db")
    demo_config_path = os.path.join(temp_dir, "burst_providers.yaml")

    demo_config = {
        "providers": [
            {
                "name": "groq",
                "priority": 1,
                "models": {"fast": "llama-3.1-8b-instant", "strong": "llama-3.3-70b-versatile"},
                "keys": [{"env": "BURST_GROQ_KEY_1"}, {"env": "BURST_GROQ_KEY_2"}],
                "daily_limit_fast": 2,  # Limit is 2 calls for Key 1 and Key 2
                "daily_limit_strong": 2,
            },
            {
                "name": "gemini",
                "priority": 2,
                "models": {"fast": "gemini-1.5-flash", "strong": "gemini-1.5-flash"},
                "keys": [{"env": "BURST_GEMINI_KEY_1"}],
                "daily_limit_fast": 5,
                "daily_limit_strong": 5,
            },
        ]
    }
    with open(demo_config_path, "w", encoding="utf-8") as f:
        yaml.dump(demo_config, f)

    os.environ["BURST_GROQ_KEY_1"] = "real_or_mock_groq_1"
    os.environ["BURST_GROQ_KEY_2"] = "real_or_mock_groq_2"
    os.environ["BURST_GEMINI_KEY_1"] = "real_or_mock_gemini_1"

    # Simulate responses for the burst:
    # Call 1 -> Groq Key 1 succeeds
    # Call 2 -> Groq Key 1 succeeds (exhausts limit 2/2)
    # Call 3 -> Groq Key 1 skipped, Groq Key 2 succeeds (usage 1/2)
    # Call 4 -> Groq Key 2 throws 429 rate limit! Router marks it exhausted and falls back to Gemini!
    # Call 5 -> Both Groq keys exhausted, routes straight to Gemini
    simulated_responses = [
        ProviderResponse(text="Resp 1 from Groq-Key-1", tokens_in=15, tokens_out=8),
        ProviderResponse(text="Resp 2 from Groq-Key-1", tokens_in=15, tokens_out=8),
        ProviderResponse(text="Resp 3 from Groq-Key-2", tokens_in=20, tokens_out=10),
        RateLimitError("Simulated Groq 429 Rate Limit on Key 2"),
        ProviderResponse(text="Resp 4 from Gemini-Key-1 (Fallback)", tokens_in=25, tokens_out=12),
        ProviderResponse(text="Resp 5 from Gemini-Key-1", tokens_in=25, tokens_out=12),
    ]

    call_index = 0

    def mock_burst_sender(provider_name, model, api_key, prompt, timeout=30):
        nonlocal call_index
        item = simulated_responses[call_index]
        call_index += 1
        print(f"  -> Attempting Provider='{provider_name}' Model='{model}' Key='{api_key[:16]}...'")
        if isinstance(item, Exception):
            print(f"     [!] Encountered: {type(item).__name__} - {item}")
            raise item
        return item

    with patch("devmem.router.llm_router.send_request", side_effect=mock_burst_sender):
        for step in range(1, 6):
            print(f"\n[Burst Call #{step}] Requesting inference (tier=fast, purpose=burst_test)...")
            res = call_llm(
                prompt=f"Burst prompt {step}",
                tier="fast",
                purpose="burst_test",
                agent_id="test_agent",
                config_path=demo_config_path,
                db_path=demo_db,
            )
            print(f"  [+] Returned: \"{res}\"")

    # Inspect SQLite database records
    print("\n--- Key Usage Table (key_usage) ---")
    conn = get_db_connection(demo_db)
    for row in conn.execute("SELECT provider, key_id, date, requests_used FROM key_usage"):
        print(f"  Provider: {row['provider']:<8} | Key: {row['key_id']:<20} | Date: {row['date']} | Used: {row['requests_used']}")

    print("\n--- LLM Call Ledger (llm_call_log) ---")
    for row in conn.execute("SELECT call_id, provider, model, purpose, tokens_in, tokens_out FROM llm_call_log"):
        print(f"  Call: {row['call_id'][:8]}... | Provider: {row['provider']:<8} | Model: {row['model']:<22} | In: {row['tokens_in']} | Out: {row['tokens_out']}")

    conn.close()
    shutil.rmtree(temp_dir, ignore_errors=True)
    print("\nBurst demonstration completed successfully.")


def run_live_check():
    """Run a live verification test if any real API keys exist in environment / .env."""
    print("\n--- Live Router Check ---")
    keys_found = []
    for k in ["GROQ_KEY_1", "GROQ_KEY_2", "GEMINI_KEY_1", "NIM_KEY_1"]:
        val = os.environ.get(k)
        if val and val.strip():
            keys_found.append(k)

    if not keys_found:
        print("No live API keys found in environment/.env.")
        print("Populate .env with your free-tier keys (GROQ_KEY_1, GEMINI_KEY_1, etc.) to perform live tests.")
        return

    print(f"Detected live keys: {keys_found}")
    try:
        response = call_llm("Reply with the word 'PONG' and nothing else.", tier="fast", purpose="live_test")
        print(f"Live Call Success! Response: {response}")
    except Exception as e:
        print(f"Live call error: {e}")


if __name__ == "__main__":
    print("Running LLM Router Test Suite...")
    suite = unittest.TestLoader().loadTestsFromTestCase(TestKeyPool)
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestRouterRotationAndFallback))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    if result.wasSuccessful():
        print("\nAll unit and rotation tests passed successfully!")
    else:
        print("\nUnit tests failed.")

    run_controlled_burst_demonstration()
    run_live_check()

