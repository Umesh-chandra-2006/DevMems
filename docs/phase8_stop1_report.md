PHASE: 8, memory inspector, STOP 1 (read-only API plus the timeline player and the memory panel, working on the Step D recording, with screenshots)
STATUS: Complete for Stop 1. Halting for review. Stop 2 (remaining views, presentation mode, README) has not started.

Labels: **recorded** (shown from saved run artifacts), **offline-captured**, **derived**. No em dashes. The panel is read-only, never calls an LLM, never writes to a run, shows no "better" or "improved" wording and no score the recording does not contain.

## 1. WHAT WAS BUILT

| Piece | Where |
|---|---|
| Data layer (standard library only; read-only SQLite; no network, no LLM) | `devmem/api/store.py` |
| FastAPI app, GET routes only, serves the UI | `devmem/api/main.py` (`devmem/api/__init__.py` added) |
| Frontend: timeline player and four-column memory panel, `React.createElement` only (no JSX, no compiler), black and gold | `devmem/api/web/index.html`, `style.css`, `app.js` |
| Vendored libraries (approved: react 18.3.1 and react-dom 18.3.1 production UMD, MIT) | `devmem/api/web/vendor/` with `VENDOR.md` (versions, tarball URLs, the published sha512 integrity values, the sha256 of the two extracted files, licenses) |
| Run labels for the two recordings | `docs/phase6_stepd_artifacts/run_label.json`, `docs/phase6_stop3_artifacts/run_label.json` |
| The two recordings made committable (172 KB and 106 KB mirror databases; `.gitignore` negation lines) | `docs/phase6_stepd_artifacts/memory.db`, `docs/phase6_stop3_artifacts/memory.db` |
| Tests | `devmem/api/test_store.py` (22), `devmem/api/test_api_http.py` (6, need fastapi and httpx) |
| Screenshots | `docs/phase8_stop1_artifacts/01` to `06` (PNG) |

**Download record (PM conditions):** react@18.3.1 and react-dom@18.3.1 only, from registry.npmjs.org, tarballs fetched with a plain download into a scratch folder outside the repository and discarded. The sha512 of each tarball computed locally equals the integrity value npm publishes (`sha512-wS+hAgJShR0KhEvPJArfuPVN1+Hz1t0Y6n5jLrGQbkb4urgPE/0Rve+1kMB1v/oWgHgm4WIcV+i7F2pTVj+2iQ==` for react, `sha512-5m4nQKp+rZRb09LNH59GM4BxTh9251/ylbKIbpe7TpGxfJ+9kv6BLkLBXIjjspbgbnIBNqlI23tRnTWT0snUIw==` for react-dom), checked BEFORE extracting. Extracted only `react.production.min.js` (10,751 bytes), `react-dom.production.min.js` (131,835 bytes) and the MIT LICENSE text. No npm install, no package scripts, no node_modules, package.json or lockfile; no Babel; no CDN link at runtime (the page makes zero requests outside this server: measured in the browser, 0 external resources). Nothing else was downloaded.

## 2. THE API (spec section 2; every route is GET)

| Endpoint | Returns |
|---|---|
| `GET /runs` | runs found under `devmem/storage` and the saved `docs/*` folders that hold a `memory.db`, with agents, sim time range, which stages are present and the label |
| `GET /runs/{run}/label`, `/agents` | the label bar fields; agents with persona names and priors counts |
| `GET /runs/{run}/agents/{agent}/state?t=...&diagnostics=...` | the agent at sim time t: Stage 1 priors; Stage 2 entries up to t (text, importance, consolidated-into, scoring status and trait ids when recorded); Stage 3 summaries with source ids and sweeps up to t; Stage 4 traits with path, sources, provenance diagnostic (only when asked); the rendered identity context at t |
| `GET /runs/{run}/timeline` | ordered events for playback (episodic entries, priors, sweeps, summaries, identity steps, trait graduations, and, when the run has an hourly ledger, sleep-state and ledger-window ticks) |
| `GET /runs/{run}/ledger/summary` | calls and tokens by purpose per sim hour per agent from the recorded ledger windows (used by the cost view at Stop 2) |
| `GET /compare?a=&b=&agent=&t=` | the same agent in two runs |

How the rules are enforced: every connection is `file:...?mode=ro` plus `PRAGMA query_only`; the store source contains no network or LLM import and no write statement (a test asserts it); every route is GET (a test sends POST, PUT, PATCH and DELETE to each and gets 405 and checks the recording hash is unchanged); the served files contain no key or key name; run databases with missing tables degrade to `available: false` with a reason.

