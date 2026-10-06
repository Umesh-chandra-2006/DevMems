"""
devmem/router/run_m1_smoke.py

Executes a live router smoke test (<= 10 calls) tagged condition="m1_smoke"
against live LLM providers.
Condition 8: Covers Gemini (gemini-3.1-flash-lite), pinned mode, and unpinned fast tier.
"""

from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import sys

# Ensure devmem is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from devmem.router.llm_router import call_llm
from devmem.router.key_pool import DEFAULT_DB_PATH, get_db_connection

def run_smoke():
    print("=" * 70)
    print("STARTING ROUTER M1 LIVE SMOKE CHECK (<= 10 calls, condition='m1_smoke')")
    print("Covers Gemini (gemini-3.1-flash-lite), Pinned Groq, and Unpinned Fast Tier")
    print("=" * 70)

    test_calls = [
        # 1. Pinned Groq
        {
            "desc": "Groq Pinned 1 (openai/gpt-oss-20b)",
            "prompt": "Respond with exactly one word: 'GROQ_OK'.",
            "pinned_model": "openai/gpt-oss-20b",
            "tier": "fast",
        },
        {
            "desc": "Groq Pinned 2 (openai/gpt-oss-20b)",
            "prompt": "Respond with exactly one word: 'GROQ_CONFIRMED'.",
            "pinned_model": "openai/gpt-oss-20b",
            "tier": "fast",
        },
        # 2. Pinned Gemini (gemini-3.1-flash-lite)
        {
            "desc": "Gemini Pinned 1 (gemini-3.1-flash-lite)",
            "prompt": "Respond with exactly one word: 'GEMINI_OK'.",
            "pinned_model": "gemini-3.1-flash-lite",
            "tier": "fast",
        },
        {
            "desc": "Gemini Pinned 2 (gemini-3.1-flash-lite)",
            "prompt": "Respond with exactly one word: 'GEMINI_CONFIRMED'.",
            "pinned_model": "gemini-3.1-flash-lite",
            "tier": "fast",
        },
        # 3. Unpinned Fast Tier
        {
            "desc": "Unpinned Fast Tier 1",
            "prompt": "Respond with exactly one word: 'FAST_OK'.",
            "pinned_model": None,
            "tier": "fast",
        },
        {
            "desc": "Unpinned Fast Tier 2",
            "prompt": "Respond with exactly one word: 'FAST_CONFIRMED'.",
            "pinned_model": None,
            "tier": "fast",
        },
    ]

    smoke_start_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    for idx, tc in enumerate(test_calls, start=1):
        print(f"\n[Call {idx}/{len(test_calls)}] {tc['desc']}...")
        try:
            resp = call_llm(
                prompt=tc["prompt"],
                tier=tc["tier"],
                pinned_model=tc["pinned_model"],
                purpose="m1_smoke",
                agent_id="smoke_agent",
                condition="m1_smoke",
                sim_day=1,
            )
            print(f"  [+] Response: {resp.strip()}")
        except Exception as e:
            print(f"  [-] Call failed: {type(e).__name__}: {e}")

    print("\n" + "=" * 70)
    print("SMOKE CHECK LEDGER AUDIT (llm_call_log for condition='m1_smoke')")
    print("=" * 70)

    conn = get_db_connection(DEFAULT_DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT call_id, provider, model, purpose, tokens_in, tokens_out, condition, created_at
            FROM llm_call_log
            WHERE condition = 'm1_smoke'
            ORDER BY created_at DESC
            LIMIT 6
        """)
        rows = cursor.fetchall()
        rows = list(reversed(rows))
        print(f"Verified {len(rows)} calls in llm_call_log:\n")
        header = f"{'Call ID':<10} | {'Provider':<10} | {'Model':<24} | {'Purpose':<12} | {'In':<4} | {'Out':<4} | {'Created At'}"
        print(header)
        print("-" * len(header))
        for r in rows:
            print(f"{r['call_id'][:8]:<10} | {r['provider']:<10} | {r['model']:<24} | {r['purpose']:<12} | {r['tokens_in']:<4} | {r['tokens_out']:<4} | {r['created_at']}")
    finally:
        conn.close()

if __name__ == "__main__":
    run_smoke()
