# Stage 1 Persona Set — DevMem-Agents

Six agents, all reusing existing Smallville character names from the upstream `generative_agents` repo (Isabella Rodriguez, Klaus Mueller, and Maria Lopez are already validated in Phase 2's baseline run; Wolfgang Schulz, Giorgio Rossi, and Sam Moore are added here to bring the roster to six). Reusing upstream names means each agent already has a defined spatial/location fit in the map, no new world-building needed for this phase.

**Important for Senior Dev:** before wiring these into Phase 4, confirm each `agent_id` string matches the exact persona folder name used in this fork's `reverie/reverie/backend_server/.../storage/<sim>/personas/` directory. If a name doesn't match exactly, `load_priors()` won't resolve correctly. Flag any mismatch rather than silently renaming either side.

## Schema
Each file: `agent_id` (string, must match upstream persona folder name) + `priors` (4-6 entries, each a `statement` and a `category` tag). The `category` field is for traceability back to plan.md Section 7's seven categories, not required by `load_priors()` logic itself, `get_prompt_context()` only needs to read `statement`.

## Deliberate Friction Pairs
Built in per plan.md Section 7's rule that every agent needs at least one prior creating predictable friction with another agent:

- **Isabella (trusting, conflict-avoidant, harmony-first) vs. Wolfgang (direct, confrontational, honesty-first):** Isabella softens disagreements, Wolfgang pushes into them. A shared event between these two should produce visibly different importance scores and different reactions once Stage 2 is wired in.
- **Sam (achievement-driven, impatient with hesitation) vs. Klaus (deliberate, dislikes being rushed):** Sam reads Klaus's carefulness as foot-dragging; Klaus reads Sam's speed as recklessness. Good source of recurring, realistic low-grade tension.
- **Wolfgang (distrusts evasiveness) vs. Giorgio (avoids conflict, keeps things light):** Wolfgang may read Giorgio's conflict-avoidance as dishonesty; Giorgio will likely withdraw rather than engage Wolfgang directly.
- **Maria (invests deeply in a few close friendships) vs. Sam (broad, achievement-oriented socializing):** different models of what a relationship is for, a natural source of divergence if they interact repeatedly.

## Humanizing Trait Check
Per plan.md Section 7's rule that no agent is purely positive or purely negative:
- Isabella's harmony-seeking is also genuine warmth, not just conflict avoidance.
- Klaus's distrust is paired with real thoroughness and reliability once trust is earned.
- Maria's fast decisions come with genuine enthusiasm and curiosity, not recklessness for its own sake.
- Wolfgang's bluntness comes from a real commitment to honesty, not hostility.
- Giorgio's conflict avoidance is also easygoing warmth that makes him good company.
- Sam's impatience is paired with genuine initiative and follow-through, not empty ambition.

## For the Baseline Fairness Injection (Section 7's fairness control)
All six files here are the single source of truth for both conditions: `priors.py`'s `load_priors()` feeds the staged condition's prompt context, and the same file's content feeds `inject_into_baseline()` for the flat-memory condition. Do not maintain two separate copies of the same agent's personality.
