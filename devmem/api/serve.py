"""
Presentation mode (Phase 8 Stop 2): ONE command starts the read-only API and the inspector on localhost against chosen recorded runs.
Offline: no key is read, no LLM is called, no network request leaves the machine (React and Phaser are vendored, upstream's town assets are
served from where they already live).

    python devmem/api/serve.py --a <left run> --b <right run> [--tab town|inspector|cost] [--t "2023-02-13 07:30:00"] [--port 8765] [--open]
    python devmem/api/serve.py --check --a <left run> --b <right run>        (rehearsal check, starts nothing)

Run it with the system Python that has fastapi and uvicorn (see devmem/api/REQUIREMENTS.md); `--check` needs only the standard library.
The two runs are whatever you choose from `GET /runs`; the demo recordings are the Phase 7/9 baseline and staged runs once they exist.
"""
import argparse
import sys
import webbrowser
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

REQUIRED_FILES = [
    "devmem/api/web/index.html", "devmem/api/web/app.js", "devmem/api/web/common.js", "devmem/api/web/town.js", "devmem/api/web/cost.js",
    "devmem/api/web/style.css", "devmem/api/web/vendor/react.production.min.js", "devmem/api/web/vendor/react-dom.production.min.js",
    "devmem/api/web/vendor/phaser.js", "reverie/environment/frontend_server/static_dirs/assets/the_ville/visuals/the_ville_jan7.json",
    "reverie/environment/frontend_server/static_dirs/assets/characters/atlas.json",
    "reverie/environment/frontend_server/static_dirs/assets/speech_bubble/v3.png",
]


def check(a: str, b: str) -> list:
    """Rehearsal check: every file the page needs exists, both runs exist, and what each run offers (movement, ledger, Stage 3 and 4)."""
    from devmem.api import store
    problems = []
    for rel in REQUIRED_FILES:
        if not (ROOT / rel).is_file():
            problems.append(f"missing file: {rel}")
    runs = store.discover()
    for side, run in (("left", a), ("right", b)):
        if run not in runs:
            problems.append(f"{side} run {run!r} not found; available: {sorted(runs)}")
            continue
        m = store.movement_meta(run)
        if not m["available"]:
            problems.append(f"{side} run {run!r} has no movement (the town pane will say so; the memory and cost views still work)")
        if not store.ledger_summary(run)["available"]:
            problems.append(f"{side} run {run!r} has no ledger windows (the cost view will say so)")
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True, help="left run id (see GET /runs)")
    ap.add_argument("--b", help="right run id (default: the same run)")
    ap.add_argument("--tab", default="town", choices=["town", "inspector", "cost"])
    ap.add_argument("--t", help="start simulated time, e.g. '2023-02-13 07:30:00'")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--open", action="store_true", help="open the page in the default browser")
    ap.add_argument("--check", action="store_true", help="rehearsal check only; start nothing")
    a = ap.parse_args(argv)
    b = a.b or a.a
    problems = check(a.a, b)
    url = f"http://127.0.0.1:{a.port}/ui/index.html?tab={a.tab}&a={quote(a.a)}&b={quote(b)}" + (f"&t={quote(a.t)}" if a.t else "")
    print(f"left run: {a.a}\nright run: {b}\nurl: {url}")
    for p in problems:
        print("note:", p)
    if a.check:
        hard = [p for p in problems if p.startswith(("missing file", "left run", "right run")) and ("not found" in p or "missing file" in p)]
        print("rehearsal check:", "FAILED" if hard else "ok")
        return 1 if hard else 0
    import uvicorn
    if a.open:
        webbrowser.open(url)
    print("read-only server; stop it with Ctrl+C; no key is needed and nothing leaves this machine")
    uvicorn.run("devmem.api.main:app", host="127.0.0.1", port=a.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
