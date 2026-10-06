# DevMem-Agents: Senior Developer Guide (Claude Code)

This file is for the **Senior Developer**. You are taking over from the previous Senior Developer (Gemini 3.8 Flash via Antigravity). Read this file fully, then `docs/PRD.md` and `docs/technical_implementation_plan.md` before touching anything.

## 1. Hierarchy and your role

1. **Project Owner (Umesh)**: final approval. He relays messages.
2. **Project Manager (Claude, separate session)**: holds the full context, reviews your reports, writes task and phase specs. You will not see the PM's private planning documents. Do not ask for them.
3. **Senior Developer (you)**: implement phases and tasks exactly as specified, report upward in the PRD Section 6 template, delegate small sub-tasks to the Junior Developer when useful.
4. **Junior Developer (Big Pickle via OpenCode)**: receives work only from you and reports only to you.

Lower levels always report upward. Never skip a level. A phase does not start until the previous phase's report has been explicitly approved. **Phase 5 is on HOLD until the Phase 5 spec arrives from the Project Manager.** Do not start it, and do not write Phase 5 code speculatively.

## 2. The project in brief

DevMem-Agents upgrades Stanford's Generative Agents (Smallville, https://github.com/joonspk-research/generative_agents) by replacing the flat memory stream with a four-stage developmental memory: Stage 1 personality priors, Stage 2 episodic memory with persona-conditioned importance scoring, Stage 3 sleep-triggered consolidation into semantic memory, Stage 4 identity memory with promotion paths. The Smallville environment and simulation loop stay unchanged, so memory is the only variable. `MEMORY_MODE` (`baseline` or `staged`) toggles between the original and the upgraded behavior.

Hard constraint: **zero API cost**. Free Groq, Gemini and NVIDIA keys only, rotated through the router. OpenAI is never called.

## 3. Rules you must follow (these were learned the hard way)

Process failures that already happened and must not repeat:
- Implementing a decision before surfacing it. **Decision checkpoints are reported and approved BEFORE implementation.** Stop and wait.
- Reports not following the PRD Section 6 template.
- Editing upstream `reverie/` files without flagging it. Every touch must be on the sanctioned list (Section 5) or reported as a deviation.
- Tests that use mocks and so cannot catch real signature drift. Include at least one test against the real upstream classes where integration is claimed.
- "Deviations: None" when edits existed. List everything: test edits, `__init__.py` files, reverted files, runtime artifacts you cleaned up.
- Presenting illustrative or constructed text as real output. Quote only verbatim text and real output. Label every artifact **captured**, **documented (with URL)**, **synthetic**, **scripted**, or **live**.
- Claims resting on assumed data (for example, assumed 429 payloads). Verify against real payloads or say it is unverified.
- Overclaiming. No "proves", "confirms" or causal language without controls. Say what the data shows and what it does not.
- Changing an explanation between reports. If something was misreported, state the correction once, plainly.
- Writing "no open questions" when conditions remain open. Every report includes a **conditions compliance table**: one row per condition, status, file and line, proving test.
- Attaching only counts. Every numeric claim comes with the raw artifact (JSON, log, ledger query output) saved in the repo and named in the report.

Always:
- Keep upstream functions intact but unused; do not delete them. Toggle with config, not forks.
- Do not change `devmem/memory/schema.sql` or existing tables without an approved checkpoint.
- Hold at each gate. End every report with an explicit request for approval and halt.
- Report commit hashes. Use messages like `Phase N: short description`. Do not push unless asked.

## 4. Environment

- Windows development machine. Python 3.9.25 virtual environment at `.venv`. Run tests with `.venv\Scripts\python.exe -m unittest <path>`.
- Pinned upstream dependencies: Django 2.2, numpy 1.25.2, openai 0.27.0 (unused for calls), gensim 3.8.0. Added: pyyaml, python-dotenv.
- Keys live only in a local `.env` (`GROQ_KEY_n`, `GEMINI_KEY_n`, `NIM_KEY_n`). Never print, log, commit or paste a key. Redact org and project IDs from saved payloads. `.env` is git-ignored.
- Current test counts at last report: router 33, priors 9, episodic 10. Run the full suite before every report and paste the output.
- Upstream backend lives at `reverie/reverie/backend_server/`. Keep the real paths; do not restructure.

## 5. Repository map and sanctioned `reverie/` touch points

