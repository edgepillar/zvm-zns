"""Reject incomplete or misleading web-control summaries."""

import unittest

from web_patches import marker, test_summary


class WebPatchDataControls(unittest.TestCase):
    def test_native_summary_needs_all_expected_tests_without_skips(self):
        raw = b'# tests 4\n# pass 4\n# fail 0\n# cancelled 0\n# skipped 0\n# todo 0\n'
        self.assertEqual(test_summary(raw, 4)['pass'], 4)
        for value in (raw + b'# tests 4\n', raw.replace(b'# skipped 0', b'# skipped 1'), raw.replace(b'# fail 0\n', b'')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                test_summary(value, 4)
        with self.assertRaises(ValueError):
            test_summary(raw, 5)

    def test_missing_or_duplicated_control_markers_are_refused(self):
        raw = b'# FIXTURE_RESULT {"version":"1.2.2"}\n'
        self.assertEqual(marker(raw, 'FIXTURE_RESULT')['version'], '1.2.2')
        for value in (b'', raw + raw):
            with self.subTest(value=value), self.assertRaises(ValueError):
                marker(value, 'FIXTURE_RESULT')


if __name__ == '__main__':
    unittest.main()
