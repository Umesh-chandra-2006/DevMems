# Phase 8 spec: memory inspector and recorded-simulation player (PM, 2026-10-07)

Plan source: Section 10 (React + Three.js town, inspection panel). Repo facts: upstream has a Django and Phaser viewer at `reverie/environment/frontend_server`; `devmem/api/main.py` is a 176-byte stub; no React or Three.js code exists.

## 0. Decisions already made

- The research value is the INSPECTION PANEL, not a 3D town. Keep upstream's Phaser viewer for the town if a town view is wanted. A Three.js town is optional and last.
- The panel is READ-ONLY. It reads saved run artifacts (per-run SQLite `memory.db`, ledgers, `consolidation_log.jsonl`, `identity_*.jsonl`, raw-reply logs). It never calls an LLM and never writes to a run.
- The same panel works on a recorded run (demo, presentation) and on a live run (read while it runs, SQLite in read-only mode).
- No em dashes. No keys anywhere in the frontend or in served files.
- Design palette: black and gold (owner preference). Use the frontend-design skill's principles; avoid a templated look.

## 1. Delegation

Component-level UI work may go to the Junior Developer (Big Pickle), against this spec, with the Senior Dev reviewing each component. The data API (section 2) stays with the Senior Dev.

## 2. Backend (Senior Dev): small read-only API

FastAPI under `devmem/api/`, read-only SQLite connections only. Endpoints (JSON), all take `run` (a storage run id):
- `GET /runs`: list runs found under `devmem/storage`, with agents and the sim time range.
- `GET /runs/{run}/agents`: agents with persona names.
- `GET /runs/{run}/agents/{agent}/state?t=<sim time>`: for that agent at sim time t: the Stage 1 priors; episodic entries up to t (text, importance, consolidated flag, scoring status); Stage 3 clusters and semantic summaries (with source ids) created up to t; Stage 4 traits active at t with path, sources and provenance diagnostic; the rendered identity_context at t.
- `GET /runs/{run}/timeline`: ordered events for playback (episodic entries, sleep and wake, sweeps, graduations, key calls) with sim times.
- `GET /runs/{run}/ledger/summary`: calls and tokens by purpose per sim hour per agent (the efficiency view).
- `GET /compare?a=<run>&b=<run>&agent=...`: the same agent in two runs side by side (baseline vs staged).
Tests: offline, against the Step D recording and the Stop 3 fixture run; every endpoint returns well-formed JSON; no endpoint writes; missing tables (Stage 4 off) degrade gracefully.

## 3. Frontend (React; Three.js optional)

Required views:
1. Timeline player: play and pause, scrub by sim time, event ticks colored by stage, speed control. This IS the recorded simulation for the presentation.
2. Agent memory panel at the scrubbed time: four stage columns (priors, episodic, semantic, identity). Click a semantic summary: show its source entries highlighted. Click a trait: show its sources, its path (count, same day, pivotal) and the provenance diagnostic.
3. Baseline vs staged side by side for the same agent and time.
4. Cost view: calls and tokens by purpose per sim hour, from the ledger summary.
5. Label bar always visible: run id, whether recorded or live, scripted or natural, model, normalizer on or off. Nothing may look like a result the data does not support: no "better" or "improved" wording, no aggregate scores unless the harness produced them.
Optional, last: a 3D town view using Three.js reading agent positions from the run's movement files if they exist (ask first whether the headless runner writes them; if not, do not invent positions).

## 4. Presentation mode

A single command (documented in `devmem/demo/README.md`) that starts the API and the frontend on localhost against a chosen recorded run, offline, no keys needed. Include a "live calls" panel that shows the call counter of a short live segment if one is running. Rehearsal checklist in the README.

## 5. Stops

- Stop 1: API plus 2 views (timeline player, memory panel) working on the Step D recording; screenshots. Halt for review.
- Stop 2: remaining views and presentation mode; screenshots; README. Halt.
- Optional Stop 3: Three.js town view, only if movement data exists and time remains.

## 6. Non-claims

The inspector displays what was recorded. It makes no claim about recall, coherence or efficiency. Natural versus scripted and live versus recorded are always labelled.
