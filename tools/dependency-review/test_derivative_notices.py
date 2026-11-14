"""Data-only checks for visible notices and generated coordinate preservation."""

import copy
import json
import unittest

from coherent_derivation import runtime_probe
from derivative_notices import MAP_NOTICE, MAPPER_NOTICE, PARSER_NOTICE, noticed_map, shift_mapper_map
from mapper_rebuild_plan import pin
import test_coherent_derivation as fixtures


class DerivativeNotices(unittest.TestCase):
    def test_notice_is_first_property_and_map_unchanged(self):
        source = {'version': 3, 'sources': [], 'mappings': ''}
        raw = noticed_map(json.dumps(source).encode())
        self.assertTrue(raw.startswith(b'{"x_edgepillar_changes":'))
        self.assertEqual(json.loads(raw), {'x_edgepillar_changes': MAP_NOTICE, **source})

    def test_duplicate_notice_refused(self):
        with self.assertRaises(ValueError): noticed_map(noticed_map(b'{}'))

    def test_prefix_preserves_existing_bytes_and_is_one_line(self):
        for value in [PARSER_NOTICE, MAPPER_NOTICE]:
            self.assertTrue(value.isascii()); self.assertEqual(value.count(b'\n'), 1)
            self.assertIn(b'Modified by edgepillar:', value)

    def fixture(self):
        source = b'const value=1;\n'
        raw = json.dumps({'version': 3, 'file': 'mapperTab.js', 'sources': ['derived-compiled-js/value.js'],
            'sourcesContent': [source.decode()], 'names': [], 'mappings': 'AAAA;AACA'}).encode()
        return raw, source

    def test_mappings_shift_only_generated_line(self):
        raw, source = self.fixture(); mapped, count = shift_mapper_map(raw, source, MAPPER_NOTICE + source)
        self.assertEqual(count, 2); before = json.loads(raw); after = json.loads(mapped)
        self.assertEqual(after.pop('mappings'), ';' + before.pop('mappings'))
        after.pop('x_edgepillar_changes'); self.assertEqual(before, after)

    def test_arbitrary_prefix_refused(self):
        raw, source = self.fixture()
        with self.assertRaises(ValueError): shift_mapper_map(raw, source, b'// other\n' + source)

    def test_noticed_probe_preserves_bootstrap(self):
        raw, review = fixtures.CoherentDerivation().probe(); raw = MAPPER_NOTICE + raw
        review = copy.deepcopy(review); review.update(generatedMapper=pin(raw), noticePrefix=pin(MAPPER_NOTICE))
        for value in review['bindings'].values(): value['generatedLine'] += 1
        probe, result = runtime_probe(raw, review)
        self.assertTrue(probe.startswith(MAPPER_NOTICE)); self.assertIn(b'generatePage();', probe)
        self.assertTrue(result['bootstrapRetained'])

    def test_unreviewed_probe_notice_refused(self):
        raw, review = fixtures.CoherentDerivation().probe(); review['noticePrefix'] = pin(b'// other\n')
        with self.assertRaises(ValueError): runtime_probe(raw, review)
