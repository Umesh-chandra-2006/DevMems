"""Offline tests for devmem.router.output_normalizer (synthetic strings)."""
import unittest

from devmem.router.output_normalizer import (
    has_duration_suffix,
    has_exotic_space,
    normalize_output,
    normalize_unicode_spaces,
    strip_duration_suffix,
)


class TestNormalizer(unittest.TestCase):
    def test_maps_unicode_spaces_to_plain_space(self):
        text = "6:00 am to 7:00 am　x"
        self.assertEqual(normalize_unicode_spaces(text), "6:00 am to 7:00 am x")
        self.assertFalse(has_exotic_space(normalize_unicode_spaces(text)))
        self.assertTrue(has_exotic_space(text))

    def test_strips_duration_suffix_only_when_asked(self):
        s = "eating breakfast (duration in minutes: 60, minutes left: 0)"
        self.assertEqual(normalize_output(s), s)
        self.assertEqual(normalize_output(s, strip_duration=True), "eating breakfast")
        self.assertTrue(has_duration_suffix(s))
        self.assertEqual(strip_duration_suffix("a (duration in minutes: 5, minutes left: 55) b"), "a b")

    def test_plain_text_and_idempotence(self):
        t = "wake up and complete the morning routine at 6:00 am."
        self.assertEqual(normalize_output(t, strip_duration=True), t)
        once = normalize_output("x y (duration in minutes: 1, minutes left: 2)", strip_duration=True)
        self.assertEqual(normalize_output(once, strip_duration=True), once)

    def test_does_not_touch_other_characters(self):
        t = "Isabella’s plan – café"
        self.assertEqual(normalize_output(t, strip_duration=True), t)


if __name__ == "__main__":
    unittest.main()
