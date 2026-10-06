PHASE: 8, memory inspector, STOP 2 (redefined: the town replay with click-to-inspect, side by side, cost view, presentation mode)
STATUS: Complete for Stop 2. Halting for review. The optional Three.js stop is dropped (your decision).

Labels: **recorded** (shown from saved run artifacts), **offline-captured**, **derived**. No em dashes. The inspector is read-only, never calls an LLM, never writes to a run, needs no key, and shows no "better" or "improved" wording and no score the recording does not contain.

## 1. WHAT WAS BUILT

| Piece | Where |
|---|---|
| Town replay: Phaser scene using upstream's map, tilesets, character atlases and speech bubble, driven by recorded movement frames; click an avatar to inspect | `devmem/api/web/town.js` |
| Two synchronized panes, one clock; app shell with tabs (Town replay, Memory inspector, Cost view), always-visible label bar, live-calls panel | `devmem/api/web/app.js`, `common.js` (shared memory components, label bar), `index.html`, `style.css` |
| Cost view (calls and tokens by purpose per recorded ledger window, two runs side by side) | `devmem/api/web/cost.js` |
| Movement archive (ONE compressed zip with a loader) and export CLI | `devmem/api/movement_archive.py` |
| New read-only routes: movement meta and frames, thoughts, live status, upstream town assets | `devmem/api/main.py`, `devmem/api/store.py` |
| Presentation command, rehearsal check | `devmem/api/serve.py` |
| README (presentation mode, rehearsal checklist; the old Stage 3 replay stays as the scripted fallback) | `devmem/demo/README.md` |
| Requirements note with the versions (no download) | `devmem/api/REQUIREMENTS.md` |
| Vendored Phaser 3.55.2 | `devmem/api/web/vendor/phaser.js`, `LICENSE-phaser.md`, `VENDOR.md` |
| Recordings made shippable | `docs/phase6_stepd_artifacts/movement.zip` (16 KB), `docs/phase6_stepc2_artifacts/movement.zip` (movement of the 2-hour Step C rerun), its `memory.db` and `run_label.json` (`.gitignore` negation) |
| Tests | `devmem/api/test_movement.py` (15), `test_store.py` (23), `test_api_http.py` (8, run under Python 3.13) |
| Screenshots | `docs/phase8_stop2_artifacts/01` to `04` |

**Upstream reuse (read-only, `git status reverie` clean):** the town is upstream's own. The Phaser scene repeats upstream's replay setup (the same 16 tileset images, the same layer names, the same per-persona atlas animations and speech bubble, `reverie/.../templates/demo/main_script.html`) and loads the files from `/town-assets`, which serves `reverie/environment/frontend_server/static_dirs/assets` read-only from where it already is (nothing copied; path traversal is refused, tested). Upstream's own Django viewer is unchanged and still works with its CDN links. Upstream's replay reads a compressed `master_movement.json`; the overlay reads the per-step `movement/{step}.json` the runner already writes (or one zip of them).

**Vendoring (PM rules; full record in `devmem/api/web/vendor/VENDOR.md`):** upstream's pages load `https://cdn.jsdelivr.net/npm/phaser@3.55.2/dist/phaser.js` (`templates/home/home.html` line 76, `templates/demo/demo.html` line 110). Vendored: **phaser 3.55.2**, tarball `https://registry.npmjs.org/phaser/-/phaser-3.55.2.tgz` (10,710,882 bytes), published integrity `sha512-amKXsbb2Ht29dGPKvt1edq3yGGYKtq8373GpJYGKPNPnneYY6MtVTOgjHDuZwtmUyK4v86FugkT3hzW/N4tjxQ==`, **verified equal to the locally computed sha512 before extraction**; extracted only `package/dist/phaser.js` (the same unminified file upstream references, 6,838,115 bytes, sha256 `494b0609ea5de72cf9dc22401343247d01a955aa48f92670f121868296418381`) and the MIT license; no npm install, no package scripts, no node_modules, package.json or lockfile; the tarball was fetched into a scratch folder outside the repository and discarded. A test asserts that both upstream pages still reference exactly this version and that the vendored files match the recorded hashes. Upstream's `base.html` also loads Bootstrap 3.4.1 and jQuery from CDNs; the overlay does not use them, so they are not vendored. **Vendored libraries in total: react 18.3.1, react-dom 18.3.1 (Stop 1) and phaser 3.55.2.** Nothing else was downloaded. At runtime the page made 0 requests outside this server (measured in the browser).

