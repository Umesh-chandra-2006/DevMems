"""
Dev tool: run the Phase 9 answer harness ONCE on a PILOT checkpoint copy with REAL embeddings for the retrieval step and a STUB chat call (no chat request is made, so no run
competes for chat quota). It proves that persona loading, upstream `new_retrieve` and the harness work together on real stored vectors before any day-3 data exists. It prints
counts only (retrieved memories per question) and writes the first retrieved descriptions of one question to a probe file (ignored by git). No outcome data is touched.

    cd reverie/reverie/backend_server && PYTHONPATH=<backend>;<repo> python -m devmem.eval.phase9.run_harness_on_checkpoint --sim p7pilot_staged__ckpt_pilot_end_0900 --key GEMINI_KEY_30
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim", required=True)
    ap.add_argument("--key", required=True, help="env var NAME of one embedding-capable key (never printed)")
    ap.add_argument("--per-agent", type=int, default=2)
    a = ap.parse_args()
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    os.environ.setdefault("DEVMEM_EMBEDDING_MODE", "live")
    src = ROOT / "reverie" / "environment" / "frontend_server" / "storage" / a.sim
    tmp = Path(tempfile.mkdtemp(prefix="p9_ckpt_copy_"))
    shutil.copytree(src, tmp / "sim")                            # retrieval runs on a COPY: last_accessed updates never touch the checkpoint
    from persona.persona import Persona
    import persona.prompt_template.gpt_structure as gs
    from devmem.embeddings.vector_store import EmbeddingStore
    from devmem.eval.phase9 import answer_harness
    gs._EMBEDDING_STORE = EmbeddingStore(stats_path=tmp / "emb_stats.json", key_envs=[a.key])
    qs = json.loads((ROOT / "docs" / "phase7_stop1_events_questions.json").read_text(encoding="utf-8"))["questions"]
    names = json.loads((tmp / "sim" / "reverie" / "meta.json").read_text(encoding="utf-8"))["persona_names"]
    summary, sample = {}, None
    for name in names:
        persona = Persona(name, str(tmp / "sim" / "personas" / name))
        mine = [q for q in qs if q["agent"] == name][:a.per_agent]
        out = answer_harness.answer_questions(name, mine, lambda p: "stub answer (no chat call)", persona=persona)
        summary[name] = [{"question_id": o["question_id"], "retrieved": o["retrieved_count"], "prompt_chars": o["prompt_chars"]} for o in out]
        if sample is None:
            sample = {"agent": name, "question": mine[0]["question"], "retrieved_first_5": answer_harness.default_retrieve(persona, mine[0]["question"], 5)}
    d = ROOT / "devmem" / "storage" / "probes"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"harness_on_{a.sim}.json").write_text(json.dumps({"sim": a.sim, "summary": summary, "sample": sample}, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    print("embedding http requests:", gs._EMBEDDING_STORE.stats.get("http_requests"), "cache hits:", gs._EMBEDDING_STORE.stats.get("cache_hits"))
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
