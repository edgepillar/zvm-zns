"""Reject unbound source/index/instrumentation inputs before package execution."""

import copy
import io
import json
import tarfile
import unittest

from changed_publications import review_changed_publications
from lock_review import ReviewError
from mapper_size_controls import BOOTSTRAP, CAPTURE, SUFFIX, indexed_archive, instrument_mapper
from test_changed_publications import fixture, raw


class MapperSourceControls(unittest.TestCase):
    def source_fixture(self):
        old, new, archives = fixture(); plan = review_changed_publications(raw(old), raw(new), archives)
        selected = plan['pairs'][0]['candidatePublication']['integrity']
        return archives[selected], new['packages']['node_modules/a'], plan['publications'][selected]

    def test_source_index_references_original_offsets_and_hashes_without_extraction(self):
        source, row, expected = self.source_fixture(); result = indexed_archive(source, 'node_modules/a', row, expected)
        self.assertEqual(len(result['members']), 3)
        self.assertTrue(all(member['offset'] % 512 == 0 for member in result['members'].values()))
        self.assertEqual({name: {key: value[key] for key in ('bytes', 'sha256')} for name, value in result['members'].items()}, expected['filePins'])

    def test_changed_raw_source_pin_is_refused(self):
        source, row, expected = self.source_fixture()
        with self.assertRaisesRegex(ReviewError, 'raw source pin differs'): indexed_archive(source + b' ', 'node_modules/a', row, expected)

    def test_missing_or_changed_member_is_refused(self):
        source, row, expected = self.source_fixture()
        for action in ['remove', 'change']:
            changed = copy.deepcopy(expected)
            if action == 'remove': changed['filePins'].pop('index.js')
            else: changed['filePins']['index.js']['sha256'] = '0' * 64
            with self.subTest(action=action), self.assertRaises(ReviewError): indexed_archive(source, 'node_modules/a', row, changed)

    def test_source_identity_and_hashed_manifest_are_required(self):
        source, row, expected = self.source_fixture(); wrong = copy.deepcopy(expected); wrong['selection']['version'] = '9.0.0'
        manifest = copy.deepcopy(expected); manifest['manifestSha256'] = '0' * 64
        for changed in [wrong, manifest]:
            with self.assertRaises(ReviewError): indexed_archive(source, 'node_modules/a', row, changed)

    def test_capture_preserves_declarations_and_removes_only_the_explicit_bootstrap_tail(self):
        prefix = '(function () {\n    const version = {};'
        original = (prefix + BOOTSTRAP + ' = null;\n' + SUFFIX).encode()
        actual, report = instrument_mapper(original)
        self.assertEqual(actual, (prefix + CAPTURE).encode())
        self.assertTrue(report['mapperBootstrapRemoved'])
        self.assertFalse(report['originalPublicationOrApplicationFilesChanged'])

    def test_missing_ambiguous_or_changed_wrapper_is_refused(self):
        for source in ['(function () {\n' + SUFFIX, '(function () {\n' + BOOTSTRAP * 2 + SUFFIX,
            '(async function () {\n' + BOOTSTRAP + SUFFIX, '(function () {\n' + BOOTSTRAP + '})();\n']:
            with self.subTest(source=source), self.assertRaises(ReviewError): instrument_mapper(source.encode())


if __name__ == '__main__': unittest.main()
