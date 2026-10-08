"""
Process rule (PM, 2026-10-08): before every commit run `python -m py_compile` on every changed Python file and the tests that cover the change, and commit ONLY if both pass.

    python -m devmem.eval.safe_commit --msg "message" --tests devmem.eval.test_outage [more modules] -- file1 file2 ...

It stages exactly the listed files, compiles every .py among them (and every staged .py), runs the listed test modules with the venv python (PYTHONPATH set for the backend), prints the
command lines and results, and commits with the co-author trailer only when everything passed. Any failure prints the output and exits non-zero without committing.
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
TRAILER = "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"


def run(cmd, env=None):
    print("$", " ".join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=str(ROOT), env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--msg", required=True)
    ap.add_argument("--tests", nargs="*", default=[])
    ap.add_argument("files", nargs="*")
    a = ap.parse_args()
    env = dict(os.environ, PYTHONPATH=f"{ROOT / 'reverie' / 'reverie' / 'backend_server'}{os.pathsep}{ROOT}", PYTHONIOENCODING="utf-8")
    if a.files:
        r = run(["git", "add", "--"] + a.files)
        if r.returncode:
            print(r.stderr); sys.exit(2)
    staged = [f for f in run(["git", "diff", "--cached", "--name-only"]).stdout.split() if f.endswith(".py")]
    for f in staged:
        r = run([sys.executable, "-m", "py_compile", f])
        print("  py_compile:", "ok" if r.returncode == 0 else "FAILED")
        if r.returncode:
            print(r.stderr); print("NOT committed"); sys.exit(3)
    for t in a.tests:
        r = run([sys.executable, "-m", "unittest", t], env=env)
        tail = [l for l in (r.stdout + r.stderr).splitlines() if l.startswith(("Ran ", "OK", "FAILED"))]
        print("  tests", t + ":", " ".join(tail))
        if r.returncode:
            print((r.stdout + r.stderr)[-1500:]); print("NOT committed"); sys.exit(4)
    r = run(["git", "commit", "-q", "-m", a.msg + "\n\n" + TRAILER])
    print(r.stdout, r.stderr)
    print("committed:", run(["git", "log", "--oneline", "-1"]).stdout.strip())
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
