"""
Step C offline replay (zero calls): the two action-location prompts that failed in the live run (sector, then arena), replayed through
upstream's own functions with the saved replies, with and without the output-layer annotation strip.

The real upstream functions run on the same persona state, maze and action description as the live call; only gpt_structure.call_llm
is a stub returning the saved replies in order. Fidelity check: the prompt the upstream function builds must equal the prompt that was
logged live (otherwise the replay is reported as not faithful). Variants: none (what the live run saw), spaces+duration (the
normalizer's full effect, applied to these two prompts as an EXPERIMENT; the router allow-list does NOT include them).
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
os.environ["DEVMEM_EMBEDDING_MODE"] = "offline"
from devmem.run_headless import load_runner_config  # noqa: F401  (chdir + sys.path for upstream imports)
import utils
utils.MEMORY_MODE = "staged"
import persona.prompt_template.gpt_structure as gs
import persona.prompt_template.run_gpt_prompt as rgp
from persona.persona import Persona
from maze import Maze
from devmem.router.output_normalizer import normalize_output

ART = ROOT / "docs" / "phase6_stepc_artifacts"
rows = [json.loads(l) for l in (ART / "raw_replies.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
ACT = "waking up and completing her morning routine"


class Exhausted(BaseException):
    pass


def main():
    persona = Persona("Isabella Rodriguez", str(ROOT / "reverie/environment/frontend_server/storage/base_the_ville_isabella_maria_klaus/personas/Isabella Rodriguez"))
    maze = Maze("the_ville")
    import datetime
    persona.scratch.curr_time = datetime.datetime(2023, 2, 13, 6, 0, 0)
    env0 = json.loads((ROOT / "reverie/environment/frontend_server/storage/base_the_ville_isabella_maria_klaus/environment/0.json").read_text())
    persona.scratch.curr_tile = (env0["Isabella Rodriguez"]["x"], env0["Isabella Rodriguez"]["y"])  # where the live run placed her
    # live calls 22-26 = sector (5 attempts), 27-31 = arena (5 attempts)
    groups = {"action_sector": rows[21:26], "action_arena": rows[26:31]}
    real_safe = rgp.safe_generate_response
    cur = {}

    def spy(prompt, gpt_parameter, repeat, fail_safe_response, func_validate, func_clean_up, verbose=False):
        def v(*a, **k):
            ok = func_validate(*a, **k)
            cur["validate"].append(bool(ok))
            return ok
        return real_safe(prompt, gpt_parameter, repeat, fail_safe_response, v, func_clean_up, verbose)
    rgp.safe_generate_response = spy
    gs.temp_sleep = lambda *a, **k: None

    out = {"label": "offline replay of saved live replies through upstream's own code; zero calls", "results": []}
    for name, calls in groups.items():
        logged_prompt = calls[0]["prompt"]
        for vname, strip in (("none", None), ("spaces+duration", True)):
            it = iter([c["raw"] for c in calls])
            seen_prompts = []

            def stub(prompt, **kw):
                seen_prompts.append(prompt)
                try:
                    raw = next(it)
                except StopIteration:
                    raise Exhausted()
                return raw if strip is None else normalize_output(raw, strip_duration=True)
            gs.call_llm = stub
            cur.clear(); cur["validate"] = []
            result, error = None, None
            try:
                if name == "action_sector":
                    result = rgp.run_gpt_prompt_action_sector(ACT, persona, maze)[0]
                else:
                    act_world = f"{maze.access_tile(persona.scratch.curr_tile)['world']}"
                    result = rgp.run_gpt_prompt_action_arena(ACT, persona, maze, act_world, "Isabella Rodriguez's apartment")[0]
            except Exhausted:
                error = "recorded replies exhausted"
            except Exception as e:
                error = f"{type(e).__name__}: {str(e)[:100]}"
            out["results"].append({"prompt": name, "variant": vname, "prompt_equals_live_prompt": bool(seen_prompts) and seen_prompts[0] == logged_prompt,
                                   "validate": list(cur["validate"]), "attempts_used": len(seen_prompts), "result": result, "error": error})
    (ART / "step_c_replay.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    for r in out["results"]:
        print(r)


if __name__ == "__main__":
    main()