## 2. WHAT YOU CAN DO WITH IT

- **Town replay:** open the page, press Play. Each pane replays its run's recorded positions; each avatar shows its pronunciatio emoji and initials; drag pans, wheel zooms. **Click an avatar:** its current action and where it is (from the recorded description), its dialogue lines (the recorded chat field), its thoughts up to that time (the thought nodes of the saved memory) and the four memory columns at the replay time; click a summary or a trait and its sources light up. A pane says so when its run has no frame at the clock time (the avatars then stay where they were last recorded; nothing is invented).
- **Side by side:** two panes, each with its own run selector, label and click-to-inspect panel, driven by one clock; the shared scrubber spans the union of the two runs' coverage.
- **Cost view:** calls and tokens by purpose per recorded ledger window for two runs; the Step D recording shows 904 calls (dialogue 49, importance scoring 445, planning 410), the same figures as the Step D report.
- **Live calls panel:** reads `run_status.json` (the arm runner writes it about every simulated hour); it says no live segment is running otherwise. A run still executing is read from its simulation folder, so the part already recorded can be replayed while it grows.
- **Presentation:** `python devmem/api/serve.py --a <run> --b <run> --open` (system Python 3.13); `--check` is the offline rehearsal check; the checklist is in `devmem/demo/README.md`.

## 3. SCREENSHOTS (`docs/phase8_stop2_artifacts/`; built-in browser pane, 1600 x 1500 viewport; every number visible is a recorded value)

| File | What it shows |
|---|---|
| `01_town_side_by_side_both_inspected.jpg` | town replay at 13 Feb 07:30: LEFT the natural Step D recording (staged, Stage 3, partial 06:00 to 13:45), RIGHT the natural Step C rerun (2 hours, offline embeddings); Isabella clicked in BOTH panes; each pane shows her current action, address, dialogue ("none at this moment"), her recorded plan thought, and the memory columns; the label bar names both runs. **This is a layout demonstration with two different recorded runs, not a baseline versus staged comparison.** The right run is shown under its local run id `p5_step_c2_gemini`; the same recording ships in the repository as `phase6_stepc2_artifacts` |
| `02_town_left_pane_inspected.jpg` | the left pane after a real mouse click on Isabella's avatar: camera follows the avatar, selection ring, card and panel |
| `03_cost_view_two_runs.jpg` | cost view: Step D (904 recorded calls, 9 windows) and Step C rerun (163 calls, 4 windows) with purposes and tokens |
| `04_memory_inspector_tab_stop3_run.jpg` | the Stop 1 inspector tab on the Stop 3 run, trait_2 selected with its sources, path and the identity context exactly as scored |

## 4. VERIFIED BEHAVIOR (built-in browser pane, real mouse and keyboard-free events)

- A real click on an avatar (the click point read from the scene) opens the card and the memory panel; this initially failed and was fixed (see section 6).
- Playing at 30 simulated minutes per second moved Isabella across the map frame by frame (tile positions 2466, 2541, 2502, 2504 px over four samples) while Klaus stayed in bed (he is recorded asleep until 13:00); Pause froze the clock; the scrubber and Start work.
- Frame requests: 3 in total for two panes (one chunk per run, 1,440 frames per request, plus one prefetch); 0 external requests.
- Note on the test environment: when the page is not the visible tab (`document.visibilityState` is `hidden`), browsers pause animation frames and Phaser does not redraw; the README says the page must be the visible tab. This is a browser rule, not a defect of the inspector.

