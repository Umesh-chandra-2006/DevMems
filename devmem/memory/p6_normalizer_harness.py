"""
Offline harness for the router-level output normalizer (zero live calls).

* `render_all_templates()`: every upstream template referenced by run_gpt_prompt.py, rendered by upstream's own `generate_prompt` from the
  real template files (dummy values for the input slots).
* `run_upstream(...)`: runs a REAL upstream prompt function. The model call goes through the REAL `llm_router.call_llm` (so the real
  normalizer wiring is exercised) with only the provider layer (`send_request`) stubbed to return saved or synthetic raw replies; the
  provider config, ledger and cooldown state are temporary. Upstream's own retry loop and validator run unmodified. When `live_prompt` is
  given, `generate_prompt` returns that exact text, so the function sees the prompt that was logged in the live run (not a rebuilt one).
"""
import contextlib
import datetime
import io
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from unittest import mock

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND = ROOT / "reverie" / "reverie" / "backend_server"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DEVMEM_EMBEDDING_MODE", "offline")
from devmem.run_headless import load_runner_config  # noqa: E402,F401  (chdir to the backend dir; upstream paths are cwd-relative)

import persona.prompt_template.gpt_structure as gs  # noqa: E402
import persona.prompt_template.run_gpt_prompt as rgp  # noqa: E402
from persona.persona import Persona  # noqa: E402
from maze import Maze  # noqa: E402

from devmem.router import llm_router, output_normalizer as on  # noqa: E402
from devmem.router.cooldown import CooldownManager  # noqa: E402
from devmem.router.providers import ProviderResponse  # noqa: E402

TEMPLATE_ROOT = BACKEND / "persona" / "prompt_template"
ACT = "waking up and completing her morning routine"
HOURS = ["00:00 AM", "01:00 AM", "02:00 AM", "03:00 AM", "04:00 AM", "05:00 AM", "06:00 AM", "07:00 AM", "08:00 AM", "09:00 AM",
         "10:00 AM", "11:00 AM", "12:00 PM", "01:00 PM", "02:00 PM", "03:00 PM", "04:00 PM", "05:00 PM", "06:00 PM", "07:00 PM",
         "08:00 PM", "09:00 PM", "10:00 PM", "11:00 PM"]
ANNOTATION = "(duration in minutes: 5, minutes left: 5)"


class RepliesExhausted(BaseException):
    pass


def used_template_paths():
    """Template paths referenced by upstream's run_gpt_prompt.py (the simulation call path), relative to backend_server."""
    src = (TEMPLATE_ROOT / "run_gpt_prompt.py").read_text(encoding="utf-8")
    return sorted(set(re.findall(r"persona/prompt_template/[A-Za-z0-9_/\.]*\.txt", src)))


def upstream_can_read(rel_path):
    """upstream's generate_prompt opens templates with the platform default encoding (cp1252 on this machine); a template with other
    characters cannot be read by the live call path here."""
    try:
        (BACKEND / rel_path).read_text(encoding="cp1252")
        return True
    except UnicodeDecodeError:
        return False


def render_template(rel_path):
    """Same substitution and trimming as upstream's generate_prompt, but reading the file as UTF-8 so every template can be rendered."""
    text = (BACKEND / rel_path).read_text(encoding="utf-8", errors="ignore")
    slots = [int(x) for x in re.findall(r"!<INPUT (\d+)>!", text)]
    for count in range((max(slots) + 1) if slots else 0):
        text = text.replace(f"!<INPUT {count}>!", f"<<value {count}>>")
    if "<commentblockmarker>###</commentblockmarker>" in text:
        text = text.split("<commentblockmarker>###</commentblockmarker>")[1]
    return text.strip()


def render_all_templates():
    return {p: render_template(p) for p in used_template_paths()}


_STATE = {}


def persona_and_maze():
    if "p" not in _STATE:
        base = ROOT / "reverie/environment/frontend_server/storage/base_the_ville_isabella_maria_klaus"
        persona = Persona("Isabella Rodriguez", str(base / "personas/Isabella Rodriguez"))
        persona.scratch.curr_time = datetime.datetime(2023, 2, 13, 6, 0, 0)
        env0 = json.loads((base / "environment/0.json").read_text())
        persona.scratch.curr_tile = (env0["Isabella Rodriguez"]["x"], env0["Isabella Rodriguez"]["y"])
        persona.scratch.daily_req = ["wake up and complete the morning routine at 6:00 am", "open Hobbs Cafe at 8:00 am"]
        _STATE["p"] = (persona, Maze("the_ville"))
    return _STATE["p"]


