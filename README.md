# DevMem-Agents

DevMem-Agents upgrades the memory of Stanford's [Generative Agents](https://github.com/joonspk-research/generative_agents) (Smallville). The flat memory stream is
replaced by a four-stage developmental memory, and everything else (the town, the agents, the simulation loop) stays as upstream, so memory is the only variable.

| Stage | What it adds |
|---|---|
| 1. Personality priors | Short persona-specific statements that reach the agent through the scoring prompt |
| 2. Episodic memory | Importance scoring conditioned on the persona, mirrored to SQLite |
| 3. Consolidation | A sleep-triggered sweep clusters similar entries (average linkage 0.82) into semantic summaries |
| 4. Identity | Traits are promoted from repeated themes (Path A) or from a single pivotal event (Path B, T = 9) and fed back into scoring |

`MEMORY_MODE=baseline` runs the original behaviour; `MEMORY_MODE=staged` runs the upgraded one. The two are compared as two arms of one experiment.

**Hard constraint: zero API cost.** Only free-tier Groq, Gemini and NVIDIA keys are used, rotated by the router. OpenAI is never called.

## Status

Phase 7 (the baseline versus staged comparison run) is prepared and has been piloted; the full runs are launched by the Project Owner's go.
Nothing in this repository is a result of the comparison. The pilot (`docs/phase7_pilot_report.md`) is a readiness check, and every report labels its
data as live, scripted, synthetic, captured, offline-captured or derived. Read `docs/CLAIMS_LEDGER.md` before quoting any number: it lists what each
artifact supports and the disclosed deviations.

## Layout

```
devmem/router/      LLM router: key pool, cooldowns, 429 classifier, model pinning, output normalizer
devmem/memory/      priors, episodic scoring, consolidation, identity, schema.sql, calibration and audit scripts
devmem/embeddings/  embedding store (one embedding model per run, cache first, fail loud)
devmem/eval/        Phase 7 harness: arm runner, supervisor, authored plan, event injector, quota gate, canary, health check
devmem/api/         read-only inspector API and web UI (React and Phaser vendored, no CDN)
devmem/config/      providers.yaml, embeddings.yaml, consolidation.yaml, identity.yaml, 6 personas
devmem/demo/        presentation notes
docs/               PRD, specs, per-phase reports with raw artifacts, pre-registration, claims ledger
reverie/            upstream Generative Agents, edited only at the sanctioned points listed in CLAUDE.md
```

## Setup (Windows)

- Python 3.9 virtual environment at `.venv`; pinned upstream dependencies: Django 2.2, numpy 1.25.2, openai 0.27.0 (never used for calls), gensim 3.8.0, plus pyyaml and python-dotenv.
- API keys live only in a local `.env` (`GROQ_KEY_n`, `GEMINI_KEY_n`, `NIM_KEY_n`). It is git-ignored. Never print, log or commit a key.
- The viewer needs a system Python with fastapi and uvicorn (see `devmem/api/REQUIREMENTS.md`).

## Common commands

Run the tests (from the repository root, venv Python):

```bash
export PYTHONPATH="reverie/reverie/backend_server;."
.venv/Scripts/python.exe -m unittest discover -s devmem -p "test_*.py" -t .
```

The HTTP API tests skip under the venv and run under the system Python: `python -m unittest devmem.api.test_api_http devmem.api.test_store devmem.api.test_movement devmem.api.test_findings`.

Open the viewer on two recorded runs (read only, no LLM call, nothing leaves the machine):

```bash
python devmem/api/serve.py --a p7pilot_staged --b p7pilot_baseline --open
```

Tabs: Town replay, Memory inspector, Cost view, Findings, Where it differs and why, Side by side, Edge cases. The Findings data is built offline from saved
artifacts by `python devmem/api/build_findings.py`.

Run one arm of the Phase 7 experiment (a free-tier run; read `docs/phase7_stop2a_report.md` and `docs/phase7_preregistration.md` first):

```bash
.venv/Scripts/python.exe -m devmem.eval.run_arm --arm staged --dry-run          # preflight only, no calls
.venv/Scripts/python.exe -m devmem.eval.supervisor --arm staged                 # supervised run, resumes after a crash or kill
.venv/Scripts/python.exe -m devmem.eval.arm_health                              # is each arm alive, paused or finished
```

`--pilot` selects the short pilot configuration. A run folder is `devmem/storage/p7_<arm>/` (git-ignored); the evidence that is committed lives under `docs/`.

## Rules the code follows

- Memory is the only variable: upstream functions stay intact and toggle by config; `reverie/` is touched only at the sanctioned points.
- Baseline and staged use the identical pinned model (`gemini-3.1-flash-lite`) and the identical normalizer.
- Every router call is tagged with `purpose` and `condition`, which feed the efficiency evaluation through the call ledger.
- A decision is reported and approved before it is implemented; each phase ends at a gate.

## Where to read next

`CLAUDE.md` (working rules), `docs/PRD.md`, `docs/phase7_preregistration.md`, `docs/CLAIMS_LEDGER.md`, `docs/phase7_pilot_report.md`, `devmem/demo/README.md`.