## 5. TESTS (`docs/phase8_stop2_artifacts/full_suite_output.txt`, verbatim)

```
=== devmem.router.test_router
Ran 33 tests in 3.652s
OK
=== devmem.router.test_call_counter
Ran 4 tests in 1.762s
OK
=== devmem.router.test_output_normalizer
Ran 4 tests in 0.000s
OK
=== devmem.router.test_normalizer_wiring
Ran 8 tests in 2.141s
OK
=== devmem.router.test_normalizer_rule
Ran 9 tests in 0.176s
OK
=== devmem.router.test_normalizer_call_path
Ran 7 tests in 5.289s
OK
=== devmem.memory.test_priors
Ran 9 tests in 1.952s
OK
=== devmem.memory.test_episodic
Ran 11 tests in 1.698s
OK
=== devmem.memory.test_reconcile
Ran 10 tests in 42.217s
OK
=== devmem.memory.test_gpt_structure_touch
Ran 5 tests in 0.027s
OK
=== devmem.memory.test_consolidation
Ran 27 tests in 7.185s
OK (skipped=1)
=== devmem.memory.test_identity
Ran 36 tests in 62.398s
OK
=== devmem.memory.test_night_key
Ran 13 tests in 2.052s
OK
=== devmem.memory.test_t_calibration
Ran 7 tests in 0.071s
OK
=== devmem.embeddings.test_vector_store
Ran 14 tests in 1.272s
OK (skipped=1)
=== devmem.demo.test_demo
Ran 2 tests in 0.006s
OK
=== devmem.api.test_store
Ran 23 tests in 2.097s
OK
=== devmem.api.test_movement
Ran 15 tests in 1.124s
OK
=== devmem.api.test_api_http
Ran 8 tests in 0.000s
OK (skipped=8)
=== devmem.eval.test_run_readiness
Ran 27 tests in 45.141s
OK
=== devmem.eval.test_run_arm_smoke
Ran 1 test in 11.182s
OK
=== devmem.api.test_api_http (system Python 3.13 with fastapi, httpx)
Ran 8 tests in 1.801s
OK
```

Count: 265 tests run and passing in the project venv (2 live-gated tests and the 8 API HTTP tests are skipped there) plus the 8 API HTTP tests passing under Python 3.13. At the end of Phase 7 Stop 2a it was 249 plus 6; the additions are the movement archive tests (15), the new store label test (1) and the two extra HTTP tests.

New and extended this stop: movement archive and API (loader, export round trip, growing folder read fresh, frame limit and stride, thoughts, live status fresh versus finished, rehearsal check and its exit code), read-only enforcement over every new route (405 for write methods, the zip and databases unchanged), upstream town assets served read-only with traversal attempts refused, the label rule (a declared `recorded` label wins over a fresh file; only a running status file makes a run live), every frontend script parses with `node --check`, no CDN or external URL in any of the files, a single `fetch` helper that only issues GET, the banned comparison words absent from every UI string, the vendored hashes and the version match with upstream's pages. There is no automated test of the Phaser scene itself; it was exercised in the browser (section 4).

## 6. PROBLEMS FOUND DURING VERIFICATION (and fixed)
- The first real click did nothing: the atlas frames carry a centre pivot, so the sprite origin resets to the centre whenever the texture changes, and my click point (computed for a bottom origin) was 10 px above the avatar; Phaser also caches the canvas position at creation and the layout shifted afterwards. Fixed: centre origin throughout and a bounds refresh before every pointer event.
- Playing a run read from a growing folder re-fetched its partial chunk on every state change and looped (over 150 requests). Fixed: a complete chunk is fetched once, a partial chunk of a live run at most every 10 seconds.
- The label bar was empty on the cost tab (labels were loaded only by the town panes). Fixed: the shell loads the labels of both runs.
- A recording copied or checked out fresh looked "live" for two minutes. Fixed: a declared `recorded` label wins unless a status file shows a running state.
- The browser pane served stale scripts after edits; the server now sends `Cache-Control: no-cache` for `/ui/`.

