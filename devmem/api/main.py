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


@app.get("/compare")
def compare(a: str, b: str, agent: str, t: Optional[str] = None):
    return guarded(store.compare, a, b, agent, t)


app.mount("/ui", StaticFiles(directory=str(WEB), html=True), name="ui")
