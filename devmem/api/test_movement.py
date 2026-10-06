"""
Phase 8 Stop 2 data-layer tests (standard library, offline): the movement archive (one zip with a loader), movement and thoughts access,
the live status reader and the rehearsal check. The committed Step D recording ships `movement.zip`; round-trip and growing-folder tests use a
small synthetic simulation folder (label: synthetic). No LLM call, no network, nothing written to a run.
"""
import json
import os
import shutil
import tempfile
import time
import unittest
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from devmem.api import movement_archive as ma
from devmem.api import store

ROOT = Path(__file__).resolve().parent.parent.parent
STEPD = "phase6_stepd_artifacts"
ISA = "Isabella Rodriguez"


def make_sim(tmp: Path, steps: int = 12, name: str = "simX") -> Path:
    sim = tmp / name
    (sim / "movement").mkdir(parents=True)
    (sim / "reverie").mkdir()
    (sim / "personas" / "A One" / "bootstrap_memory" / "associative_memory").mkdir(parents=True)
    (sim / "reverie" / "meta.json").write_text(json.dumps({
        "fork_sim_code": "f", "start_date": "February 13, 2023", "curr_time": "February 13, 2023, 06:02:00", "sec_per_step": 10,
        "maze_name": "the_ville", "persona_names": ["A One", "B Two"], "step": steps}), encoding="utf-8")
    for s in range(steps):
        (sim / "movement" / f"{s}.json").write_text(json.dumps({"persona": {
            "A One": {"movement": [s, 2 * s], "pronunciatio": "A", "description": f"walking {s} @ the Ville:Cafe:main:table", "chat": [["A One", f"hello {s}"]] if s == 3 else None},
            "B Two": {"movement": [5, 5], "pronunciatio": "B", "description": "sleeping @ the Ville:Dorm:room:bed", "chat": None}}, "meta": {}}), encoding="utf-8")
    (sim / "personas" / "A One" / "bootstrap_memory" / "associative_memory" / "nodes.json").write_text(json.dumps({
        "node_1": {"type": "event", "created": "2023-02-13 06:00:10", "description": "an event"},
        "node_2": {"type": "thought", "created": "2023-02-13 06:00:00", "description": "a plan thought"},
        "node_3": {"type": "thought", "created": "2023-02-13 06:01:30", "description": "a later thought"},
        "node_4": {"type": "chat", "created": "2023-02-13 06:01:00", "description": "a chat node"}}), encoding="utf-8")
    return sim


class TestCommittedMovementArchive(unittest.TestCase):
    def test_the_step_d_archive_loads_with_meta_frames_and_thoughts(self):
        m = store.movement_meta(STEPD)
        self.assertTrue(m["available"])
        self.assertEqual((m["source"], m["frames"], m["sec_per_step"], m["start_time"]), ("zip", 2791, 10, "2023-02-13 06:00:00"))
        self.assertEqual((m["t_min"], m["t_max"]), ("2023-02-13 06:00:00", "2023-02-13 13:45:00"))
        self.assertEqual(m["persona_names"], ["Isabella Rodriguez", "Maria Lopez", "Klaus Mueller"])
        f = store.movement_frames(STEPD, 1000, 1002)
        self.assertEqual([x["s"] for x in f["frames"]], [1000, 1001, 1002])
        p = f["frames"][0]["p"][ISA]
        self.assertEqual(p[:2], [79, 19])
        self.assertIn("opening Hobbs Cafe", p[3])
        self.assertIn("@ the Ville:Hobbs Cafe", p[3])
        s = store.movement_frames(STEPD, 0, 2790, stride=360)
        self.assertEqual([x["s"] for x in s["frames"]], [0, 360, 720, 1080, 1440, 1800, 2160, 2520])
        t = store.agent_thoughts(STEPD, ISA, "2023-02-13 07:00:00")
        self.assertTrue(t["available"])
        self.assertEqual((t["up_to_t"], t["total_in_record"]), (1, 1))
        self.assertIn("plan for Monday February 13", t["thoughts"][0]["description"])
        self.assertEqual(store.agent_thoughts(STEPD, ISA, "2023-02-13 05:00:00")["up_to_t"], 0)

    def test_movement_zip_is_read_only_and_unchanged_by_reads(self):
        import hashlib
        z = ROOT / "docs" / STEPD / "movement.zip"
        before = hashlib.sha256(z.read_bytes()).hexdigest()
        for _ in range(3):
            store.movement_meta(STEPD); store.movement_frames(STEPD, 0, 100); store.agent_thoughts(STEPD, ISA)
        self.assertEqual(hashlib.sha256(z.read_bytes()).hexdigest(), before)

    def test_the_committed_archive_equals_its_own_documented_layout(self):
        with zipfile.ZipFile(ROOT / "docs" / STEPD / "movement.zip") as zf:
            self.assertEqual(sorted(zf.namelist()), ["frames.jsonl", "meta.json", "thoughts.json"])
            lines = zf.read("frames.jsonl").decode().splitlines()
            self.assertEqual(len(lines), 2791)
            first = json.loads(lines[0])
            self.assertEqual(set(first), {"s", "p"})
            self.assertEqual(len(first["p"]["Maria Lopez"]), 5)