def run_upstream(call, replies, flag_on, live_prompt=None):
    """`call()` runs one upstream prompt function and returns its first return value. `replies` are the raw provider replies, served in
    order (upstream's retry loop consumes as many as it needs). Returns {result, validate, attempts, delivered, prompt_seen, error}."""
    tmp = Path(tempfile.mkdtemp(prefix="p6_harness_"))
    cfg = tmp / "providers.yaml"
    cfg.write_text(yaml.dump({"providers": [{"name": "groq", "priority": 1, "models": {"fast": "openai/gpt-oss-20b"},
                                              "keys": [{"env": "HARNESS_TEST_KEY"}], "rpm": 100000, "rpd": 10 ** 9, "tpd": 10 ** 12}]}))
    served = iter(replies)
    seen = {"prompts": [], "delivered": [], "validate": []}

    def send(**kw):
        seen["prompts"].append(kw["prompt"])
        try:
            return ProviderResponse(next(served), 1, 1)
        except StopIteration:
            raise RepliesExhausted()

    real_router_call = llm_router.call_llm
    real_safe = rgp.safe_generate_response

    def spy(prompt, gpt_parameter, repeat, fail_safe_response, func_validate, func_clean_up, verbose=False):
        def v(*a, **k):
            ok = func_validate(*a, **k)
            seen["validate"].append(bool(ok))
            return ok
        return real_safe(prompt, gpt_parameter, repeat, fail_safe_response, v, func_clean_up, verbose)

    def routed(prompt, **kw):
        out = real_router_call(prompt, config_path=str(cfg), db_path=str(tmp / "ledger.db"), **kw)
        seen["delivered"].append(out)
        return out

    env = {"HARNESS_TEST_KEY": "not-a-real-key", "DEVMEM_OUTPUT_NORMALIZER": "on" if flag_on else "off"}
    result, error = None, None
    try:
        with contextlib.redirect_stdout(io.StringIO()), mock.patch.dict(os.environ, env), \
             mock.patch.object(llm_router, "cooldown_manager", CooldownManager(state_file=tmp / "cd.json")), \
             mock.patch.object(llm_router, "send_request", side_effect=send), \
             mock.patch.object(gs, "call_llm", routed), mock.patch.object(gs, "temp_sleep"), \
             mock.patch.object(rgp, "safe_generate_response", spy), \
             mock.patch.object(rgp, "generate_prompt", (lambda *a, **k: live_prompt) if live_prompt is not None else rgp.generate_prompt):
            result = call()
    except RepliesExhausted:
        error = "recorded replies exhausted"
    except Exception as e:  # a real upstream exception is a RESULT here (it is what a run would have hit)
        error = f"{type(e).__name__}: {str(e)[:100]}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return {"result": result, "validate": seen["validate"], "attempts": len(seen["prompts"]), "delivered": seen["delivered"],
            "prompt_seen": seen["prompts"][0] if seen["prompts"] else None, "error": error}


# ---- the upstream functions, as callables bound to the harness persona and maze --------------------------------------------------
def fn_wake_up():
    p, _ = persona_and_maze()
    return lambda: rgp.run_gpt_prompt_wake_up_hour(p)[0]


def fn_daily_plan():
    p, _ = persona_and_maze()
    return lambda: rgp.run_gpt_prompt_daily_plan(p, 6)[0]


def fn_hourly():
    p, _ = persona_and_maze()
    return lambda: rgp.run_gpt_prompt_generate_hourly_schedule(p, "07:00 AM", ["sleeping"] * 7, HOURS)[0]


def fn_sector():
    p, m = persona_and_maze()
    return lambda: rgp.run_gpt_prompt_action_sector(ACT, p, m)[0]


def fn_arena():
    p, m = persona_and_maze()
    world = f"{m.access_tile(p.scratch.curr_tile)['world']}"
    return lambda: rgp.run_gpt_prompt_action_arena(ACT, p, m, world, "Isabella Rodriguez's apartment")[0]


def fn_game_object():
    p, m = persona_and_maze()
    return lambda: rgp.run_gpt_prompt_action_game_object(ACT, p, m, "the Ville:Isabella Rodriguez's apartment:main room")[0]


def fn_pronunciatio():
    p, _ = persona_and_maze()
    return lambda: rgp.run_gpt_prompt_pronunciatio(ACT, p)[0]


def fn_event_triple():
    p, _ = persona_and_maze()
    return lambda: rgp.run_gpt_prompt_event_triple(ACT, p)[0]


def fn_act_obj_desc():
    p, _ = persona_and_maze()
    return lambda: rgp.run_gpt_prompt_act_obj_desc("bed", ACT, p)[0]


def fn_act_obj_event():
    p, _ = persona_and_maze()
    return lambda: rgp.run_gpt_prompt_act_obj_event_triple("bed", "being used", p)[0]


def fn_poignancy_event():
    p, _ = persona_and_maze()
    return lambda: rgp.run_gpt_prompt_event_poignancy(p, "Isabella is waking up")[0]


def fn_poignancy_chat():
    p, _ = persona_and_maze()
    return lambda: rgp.run_gpt_prompt_chat_poignancy(p, "Isabella: good morning")[0]


# synthetic checks: (name, callable factory, plausible CLEAN reply). The annotated variant appends the observed annotation.
# synthetic checks: (name, callable factory, reply form, plausible CLEAN value). form "plain": the reply is the value, and the annotated
# variant appends the observed annotation after it; form "json": upstream's chat path expects {"output": value}; the annotated variant
# puts the annotation INSIDE the value (the harder case; an annotation after the closing brace is cut off by upstream anyway).
SYNTHETIC = [
    ("action game object", fn_game_object, "plain", "bed"),
    ("event triple", fn_event_triple, "plain", " wake up, bed)"),
    ("act obj event triple", fn_act_obj_event, "plain", " is, being used)"),
    ("pronunciatio", fn_pronunciatio, "json", "😴"),
    ("act obj desc", fn_act_obj_desc, "json", "being used by Isabella"),
    ("poignancy event", fn_poignancy_event, "json", "3"),
    ("poignancy chat", fn_poignancy_chat, "json", "3"),
]


def synthetic_replies(form, value):
    """(clean_reply, annotated_reply) for one synthetic check."""
    if form == "json":
        return json.dumps({"output": value}), json.dumps({"output": f"{value} {ANNOTATION}"})
    return value, f"{value} {ANNOTATION}"
