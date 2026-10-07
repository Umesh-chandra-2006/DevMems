"""
devmem/router/test_router.py

Comprehensive test suite for DevMem LLM Router:
1. Key Pool SQLite tracking with per-model buckets and token tracking.
2. 429 Classifier verified against saved JSON fixtures (captured and documented).
3. Groq TPD regression test (verifies key is NOT marked exhausted for the day).
4. Circuit breaker escalating cooldown and reset-on-success.
5. Groq 8,000 TPM pre-check and TPD token budgeting.
6. Model pinning and loud failure verification.
7. Multi-key rotation and multi-provider fallback regression tests.
"""

from datetime import date
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch
import sys
import yaml

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from devmem.router.classifier import ClassificationResult, classify_429
from devmem.router.cooldown import (
    CooldownManager,
    MAX_COOLDOWN_SECONDS,
    UNKNOWN_COOLDOWN_SEQUENCE,
    get_seconds_until_pt_midnight,
    get_seconds_until_utc_midnight,
)
from devmem.router.key_pool import (
    get_db_connection,
    get_today_str,
    get_token_usage,
    get_usage,
    increment_token_usage,
    increment_usage,
    is_key_available,
    make_composite_key,
    mark_key_exhausted,
    reset_usage_for_test,
)
from devmem.router.llm_router import (
    AllProvidersExhaustedError,
    ModelPinnedError,
    call_llm,
    estimate_tokens,
    load_providers_config,
    log_llm_call,
)
from devmem.router.providers import (
    AuthOrBillingError,
    ProviderError,
    ProviderResponse,
    ProviderTimeoutError,
    RateLimitError,
    send_request,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "429"


class TestKeyPool(unittest.TestCase):
    """Test SQLite-based key usage tracking, composite per-model buckets, and token tracking."""

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

    def test_composite_per_model_buckets(self):
        """Verify (key_id, model) buckets maintain distinct counts without schema changes."""
        increment_usage("gemini", "GEMINI_KEY_1", count=2, model="gemini-3.1-flash-lite", db_path=self.db_path)
        increment_usage("gemini", "GEMINI_KEY_1", count=5, model="gemini-3.6-flash", db_path=self.db_path)

        usage_lite = get_usage("gemini", "GEMINI_KEY_1", model="gemini-3.1-flash-lite", db_path=self.db_path)
        usage_flash = get_usage("gemini", "GEMINI_KEY_1", model="gemini-3.6-flash", db_path=self.db_path)

        self.assertEqual(usage_lite, 2)
        self.assertEqual(usage_flash, 5)

    def test_token_usage_tracking(self):
        """Verify token usage tracking in SQLite."""
        self.assertEqual(get_token_usage("groq", "GROQ_KEY_1", model="openai/gpt-oss-20b", db_path=self.db_path), 0)
        increment_token_usage("groq", "GROQ_KEY_1", tokens=1500, model="openai/gpt-oss-20b", db_path=self.db_path)
        self.assertEqual(get_token_usage("groq", "GROQ_KEY_1", model="openai/gpt-oss-20b", db_path=self.db_path), 1500)


class TestClassifierWithFixtures(unittest.TestCase):
    """Parametrized classifier tests using saved captured and documented fixtures."""

    def _load_fixture(self, filename: str) -> dict:
        filepath = FIXTURES_DIR / filename
        self.assertTrue(filepath.exists(), f"Fixture file not found: {filepath}")
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    def test_groq_rpm_captured(self):
        """Captured: Groq requests per minute (RPM) -> transient_minute with retry_after."""
        data = self._load_fixture("groq_captured_429.json")
        res = classify_429(
            provider=data["provider"],
            status=data["status_code"],
            headers=data["headers"],
            body=data["body"]
        )
        self.assertEqual(res.kind, "transient_minute")
        self.assertEqual(res.retry_after, 2)

    def test_groq_tpm_documented(self):
        """Documented: Groq tokens per minute (TPM) -> transient_minute with retry_after."""
        data = self._load_fixture("groq_documented_tpm.json")
        res = classify_429(
            provider=data["provider"],
            status=data["status_code"],
            headers=data["headers"],
            body=data["body"]
        )
        self.assertEqual(res.kind, "transient_minute")
        self.assertEqual(res.retry_after, 4)

    def test_groq_tpd_documented_regression(self):
        """Documented & Regression: Groq tokens per day (TPD) -> tokens_recoverable, NOT daily_requests!"""
        data = self._load_fixture("groq_documented_tpd.json")
        res = classify_429(
            provider=data["provider"],
            status=data["status_code"],
            headers=data["headers"],
            body=data["body"]
        )
        self.assertEqual(res.kind, "tokens_recoverable")
        self.assertNotEqual(res.kind, "daily_requests")
        self.assertEqual(res.retry_after, 578)

    def test_groq_rpd_documented(self):
        """Documented: Groq requests per day (RPD) -> daily_requests."""
        data = self._load_fixture("groq_documented_rpd.json")
        res = classify_429(
            provider=data["provider"],
            status=data["status_code"],
            headers=data["headers"],
            body=data["body"]
        )
        self.assertEqual(res.kind, "daily_requests")
        self.assertEqual(res.retry_after, 45200)

    def test_gemini_per_minute_captured(self):
        """Captured: Gemini PerMinute QuotaFailure -> transient_minute."""
        data = self._load_fixture("gemini_captured_429.json")
        res = classify_429(
            provider=data["provider"],
            status=data["status_code"],
            headers=data["headers"],
            body=data["body"]
        )
        self.assertEqual(res.kind, "transient_minute")
        self.assertEqual(res.retry_after, 36)

    def test_gemini_per_day_documented(self):
        """Documented: Gemini PerDay QuotaFailure -> daily_requests."""
        data = self._load_fixture("gemini_documented_per_day.json")
        res = classify_429(
            provider=data["provider"],
            status=data["status_code"],
            headers=data["headers"],
            body=data["body"]
        )
        self.assertEqual(res.kind, "daily_requests")

    def test_gemini_multiple_violations_per_day_wins(self):
        """Documented: Multiple violations (PerMinute + PerDay) -> daily_requests must win."""
        data = self._load_fixture("gemini_documented_multiple_violations.json")
        res = classify_429(
            provider=data["provider"],
            status=data["status_code"],
            headers=data["headers"],
            body=data["body"]
        )
        self.assertEqual(res.kind, "daily_requests")

    def test_unknown_429_fixture(self):
        """Generic unclassifiable 429 -> unknown kind with retry-after preserved."""
        data = self._load_fixture("unknown_429.json")
        res = classify_429(
            provider="some_provider",
            status=data["status_code"],
            headers=data["headers"],
            body=data["body"]
        )
        self.assertEqual(res.kind, "unknown")
        self.assertEqual(res.retry_after, 45)

    def test_known_kind_preserves_retry_after_beyond_15_minutes(self):
        """Condition 2: Known rate-limit kinds honor retry-after beyond 15 minutes (900s)."""
        res_tpd = classify_429(
            provider="groq",
            status=429,
            headers={"retry-after": "1800"},
            body={"error": {"message": "tokens per day (TPD) exceeded"}}
        )
        self.assertEqual(res_tpd.kind, "tokens_recoverable")
        self.assertEqual(res_tpd.retry_after, 1800)

        res_unknown = classify_429(
            provider="unknown_prov",
            status=429,
            headers={"retry-after": "1800"},
            body={"error": {"message": "some mysterious rate limit"}}
        )
        self.assertEqual(res_unknown.kind, "unknown")
        self.assertEqual(res_unknown.retry_after, 900)  # Unknown is capped at 900s

    def test_auth_failure_401_fixture(self):
        """Documented: HTTP 401 Auth failure -> auth_billing_failure."""
        data = self._load_fixture("auth_failure_401.json")
        res = classify_429(
            provider="groq",
            status=data["status_code"],
            headers=data["headers"],
            body=data["body"]
        )
        self.assertEqual(res.kind, "auth_billing_failure")


class TestCircuitBreakerAndRegression(unittest.TestCase):
    """Test circuit breaker escalating cooldown, reset on success, and TPD regression behavior."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.state_file = Path(self.temp_dir) / "test_cooldown.json"
        self.mgr = CooldownManager(state_file=self.state_file)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_escalating_unknown_cooldown_sequence(self):
        """Verify unknown 429 escalates 30s -> 60s -> 120s -> 240s -> 480s -> 900s."""
        durations = []
        for _ in range(len(UNKNOWN_COOLDOWN_SEQUENCE) + 2):
            d = self.mgr.set_cooldown(
                provider="nemotron",
                key_env="NIM_KEY_1",
                model=None,
                kind="unknown",
                reason="test circuit breaker"
            )
            durations.append(int(d))

        expected = [30, 60, 120, 240, 480, 900, 900, 900]
        self.assertEqual(durations, expected)

    def test_reset_on_success(self):
        """Verify circuit breaker consecutive count resets to 0 upon successful call."""
        self.mgr.set_cooldown("nemotron", "NIM_KEY_1", None, kind="unknown")
        self.mgr.set_cooldown("nemotron", "NIM_KEY_1", None, kind="unknown")
        key_id = "nemotron:NIM_KEY_1"
        self.assertEqual(self.mgr.state["cooldowns"][key_id]["consecutive_unknown"], 2)

        self.mgr.record_success("nemotron", "NIM_KEY_1", None)
        self.assertEqual(self.mgr.state["cooldowns"][key_id]["consecutive_unknown"], 0)
        is_cooling, _ = self.mgr.is_cooling_down("nemotron", "NIM_KEY_1", None)
        self.assertFalse(is_cooling)

    def test_groq_tpd_does_not_lock_key_for_day(self):
        """
        REGRESSION TEST: Encountering Groq TPD rate limit sets transient cooldown
        but does NOT mark the key exhausted in SQLite (remains < 9999999).
        """
        temp_db = os.path.join(self.temp_dir, "tpd_reg.db")
        config_path = os.path.join(self.temp_dir, "providers.yaml")
        test_config = {
            "providers": [
                {
                    "name": "groq",
                    "priority": 1,
                    "models": {"fast": "openai/gpt-oss-20b"},
                    "keys": [{"env": "GROQ_MOCK_TPD"}],
                    "rpm": 30,
                    "rpd": 1000,
                    "tpd": 200000,
                }
            ]
        }
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(test_config, f)

        os.environ["GROQ_MOCK_TPD"] = "mock-key-tpd"

        tpd_body = {
            "error": {
                "message": "Rate limit reached for model `openai/gpt-oss-20b` on tokens per day (TPD): Limit 200000, Used 200000. Please try again in 9m38s.",
                "type": "tokens",
                "code": "rate_limit_exceeded"
            }
        }

        with patch("devmem.router.llm_router.send_request") as mock_send:
            mock_send.side_effect = RateLimitError(
                message=json.dumps(tpd_body),
                status_code=429,
                headers={"retry-after": "578"},
                body=tpd_body,
                provider="groq"
            )

            with self.assertRaises(AllProvidersExhaustedError):
                call_llm(
                    "Test prompt for TPD",
                    tier="fast",
                    config_path=config_path,
                    db_path=temp_db
                )

        # Confirm the key is NOT marked with 9999999 in key_usage
        usage = get_usage("groq", "GROQ_MOCK_TPD", model="openai/gpt-oss-20b", db_path=temp_db)
        self.assertLess(usage, 9999999, "TPD rate limit must NOT mark key exhausted for the day!")
        os.environ.pop("GROQ_MOCK_TPD", None)

    def test_cooldown_state_atomic_write_and_corruption_resilience(self):
        """Condition 5: Cooldown state atomic write and graceful recovery from corrupt/missing state."""
        # 1. Atomic write creates the file, and .tmp is cleaned up
        self.mgr.set_provider_cooldown("groq", duration=30.0, reason="test atomic")
        self.assertTrue(self.state_file.exists())
        temp_file = self.state_file.with_suffix(".json.tmp")
        self.assertFalse(temp_file.exists(), ".tmp file should not linger after atomic write")

        # 2. Corrupt file starts clean without error
        with open(self.state_file, "w", encoding="utf-8") as f:
            f.write("CORRUPT_JSON_DATA{{{{")

        new_mgr = CooldownManager(state_file=self.state_file)
        self.assertEqual(new_mgr.state["cooldowns"], {})
        self.assertEqual(new_mgr.state["provider_cooldowns"], {})

        # 3. Missing file starts clean
        missing_file = Path(self.temp_dir) / "non_existent.json"
        missing_mgr = CooldownManager(state_file=missing_file)
        self.assertEqual(missing_mgr.state["cooldowns"], {})

    def test_daily_lock_reset_timing_groq_and_gemini(self):
        """Condition 1 & 6: Groq resets at now + retry_after; Gemini resets at LA midnight."""
        # Condition 1: Groq daily lock honors retry_after (now + x-ratelimit-reset-requests)
        groq_cd = self.mgr.set_cooldown(
            provider="groq",
            key_env="GROQ_KEY_1",
            model="openai/gpt-oss-20b",
            kind="daily_requests",
            retry_after=2938,  # e.g. 48m58s
            reason="RPD reached"
        )
        self.assertEqual(groq_cd, 2938.0)

        # Condition 6: Gemini daily lock uses zoneinfo America/Los_Angeles midnight
        gemini_cd = self.mgr.set_cooldown(
            provider="gemini",
            key_env="GEMINI_KEY_1",
            model="gemini-3.1-flash-lite",
            kind="daily_requests",
            retry_after=None,
            reason="Gemini PerDay"
        )
        expected_pt = get_seconds_until_pt_midnight()
        self.assertAlmostEqual(gemini_cd, expected_pt, delta=2)

    def test_rpm_pacer_pacing_delay(self):
        """Condition 7: RPM pacer enforces minimum interval between calls."""
        key_id = self.mgr._make_key_id("groq", "KEY", "model")
        self.mgr.state["last_call_timestamps"][key_id] = time.time()
        with patch("time.sleep") as mock_sleep:
            slept = self.mgr.pace_request("groq", "KEY", "model", rpm=60)
            self.assertGreater(slept, 0.0)
            self.assertLessEqual(slept, 1.0)
            mock_sleep.assert_called_once()

    def test_sliding_window_tpm_pacer(self):
        """M1.2: Sliding-window TPM pacer sleeps until tokens clear 60s rolling window."""
        key_id = self.mgr._make_key_id("groq", "KEY", "model")
        now = time.time()
        # Seed sliding window with 5,000 tokens granted 40 seconds ago
        self.mgr.state["tpm_sliding_windows"] = {
            key_id: [[now - 40.0, 5000]]
        }

        # 1. A request for 2,000 tokens (5,000 + 2,000 = 7,000 <= 8,000 TPM) does not sleep
        with patch("time.sleep") as mock_sleep:
            slept = self.mgr.pace_tpm_window("groq", "KEY", "model", estimated_tokens=2000, tpm=8000)
            self.assertEqual(slept, 0.0)
            mock_sleep.assert_not_called()

        # Window now has 5,000 + 2,000 = 7,000 tokens
        # 2. A request for 2,000 tokens (7,000 + 2,000 = 9,000 > 8,000 TPM) must wait for oldest entry to expire (~20s)
        with patch("time.sleep") as mock_sleep:
            slept = self.mgr.pace_tpm_window("groq", "KEY", "model", estimated_tokens=2000, tpm=8000)
            self.assertGreater(slept, 18.0)
            self.assertLessEqual(slept, 22.0)
            mock_sleep.assert_called_once()




class TestTokenBudgetAndPinning(unittest.TestCase):
    """Test token estimation, Groq 8,000 TPM pre-check, and model pinning enforcement."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_budget.db")
        self.config_path = os.path.join(self.temp_dir, "providers.yaml")

        test_config = {
            "providers": [
                {
                    "name": "groq",
                    "priority": 1,
                    "models": {"fast": "openai/gpt-oss-20b"},
                    "keys": [{"env": "GROQ_TEST_KEY"}],
                    "rpm": 30,
                    "rpd": 1000,
                    "tpm": 8000,
                    "tpd": 200000,
                },
                {
                    "name": "gemini",
                    "priority": 2,
                    "models": {"fast": "gemini-3.1-flash-lite"},
                    "keys": [{"env": "GEMINI_TEST_KEY"}],
                    "rpm": 15,
                    "rpd": 500,
                    "tpm": 250000,
                    "tpd": None,
                }
            ]
        }
        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.dump(test_config, f)

        os.environ["GROQ_TEST_KEY"] = "mock-groq-key"
        os.environ["GEMINI_TEST_KEY"] = "mock-gemini-key"

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        os.environ.pop("GROQ_TEST_KEY", None)
        os.environ.pop("GEMINI_TEST_KEY", None)

    @patch("devmem.router.llm_router.send_request")
    def test_groq_tpm_cap_reroutes_to_gemini(self, mock_send):
        """A prompt exceeding Groq 8,000 TPM limit must bypass Groq and route directly to Gemini."""
        huge_prompt = "word " * 6500  # ~8,700 tokens (> 8,000 TPM)
        mock_send.return_value = ProviderResponse(text="Gemini Answer", tokens_in=8700, tokens_out=10)

        res = call_llm(
            huge_prompt,
            tier="fast",
            config_path=self.config_path,
            db_path=self.db_path
        )
        self.assertEqual(res, "Gemini Answer")
        # Provider called must be gemini, not groq!
        self.assertEqual(mock_send.call_args.kwargs["provider_name"], "gemini")

    @patch("time.sleep")
    @patch("devmem.router.llm_router.send_request")
    def test_model_pinning_fails_loudly_on_error(self, mock_send, mock_sleep):
        """When pinned_model is specified, rate-limiting must raise ModelPinnedError without fallback."""
        mock_send.side_effect = RateLimitError(
            "Rate limited on pinned model",
            status_code=429,
            headers={"retry-after": "5"},
            body={"error": {"message": "Rate limit"}},
            provider="groq"
        )

        with self.assertRaises(ModelPinnedError):
            call_llm(
                "Short prompt",
                tier="fast",
                pinned_model="openai/gpt-oss-20b",
                config_path=self.config_path,
                db_path=self.db_path
            )

    def test_token_budget_precheck_skipping(self):
        """Condition 7: Pre-emptive check skips key whose remaining TPD budget is insufficient."""
        cm = CooldownManager(state_file=Path(self.temp_dir) / "budget_cd.json")
        cm.record_token_usage("groq", "GROQ_TEST_KEY", "openai/gpt-oss-20b", 199500)

        # Request requires ~1000 tokens (> 500 remaining)
        prompt_1000_tokens = "word " * 750
        with patch("devmem.router.llm_router.send_request") as mock_send:
            mock_send.return_value = ProviderResponse(text="Gemini Fallback", tokens_in=1000, tokens_out=10)
            res = call_llm(
                prompt_1000_tokens,
                tier="fast",
                config_path=self.config_path,
                db_path=self.db_path,
                cooldown_mgr=cm
            )
            # Groq skipped pre-emptively without sending request, fallback to Gemini!
            self.assertEqual(res, "Gemini Fallback")
            self.assertEqual(mock_send.call_args.kwargs["provider_name"], "gemini")

    def test_purpose_timeouts_and_provider_cooldown(self):
        """Condition 4: Configurable timeout per purpose & timeout sets 30s provider cooldown."""
        cm = CooldownManager(state_file=Path(self.temp_dir) / "timeout_cd.json")

        with patch("devmem.router.llm_router.send_request") as mock_send:
            # 1. Verify purpose="importance_score" passes timeout=15
            mock_send.return_value = ProviderResponse(text="Score 5", tokens_in=10, tokens_out=2)
            call_llm(
                "Rate this",
                tier="fast",
                purpose="importance_score",
                config_path=self.config_path,
                db_path=self.db_path,
                cooldown_mgr=cm
            )
            self.assertEqual(mock_send.call_args.kwargs["timeout"], 30)   # importance scoring: 15 s until 2026-10-08, 30 s since (PM decision)

            # 2. Verify timeout on Groq sets 30s provider cooldown and falls back to Gemini
            mock_send.side_effect = [
                ProviderTimeoutError("Connection timed out after 15s"),
                ProviderResponse(text="Gemini Answer after Timeout", tokens_in=10, tokens_out=5)
            ]
            res = call_llm(
                "Rate this again",
                tier="fast",
                purpose="importance_score",
                config_path=self.config_path,
                db_path=self.db_path,
                cooldown_mgr=cm
            )
            self.assertEqual(res, "Gemini Answer after Timeout")
            # Since 2026-10-08 a timeout cools only the key that timed out (10 s), not every key of the provider
            self.assertFalse(cm.is_provider_cooling_down("groq")[0])
            cooled = [k for k, v in cm.state["cooldowns"].items() if v.get("cooldown_until", 0) > __import__("time").time()]
            self.assertEqual(len(cooled), 1)
            self.assertTrue(cooled[0].startswith("groq"))

    def test_ledger_reconciliation_warning(self):
        """Condition 7: Unexpected early daily 429 triggers ledger reconciliation."""
        cm = CooldownManager(state_file=Path(self.temp_dir) / "recon_cd.json")

        # Key usage is 5 in SQLite, but configured limit is 1000
        increment_usage("groq", "GROQ_TEST_KEY", count=5, model="openai/gpt-oss-20b", db_path=self.db_path)

        with patch("devmem.router.llm_router.send_request") as mock_send, \
             patch("devmem.router.llm_router.logger.warning") as mock_warn:
            mock_send.side_effect = [
                RateLimitError(
                    "Rate limit reached for requests per day (RPD)",
                    status_code=429,
                    headers={"retry-after": "3600"},
                    body={"error": {"message": "Rate limit reached for requests per day (RPD)"}},
                    provider="groq"
                ),
                ProviderResponse(text="Gemini fallback", tokens_in=10, tokens_out=5)
            ]
            call_llm(
                "Test reconciliation",
                tier="fast",
                config_path=self.config_path,
                db_path=self.db_path,
                cooldown_mgr=cm
            )
            warn_calls = [c.args[0] for c in mock_warn.call_args_list if len(c.args) > 0]
            self.assertTrue(any("LEDGER RECONCILIATION" in str(msg) for msg in warn_calls))
            target_key_id = cm._make_key_id("groq", "GROQ_TEST_KEY", "openai/gpt-oss-20b")
            self.assertEqual(cm.state["observed_limits"].get(target_key_id), 5)

    def test_pinned_mode_key_rotation_and_cooldown_wait(self):
        """Condition 7: Pinned mode rotates keys of pinned model, waits on cooldown <= 90s, and raises on > 90s."""
        pinned_config_path = os.path.join(self.temp_dir, "pinned_providers.yaml")
        pinned_config = {
            "providers": [
                {
                    "name": "groq",
                    "priority": 1,
                    "models": {"fast": "openai/gpt-oss-20b"},
                    "keys": [{"env": "PINNED_KEY_1"}, {"env": "PINNED_KEY_2"}],
                    "rpd": 1000,
                },
                {
                    "name": "gemini",
                    "priority": 2,
                    "models": {"fast": "gemini-3.1-flash-lite"},
                    "keys": [{"env": "GEMINI_PINNED_TEST"}],
                    "rpd": 500,
                }
            ]
        }
        with open(pinned_config_path, "w", encoding="utf-8") as f:
            yaml.dump(pinned_config, f)

        os.environ["PINNED_KEY_1"] = "key-1-pinned"
        os.environ["PINNED_KEY_2"] = "key-2-pinned"
        os.environ["GEMINI_PINNED_TEST"] = "gemini-key"
        cm = CooldownManager(state_file=Path(self.temp_dir) / "pinned_cd.json")

        try:
            # 1. Key 1 fails with 429, rotates to Key 2 which succeeds
            with patch("devmem.router.llm_router.send_request") as mock_send:
                mock_send.side_effect = [
                    RateLimitError("429 on Key 1", status_code=429, headers={"retry-after": "120"}, body={}, provider="groq"),
                    ProviderResponse(text="Success on Key 2", tokens_in=10, tokens_out=5)
                ]
                res = call_llm(
                    "Pinned prompt",
                    tier="fast",
                    pinned_model="openai/gpt-oss-20b",
                    config_path=pinned_config_path,
                    db_path=self.db_path,
                    cooldown_mgr=cm
                )
                self.assertEqual(res, "Success on Key 2")
                self.assertEqual(mock_send.call_count, 2)

            # 2. Both keys cooling down with shortest wait <= 90s: waits and retries
            cm.reset_for_test()
            with patch("devmem.router.llm_router.send_request") as mock_send, \
                 patch("time.sleep") as mock_sleep:
                mock_sleep.side_effect = lambda s: cm.state["cooldowns"].clear()
                mock_send.side_effect = [
                    RateLimitError("429 Key 1", status_code=429, headers={"retry-after": "10"}, body={}, provider="groq"),
                    RateLimitError("429 Key 2", status_code=429, headers={"retry-after": "10"}, body={}, provider="groq"),
                    ProviderResponse(text="Success after wait", tokens_in=10, tokens_out=5)
                ]
                res = call_llm(
                    "Pinned prompt 2",
                    tier="fast",
                    pinned_model="openai/gpt-oss-20b",
                    config_path=pinned_config_path,
                    db_path=self.db_path,
                    cooldown_mgr=cm
                )
                self.assertEqual(res, "Success after wait")
                mock_sleep.assert_called()

            # 3. Both keys cooling down with shortest wait > 90s: raises ModelPinnedError immediately
            cm.reset_for_test()
            with patch("devmem.router.llm_router.send_request") as mock_send, \
                 patch("time.sleep") as mock_sleep:
                mock_send.side_effect = [
                    RateLimitError("429 Key 1", status_code=429, headers={"retry-after": "200"}, body={}, provider="groq"),
                    RateLimitError("429 Key 2", status_code=429, headers={"retry-after": "300"}, body={}, provider="groq"),
                ]
                with self.assertRaises(ModelPinnedError):
                    call_llm(
                        "Pinned prompt 3",
                        tier="fast",
                        pinned_model="openai/gpt-oss-20b",
                        config_path=pinned_config_path,
                        db_path=self.db_path,
                        cooldown_mgr=cm
                    )
        finally:
            os.environ.pop("PINNED_KEY_1", None)
            os.environ.pop("PINNED_KEY_2", None)
            os.environ.pop("GEMINI_PINNED_TEST", None)