## 7. CONDITIONS COMPLIANCE TABLE

| Condition | Status | Evidence |
|---|---|---|
| Reuse upstream's town (map, sprites, replay logic) read-only as an overlay; `git status reverie` clean; upstream's viewer still works | Done | section 1; the upstream pages reference the same Phaser version (test) |
| Clicking an avatar opens the memory panel for that agent at the current replay time, shows the current action, any thought and dialogue lines | Done | section 2 and screenshots 01, 02 |
| Offline: vendor what upstream loads from a CDN (exact version, published hash verified before extraction, license, no npm install, no CDN at runtime); list each in the report | Done: Phaser 3.55.2 (Bootstrap and jQuery are loaded by upstream's base template but not used by the overlay, so not vendored) | section 1, `VENDOR.md` |
| Anything beyond that needs approval | Nothing else downloaded | section 1 |
| Side by side: two synchronized town panes driven by one clock, each with its own click-to-inspect panel | Done | screenshot 01 |
| Cost view, label bar, presentation command, README | Done | sections 1 to 3 |
| Export the movement files of a chosen recording as one compressed archive (a single zip) with a loader | Done: `movement_archive.py`, `movement.zip` for two recordings | tests |
| Read-only, no LLM, no writes, no keys, no "better or improved" wording | Done and tested | section 5 |
| Requirements note with versions, API stays on system Python 3.13, no download | Done | `REQUIREMENTS.md` |
| Demo recordings are the Phase 7/9 baseline and staged runs; Step D and the Stop 3 run stay as test fixtures | Honored: the screenshots use test fixtures only; the demo pair is chosen at run time with `--a` and `--b` | README |
| Halt for review with screenshots | This report | n/a |

## 8. DEVIATIONS (complete)
- Three.js was dropped (your decision), recorded as ledger row H8; the town is upstream's Phaser replay.
- `phaser.js` (6.8 MB, unminified) is the file upstream references; the minified build would be 1.2 MB. I vendored the exact file upstream uses.
- Avatars glide between recorded 10-second frames and between tile positions on screen; the interpolation is visual, the recorded positions are the frames.
- "Thoughts" are the thought nodes of the saved memory (for Step D only the day's plan; reflection is off in staged mode, so there is nothing else to show) and "dialogue" is the recorded chat field (none in these recordings: no conversation happened).
- The right pane of screenshots 01 and 02 and screenshot 03 show the Step C rerun under its local run id; the same recording is committed as `docs/phase6_stepc2_artifacts` with its `movement.zip`, `memory.db` (40 KB, `.gitignore` negation) and a label.
- The scripted `phase6_stop3_artifacts` run has no movement (scripted events), so its town pane says so.
- Screenshots were taken in the built-in browser pane (an emulated 1600 x 1500 viewport), not headless Chrome: headless Chrome with Phaser did not finish in 200 seconds here and was stopped.

## 9. OPEN QUESTIONS
1. For the presentation, which two runs are shown first when the Phase 9 baseline and staged runs exist? (`--a` and `--b` take any run id.)
2. Exporting `movement.zip` for each arm run is a post-run step (`python -m devmem.api.movement_archive export <sim folder> <run folder>/movement.zip`); the arm runner could do it at the end of a run. Shall I add that to the runner at the next stop?
3. The live segment: do you want a short scripted live run (Groq keys, a few agents, a few steps) for the room demonstration, or is the call counter of the real Phase 9 run enough?

REQUEST: Review of Stop 2 and answers to 1 to 3. Halting.
