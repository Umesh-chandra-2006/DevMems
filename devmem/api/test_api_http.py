"""
HTTP-level tests of the memory inspector API (Phase 8 Stop 1), offline, against the committed recordings. They need fastapi and httpx,
which the project venv (Python 3.9) does not have; they SKIP there and are run with the system Python that has them:
    python313 -m unittest devmem.api.test_api_http
No LLM call, no network (the client talks to the app in-process), no write to a run.
"""
import hashlib
import json
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient
    from devmem.api.main import app
    HAVE = True
except Exception:  # pragma: no cover - environment without fastapi
    HAVE = False

ROOT = Path(__file__).resolve().parent.parent.parent
STEPD, STOP3, ISA = "phase6_stepd_artifacts", "phase6_stop3_artifacts", "Isabella Rodriguez"


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


@unittest.skipUnless(HAVE, "fastapi/httpx not installed in this interpreter")
class TestApiHttp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = TestClient(app)

    def get(self, path, status=200):
        r = self.c.get(path)
        self.assertEqual(r.status_code, status, r.text[:300])
        self.assertTrue(r.headers["content-type"].startswith("application/json"), r.headers["content-type"])
        return r.json()

    def test_every_endpoint_returns_well_formed_json_on_both_recordings(self):
        runs = self.get("/runs")["runs"]
        ids = {r["run"] for r in runs}
        self.assertTrue({STEPD, STOP3} <= ids)
        for run in (STEPD, STOP3):
            lab = self.get(f"/runs/{run}/label")
            self.assertEqual(lab["run"], run)
            ag = self.get(f"/runs/{run}/agents")
            self.assertTrue(ag["agents"])
            for a in ag["agents"]:
                st = self.get(f"/runs/{run}/agents/{a['agent']}/state")
                self.assertEqual(set(st), {"run", "agent", "sim_time", "label", "stage1_priors", "stage2_episodic", "stage3_semantic",
                                           "stage4_identity", "identity_context_at_t"})
                json.dumps(st)
            tl = self.get(f"/runs/{run}/timeline")
            self.assertEqual(tl["count"], len(tl["events"]))
            led = self.get(f"/runs/{run}/ledger/summary")
            self.assertIn("available", led)
        cmp_ = self.get(f"/compare?a={STEPD}&b={STOP3}&agent=Isabella%20Rodriguez&t=2023-02-13%2013:00:00")
        self.assertEqual((cmp_["a"]["run"], cmp_["b"]["run"]), (STEPD, STOP3))

    def test_time_parameter_changes_the_state(self):
        early = self.get(f"/runs/{STEPD}/agents/Isabella%20Rodriguez/state?t=2023-02-13%2008:00:00")
        late = self.get(f"/runs/{STEPD}/agents/Isabella%20Rodriguez/state?t=2023-02-13%2013:00:00")
        self.assertLess(early["stage2_episodic"]["entries_total_up_to_t"], late["stage2_episodic"]["entries_total_up_to_t"])

    def test_errors_are_json_404_and_422_not_stack_traces(self):
        self.assertIn("unknown run", self.get("/runs/nope/agents", 404)["detail"])
        self.assertIn("unknown agent", self.get(f"/runs/{STEPD}/agents/Nobody/state", 404)["detail"])
        self.assertIn("time must look like", self.get(f"/runs/{STEPD}/agents/Isabella%20Rodriguez/state?t=yesterday", 422)["detail"])
        self.assertEqual(self.c.get("/compare?a=x").status_code, 422)

    def test_no_route_accepts_a_write_method(self):
        paths = ["/runs", f"/runs/{STEPD}/label", f"/runs/{STEPD}/agents", f"/runs/{STEPD}/agents/Isabella%20Rodriguez/state",
                 f"/runs/{STEPD}/timeline", f"/runs/{STEPD}/ledger/summary", "/compare?a=x&b=y&agent=z"]
        before = {r: sha(ROOT / "docs" / r / "memory.db") for r in (STEPD, STOP3)}
        for p in paths:
            for method in ("post", "put", "patch", "delete"):
                self.assertEqual(getattr(self.c, method)(p).status_code, 405, (method, p))
        self.assertEqual(before, {r: sha(ROOT / "docs" / r / "memory.db") for r in (STEPD, STOP3)})
        methods = {m for route in app.routes if hasattr(route, "methods") for m in route.methods if route.path not in ("/openapi.json", "/docs", "/redoc", "/docs/oauth2-redirect")}
        self.assertEqual(methods - {"GET", "HEAD"}, set())

    def test_static_ui_is_served_from_the_vendored_files_without_a_cdn(self):
        html = self.c.get("/ui/index.html")
        self.assertEqual(html.status_code, 200)
        self.assertNotIn("http://", html.text.replace("http://www.w3.org", ""))
        self.assertNotIn("https://", html.text)
        for f in ("vendor/react.production.min.js", "vendor/react-dom.production.min.js", "app.js", "style.css"):
            self.assertEqual(self.c.get("/ui/" + f).status_code, 200, f)
        js = self.c.get("/ui/app.js").text
        self.assertNotIn("https://", js)
        for banned in ("POST", "method:", "XMLHttpRequest", "sendBeacon", "WebSocket"):
            self.assertNotIn(banned, js, banned)
        self.assertEqual(js.count("fetch("), 1, "the single helper `api` issues every request, GET only")

    def test_no_key_or_secret_is_served(self):
        blob = json.dumps(self.get("/runs")) + self.c.get("/ui/app.js").text + self.c.get("/ui/index.html").text
        for pat in ("AIza", "gsk_", "nvapi-", "GEMINI_KEY", "GROQ_KEY", "NIM_KEY"):
            self.assertNotIn(pat, blob, pat)


if __name__ == "__main__":
    unittest.main()
