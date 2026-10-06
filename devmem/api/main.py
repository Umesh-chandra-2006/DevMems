"""
FastAPI server of the memory inspector (Phase 8). READ-ONLY: every route is a GET over `devmem.api.store`, which opens run databases
read-only, never calls an LLM or the network and never writes to a run. No API key is read, held or served.

Run (system Python with fastapi and uvicorn): python -m uvicorn devmem.api.main:app --port 8765   (from the repository root)
The frontend is served at /ui/ (static files under devmem/api/web, React vendored for offline use, no CDN).
"""
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from devmem.api import store

app = FastAPI(title="DevMem memory inspector (read-only)", version="phase8-stop1",
              description="Reads saved run artifacts. Never writes to a run, never calls an LLM.")
WEB = Path(__file__).resolve().parent / "web"


def guarded(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except store.NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0]))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.middleware("http")
async def no_cache_for_the_ui(request, call_next):
    """The UI files are small and change during development and rehearsal: always revalidate (the town assets keep normal caching)."""
    response = await call_next(request)
    if request.url.path.startswith("/ui/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/")
def root():
    return RedirectResponse("/ui/index.html")


@app.get("/runs")
def runs():
    return {"runs": store.list_runs()}


@app.get("/runs/{run}/label")
def label(run: str):
    return guarded(store.run_label, run)


@app.get("/runs/{run}/agents")
def agents(run: str):
    return {"run": run, "label": guarded(store.run_label, run), "agents": guarded(store.list_agents, run)}


@app.get("/runs/{run}/agents/{agent}/state")
def state(run: str, agent: str, t: Optional[str] = Query(None, description="simulated time, e.g. 2023-02-13 09:30:00"),
          diagnostics: bool = Query(False, description="compute the trait provenance diagnostic from cached embeddings (no network)")):
    return guarded(store.agent_state, run, agent, t, diagnostics)


@app.get("/runs/{run}/timeline")
def timeline(run: str):
    return guarded(store.timeline, run)


@app.get("/runs/{run}/ledger/summary")
def ledger(run: str):
    return guarded(store.ledger_summary, run)


@app.get("/runs/{run}/movement/meta")
def movement_meta(run: str):
    return guarded(store.movement_meta, run)


@app.get("/runs/{run}/movement/frames")
def movement_frames(run: str, from_step: int = Query(0, ge=0), to_step: int = Query(2159, ge=0), stride: int = Query(1, ge=1, le=360)):
    return guarded(store.movement_frames, run, from_step, to_step, stride)


@app.get("/runs/{run}/agents/{agent}/thoughts")
def thoughts(run: str, agent: str, t: Optional[str] = None):
    return guarded(store.agent_thoughts, run, agent, t)


@app.get("/runs/{run}/status")
def status(run: str):
    return guarded(store.run_status, run)


@app.get("/compare")
def compare(a: str, b: str, agent: str, t: Optional[str] = None):
    return guarded(store.compare, a, b, agent, t)


TOWN_ASSETS = Path(__file__).resolve().parent.parent.parent / "reverie" / "environment" / "frontend_server" / "static_dirs" / "assets"
# upstream's town assets (map, tilesets, character atlases, speech bubble), served READ-ONLY from where they already live; nothing is copied
# and no upstream file is touched. Starlette's StaticFiles refuses paths that escape the directory.
app.mount("/town-assets", StaticFiles(directory=str(TOWN_ASSETS)), name="town-assets")
app.mount("/ui", StaticFiles(directory=str(WEB), html=True), name="ui")
