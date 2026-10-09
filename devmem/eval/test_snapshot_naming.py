"""Test of the crash snapshot naming: two crashes without an autosave in between must not share a folder name (ledger H28)."""
import tempfile
import unittest
from pathlib import Path

from devmem.eval.run_support import unique_snapshot_path


class TestSnapshotNaming(unittest.TestCase):
    def test_a_second_crash_gets_the_next_free_name_and_the_first_snapshot_stays(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            first = unique_snapshot_path(t, "p7_staged", 5)
            self.assertEqual(first.name, "p7_staged__crash_snapshot_6")
            first.mkdir()
            (first / "marker.txt").write_text("first crash")
            second = unique_snapshot_path(t, "p7_staged", 5)               # the run counter did not move: same input as before
            self.assertEqual(second.name, "p7_staged__crash_snapshot_7")
            second.mkdir()
            self.assertEqual(unique_snapshot_path(t, "p7_staged", 5).name, "p7_staged__crash_snapshot_8")
            self.assertEqual((first / "marker.txt").read_text(), "first crash")      # never removed
            self.assertEqual(unique_snapshot_path(t, "p7_baseline", 0).name, "p7_baseline__crash_snapshot_1")


if __name__ == "__main__":
    unittest.main()
