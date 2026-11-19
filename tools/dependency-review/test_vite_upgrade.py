"""Check that the Vite candidate cannot silently change other inputs."""

import json
from pathlib import Path
import unittest

from lock_review import ReviewError, read_input
from openzeppelin_candidate import encoded
from vite_upgrade import PLATFORM_PLAN, LOCATION, PUBLICATION, candidate_lock, carry_published_libc, review_platform_installation


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


class PublishedLibcControls(unittest.TestCase):
    def setUp(self):
        repo = Path(__file__).resolve().parents[2]
        self.plan = read_input(repo, PLATFORM_PLAN)
        self.rows = {LOCATION: {'dependencies': {}}}
        for family in json.loads(self.plan)['families']:
            parent = family['selection']
            parent_path = LOCATION + '/node_modules/' + parent['name']
            self.rows[LOCATION]['dependencies'][parent['name']] = parent['version']
            optional = {}
            for publication in family['publications']:
                selection = publication['selection']
                optional[selection['name']] = selection['version']
                self.rows[parent_path + '/node_modules/' + selection['name']] = {**selection, 'optional': True,
                    **{field: publication['selectors'][field] for field in ('os', 'cpu')}}
            self.rows[parent_path] = {**parent, 'optionalDependencies': optional}

    def test_exact_publications_get_their_selectors_and_repeat_is_idempotent(self):
        checked = carry_published_libc(self.rows, self.plan)
        self.assertEqual(len(checked['publications']), 10)
        self.assertEqual(len(checked['carriedLocations']), 10)
        for location, publication in checked['publications'].items():
            self.assertEqual(self.rows[location]['libc'], publication['selectors']['libc'])
            self.assertEqual(self.rows[location]['integrity'], publication['selection']['integrity'])
        self.assertEqual(carry_published_libc(self.rows, self.plan)['carriedLocations'], [])

    def test_different_publication_or_explicit_abi_cannot_be_overwritten(self):
        location = next(name for name in self.rows if name.endswith('binding-linux-x64-gnu'))
        original = self.rows[location]['integrity']
        self.rows[location]['integrity'] = PUBLICATION['integrity']
        with self.assertRaisesRegex(ReviewError, 'native publication identity differs'):
            carry_published_libc(self.rows, self.plan)
        self.rows[location]['integrity'] = original
        self.rows[location]['libc'] = ['musl']
        with self.assertRaisesRegex(ReviewError, 'conflicting published libc selector'):
            carry_published_libc(self.rows, self.plan)

    def test_glibc_installation_requires_gnu_and_excludes_both_musl_packages(self):
        checked = carry_published_libc(self.rows, self.plan)
        compatible = {location for location in checked['publications'] if location.endswith('linux-x64-gnu')}
        excluded = set(checked['publications']) - compatible
        installed = {location: {'manifestSelectors': checked['publications'][location]['selectors']} for location in compatible}
        result = review_platform_installation(checked, installed, excluded)
        self.assertEqual(len(result['excludedByLibc']), 2)
        self.assertEqual(result['excludedUnpackedBytesFromRegistry'], 31246836)
        musl = result['excludedByLibc'][0]
        with self.assertRaisesRegex(ReviewError, 'install differs'):
            review_platform_installation(checked, {**installed, musl: {}}, excluded - {musl})
