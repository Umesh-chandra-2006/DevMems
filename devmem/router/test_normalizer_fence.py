"""
Tests for the JSON fence rule of the output normalizer (PM verdict after the pilot, 2026-10-07).

The two real fenced replies are the captured live replies that crashed the pilot arms (fixtures/fence/captured_fenced_replies.json). The
second test class runs the real upstream ChatGPT_safe_generate_response parse path on them with only the provider stubbed.
"""
import devmem.testing_env  # noqa: F401
import json
import os
import unittest
from pathlib import Path
import sys
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (str(ROOT / "reverie" / "reverie" / "backend_server"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from devmem.router import output_normalizer as on  # noqa: E402

FIX = json.loads((Path(__file__).parent / "fixtures" / "fence" / "captured_fenced_replies.json").read_text(encoding="utf-8"))["replies"]
PLAIN_PROMPT = 'Output the response to the prompt above in json. x\nExample output json:\n{"output": "y"}'


class TestStripJsonFence(unittest.TestCase):
    def test_real_captured_replies_from_both_crash_snapshots(self):
        for arm, rec in FIX.items():
            raw = rec["raw"]
            self.assertTrue(raw.startswith("```json"), arm)
            out = on.strip_json_fence(raw)
            self.assertFalse(out.startswith("```"))
            self.assertIn("output", json.loads(out))
            lines = raw.split("\n")
            self.assertEqual(out, "\n".join(lines[1:-1]))   # the inner text, byte for byte

    def test_plain_fence_and_whitespace(self):
        self.assertEqual(on.strip_json_fence('```\n{"output": "a"}\n```'), '{"output": "a"}')
        self.assertEqual(on.strip_json_fence('  \n```json\n{"output": "a"}\n```\n\n '), '{"output": "a"}')
        self.assertEqual(on.strip_json_fence('```json{"output": "a"}```'), '{"output": "a"}')

    def test_inner_content_unaltered(self):
        inner = '{"output": "a  b\\n  c ```x``` d"}'
        self.assertEqual(on.strip_json_fence("```json\n" + inner + "\n```"), inner)

    def test_fence_inside_a_json_string_untouched(self):
        s = '{"output": "see ```json\\n{}\\n``` here"}'
        self.assertEqual(on.strip_json_fence(s), s)

    def test_unterminated_or_truncated_fence_untouched(self):
        for s in ('```json\n{"output": "a"}', '```json\n{"output": "a', '{"output": "a"}\n```'):
            self.assertEqual(on.strip_json_fence(s), s)

    def test_non_json_fenced_reply_untouched(self):
        for s in ("```\nhello there\n```", "```python\nprint(1)\n```", '```json\n{"output": \n```'):
            self.assertEqual(on.strip_json_fence(s), s)

    def test_unfenced_reply_unchanged(self):
        for s in ('{"output": "a"}', "plain text", "", '  {"output": 5}\n'):
            self.assertEqual(on.strip_json_fence(s), s)

    def test_two_separate_fenced_blocks_untouched(self):
        s = '```json\n{"output": "a"}\n```\ntext\n```json\n{"output": "b"}\n```'
        self.assertEqual(on.strip_json_fence(s), s)


class TestWiring(unittest.TestCase):
    def setUp(self):
        on.STATS.clear()

    def test_default_off_with_flag_unset(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(on.ENV_FLAG, None)
            raw = FIX["baseline"]["raw"]
            self.assertEqual(on.maybe_normalize(PLAIN_PROMPT, raw), (raw, None))
            self.assertEqual(on.STATS, {})

    def test_on_strips_and_counts_per_call(self):
        with mock.patch.dict(os.environ, {on.ENV_FLAG: "on"}):
            out, label = on.maybe_normalize(PLAIN_PROMPT, FIX["staged"]["raw"])
            self.assertEqual(label, "call_path")
            self.assertEqual(json.loads(out)["output"][:5], json.loads(on.strip_json_fence(FIX["staged"]["raw"]))["output"][:5])
            on.maybe_normalize(PLAIN_PROMPT, '{"output": "a"}')
            self.assertEqual(on.STATS["fence_strip"], {"applied": 2, "changed": 1})

    def test_applies_under_the_decomposition_veto(self):
        veto = on.VETO_MARKERS[0] + "\n" + PLAIN_PROMPT
        with mock.patch.dict(os.environ, {on.ENV_FLAG: "on"}):
            out, label = on.maybe_normalize(veto, '```json\n{"output": "x (duration in minutes: 5, minutes left: 10)"}\n```')
            self.assertIsNone(label)                                           # vetoed prompt: the annotation rule still does not run
            self.assertEqual(out, '{"output": "x (duration in minutes: 5, minutes left: 10)"}')   # annotation kept, only the fence removed


class TestRealUpstreamParsePath(unittest.TestCase):
    """The upstream function that crashed the pilot, with only ChatGPT_request stubbed to return the captured reply."""

    def _run(self, raw, flag):
        import persona.prompt_template.gpt_structure as gs
        env = {on.ENV_FLAG: "on"} if flag else {}
        with mock.patch.dict(os.environ, env):
            if not flag:
                os.environ.pop(on.ENV_FLAG, None)
            delivered, _ = on.maybe_normalize(PLAIN_PROMPT, raw)
            with mock.patch.object(gs, "ChatGPT_request", return_value=delivered):
                return gs.ChatGPT_safe_generate_response("p", "e", "s", 3, "FAILSAFE", lambda r, prompt="": True, lambda r, prompt="": "OK:" + r)

    def test_captured_replies_crash_the_parse_without_the_fence_rule_and_pass_with_it(self):
        for arm, rec in FIX.items():
            self.assertIs(self._run(rec["raw"], flag=False), False, arm)
            self.assertTrue(str(self._run(rec["raw"], flag=True)).startswith("OK:"), arm)


if __name__ == "__main__":
    unittest.main()