**What the data does and does not give (stated, not hidden):**
- `consolidated_into` for an entry is the first summary (created at or before t) that lists it as a source; sources added by a later reinforcement appear only from the summary's own creation time in the record.
- Trait eviction is not timestamped in the database, so the state shows `active_now` (the recorded flag) and says `active_at_t` is unknown.
- Individual router calls carry no simulated time in the logs, so they appear only as per-window counts (the Step D hourly ledger). Sleep and wake come from the per-window sleeping fractions, not exact instants.
- The Step D recording has no scoring-context table (it predates it), so each entry shows "scoring context: not recorded"; the Stop 3 run shows the recorded status and the trait ids in each scoring prompt.
- Label fields come from the run's `run_label.json` or its recorded report; with neither, fields stay "unknown" and the recorded-or-live field reads "recorded (inferred: the database was not written in the last 120 s)"; a database written in the last 120 s is labelled live. Only the two recordings above have declared labels.

## 3. THE VIEWS (spec section 3, items 1, 2 and 5 at this stop)

1. **Timeline player:** play and pause, a scrubber, speed in simulated minutes per second (10, 30, 120, 600), an SVG track with one tick per recorded event colored by stage (Stage 1 ivory, Stage 2 gold, Stage 3 copper, Stage 4 teal, infrastructure grey), the selected agent's ticks bright and the others faint, a playhead, click-to-seek. Measured in the browser pane on the Stop 3 run: at speed 600 the clock advanced 24 simulated hours in 2.5 s; pause froze it; scrubbing to the end loaded the end state; every request was a GET to this server.
2. **Agent memory panel:** four stage columns at the scrubbed time (priors, episodic, semantic, identity). Click a semantic summary: its source entries are highlighted in the episodic column (and scrolled into view). Click a trait: its sources (semantic ids and event ids), its path and the provenance diagnostic (a checkbox computes it from cached embeddings only, never the network; when a vector is not cached the panel says so) are shown, and its source entries and summaries are highlighted. The exact rendered identity context at that time is shown under the identity column. Entries whose text contains "idle" can be hidden (a count is shown).
5. **Label bar:** always visible: run id, recorded or live, scripted or natural, model, normalizer, stages, label source, a READ ONLY badge, and the line "This view displays what was recorded in the run. It makes no claim about recall, coherence or efficiency."

Not at this stop (Stop 2): baseline-versus-staged side by side, the cost view, presentation mode and the README. Wording check: the UI strings contain no "better" or "improved", and the only numbers shown are recorded values (importance scores, counts, cosines from the recording or cache, token counts).

## 4. SCREENSHOTS (`docs/phase8_stop1_artifacts/`, headless Chrome, 1500 x 1500, produced from URLs the UI understands: `?run=&agent=&t=&select=&diag=&idle=`)

| File | Run, agent, time | What it shows |
|---|---|---|
| `01_stepd_isabella_0900.png` | Step D recording (natural, partial), Isabella, 13 Feb 09:00 | label bar, timeline with the playhead at 09:00, 211 entries up to that time (88 with "idle" in the text, hidden), "scoring context: not recorded", empty Stage 3 and Stage 4 columns |
| `02_stepd_isabella_end_show_idle.png` | same, 13:45, idle entries shown | the end of the recording with dimmed idle-text entries |
| `03_stepd_maria_asleep.png` | same recording, Maria, 13:00 | an agent with 8 entries who slept through the window |
| `04_stop3_night1.png` | Stop 3 fixture run, Isabella, after night 1 | one summary and no trait yet |
| `05_stop3_trait2_selected.png` | Stop 3, 17 Feb 20:00, trait_2 selected, diagnostic on | all four stages populated; the pivotal trait expanded with its source (`node_11`, event), its path, and the diagnostic reporting that the trait text embedding is not in the cache; the identity context block exactly as scored |
| `06_stop3_summary_selected.png` | Stop 3, summary `node_4` selected | the 16 source entries highlighted in the episodic column; they include the cake-decorating entries, which shows the theme mixing recorded in ledger row H6 |

Numbers visible in the screenshots are recorded values and match the Stop 3 and Step D reports (for example the 211 episodic entries up to 09:00 and the identity block, byte for byte; a test compares the rendered block with the tail of the five saved scoring prompts).

## 5. TESTS (`docs/phase8_stop1_artifacts/full_suite_output.txt`, verbatim)

```
=== devmem.router.test_router
Ran 33 tests in 4.573s
OK
=== devmem.router.test_call_counter
Ran 4 tests in 11.216s
OK
=== devmem.router.test_output_normalizer
Ran 4 tests in 0.000s
OK
=== devmem.router.test_normalizer_wiring
Ran 8 tests in 2.411s
OK
=== devmem.router.test_normalizer_rule
Ran 9 tests in 0.238s
OK
=== devmem.router.test_normalizer_call_path
Ran 7 tests in 7.003s
OK
=== devmem.memory.test_priors
Ran 9 tests in 3.663s
OK
=== devmem.memory.test_episodic
Ran 11 tests in 1.900s
OK
=== devmem.memory.test_reconcile
Ran 10 tests in 65.169s
OK
=== devmem.memory.test_gpt_structure_touch
Ran 5 tests in 0.056s
OK
=== devmem.memory.test_consolidation
Ran 27 tests in 8.020s
OK (skipped=1)
=== devmem.memory.test_identity
Ran 36 tests in 97.548s
OK
=== devmem.memory.test_night_key
Ran 9 tests in 1.822s
OK
=== devmem.memory.test_t_calibration
Ran 7 tests in 0.129s
OK
=== devmem.embeddings.test_vector_store
Ran 14 tests in 2.332s
OK (skipped=1)
=== devmem.demo.test_demo
Ran 2 tests in 0.026s
OK
=== devmem.api.test_store
Ran 22 tests in 4.707s
OK
=== devmem.api.test_api_http
Ran 6 tests in 0.000s
OK (skipped=6)
=== devmem.api.test_api_http (system Python 3.13 with fastapi, httpx)
Ran 6 tests in 2.893s
OK
```

