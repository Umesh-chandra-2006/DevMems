"""
devmem/memory/run_phase4_task7b.py

Phase 4 Task 7b: Live Differential Test between Baseline and Staged Memory Scoring.
- Model: Pinned to openai/gpt-oss-20b (DEVMEM_PINNED_MODEL)
- Hard Cap: Exactly 150 calls (25 events x 2 conditions x 3 repeats = 150)
- Event Mix:
    * 10 Mundane events (daily routine, background noise)
    * 8 Social-Friction events (tailored to intersect Isabella's priors)
    * 4 Emotionally Pivotal events (unexpected bad news, community milestones)
    * 3 Chat events (dialogue observations using kind="chat")
- Analyzes:
    * Mean score and spread (min, max, stdev) per event across 3 repeats
    * Token overhead of Stage 1 priors block in staged mode
    * llm_call_log audit
"""

from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sqlite3
import sys
import time
from typing import Any, Dict, List

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Enforce model pinning to openai/gpt-oss-20b for Task 7b
os.environ["DEVMEM_PINNED_MODEL"] = "openai/gpt-oss-20b"

from devmem.memory.episodic import (
    build_staged_prompt,
    get_upstream_prompt,
    parse_importance_score,
)
from devmem.memory.priors import get_prompt_context
from devmem.router.llm_router import call_llm
from devmem.router.key_pool import DEFAULT_DB_PATH, get_db_connection

AGENT_ID = "Isabella Rodriguez"

