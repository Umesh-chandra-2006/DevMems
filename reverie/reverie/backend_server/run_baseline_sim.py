"""
DevMem-Agents: Baseline Simulation Runner for Phase 2 Validation.
Forks the 3-agent Smallville simulation (Isabella Rodriguez, Klaus Mueller, Maria Lopez)
and runs simulation steps end-to-end entirely through the DevMem LLM Router.
"""

import datetime
import json
import os
from pathlib import Path
import shutil
import sys
import time

# Ensure backend_server directory is in sys.path and is current working directory
backend_dir = Path(__file__).resolve().parent
os.chdir(str(backend_dir))
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Configure stdout and stderr for UTF-8 on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Ensure devmem package root is in sys.path
project_root = backend_dir.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from utils import fs_storage, fs_temp_storage
from reverie import ReverieServer
from devmem.router.key_pool import get_db_connection


def step_environment_bridge(sim_folder: str, step: int):
    """
    Read movement/{step-1}.json and write environment/{step}.json,
    mirroring the Django frontend's update_environment behavior headlessly.
    """
    prev_move_file = f"{sim_folder}/movement/{step - 1}.json"
    target_env_file = f"{sim_folder}/environment/{step}.json"

    if os.path.exists(target_env_file):
        return

    if not os.path.exists(prev_move_file):
        raise FileNotFoundError(f"Missing previous movement file: {prev_move_file}")

    with open(prev_move_file, "r", encoding="utf-8") as f:
        move_data = json.load(f)

    personas = move_data.get("persona", {})
    env_data = {}
    for p_name, p_info in personas.items():
        coords = p_info.get("movement", [0, 0])
        env_data[p_name] = {
            "maze": "the_ville",
            "x": coords[0],
            "y": coords[1],
        }

    with open(target_env_file, "w", encoding="utf-8") as f:
        json.dump(env_data, f, indent=2)


def run_baseline_test(steps: int = 3, sim_name: str = "baseline_validation_run"):
    print("=" * 70)
    print("DEVMEM-AGENTS: PHASE 2 BASELINE SIMULATION VALIDATION")
    print(f"Simulation: {sim_name} | Steps: {steps} | Condition: baseline")
    print("=" * 70)

    sim_folder = f"{fs_storage}/{sim_name}"
    # Clean up previous test run if exists
    if os.path.exists(sim_folder):
        print(f"Removing existing test simulation folder: {sim_folder}")
        shutil.rmtree(sim_folder, ignore_errors=True)

    os.environ["MEMORY_MODE"] = "baseline"

    print("\n[1/3] Initializing ReverieServer from 'base_the_ville_isabella_maria_klaus'...")
    rs = ReverieServer("base_the_ville_isabella_maria_klaus", sim_name)
    os.makedirs(f"{sim_folder}/movement", exist_ok=True)
    print(f"  Loaded {len(rs.personas)} personas: {list(rs.personas.keys())}")
    print(f"  Simulation start time: {rs.curr_time}")

    print(f"\n[2/3] Executing {steps} simulation steps...")
    for s in range(steps):
        current_step = rs.step
        print(f"\n--- Running Step {current_step} (Game Clock: {rs.curr_time.strftime('%H:%M:%S')}) ---")

        # Ensure environment file for this step exists
        if current_step > 0:
            step_environment_bridge(sim_folder, current_step)

        # Run 1 step
        rs.start_server(1)

        # Read and display movements & observed agent behavior
        move_file = f"{sim_folder}/movement/{current_step}.json"
        if os.path.exists(move_file):
            with open(move_file, "r", encoding="utf-8") as f:
                move_data = json.load(f)
            personas = move_data.get("persona", {})
            for p_name, p_info in personas.items():
                desc = p_info.get("description", "No description")
                emoji = p_info.get("pronunciatio", "")
                loc = p_info.get("movement", [])
                print(f"  [Agent] {p_name:<20} | Pos: {str(loc):<10} | Action: {emoji} {desc}")

    print("\n[3/3] Saving simulation state...")
    rs.save()
    print(f"  Simulation saved to {sim_folder}")

    # Inspect LLM Call Ledger
    print("\n" + "=" * 70)
    print("LLM CALL LOG VERIFICATION (llm_call_log)")
    print("=" * 70)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT call_id, provider, model, purpose, condition, tokens_in, tokens_out, created_at
        FROM llm_call_log
        WHERE condition = 'baseline'
        ORDER BY created_at DESC
        LIMIT 20
    """)
    rows = cursor.fetchall()
    print(f"Found {len(rows)} recent baseline LLM call(s) in SQLite database:")
    for r in rows:
        print(f"  ID: {r['call_id'][:8]}... | Provider: {r['provider']:<6} | Model: {r['model']:<22} | Purpose: {r['purpose']:<20} | Condition: {r['condition']} | In: {r['tokens_in']:<4} | Out: {r['tokens_out']:<3}")

    cursor.execute("SELECT COUNT(*), SUM(tokens_in), SUM(tokens_out) FROM llm_call_log WHERE condition = 'baseline'")
    total_calls, total_in, total_out = cursor.fetchone()
    print(f"\nTotal Baseline Calls: {total_calls} | Total Tokens In: {total_in} | Total Tokens Out: {total_out}")
    conn.close()

    print("\nBaseline simulation validation completed successfully!")


if __name__ == "__main__":
    run_baseline_test(steps=2)