Count: 217 tests run in the project venv and passing (the 2 live-gated tests and the 6 API HTTP tests are skipped there), plus the 6 API HTTP tests passing under Python 3.13. Before this round the count was 178; the additions are the A1 scorer test (1), the night-key checkpoint tests (9), the T calibration tests (7), the data layer tests (22) and the API HTTP tests (6, run under 3.13).

The API HTTP tests need fastapi and httpx, which the project venv (Python 3.9) does not have; they skip there and run with the system Python 3.13 that already has fastapi 0.111, uvicorn 0.29 and httpx 0.27 (nothing was installed). The data layer is standard library only, so its 22 tests run in the project venv. A browser check (the interaction measurements in section 3) was run in the built-in browser pane; no automated frontend test exists yet.

## 6. CONDITIONS COMPLIANCE TABLE

| Condition | Status | Evidence |
|---|---|---|
| API plus timeline player plus memory panel working on the Step D recording, with screenshots | Done | sections 2 to 4 |
| Read-only, never calls an LLM, never writes to a run | Done and tested | `test_store.TestReadOnlyAndGraceful`, `test_api_http.test_no_route_accepts_a_write_method`, hash check of both recordings |
| No "better" or "improved" wording, no invented scores | Done | section 3 |
| Label bar always visible with recorded or live, scripted or natural, model, normalizer | Done; unknown stays unknown | `test_store.TestRunsAndLabels` |
| No keys in the frontend or served files | Done and tested | `test_api_http.test_no_key_or_secret_is_served` |
| Missing tables degrade gracefully | Done and tested | `test_store.test_missing_stage_tables_degrade_to_unavailable_not_an_error` |
| Tests offline against the Step D recording and the Stop 3 fixture run | Done | `test_store` (22), `test_api_http` (6) |
| React: exact versions, integrity verified, only the two UMD files and the license, no npm install, no JSX or compiler, no CDN | Done | section 1 and `VENDOR.md` |
| No upstream edit; palette black and gold | Compliant | `git status reverie` clean |
| Delegation to the Junior Developer for component-level UI | Not used: I have no channel to the Junior Developer from this session, so I wrote and reviewed every component myself | section 7 |

## 7. DEVIATIONS (complete)
- The API runs under the system Python 3.13 (fastapi, uvicorn, httpx already installed there), not the project venv (3.9, no fastapi); the data layer is standard library only so it works in both. FastAPI is therefore not in the project's pinned requirements.
- `.gitignore` now un-ignores two recording databases (`docs/phase6_stepd_artifacts/memory.db`, `docs/phase6_stop3_artifacts/memory.db`) so tests and the demo work from a fresh checkout; every other `*.db` stays ignored.
- No delegation to the Junior Developer (see the table).
- Run labels: two new `run_label.json` files hold facts I took from my own reports (natural versus scripted, model, normalizer, stage settings); all other runs show unknown fields.
- The two console errors seen in the browser during development came from the first page load before a parenthesis typo in `app.js` was fixed (`node --check` now passes); a fresh load has no error.
- Earlier artifacts untouched; no live call and no LLM call were made in this stop.

## 8. OPEN QUESTIONS
1. **Three.js town (optional Stop 3):** the question the spec says to ask first. Yes: upstream's `start_server` writes `movement/{step}.json` and the headless runner keeps them; the Step D folder has 2,791 files with each agent's tile, description and pronunciatio per step (for example `movement/100.json` has Isabella's tile `[76, 14]` and her action). They are not committed (large, under the reverie storage). Three.js would be a new download needing your approval under the same pinning rule. Do you want it, and should the movement files of the Step D recording be exported compactly for the repository?
2. **Recordings for the demo:** the two small databases are committed; the Step D raw-reply log and ledger are already in `docs/phase6_stepd_artifacts`. Is that the intended recording set for presentation mode, or should the demo use a different run (for example the Phase 7 validation run later)?
3. **Interpreter:** keep the API on the system Python 3.13, or should FastAPI and uvicorn be added to the project venv (a download needing approval)?
4. **Presentation mode (Stop 2):** one command, offline, documented in `devmem/demo/README.md`. The existing `devmem/demo` replay script is separate; confirm that the inspector, not the old replay, is the presentation entry point.

REQUEST: Review of Stop 1 and answers to questions 1 to 4. Halting; Stop 2 will not start until you approve.