# 25 Curated Events: 10 Mundane, 8 Social Friction, 4 Emotionally Pivotal, 3 Chat
EVENTS = [
    # --- 10 MUNDANE EVENTS ---
    {
        "id": "M01",
        "category": "mundane",
        "kind": "event",
        "desc": "Isabella makes her bed in the morning.",
        "obs": "Isabella Rodriguez makes her bed in the morning bedroom.",
    },
    {
        "id": "M02",
        "category": "mundane",
        "kind": "event",
        "desc": "Isabella wipes down the cafe counter.",
        "obs": "Isabella Rodriguez wipes down the wooden counter at Hobbs Cafe with a damp cloth.",
    },
    {
        "id": "M03",
        "category": "mundane",
        "kind": "event",
        "desc": "Empty refrigerator observation.",
        "obs": "refrigerator door is closed and quiet in the cafe kitchen.",
    },
    {
        "id": "M04",
        "category": "mundane",
        "kind": "event",
        "desc": "Placing cups on drying rack.",
        "obs": "Isabella Rodriguez puts clean coffee mugs onto the wire drying rack.",
    },
    {
        "id": "M05",
        "category": "mundane",
        "kind": "event",
        "desc": "Checking the cafe wall clock.",
        "obs": "Isabella Rodriguez glances at the clock on the cafe wall showing 8:15 AM.",
    },
    {
        "id": "M06",
        "category": "mundane",
        "kind": "event",
        "desc": "Sweeping the cafe entryway.",
        "obs": "Isabella Rodriguez sweeps dry leaves away from the entryway of Hobbs Cafe.",
    },
    {
        "id": "M07",
        "category": "mundane",
        "kind": "event",
        "desc": "Bedroom closet door is closed.",
        "obs": "closet door is shut in the bedroom hallway.",
    },
    {
        "id": "M08",
        "category": "mundane",
        "kind": "event",
        "desc": "Restocking napkin dispensers.",
        "obs": "Isabella Rodriguez restocks paper napkins in the cafe table dispensers.",
    },
    {
        "id": "M09",
        "category": "mundane",
        "kind": "event",
        "desc": "Turning off the water faucet.",
        "obs": "Isabella Rodriguez turns off the sink faucet after washing a spoon.",
    },
    {
        "id": "M10",
        "category": "mundane",
        "kind": "event",
        "desc": "Dusty front window pane.",
        "obs": "the front display window of Hobbs Cafe is slightly dusty in the morning light.",
    },

    # --- 8 SOCIAL-FRICTION EVENTS (Targeting Isabella's Priors) ---
    {
        "id": "SF01",
        "category": "social_friction",
        "kind": "event",
        "desc": "Customer accuses Isabella of shortchanging (Conflict/Harmony).",
        "obs": "A regular customer bluntly accuses Isabella of shortchanging them at the register and demands an immediate apology in front of other patrons.",
    },
    {
        "id": "SF02",
        "category": "social_friction",
        "kind": "event",
        "desc": "Klaus loudly insults Maria's music (Harmony/Smoothing).",
        "obs": "Klaus Mueller loudly criticizes Maria Lopez's musical performance in the cafe lounge while others watch awkwardly.",
    },
    {
        "id": "SF03",
        "category": "social_friction",
        "kind": "event",
        "desc": "Newcomer acts cold and refuses greeting (Community Frustration).",
        "obs": "A newcomer in town acts distant and cold, actively refusing to exchange greetings or introduce themselves to neighbors at the cafe.",
    },
    {
        "id": "SF04",
        "category": "social_friction",
        "kind": "event",
        "desc": "Pressure to deliver hurtful truth (Harmony above Honesty).",
        "obs": "Arthur demands that Isabella tell a mutual friend an uncomfortable truth about their flawed project that will ruin their evening.",
    },
    {
        "id": "SF05",
        "category": "social_friction",
        "kind": "event",
        "desc": "Patron incites heated political argument (Conflict Avoidance).",
        "obs": "A customer begins an aggressive political argument at the cafe counter, trying to force Isabella to take a controversial side.",
    },
    {
        "id": "SF06",
        "category": "social_friction",
        "kind": "event",
        "desc": "Stranger asks to borrow money (Trusting Strangers).",
        "obs": "A complete stranger approaches Isabella at the cafe asking to borrow twenty dollars for travel without any identification or collateral.",
    },
    {
        "id": "SF07",
        "category": "social_friction",
        "kind": "event",
        "desc": "Patrons fight over table seating (Conflict/Smoothing).",
        "obs": "Two cafe patrons get into a loud, escalating shouting match over a spilled drink and disputed table seating.",
    },
    {
        "id": "SF08",
        "category": "social_friction",
        "kind": "event",
        "desc": "Neighbor aggressively complains about cafe noise (Conflict/Harmony).",
        "obs": "A neighboring shopkeeper angrily enters Hobbs Cafe, slamming the counter and threatening to file formal complaints over morning music.",
    },

    # --- 4 EMOTIONALLY PIVOTAL EVENTS ---
    {
        "id": "EP01",
        "category": "emotionally_pivotal",
        "kind": "event",
        "desc": "Cafe lease termination notice (Bad News/Immediate Fixing).",
        "obs": "The landlord delivers a formal notice informing Isabella that Hobbs Cafe's commercial lease will not be renewed and the cafe must vacate in thirty days.",
    },
    {
        "id": "EP02",
        "category": "emotionally_pivotal",
        "kind": "event",
        "desc": "Close friend relocates overseas permanently (Alone Uneasiness).",
        "obs": "A longtime close friend tearfully tells Isabella they are permanently moving to another continent tomorrow and won't be returning.",
    },
    {
        "id": "EP03",
        "category": "emotionally_pivotal",
        "kind": "event",
        "desc": "Hobbs Cafe wins Community Pillar Award (Community Value).",
        "obs": "The town council announces that Hobbs Cafe has won the Oakville Community Pillar Award for bringing neighbors together.",
    },
    {
        "id": "EP04",
        "category": "emotionally_pivotal",
        "kind": "event",
        "desc": "Severe pipe leak destroys coffee inventory (Bad News Reaction).",
        "obs": "Isabella walks into the back storage room to discover a burst pipe has flooded the floor and ruined the entire month's premium roast inventory.",
    },

    # --- 3 CHAT EVENTS (Dialogue observations via kind="chat") ---
    {
        "id": "CH01",
        "category": "chat",
        "kind": "chat",
        "desc": "Morning coffee order banter with Klaus.",
        "obs": '[Isabella Rodriguez]: "Good morning Klaus! Can I pour your usual dark roast today?" -- [Klaus Mueller]: "Morning Isabella. Yes, and please ensure the cup is clean." -- [Isabella Rodriguez]: "Of course Klaus, coming right up with a warm smile!"',
    },
    {
        "id": "CH02",
        "category": "chat",
        "kind": "chat",
        "desc": "Comforting Maria Lopez after criticism (Smoothing/Harmony).",
        "obs": '[Maria Lopez]: "Isabella, Klaus said my recital piece was dreadful and everyone agreed." -- [Isabella Rodriguez]: "Oh Maria, please pay no mind to harsh words! Your music filled this cafe with warmth and joy, and everyone loved hearing you play."',
    },
    {
        "id": "CH03",
        "category": "chat",
        "kind": "chat",
        "desc": "Urgent talk with landlord on repairs (Immediate Fixing/Bad News).",
        "obs": '[Landlord]: "Isabella, the foundation inspection failed and we may need to shut the building down this week." -- [Isabella Rodriguez]: "Oh no, please tell me what contractors we can call! I will coordinate the emergency repairs today so we can keep our community space open!"',
    },
]