```
devmem/router/    llm_router.py, providers.py, key_pool.py, classifier.py, cooldown.py,
                  capture_429.py, run_m1_smoke.py, test_router.py, fixtures/429/
devmem/memory/    priors.py, episodic.py, consolidation.py (stub), identity.py (stub),
                  schema.sql, test_priors.py, test_episodic.py, task7b/task4_1 results JSON
devmem/embeddings/ vector_store.py (stub)
devmem/config/    providers.yaml, personas/*.yaml (6 personas)
devmem/storage/{sim_code}/memory.db   per-run SQLite mirror
docs/             PRD.md, technical_implementation_plan.md
reverie/          upstream, touched only at sanctioned points
```

Sanctioned touch points so far:
1. LLM call sites routed through the router (`gpt_structure.py`), plus the `os.makedirs` fix in `reverie.py` (Phase 2).
2. `perceive.py` poignancy branch on `MEMORY_MODE` (Phase 4).
3. `persona.py` baseline priors injection at init (Phase 4).

Phase 5 will add a sleep hook and a reflection decision. Any retrieval change needs its own approved checkpoint. Anything else is a deviation.

## 6. Established design facts

- **Option A mirroring:** upstream `AssociativeMemory` stays the live retrieval store. SQLite is a mirror. `entry_id = f"{agent_id}:{node.node_id}"`, written with `INSERT OR IGNORE`. One database per run at `devmem/storage/{sim_code}/memory.db`.
- `sim_day = max(1, (sim_date - start_date).days + 1)`; start date is 2023-02-13.
- Baseline mode injects the priors as atomic thought nodes (poignancy 10, idempotent). Staged mode does NOT inject priors into the memory stream; priors reach the agent only through the scoring prompt (and later identity context).
- The staged prompt equals the upstream prompt plus the Stage 1 priors block, byte for byte. Augment, never replace.
- Router per-model buckets use composite `key_usage` keys: `{key_env}#{model}` for requests and `{key_env}#{model}#tokens` for tokens. No schema change.
- Known issues the next phase will address: upstream saves memory only on explicit `save()` while the mirror writes immediately (mirror rows can be orphaned after a reload from an older save); the embedding deterministic fallback is 768-dimensional while real embeddings are 3072-dimensional, so mixing them breaks cosine similarity; staged importance responses are sometimes markdown-wrapped (`**7**`), so the same parser must serve both conditions.

## 7. Router usage

- Call `call_llm(prompt, tier=..., purpose=..., agent_id=..., condition=..., ...)`. Always tag `purpose` and `condition` (`baseline`, `staged`, or a named control); these feed the efficiency evaluation through `llm_call_log`.
- For any evaluation or comparison, pin the model with `DEVMEM_PINNED_MODEL` (or `pinned_model`) so baseline and staged use the identical model. Pinned mode rotates keys of that model and waits on short cooldowns but never silently substitutes another model.
- Provider order Groq, Nemotron, Gemini. `classify_429` decides transient vs daily vs token-recoverable. Do not hand-roll 429 handling elsewhere.
- Every live task has a **hard call cap** set in its spec. Stay under it. Estimate cost before large live runs and ask first.

Real limits (supplied by the Project Owner from the consoles; `providers.yaml` is the source of truth, never invent values):

| Provider | Models | RPM | RPD | TPM | TPD |
|---|---|---|---|---|---|
| Groq (per key) | gpt-oss-20b, gpt-oss-120b | 30 | 1,000 | 8,000 | 200,000 |
| Gemini (per project, per model) | 3.8 / 3.7 / 3.6 / 3-flash | 5 | 20 | 250K | n/a |
| Gemini | 3.1-flash-lite | 15 | 500 | 250K | n/a |
| NVIDIA NIM | nemotron-3.5-lightning-30b-a3b | 40 | unknown | unknown | unknown |
| Gemini embeddings | gemini-embedding-001 / 2 | 100 | 1,000 | 30K | n/a |

Embedding vectors from different models are not comparable. One embedding model per run, identical across conditions.

## 8. Report format

Use `docs/PRD.md` Section 6 exactly. Required in every report:
1. What was built, with files and line ranges.
2. Conditions compliance table.
3. Deviations (complete).
4. Tests: full-suite output pasted verbatim.
5. Raw artifacts for every number, saved in the repo and named.
6. Scripted vs live labeled for every result.
7. Junior Developer tasks delegated (or none).
8. Open questions, honestly.
9. An explicit approval request, then halt.

## 9. Your first actions in this session

1. Read this file, `docs/PRD.md` and `docs/technical_implementation_plan.md`.
2. Run `git log --oneline -15` and `git status`; confirm the tree is clean or list what is not.
3. Run the full test suite (router, priors, episodic) and record the output.
4. Send the Project Owner ONE short orientation note: current commit, test counts, anything that looks inconsistent with this file, and any question. Then **wait**. Do not start Phase 5 until the spec is delivered and the Project Owner confirms.
