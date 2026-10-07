"""
Offline audit (zero calls) of the importance-parser echo artifact, requested by the PM on 2026-10-07.

For every saved reply to an importance prompt it applies the OLD parser (episodic.py as of commit 21ada50, extracted from git) and the CORRECTED
parser (commit f25a10b, the working copy), and counts the replies that use the echo format "Rate (return ...): N". Past artifacts are NOT changed;
the output is `docs/phase7_parser_echo_audit.json`.
Sources: Phase 4 result JSONs (task4_1, task7b), the raw reply logs of Step C, Step C2, Step D, Stop 3 and the pilot.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from devmem.memory.episodic import parse_importance_score as new_parse  # noqa: E402

ECHO = re.compile(r"Rate\s*\(return[^)]*\)\s*:")


def load_old():
    src = subprocess.check_output(["git", "show", "21ada50:devmem/memory/episodic.py"], cwd=str(ROOT), text=True, encoding="utf-8")
    a = src.index("def parse_importance_score")
    b = src.index("def score_importance_persona_conditioned")
    ns = {"re": re}
    exec(src[a:b], ns)
    return ns["parse_importance_score"]


def collect_phase4(path):
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    out = []

    def walk(o, trail):
        if isinstance(o, dict):
            if "raw_resp" in o and "score" in o:
                out.append(("/".join(trail), o["raw_resp"], o["score"]))
            for k, v in o.items():
                walk(v, trail + [str(k)])
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, trail + [str(i)])
    walk(d["event_results"], [])
    return out


def collect_raw(path):
    out = []
    for l in Path(path).read_text(encoding="utf-8").splitlines():
        if l.strip():
            r = json.loads(l)
            if r.get("purpose") == "importance_scoring":
                out.append((r.get("agent_id", ""), r["raw"], None))
    return out


def audit(name, rows, old):
    n, echo, differ, examples = len(rows), 0, 0, []
    for trail, raw, recorded in rows:
        o, nw = old(raw), new_parse(raw)
        is_echo = bool(ECHO.search(raw))
        echo += is_echo
        if o != nw:
            differ += 1
            if len(examples) < 5:
                examples.append({"where": trail, "echo_format": is_echo, "old": o, "corrected": nw, "recorded_score": recorded, "raw_start": raw[:80]})
    return {"artifact": name, "importance_replies": n, "echo_format_replies": echo, "old_vs_corrected_differ": differ, "examples": examples}


def main():
    old = load_old()
    srcs = [("phase4 task4_1 (gpt-oss-20b, control_mismatch/control_filler)", collect_phase4(ROOT / "devmem/memory/task4_1_control_results.json")),
            ("phase4 task7b (gpt-oss-20b, baseline vs staged)", collect_phase4(ROOT / "devmem/memory/task7b_differential_results.json"))]
    for label, p in [("step C (p5_step_c_gemini)", "devmem/storage/p5_step_c_gemini/raw_replies.jsonl"),
                     ("step C2 (p5_step_c2_gemini)", "devmem/storage/p5_step_c2_gemini/raw_replies.jsonl"),
                     ("step D (docs/phase6_stepd_artifacts)", "docs/phase6_stepd_artifacts/raw_replies.jsonl"),
                     ("stop 3 (docs/phase6_stop3_artifacts)", "docs/phase6_stop3_artifacts/raw_replies.jsonl"),
                     ("pilot baseline (p7pilot_baseline)", "devmem/storage/p7pilot_baseline/raw_replies.jsonl"),
                     ("pilot staged (p7pilot_staged)", "devmem/storage/p7pilot_staged/raw_replies.jsonl")]:
        if (ROOT / p).exists():
            srcs.append((label, collect_raw(ROOT / p)))
    res = {"label": "offline-captured recomputation of saved live replies, zero calls; past artifacts not changed",
           "old_parser": "devmem/memory/episodic.py at commit 21ada50", "corrected_parser": "devmem/memory/episodic.py at commit f25a10b",
           "results": [audit(n, r, old) for n, r in srcs]}
    out = ROOT / "docs" / "phase7_parser_echo_audit.json"
    out.write_text(json.dumps(res, indent=1), encoding="utf-8")
    for r in res["results"]:
        print(r["artifact"], r["importance_replies"], r["echo_format_replies"], r["old_vs_corrected_differ"])


if __name__ == "__main__":
    main()