class TestRouterRotationAndFallback(unittest.TestCase):
    """Test router multi-key rotation and multi-provider fallback logic (preserving Phase 2 tests)."""

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
                    "models": {"fast": "openai/gpt-oss-20b", "strong": "openai/gpt-oss-120b"},
                    "keys": [{"env": "MOCK_GROQ_KEY_1"}, {"env": "MOCK_GROQ_KEY_2"}],
                    "daily_limit_fast": 2,  # Limit is 2 calls for quick rotation test
                    "daily_limit_strong": 2,
                    "rpd": 2,
                },
                {
                    "name": "gemini",
                    "priority": 2,
                    "models": {"fast": "gemini-3.1-flash-lite", "strong": "gemini-3.6-flash"},
                    "keys": [{"env": "MOCK_GEMINI_KEY_1"}],
                    "daily_limit_fast": 5,
                    "daily_limit_strong": 5,
                    "rpd": 5,
                },
            ]
        }
        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.dump(test_config, f)

        # Set mock env vars
        os.environ["MOCK_GROQ_KEY_1"] = "groq-key-1"
        os.environ["MOCK_GROQ_KEY_2"] = "groq-key-2"
        os.environ["MOCK_GEMINI_KEY_1"] = "gemini-key-1"
        self.cooldown_mgr = CooldownManager(state_file=Path(self.temp_dir) / "test_cd.json")

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
        res1 = call_llm("test prompt 1", tier="fast", config_path=self.config_path, db_path=self.db_path, cooldown_mgr=self.cooldown_mgr)
        self.assertEqual(res1, "Resp 1")
        self.assertEqual(get_usage("groq", "MOCK_GROQ_KEY_1", model="openai/gpt-oss-20b", db_path=self.db_path), 1)

        # Call 2 -> Uses Groq Key 1 (usage becomes 2/2 -> reached limit)
        res2 = call_llm("test prompt 2", tier="fast", config_path=self.config_path, db_path=self.db_path, cooldown_mgr=self.cooldown_mgr)
        self.assertEqual(res2, "Resp 2")
        self.assertEqual(get_usage("groq", "MOCK_GROQ_KEY_1", model="openai/gpt-oss-20b", db_path=self.db_path), 2)

        # Call 3 -> Groq Key 1 is at limit (2 >= 2). Must automatically rotate to Groq Key 2!
        res3 = call_llm("test prompt 3", tier="fast", config_path=self.config_path, db_path=self.db_path, cooldown_mgr=self.cooldown_mgr)
        self.assertEqual(res3, "Resp 3 from Key 2")
        self.assertEqual(get_usage("groq", "MOCK_GROQ_KEY_2", model="openai/gpt-oss-20b", db_path=self.db_path), 1)

        # Check mock calls to confirm key rotation
        self.assertEqual(mock_send.call_args_list[0].kwargs["api_key"], "groq-key-1")
        self.assertEqual(mock_send.call_args_list[1].kwargs["api_key"], "groq-key-1")
        self.assertEqual(mock_send.call_args_list[2].kwargs["api_key"], "groq-key-2")

    @patch("devmem.router.llm_router.send_request")
    def test_429_rate_limit_marks_exhausted_and_fails_over(self, mock_send):
        """Verify dynamic daily 429 marks key exhausted and immediately rotates to next key."""
        mock_send.side_effect = [
            RateLimitError(
                message="Rate limit reached for requests per day (RPD)",
                status_code=429,
                headers={"retry-after": "45200"},
                body={"error": {"message": "Rate limit reached for requests per day (RPD)"}},
                provider="groq"
            ),
            ProviderResponse(text="Success from Key 2", tokens_in=12, tokens_out=6),
        ]

        res = call_llm("prompt on 429", tier="fast", config_path=self.config_path, db_path=self.db_path, cooldown_mgr=self.cooldown_mgr)
        self.assertEqual(res, "Success from Key 2")

        # Key 1 must now be marked exhausted in database
        usage_key_1 = get_usage("groq", "MOCK_GROQ_KEY_1", model="openai/gpt-oss-20b", db_path=self.db_path)
        self.assertGreaterEqual(usage_key_1, 9999999)
        # Key 2 should have recorded 1 successful request
        self.assertEqual(get_usage("groq", "MOCK_GROQ_KEY_2", model="openai/gpt-oss-20b", db_path=self.db_path), 1)

    @patch("devmem.router.llm_router.send_request")
    def test_provider_fallback(self, mock_send):
        """Verify that when all keys of Groq are exhausted, router falls back to Gemini."""
        increment_usage("groq", "MOCK_GROQ_KEY_1", count=2, model="openai/gpt-oss-20b", db_path=self.db_path)
        increment_usage("groq", "MOCK_GROQ_KEY_2", count=2, model="openai/gpt-oss-20b", db_path=self.db_path)

        mock_send.return_value = ProviderResponse(text="Gemini Response", tokens_in=20, tokens_out=15)

        res = call_llm("prompt for gemini", tier="fast", config_path=self.config_path, db_path=self.db_path, cooldown_mgr=self.cooldown_mgr)
        self.assertEqual(res, "Gemini Response")

        # Gemini key should have incremented
        self.assertEqual(get_usage("gemini", "MOCK_GEMINI_KEY_1", model="gemini-3.1-flash-lite", db_path=self.db_path), 1)
        self.assertEqual(mock_send.call_args.kwargs["provider_name"], "gemini")
        self.assertEqual(mock_send.call_args.kwargs["api_key"], "gemini-key-1")

    @patch("devmem.router.llm_router.send_request")
    def test_all_providers_exhausted_raises_exception(self, mock_send):
        """Verify AllProvidersExhaustedError is raised when no keys/providers remain."""
        increment_usage("groq", "MOCK_GROQ_KEY_1", count=2, model="openai/gpt-oss-20b", db_path=self.db_path)
        increment_usage("groq", "MOCK_GROQ_KEY_2", count=2, model="openai/gpt-oss-20b", db_path=self.db_path)
        increment_usage("gemini", "MOCK_GEMINI_KEY_1", count=5, model="gemini-3.1-flash-lite", db_path=self.db_path)

        with self.assertRaises(AllProvidersExhaustedError):
            call_llm("prompt when all dead", tier="fast", config_path=self.config_path, db_path=self.db_path, cooldown_mgr=self.cooldown_mgr)

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
            cooldown_mgr=self.cooldown_mgr,
        )

        conn = get_db_connection(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM llm_call_log")
            rows = cursor.fetchall()
            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row["provider"], "groq")
            self.assertEqual(row["model"], "openai/gpt-oss-20b")
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
    Controlled burst demonstration:
    Fires a burst of calls across low-limit keys, proves key rotation,
    daily rate-limit failover to next provider, and logs ledger entries.
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
                "models": {"fast": "openai/gpt-oss-20b", "strong": "openai/gpt-oss-120b"},
                "keys": [{"env": "BURST_GROQ_KEY_1"}, {"env": "BURST_GROQ_KEY_2"}],
                "daily_limit_fast": 2,
                "daily_limit_strong": 2,
                "rpd": 2,
            },
            {
                "name": "gemini",
                "priority": 2,
                "models": {"fast": "gemini-3.1-flash-lite", "strong": "gemini-3.6-flash"},
                "keys": [{"env": "BURST_GEMINI_KEY_1"}],
                "daily_limit_fast": 5,
                "daily_limit_strong": 5,
                "rpd": 5,
            },
        ]
    }
    with open(demo_config_path, "w", encoding="utf-8") as f:
        yaml.dump(demo_config, f)

    os.environ["BURST_GROQ_KEY_1"] = "real_or_mock_groq_1"
    os.environ["BURST_GROQ_KEY_2"] = "real_or_mock_groq_2"
    os.environ["BURST_GEMINI_KEY_1"] = "real_or_mock_gemini_1"

    simulated_responses = [
        ProviderResponse(text="Resp 1 from Groq-Key-1", tokens_in=15, tokens_out=8),
        ProviderResponse(text="Resp 2 from Groq-Key-1", tokens_in=15, tokens_out=8),
        ProviderResponse(text="Resp 3 from Groq-Key-2", tokens_in=20, tokens_out=10),
        RateLimitError(
            message="Rate limit reached for requests per day (RPD)",
            status_code=429,
            headers={"retry-after": "45200"},
            body={"error": {"message": "Rate limit reached for requests per day (RPD)"}},
            provider="groq"
        ),
        ProviderResponse(text="Resp 4 from Gemini-Key-1 (Fallback)", tokens_in=25, tokens_out=12),
        ProviderResponse(text="Resp 5 from Gemini-Key-1", tokens_in=25, tokens_out=12),
    ]

    call_index = 0

    def mock_burst_sender(provider_name, model, api_key, prompt, **kwargs):
        nonlocal call_index
        item = simulated_responses[call_index]
        call_index += 1
        print(f"  -> Attempting Provider='{provider_name}' Model='{model}' Key='{api_key[:16]}...'")
        if isinstance(item, Exception):
            print(f"     [!] Encountered: {type(item).__name__} - {item}")
            raise item
        return item

    burst_cooldown_mgr = CooldownManager(state_file=Path(temp_dir) / "burst_cd.json")

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
                cooldown_mgr=burst_cooldown_mgr,
            )
            print(f"  [+] Returned: \"{res}\"")

    print("\n--- Key Usage Table (key_usage) ---")
    conn = get_db_connection(demo_db)
    for row in conn.execute("SELECT provider, key_id, date, requests_used FROM key_usage"):
        print(f"  Provider: {row['provider']:<8} | Key: {row['key_id']:<35} | Date: {row['date']} | Used: {row['requests_used']}")

    print("\n--- LLM Call Ledger (llm_call_log) ---")
    for row in conn.execute("SELECT call_id, provider, model, purpose, tokens_in, tokens_out FROM llm_call_log"):
        print(f"  Call: {row['call_id'][:8]}... | Provider: {row['provider']:<8} | Model: {row['model']:<25} | In: {row['tokens_in']} | Out: {row['tokens_out']}")

    conn.close()
    shutil.rmtree(temp_dir, ignore_errors=True)
    print("\nBurst demonstration completed successfully.")


if __name__ == "__main__":
    print("Running DevMem LLM Router Test Suite (M1 Hardened)...")
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestKeyPool))
    suite.addTests(loader.loadTestsFromTestCase(TestClassifierWithFixtures))
    suite.addTests(loader.loadTestsFromTestCase(TestCircuitBreakerAndRegression))
    suite.addTests(loader.loadTestsFromTestCase(TestTokenBudgetAndPinning))
    suite.addTests(loader.loadTestsFromTestCase(TestRouterRotationAndFallback))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    if result.wasSuccessful():
        print(f"\n[+] All {result.testsRun} router tests passed successfully!")
    else:
        print(f"\n[-] Router tests failed ({len(result.failures)} failures, {len(result.errors)} errors).")
        sys.exit(1)

    run_controlled_burst_demonstration()
