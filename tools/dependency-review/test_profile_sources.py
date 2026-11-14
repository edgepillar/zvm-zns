"""Keep cache/profile source refusals memory-only before installed code runs."""

import base64
import hashlib
import io
import json
import tarfile
import unittest

from lock_review import ReviewError
from profile_sources import inspect_profile_archive, matches_profile, select_profile

PROFILE = {'os': 'linux', 'cpu': 'x64', 'libc': 'glibc'}


def raw(value):
    return json.dumps(value, sort_keys=True).encode()


def publication(root='package', *, special=None, extra=None, manifest=None):
    manifest = manifest or {'name': 'example', 'version': '1.0.0', 'dependencies': {'child': '^1.0.0'}}
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode='w:gz') as target:
        members = [(root + '/package.json', raw(manifest)), (root + '/index.js', b'export const value = 1;\n')]
        if extra: members.extend(extra)
        for name, body in members:
            item = tarfile.TarInfo(name); item.size = len(body); target.addfile(item, io.BytesIO(body))
        if special:
            item = tarfile.TarInfo(root + '/link'); item.type = special; item.linkname = 'index.js'; target.addfile(item)
    data = payload.getvalue()
    selection = {'name': 'example', 'version': '1.0.0', 'resolved': 'https://registry.npmjs.org/example/-/example-1.0.0.tgz',
        'integrity': 'sha512-' + base64.b64encode(hashlib.sha512(data).digest()).decode()}
    return data, selection, {'dependencies': {'child': '^1.0.0'}}


def table():
    selected = {'version': '1.0.0', 'resolved': 'https://registry.npmjs.org/a/-/a-1.0.0.tgz',
        'integrity': 'sha512-' + base64.b64encode(b'x' * 64).decode()}
    return {'lockfileVersion': 3, 'packages': {'': {}, 'node_modules/a': selected,
        'node_modules/macos': {**selected, 'optional': True, 'os': ['darwin']},
        'node_modules/macos/node_modules/inside': {'inBundle': True, 'version': '1.0.0'}}}


class ProfileSourceControls(unittest.TestCase):
    def test_regular_archive_and_nonstandard_single_root_bind_manifest_and_members(self):
        for root in ['package', 'types v1.0']:
            data, selection, row = publication(root)
            result = inspect_profile_archive(data, selection, row)
            self.assertEqual(result['archiveRoot'], root)
            self.assertEqual(set(result['filePins']), {'package.json', 'index.js'})
            self.assertEqual(result['filePins']['index.js']['sha256'], hashlib.sha256(b'export const value = 1;\n').hexdigest())

    def test_integrity_is_checked_before_tar_processing(self):
        data, selection, row = publication()
        with self.assertRaisesRegex(ReviewError, 'integrity differs'): inspect_profile_archive(data + b' ', selection, row)

    def test_manifest_identity_and_dependency_declarations_are_required(self):
        data, selection, row = publication()
        for key, value in [('name', 'other'), ('version', '2.0.0')]:
            changed = {**selection, key: value}
            with self.subTest(key=key), self.assertRaisesRegex(ReviewError, 'identity differs'): inspect_profile_archive(data, changed, row)
        with self.assertRaisesRegex(ReviewError, 'dependency declarations differ'): inspect_profile_archive(data, selection, {})

    def test_links_and_other_nonregular_archive_entries_are_refused(self):
        for kind in [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE, tarfile.CHRTYPE]:
            data, selection, row = publication(special=kind)
            with self.subTest(kind=kind), self.assertRaises(ReviewError): inspect_profile_archive(data, selection, row)

    def test_traversal_case_aliases_and_multiple_roots_are_refused(self):
        for name in ['package/../outside.js', 'package/INDEX.js', 'other/root.js', '/absolute.js']:
            data, selection, row = publication(extra=[(name, b'1')])
            with self.subTest(name=name), self.assertRaises(ReviewError): inspect_profile_archive(data, selection, row)

    def test_archive_expansion_budget_is_explicit(self):
        data, selection, row = publication()
        with self.assertRaisesRegex(ReviewError, 'expanded source budget'): inspect_profile_archive(data, selection, row, expanded_limit=512)

    def test_all_lock_rows_are_classified_including_absent_bundled_descendants(self):
        result = select_profile(raw(table()), {'node_modules/a'}, PROFILE)
        self.assertEqual(set(result['selected']), {'node_modules/a'})
        self.assertEqual(result['excluded']['node_modules/macos']['reason'], 'OPTIONAL_PLATFORM_MISMATCH')
        self.assertEqual(result['excluded']['node_modules/macos/node_modules/inside']['ancestor'], 'node_modules/macos')
        self.assertEqual(len(result['decisions']), 3)

    def test_missing_compatible_optional_packages_are_not_silently_waived(self):
        value = table(); value['packages']['node_modules/a']['optional'] = True
        with self.assertRaisesRegex(ReviewError, 'compatible package missing'): select_profile(raw(value), set(), PROFILE)

    def test_installed_mismatch_unknown_location_or_required_mismatch_is_refused(self):
        with self.assertRaises(ReviewError): select_profile(raw(table()), {'node_modules/a', 'node_modules/macos'}, PROFILE)
        with self.assertRaises(ReviewError): select_profile(raw(table()), {'node_modules/unknown'}, PROFILE)
        value = table(); value['packages']['node_modules/macos'].pop('optional')
        with self.assertRaises(ReviewError): select_profile(raw(value), {'node_modules/a'}, PROFILE)

    def test_selector_negation_and_positive_constraints_both_apply(self):
        self.assertTrue(matches_profile({'os': ['linux', '!darwin'], 'cpu': ['x64'], 'libc': ['glibc']}, PROFILE))
        for value in [{'os': ['linux', '!linux']}, {'cpu': ['!x64']}, {'libc': ['musl']}, {'os': ['!any']}]:
            with self.subTest(value=value): self.assertFalse(matches_profile(value, PROFILE))
        self.assertTrue(matches_profile({'os': ['any']}, PROFILE))


if __name__ == '__main__': unittest.main()
