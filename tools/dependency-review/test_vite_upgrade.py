"""Check that the Vite candidate cannot silently change other inputs."""

import json
from pathlib import Path
import unittest

from lock_review import ReviewError, read_input
from openzeppelin_candidate import encoded
from vite_upgrade import LOCATION, PUBLICATION, candidate_lock


class ViteCandidateLockControls(unittest.TestCase):
    def setUp(self):
        repo = Path(__file__).resolve().parents[2]
        self.baseline = read_input(repo, 'web/package-lock.json')
        self.candidate = json.loads(self.baseline)
        self.rows = self.candidate['packages']
        self.rows['']['devDependencies']['vite'] = PUBLICATION['version']
        self.rows[LOCATION].update({key: PUBLICATION[key] for key in ('version', 'resolved', 'integrity')})

    def review(self):
        return candidate_lock(self.baseline, encoded(self.candidate))

    def test_pin_and_runtime_rows_are_retained(self):
        result, report = self.review()
        self.assertEqual(result, encoded(self.candidate))
        changes = report['lockDelta']['publicationChanges']
        self.assertEqual([row['location'] for row in changes], [LOCATION])
        self.assertIn('node_modules/chromium-bidi', report['unchangedRuntimeLocations'])
        self.assertIn('node_modules/zod', report['unchangedRuntimeLocations'])

    def test_reference_to_different_vite_bytes_is_refused(self):
        self.rows[LOCATION]['integrity'] = self.rows['node_modules/zod']['integrity']
        with self.assertRaisesRegex(ReviewError, 'Vite publication differs'):
            self.review()

    def test_unreviewed_runtime_change_is_refused(self):
        self.rows['node_modules/chromium-bidi']['integrity'] = self.rows[LOCATION]['integrity']
        with self.assertRaisesRegex(ReviewError, 'runtime dependency graph changed'):
            self.review()

    def test_other_root_or_package_changes_are_refused(self):
        unrelated = self.rows['node_modules/vue']
        unrelated['integrity'] = self.rows[LOCATION]['integrity']
        with self.assertRaisesRegex(ReviewError, 'outside the Vite graph changed'):
            self.review()
        self.rows['']['dependencies']['vue'] = '3.0.0'
        with self.assertRaisesRegex(ReviewError, 'root declarations differ beyond Vite'):
            self.review()
