# Requirements of the memory inspector (a note, nothing is installed by this file)

The inspector runs on the SYSTEM Python 3.13 (not the project's pinned Python 3.9 venv, which has no FastAPI). Versions found installed there
and used for every test and screenshot of Phase 8:

| Package | Version | Used for |
|---|---|---|
| Python | 3.13 (`C:\Users\...\Programs\Python\Python313`) | the API server |
| fastapi | 0.111.0 | the read-only API (`devmem/api/main.py`) |
| starlette | 0.37.2 | static files, middleware (comes with fastapi) |
| uvicorn | 0.29.0 | the server (`devmem/api/serve.py`) |
| pydantic | 2.12.5 | fastapi dependency |
| httpx | 0.27.0 | the HTTP tests (`devmem/api/test_api_http.py`, `TestClient`) |

The data layer (`devmem/api/store.py`, `movement_archive.py`) is standard library only and also runs in the project venv (Python 3.9), which is
where its tests run. Frontend libraries are vendored (no CDN, no npm): React 18.3.1, ReactDOM 18.3.1 and Phaser 3.55.2, with versions, tarball
URLs, published integrity hashes and licenses in `devmem/api/web/vendor/VENDOR.md`. Upstream's town assets are served from
`reverie/environment/frontend_server/static_dirs/assets` (read-only; nothing is copied).

Screenshots in `docs/phase8_stop*_artifacts` were taken in the Claude desktop app's built-in browser pane and (Stop 1) with headless Chrome.
Install commands, only if a machine lacks them: `python -m pip install fastapi==0.111.0 uvicorn==0.29.0 httpx==0.27.0` (a download; not run by
any script of this repository).
