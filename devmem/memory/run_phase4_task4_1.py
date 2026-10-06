"""
devmem/memory/run_phase4_task4_1.py

Phase 4 Task 4.1: Control Experiments for Personality-Conditioned Importance Scoring.
- Model: Pinned to openai/gpt-oss-20b (DEVMEM_PINNED_MODEL)
- Hard Cap: Exactly 150 calls (25 events x 2 controls x 3 repeats = 150)
- Controls Evaluated:
    * condition="control_mismatch": Wolfgang Schulz's priors injected on Isabella's events
    * condition="control_filler": Neutral factual infrastructure text of matching length (110 words, ~126 tokens)
- Evaluates:
    * Per-event means and spread (min, max, stdev) across 3 repeats
    * Comparative shifts against baseline and staged results from Task 7b
    * Total token overhead (input + output)
"""

from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any, Dict, List

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Enforce model pinning
os.environ["DEVMEM_PINNED_MODEL"] = "openai/gpt-oss-20b"

from devmem.memory.episodic import (
    get_upstream_prompt,
    parse_importance_score,
)
from devmem.memory.priors import get_prompt_context
from devmem.router.llm_router import call_llm
from devmem.router.key_pool import DEFAULT_DB_PATH, get_db_connection

AGENT_ID = "Isabella Rodriguez"

# Wolfgang Schulz priors block (mismatch control)
WOLFGANG_PRIORS = get_prompt_context("Wolfgang Schulz")

# Neutral factual filler block (110 words, ~126 tokens, zero personality/affective valence)
NEUTRAL_FILLER = """General background notes on town infrastructure:
- The municipal water distribution system was established thirty years ago and connects all central public buildings.
- Commercial properties along the main avenue maintain standard wooden architectural facades dating from the early settlement.
- The local public library maintains reference catalogs covering historical municipal records and district land surveys.
- Standard business operating hours for commercial establishments typically run from early morning until late afternoon.
- Residential parcels are divided into rectangular lots bordered by asphalt sidewalks and stone masonry drainage gutters.
- Seasonal weather patterns bring moderate rainfall during late winter followed by mild and overcast spring mornings.
- The public transit schedule operates four fixed routes connecting residential neighborhoods with downtown commercial plazas."""

