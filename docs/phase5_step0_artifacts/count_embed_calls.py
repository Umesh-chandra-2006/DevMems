"""Count how many Gemini embedding HTTP calls a normal test-module run would make.
No network: a fake key is set and requests.post is stubbed to return HTTP 500 (get_embedding then
falls back to its deterministic vector). Prints counts only; never prints URLs with keys."""
import os, sys, json, unittest, collections
os.environ["GEMINI_KEY_1"] = "FAKE"
os.environ["GEMINI_KEY_2"] = "FAKE"
sys.path.insert(0, "D:/DevMems")
import requests

calls = collections.Counter()

class R:
    status_code = 500
    def json(self):
        return {}

def fake_post(url, *a, **k):
    if "embedContent" in url or "embedding" in url:
        model = url.split("/models/")[1].split(":")[0]
        calls[model] += 1
    else:
        calls["OTHER"] += 1
    return R()

requests.post = fake_post
mods = sys.argv[1:]
suite = unittest.defaultTestLoader.loadTestsFromNames(mods)
res = unittest.TextTestRunner(stream=open(os.devnull, "w")).run(suite)
print(json.dumps({"modules": mods, "tests_run": res.testsRun, "failures": len(res.failures), "errors": len(res.errors),
                  "embedding_http_calls_by_model": dict(calls)}))
