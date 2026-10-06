"""
P5.0d cost estimate (label: DERIVED, not measured). Combines
  (a) captured ledger means (docs/phase5_step0_artifacts/p5_0d_ledger_analysis.json), and
  (b) code-path call counts read from the upstream source (cited in the report), and
  (c) explicit assumptions in LOW / MID / HIGH, because no baseline run ever covered more than a few
      simulated seconds, so calls per simulated hour have NOT been measured.
Writes docs/phase5_step0_artifacts/p5_0d_cost_estimate.json.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
ART = ROOT / "docs" / "phase5_step0_artifacts"
led = json.loads((ART / "p5_0d_ledger_analysis.json").read_text())
pp = led["per_purpose_mean_tokens_gpt_oss_20b"]

plan_tok = pp["planning|baseline"]["mean_in"] + pp["planning|baseline"]["mean_out"]       # captured mean
score_tok = pp["importance_scoring|baseline"]["mean_in"] + pp["importance_scoring|baseline"]["mean_out"]
staged_score_tok = pp["importance_scoring|staged"]["mean_in"] + pp["importance_scoring|staged"]["mean_out"]

# captured day-start burst for 3 agents: the 61-call first burst in the ledger
burst = led["baseline_sim_bursts"][0]
daystart_calls_per_agent = burst["calls"] / 3
daystart_tokens_per_agent = (burst["tokens_in"] + burst["tokens_out"]) / 3

CALLS_PER_ACTION = 8      # plan.py _determine_action: sector, arena, game_object, pronunciatio, event_triple,
                          # act_obj_desc, obj pronunciatio, obj event_triple (code-read)
AWAKE_HOURS = 16
SLEEP_ACTIONS = 2
scen = {
    #            actions/h, perceive-scored events/h, chat calls per agent-hour, tokens per planning-type call
    "low":  dict(actions=3, perceive=3,  chat=0, tok=plan_tok * 0.5),
    "mid":  dict(actions=5, perceive=6,  chat=3, tok=plan_tok),
    "high": dict(actions=8, perceive=12, chat=8, tok=plan_tok * 1.3),
}
out = {"label": "derived (ledger means x code-read call counts x stated assumptions); NOT measured",
       "captured_inputs": {"planning_tokens_per_call_gpt_oss_20b": plan_tok, "scoring_tokens_per_call_baseline": score_tok,
                           "scoring_tokens_per_call_staged": staged_score_tok,
                           "daystart_burst_calls_3_agents": burst["calls"], "daystart_burst_tokens_in": burst["tokens_in"],
                           "daystart_burst_tokens_out": burst["tokens_out"],
                           "daystart_calls_per_agent": round(daystart_calls_per_agent, 1),
                           "daystart_tokens_per_agent": round(daystart_tokens_per_agent)},
       "assumptions_fixed": {"calls_per_action": CALLS_PER_ACTION, "decomp_calls_per_awake_hour": 1,
                             "awake_hours": AWAKE_HOURS, "sleep_actions_per_day": SLEEP_ACTIONS},
       "scenarios": {}}
GROQ_20B_TPD_3KEYS = 3 * 200_000
GROQ_RPD_3KEYS = 3 * 1000
for name, s in scen.items():
    plan_calls_h = 1 + s["actions"] * CALLS_PER_ACTION + s["chat"]
    score_calls_h = s["perceive"]
    tokens_h = plan_calls_h * s["tok"] + score_calls_h * score_tok
    calls_h = plan_calls_h + score_calls_h
    agent_day_calls = calls_h * AWAKE_HOURS + daystart_calls_per_agent + SLEEP_ACTIONS * CALLS_PER_ACTION
    agent_day_tokens = tokens_h * AWAKE_HOURS + daystart_tokens_per_agent + SLEEP_ACTIONS * CALLS_PER_ACTION * s["tok"]
    d3_calls, d3_tokens = agent_day_calls * 3, agent_day_tokens * 3
    out["scenarios"][name] = {
        "assumptions": s,
        "per_agent_awake_hour": {"calls": calls_h, "tokens": round(tokens_h)},
        "per_3_agents_sim_hour": {"calls": calls_h * 3, "tokens": round(tokens_h * 3)},
        "per_3_agents_sim_day": {"calls": round(d3_calls), "tokens": round(d3_tokens)},
        "groq_gpt_oss_20b_3keys_days_of_quota_per_sim_day_by_tokens": round(d3_tokens / GROQ_20B_TPD_3KEYS, 1),
        "groq_3keys_days_of_quota_per_sim_day_by_requests": round(d3_calls / GROQ_RPD_3KEYS, 1),
        "gemini_3.1_flash_lite_days_per_sim_day_1_project_500rpd": round(d3_calls / 500, 1),
    }

# Stage 3 nightly addition, per agent, for a cap of S summaries
SUM_IN, SUM_OUT = 650, 350   # ASSUMED summarization prompt/out (priors block measured at +126 tokens; <=12 entries x ~35 tokens)
night = {}
for S in (4, 6, 8):
    calls = 2 * S
    tokens = S * (SUM_IN + SUM_OUT + staged_score_tok)
    night[f"cap_{S}_summaries"] = {"llm_calls_per_agent_night": calls, "tokens_per_agent_night": round(tokens),
                                   "llm_calls_3_agents": calls * 3, "tokens_3_agents": round(tokens * 3),
                                   "embedding_requests_for_new_summaries_3_agents": S * 3,
                                   "fraction_of_one_groq_key_day_3_agents": round(tokens * 3 / 200_000, 3)}
out["stage3_nightly_addition"] = {"assumed_summarization_tokens_in_out": [SUM_IN, SUM_OUT],
                                  "scoring_call_tokens_measured_staged": staged_score_tok, "by_cap": night,
                                  "embeddings_for_clustering": "0 if clustering reuses a_mem.embeddings (every mirrored "
                                  "node is already embedded at perceive time); otherwise ceil(entries/batch) requests"}
(ART / "p5_0d_cost_estimate.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