# Exact 25 events from Task 7b
EVENTS = [
    {"id": "M01", "category": "mundane", "kind": "event", "desc": "Isabella makes her bed in the morning.", "obs": "Isabella Rodriguez makes her bed in the morning bedroom."},
    {"id": "M02", "category": "mundane", "kind": "event", "desc": "Isabella wipes down the cafe counter.", "obs": "Isabella Rodriguez wipes down the wooden counter at Hobbs Cafe with a damp cloth."},
    {"id": "M03", "category": "mundane", "kind": "event", "desc": "Empty refrigerator observation.", "obs": "refrigerator door is closed and quiet in the cafe kitchen."},
    {"id": "M04", "category": "mundane", "kind": "event", "desc": "Placing cups on drying rack.", "obs": "Isabella Rodriguez puts clean coffee mugs onto the wire drying rack."},
    {"id": "M05", "category": "mundane", "kind": "event", "desc": "Checking the cafe wall clock.", "obs": "Isabella Rodriguez glances at the clock on the cafe wall showing 8:15 AM."},
    {"id": "M06", "category": "mundane", "kind": "event", "desc": "Sweeping the cafe entryway.", "obs": "Isabella Rodriguez sweeps dry leaves away from the entryway of Hobbs Cafe."},
    {"id": "M07", "category": "mundane", "kind": "event", "desc": "Bedroom closet door is closed.", "obs": "closet door is shut in the bedroom hallway."},
    {"id": "M08", "category": "mundane", "kind": "event", "desc": "Restocking napkin dispensers.", "obs": "Isabella Rodriguez restocks paper napkins in the cafe table dispensers."},
    {"id": "M09", "category": "mundane", "kind": "event", "desc": "Turning off the water faucet.", "obs": "Isabella Rodriguez turns off the sink faucet after washing a spoon."},
    {"id": "M10", "category": "mundane", "kind": "event", "desc": "Dusty front window pane.", "obs": "the front display window of Hobbs Cafe is slightly dusty in the morning light."},
    {"id": "SF01", "category": "social_friction", "kind": "event", "desc": "Customer accuses Isabella of shortchanging (Conflict/Harmony).", "obs": "A regular customer bluntly accuses Isabella of shortchanging them at the register and demands an immediate apology in front of other patrons."},
    {"id": "SF02", "category": "social_friction", "kind": "event", "desc": "Klaus loudly insults Maria's music (Harmony/Smoothing).", "obs": "Klaus Mueller loudly criticizes Maria Lopez's musical performance in the cafe lounge while others watch awkwardly."},
    {"id": "SF03", "category": "social_friction", "kind": "event", "desc": "Newcomer acts cold and refuses greeting (Community Frustration).", "obs": "A newcomer in town acts distant and cold, actively refusing to exchange greetings or introduce themselves to neighbors at the cafe."},
    {"id": "SF04", "category": "social_friction", "kind": "event", "desc": "Pressure to deliver hurtful truth (Harmony above Honesty).", "obs": "Arthur demands that Isabella tell a mutual friend an uncomfortable truth about their flawed project that will ruin their evening."},
    {"id": "SF05", "category": "social_friction", "kind": "event", "desc": "Patron incites heated political argument (Conflict Avoidance).", "obs": "A customer begins an aggressive political argument at the cafe counter, trying to force Isabella to take a controversial side."},
    {"id": "SF06", "category": "social_friction", "kind": "event", "desc": "Stranger asks to borrow money (Trusting Strangers).", "obs": "A complete stranger approaches Isabella at the cafe asking to borrow twenty dollars for travel without any identification or collateral."},
    {"id": "SF07", "category": "social_friction", "kind": "event", "desc": "Patrons fight over table seating (Conflict/Smoothing).", "obs": "Two cafe patrons get into a loud, escalating shouting match over a spilled drink and disputed table seating."},
    {"id": "SF08", "category": "social_friction", "kind": "event", "desc": "Neighbor aggressively complains about cafe noise (Conflict/Harmony).", "obs": "A neighboring shopkeeper angrily enters Hobbs Cafe, slamming the counter and threatening to file formal complaints over morning music."},
    {"id": "EP01", "category": "emotionally_pivotal", "kind": "event", "desc": "Cafe lease termination notice (Bad News/Immediate Fixing).", "obs": "The landlord delivers a formal notice informing Isabella that Hobbs Cafe's commercial lease will not be renewed and the cafe must vacate in thirty days."},
    {"id": "EP02", "category": "emotionally_pivotal", "kind": "event", "desc": "Close friend relocates overseas permanently (Alone Uneasiness).", "obs": "A longtime close friend tearfully tells Isabella they are permanently moving to another continent tomorrow and won't be returning."},
    {"id": "EP03", "category": "emotionally_pivotal", "kind": "event", "desc": "Hobbs Cafe wins Community Pillar Award (Community Value).", "obs": "The town council announces that Hobbs Cafe has won the Oakville Community Pillar Award for bringing neighbors together."},
    {"id": "EP04", "category": "emotionally_pivotal", "kind": "event", "desc": "Severe pipe leak destroys coffee inventory (Bad News Reaction).", "obs": "Isabella walks into the back storage room to discover a burst pipe has flooded the floor and ruined the entire month's premium roast inventory."},
    {"id": "CH01", "category": "chat", "kind": "chat", "desc": "Morning coffee order banter with Klaus.", "obs": '[Isabella Rodriguez]: "Good morning Klaus! Can I pour your usual dark roast today?" -- [Klaus Mueller]: "Morning Isabella. Yes, and please ensure the cup is clean." -- [Isabella Rodriguez]: "Of course Klaus, coming right up with a warm smile!"'},
    {"id": "CH02", "category": "chat", "kind": "chat", "desc": "Comforting Maria Lopez after criticism (Smoothing/Harmony).", "obs": '[Maria Lopez]: "Isabella, Klaus said my recital piece was dreadful and everyone agreed." -- [Isabella Rodriguez]: "Oh Maria, please pay no mind to harsh words! Your music filled this cafe with warmth and joy, and everyone loved hearing you play."'},
    {"id": "CH03", "category": "chat", "kind": "chat", "desc": "Urgent talk with landlord on repairs (Immediate Fixing/Bad News).", "obs": '[Landlord]: "Isabella, the foundation inspection failed and we may need to shut the building down this week." -- [Isabella Rodriguez]: "Oh no, please tell me what contractors we can call! I will coordinate the emergency repairs today so we can keep our community space open!"'},
]

def calculate_stats(scores: List[int]) -> Dict[str, float]:
    n = len(scores)
    if n == 0:
        return {"mean": 0.0, "min": 0.0, "max": 0.0, "stdev": 0.0}
    mean = sum(scores) / n
    variance = sum((x - mean) ** 2 for x in scores) / n
    stdev = math.sqrt(variance)
    return {
        "mean": round(mean, 2),
        "min": min(scores),
        "max": max(scores),
        "stdev": round(stdev, 2),
    }