class TestExportRoundTripAndGrowingFolder(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="p8_mov_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_export_then_load_equals_reading_the_folder(self):
        sim = make_sim(self.tmp)
        out = self.tmp / "run" / "movement.zip"
        meta = ma.export(sim, out)
        self.assertEqual((meta["frames"], meta["first_step"], meta["last_step"], meta["start_time"]), (12, 0, 11, "2023-02-13 06:00:00"))
        from_zip = ma.MovementSource.open(out.parent, "simX")
        from_folder = ma.MovementSource("folder", sim, {})
        self.assertEqual(from_zip.kind, "zip")
        a, b = from_zip.frames(0, 11), from_folder.frames(0, 11)
        self.assertEqual(a["frames"], b["frames"])
        self.assertEqual(a["frames"][3]["p"]["A One"][4], [["A One", "hello 3"]])
        da, db = from_zip.describe(), from_folder.describe()
        for k in ("start_time", "sec_per_step", "persona_names", "first_step", "last_step", "frames", "t_min", "t_max"):
            self.assertEqual(da[k], db[k], k)
        ta, tb = from_zip.thoughts("A One", None), from_folder.thoughts("A One", None)
        self.assertEqual([x["description"] for x in ta["thoughts"]], ["a plan thought", "a later thought"])
        self.assertEqual(ta["thoughts"], tb["thoughts"])
        self.assertEqual([x["description"] for x in from_zip.thoughts("A One", "2023-02-13 06:00:30")["thoughts"]], ["a plan thought"])

    def test_a_folder_that_is_still_growing_is_read_fresh(self):
        sim = make_sim(self.tmp, steps=6)
        src = ma.MovementSource("folder", sim, {})
        self.assertEqual(src.describe()["last_step"], 5)
        extra = json.loads((sim / "movement" / "5.json").read_text())
        (sim / "movement" / "6.json").write_text(json.dumps(extra))
        self.assertEqual(src.describe()["last_step"], 6)
        self.assertEqual([f["s"] for f in src.frames(5, 9)["frames"]], [5, 6], "a step with no file is simply absent, nothing is invented")

    def test_frame_limit_and_stride(self):
        sim = make_sim(self.tmp, steps=12)
        src = ma.MovementSource("folder", sim, {})
        self.assertEqual(len(src.frames(0, 11, stride=1, limit=5)["frames"]), 5)
        self.assertTrue(src.frames(0, 11, stride=1, limit=5)["truncated"])
        self.assertEqual([f["s"] for f in src.frames(0, 11, stride=4)["frames"]], [0, 4, 8])

    def test_export_refuses_a_folder_without_movement(self):
        sim = make_sim(self.tmp)
        for f in (sim / "movement").glob("*.json"):
            f.unlink()
        with self.assertRaises(ValueError):
            ma.export(sim, self.tmp / "x.zip")

    def test_a_reversed_step_range_is_rejected(self):
        with self.assertRaises(ValueError):
            store.movement_frames(STEPD, 10, 5)

    def test_runs_without_movement_say_so(self):
        run = self.tmp / "norun"
        run.mkdir()
        import sqlite3
        sqlite3.connect(str(run / "memory.db")).close()
        with mock.patch.dict(os.environ, {"DEVMEM_API_ROOTS": str(self.tmp)}):
            m = store.movement_meta("norun")
            self.assertFalse(m["available"])
            self.assertIn("no movement.zip", m["reason"])
            with self.assertRaises(store.NotFound):
                store.movement_frames("norun", 0, 10)
            self.assertFalse(store.agent_thoughts("norun", ISA)["available"])


class TestLiveStatus(unittest.TestCase):
    def test_fresh_running_status_is_live_and_old_or_finished_is_not(self):
        import sqlite3
        tmp = Path(tempfile.mkdtemp(prefix="p8_live_"))
        self.addCleanup(shutil.rmtree, tmp, True)
        run = tmp / "r"
        run.mkdir()
        sqlite3.connect(str(run / "memory.db")).close()
        sf = run / "run_status.json"
        with mock.patch.dict(os.environ, {"DEVMEM_API_ROOTS": str(tmp)}):
            self.assertFalse(store.run_status("r")["available"])
            sf.write_text(json.dumps({"state": "running", "router_calls_total": 42, "quota_pauses": 1, "sim_clock": "2023-02-13 08:00:00"}))
            s = store.run_status("r")
            self.assertTrue(s["fresh"] and s["available"])
            self.assertEqual(s["status"]["router_calls_total"], 42)
            old = time.time() - 600
            os.utime(sf, (old, old))
            self.assertFalse(store.run_status("r")["fresh"])
            sf.write_text(json.dumps({"state": "finished: completed", "router_calls_total": 42}))
            self.assertFalse(store.run_status("r")["fresh"], "a finished run is not a live segment")


class TestRehearsalCheck(unittest.TestCase):
    def test_check_is_clean_on_the_recordings_and_flags_a_missing_run(self):
        from devmem.api import serve
        self.assertFalse([p for p in serve.check(STEPD, STEPD) if p.startswith("missing file")])
        self.assertEqual([p for p in serve.check(STEPD, STEPD) if "not found" in p], [])
        bad = serve.check(STEPD, "no_such_run")
        self.assertTrue(any("right run 'no_such_run' not found" in p for p in bad))
        notes = serve.check("phase6_stop3_artifacts", STEPD)
        self.assertTrue(any("has no movement" in p for p in notes))

    def test_check_exit_code(self):
        from devmem.api import serve
        self.assertEqual(serve.main(["--check", "--a", STEPD, "--b", STEPD]), 0)
        self.assertEqual(serve.main(["--check", "--a", STEPD, "--b", "no_such_run"]), 1)


class TestFrontendFiles(unittest.TestCase):
    def test_every_frontend_script_parses_with_node_when_node_is_available(self):
        import shutil as sh
        import subprocess
        node = sh.which("node")
        if node is None:
            self.skipTest("node is not installed here")
        for f in ("app.js", "common.js", "town.js", "cost.js"):
            r = subprocess.run([node, "--check", str(ROOT / "devmem" / "api" / "web" / f)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, f + ": " + r.stderr[:300])

    def test_vendor_note_records_phaser_with_its_published_hash_and_the_file_matches_the_recorded_sha256(self):
        import hashlib
        note = (ROOT / "devmem" / "api" / "web" / "vendor" / "VENDOR.md").read_text(encoding="utf-8")
        self.assertIn("sha512-amKXsbb2Ht29dGPKvt1edq3yGGYKtq8373GpJYGKPNPnneYY6MtVTOgjHDuZwtmUyK4v86FugkT3hzW/N4tjxQ==", note)
        data = (ROOT / "devmem" / "api" / "web" / "vendor" / "phaser.js").read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), "494b0609ea5de72cf9dc22401343247d01a955aa48f92670f121868296418381")
        for lib, digest in (("react.production.min.js", "d949f1c3687aedadcedac85261865f29b17cd273997e7f6b2bfc53b2f9d4c4dd"),
                            ("react-dom.production.min.js", "35f4f974f4b2bcd44da73963347f8952e341f83909e4498227d4e26b98f66f0d")):
            self.assertEqual(hashlib.sha256((ROOT / "devmem" / "api" / "web" / "vendor" / lib).read_bytes()).hexdigest(), digest, lib)
        self.assertTrue((ROOT / "devmem/api/web/vendor/LICENSE-phaser.md").exists())

    def test_the_two_upstream_pages_reference_exactly_the_vendored_phaser_version(self):
        up = ROOT / "reverie" / "environment" / "frontend_server" / "templates"
        for page in ("home/home.html", "demo/demo.html"):
            self.assertIn("phaser@3.55.2/dist/phaser.js", (up / page).read_text(encoding="utf-8"), page)


if __name__ == "__main__":
    unittest.main()