def calculate_stats(scores: List[int]) -> Dict[str, float]:
    n = len(scores)
    if n == 0:
        return {"mean": 0.0, "min": 0.0, "max": 0.0, "stdev": 0.0}
    mean = sum(scores) / n
    variance = sum((x - mean) ** 2 for x in scores) / n  # population variance or sample variance
    stdev = math.sqrt(variance)
    return {
        "mean": round(mean, 2),
        "min": min(scores),
        "max": max(scores),
        "stdev": round(stdev, 2),
    }

def run_task7b():
    print("=" * 80)
    print("PHASE 4 TASK 7B: LIVE DIFFERENTIAL TEST (BASELINE vs STAGED)")
    print(f"Model: {os.environ.get('DEVMEM_PINNED_MODEL')}")
    print(f"Total Events: {len(EVENTS)} (10 mundane, 8 social friction, 4 emotionally pivotal, 3 chat)")
    print(f"Conditions: baseline (3 repeats), staged (3 repeats)")
    print(f"Total Calls Cap: {len(EVENTS) * 2 * 3} calls (Hard Cap: 150)")
    print("=" * 80)

    test_start_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # Storage for results
    # event_id -> condition -> list of (score, tokens_in, tokens_out)
    results: Dict[str, Dict[str, List[Dict[str, Any]]]] = {
        ev["id"]: {"baseline": [], "staged": []} for ev in EVENTS
    }

    call_count = 0

    # Run 3 repeats for each condition
    for repeat in range(1, 4):
        print(f"\n>>> BEGIN REPEAT {repeat}/3 <<<")
        for condition in ["baseline", "staged"]:
            print(f"\n--- Testing Condition: '{condition}' (Repeat {repeat}) ---")
            for ev in EVENTS:
                call_count += 1
                ev_id = ev["id"]
                kind = ev["kind"]
                obs = ev["obs"]

                if condition == "baseline":
                    prompt = get_upstream_prompt(AGENT_ID, obs, kind=kind)
                else:
                    prompt = build_staged_prompt(AGENT_ID, obs, kind=kind)

                print(f"[{call_count:03d}/150] Rep {repeat} | {condition:<8} | {ev_id} ({ev['category']}): ", end="", flush=True)

                raw_resp = call_llm(
                    prompt=prompt,
                    tier="fast",
                    purpose="importance_scoring",
                    agent_id=AGENT_ID,
                    condition=condition,
                    sim_day=repeat,
                    return_obj=True,
                )

                score = parse_importance_score(raw_resp.text)
                t_in = raw_resp.tokens_in or 0
                t_out = raw_resp.tokens_out or 0

                results[ev_id][condition].append({
                    "score": score,
                    "tokens_in": t_in,
                    "tokens_out": t_out,
                    "raw_resp": raw_resp.text.strip(),
                })

                print(f"Score={score} (In={t_in}, Out={t_out})")

    print("\n" + "=" * 80)
    print("ALL 150 INFERENCE CALLS COMPLETED SUCCESSFULLY.")
    print("=" * 80)

    # -------------------------------------------------------------
    # 1. SCORE COMPARISON TABLE
    # -------------------------------------------------------------
    print("\n### 1. IMPORTANCE SCORE COMPARISON: BASELINE vs STAGED (3 Repeats)")
    print(f"{'ID':<5} | {'Category':<18} | {'Baseline (M±SD)':<16} | {'Staged (M±SD)':<16} | {'Score Shift':<12} | {'Description'}")
    print("-" * 105)

    category_shifts: Dict[str, List[float]] = {}

    for ev in EVENTS:
        ev_id = ev["id"]
        cat = ev["category"]
        b_scores = [x["score"] for x in results[ev_id]["baseline"]]
        s_scores = [x["score"] for x in results[ev_id]["staged"]]

        b_stat = calculate_stats(b_scores)
        s_stat = calculate_stats(s_scores)
        diff = round(s_stat["mean"] - b_stat["mean"], 2)

        category_shifts.setdefault(cat, []).append(diff)

        b_str = f"{b_stat['mean']:.1f} ± {b_stat['stdev']:.1f}"
        s_str = f"{s_stat['mean']:.1f} ± {s_stat['stdev']:.1f}"
        shift_str = f"{diff:+.2f}"

        print(f"{ev_id:<5} | {cat:<18} | {b_str:<16} | {s_str:<16} | {shift_str:<12} | {ev['desc']}")

    print("\n### Mean Shift by Category:")
    for cat, diffs in category_shifts.items():
        avg_shift = sum(diffs) / len(diffs)
        print(f"  * {cat:<20}: {avg_shift:+.2f} points (across {len(diffs)} events)")

    # -------------------------------------------------------------
    # 2. TOKEN OVERHEAD ANALYSIS
    # -------------------------------------------------------------
    print("\n" + "=" * 80)
    print("### 2. PRIORS TOKEN OVERHEAD PER STAGED CALL")
    print("=" * 80)

    baseline_tokens_in = []
    staged_tokens_in = []
    deltas = []

    for ev in EVENTS:
        ev_id = ev["id"]
        for b_item, s_item in zip(results[ev_id]["baseline"], results[ev_id]["staged"]):
            b_in = b_item["tokens_in"]
            s_in = s_item["tokens_in"]
            delta = s_in - b_in
            baseline_tokens_in.append(b_in)
            staged_tokens_in.append(s_in)
            deltas.append(delta)

    avg_b = sum(baseline_tokens_in) / len(baseline_tokens_in)
    avg_s = sum(staged_tokens_in) / len(staged_tokens_in)
    avg_delta = sum(deltas) / len(deltas)

    print(f"Mean Baseline Tokens In : {avg_b:.1f} tokens")
    print(f"Mean Staged Tokens In   : {avg_s:.1f} tokens")
    print(f"Mean Priors Overhead    : {avg_delta:+.1f} tokens per staged prompt (+{round((avg_delta/avg_b)*100, 1)}%)")
    print(f"Total Token Overhead    : {sum(deltas)} tokens across 75 staged calls")

    # -------------------------------------------------------------
    # 3. LLM CALL LOG SUMMARY
    # -------------------------------------------------------------
    print("\n" + "=" * 80)
    print("### 3. LLM CALL LEDGER AUDIT (llm_call_log)")
    print("=" * 80)

    conn = get_db_connection(DEFAULT_DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT condition, COUNT(*) as cnt, SUM(tokens_in) as tot_in, SUM(tokens_out) as tot_out
            FROM llm_call_log
            WHERE created_at >= ? AND purpose = 'importance_scoring'
            GROUP BY condition
        """, (test_start_iso,))
        summary_rows = cursor.fetchall()
        print("Summary of logged calls in Task 7b run:")
        for sr in summary_rows:
            print(f"  Condition: {sr['condition']:<10} | Calls: {sr['cnt']:<4} | Tokens In: {sr['tot_in']:<6} | Tokens Out: {sr['tot_out']:<5}")
    finally:
        conn.close()

    # Save detailed JSON artifact
    out_file = REPO_ROOT / "devmem" / "memory" / "task7b_differential_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "test_start_iso": test_start_iso,
            "pinned_model": os.environ.get("DEVMEM_PINNED_MODEL"),
            "event_results": results,
            "category_shifts": category_shifts,
            "token_overhead": {
                "mean_baseline_tokens_in": avg_b,
                "mean_staged_tokens_in": avg_s,
                "mean_priors_overhead": avg_delta,
            }
        }, f, indent=2)
    print(f"\n[+] Detailed results persisted to {out_file}")

if __name__ == "__main__":
    run_task7b()