def run_task4_1():
    print("=" * 80)
    print("TASK 4.1: CONTROL EXPERIMENTS FOR IMPORTANCE SCORING (150 CALLS CAP)")
    print(f"Model: {os.environ.get('DEVMEM_PINNED_MODEL')}")
    print("Controls: 'control_mismatch' (Wolfgang Schulz) & 'control_filler' (Neutral text)")
    print("Calls: 25 events x 2 controls x 3 repeats = 150 calls")
    print("=" * 80)

    test_start_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    results: Dict[str, Dict[str, List[Dict[str, Any]]]] = {
        ev["id"]: {"control_mismatch": [], "control_filler": []} for ev in EVENTS
    }

    call_count = 0

    for repeat in range(1, 4):
        print(f"\n>>> BEGIN CONTROL REPEAT {repeat}/3 <<<")
        for condition in ["control_mismatch", "control_filler"]:
            print(f"\n--- Testing Condition: '{condition}' (Repeat {repeat}) ---")
            for ev in EVENTS:
                call_count += 1
                ev_id = ev["id"]
                kind = ev["kind"]
                obs = ev["obs"]

                upstream_prompt = get_upstream_prompt(AGENT_ID, obs, kind=kind)
                if condition == "control_mismatch":
                    prompt = f"{upstream_prompt}\n\n{WOLFGANG_PRIORS}"
                else:
                    prompt = f"{upstream_prompt}\n\n{NEUTRAL_FILLER}"

                print(f"[{call_count:03d}/150] Rep {repeat} | {condition:<16} | {ev_id} ({ev['category']}): ", end="", flush=True)

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
    print("ALL 150 CONTROL INFERENCE CALLS COMPLETED.")
    print("=" * 80)

    # Load Task 7b results for comparative table
    task7b_file = REPO_ROOT / "devmem" / "memory" / "task7b_differential_results.json"
    task7b_data = {}
    if task7b_file.exists():
        with open(task7b_file, "r", encoding="utf-8") as f:
            task7b_data = json.load(f).get("event_results", {})

    print("\n### 4-WAY COMPARISON TABLE: BASELINE vs STAGED vs MISMATCH vs FILLER (Means ± SD)")
    header = f"{'ID':<5} | {'Category':<16} | {'Baseline (B)':<13} | {'Staged (S)':<13} | {'Mismatch (W)':<13} | {'Filler (F)':<13} | {'S - B':<7} | {'W - B':<7} | {'F - B':<7}"
    print(header)
    print("-" * len(header))

    comparison_summary: Dict[str, Any] = {}

    for ev in EVENTS:
        ev_id = ev["id"]
        cat = ev["category"]

        # Baseline & Staged
        b_scores = [x["score"] for x in task7b_data.get(ev_id, {}).get("baseline", [])] if task7b_data else []
        s_scores = [x["score"] for x in task7b_data.get(ev_id, {}).get("staged", [])] if task7b_data else []
        # Controls
        w_scores = [x["score"] for x in results[ev_id]["control_mismatch"]]
        f_scores = [x["score"] for x in results[ev_id]["control_filler"]]

        b_stat = calculate_stats(b_scores)
        s_stat = calculate_stats(s_scores)
        w_stat = calculate_stats(w_scores)
        f_stat = calculate_stats(f_scores)

        diff_s = round(s_stat["mean"] - b_stat["mean"], 2) if b_scores else 0.0
        diff_w = round(w_stat["mean"] - b_stat["mean"], 2) if b_scores else 0.0
        diff_f = round(f_stat["mean"] - b_stat["mean"], 2) if b_scores else 0.0

        b_str = f"{b_stat['mean']:.1f} ± {b_stat['stdev']:.1f}" if b_scores else "N/A"
        s_str = f"{s_stat['mean']:.1f} ± {s_stat['stdev']:.1f}" if s_scores else "N/A"
        w_str = f"{w_stat['mean']:.1f} ± {w_stat['stdev']:.1f}"
        f_str = f"{f_stat['mean']:.1f} ± {f_stat['stdev']:.1f}"

        print(f"{ev_id:<5} | {cat:<16} | {b_str:<13} | {s_str:<13} | {w_str:<13} | {f_str:<13} | {diff_s:+5.2f} | {diff_w:+5.2f} | {diff_f:+5.2f}")

        comparison_summary[ev_id] = {
            "category": cat,
            "desc": ev["desc"],
            "baseline": b_stat,
            "staged": s_stat,
            "control_mismatch": w_stat,
            "control_filler": f_stat,
            "shift_staged": diff_s,
            "shift_mismatch": diff_w,
            "shift_filler": diff_f,
        }

    # Token audit
    print("\n" + "=" * 80)
    print("### TOKEN AUDIT FOR CONTROLS (llm_call_log)")
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
        rows = cursor.fetchall()
        for r in rows:
            tot = (r["tot_in"] or 0) + (r["tot_out"] or 0)
            avg_in = round(r["tot_in"] / r["cnt"], 1) if r["cnt"] else 0
            avg_out = round(r["tot_out"] / r["cnt"], 1) if r["cnt"] else 0
            print(f"Condition: {r['condition']:<18} | Calls: {r['cnt']:<4} | In: {r['tot_in']:<6} (avg {avg_in}) | Out: {r['tot_out']:<5} (avg {avg_out}) | Total: {tot:<6}")
    finally:
        conn.close()

    # Save output
    out_file = REPO_ROOT / "devmem" / "memory" / "task4_1_control_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "test_start_iso": test_start_iso,
            "pinned_model": os.environ.get("DEVMEM_PINNED_MODEL"),
            "event_results": results,
            "comparison_summary": comparison_summary,
        }, f, indent=2)
    print(f"\n[+] Control results persisted to {out_file}")

if __name__ == "__main__":
    run_task4_1()
