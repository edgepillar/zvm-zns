"""Keep compiled labels complete within scope and separate from package facts."""

import unittest

from compiled_labels import canonical_sha256, inspect_labels


class CompiledLabelControls(unittest.TestCase):
    def test_scoped_and_peer_qualified_region_labels_are_preserved(self):
        raw = b'//#region ../../node_modules/.pnpm/@scope+tool@1.2.3_peer@2.0.0/node_modules/@scope/tool/index.js\n'
        value = inspect_labels({'dist/config.js': raw})
        self.assertEqual(value['distinctNameVersionLabels'], [{'name': '@scope/tool', 'version': '1.2.3'}])
        self.assertIn('_peer@2.0.0', value['generatedRegionLabels'][0]['generatedLocator'])
        self.assertFalse(value['independentlyAuthenticatedPackageManifests'])
        self.assertFalse(value['applicationRuntimeReachabilityEstablished'])
        self.assertFalse(value['completeSBOM'])

    def test_repeated_regions_keep_locations_but_deduplicate_request_pairs(self):
        line = b'//#region ../../node_modules/.pnpm/tool@1.0.0/node_modules/tool/index.js\n'
        value = inspect_labels({'dist/a.js': line + line, 'dist/b.js': line})
        self.assertEqual(len(value['generatedRegionLabels']), 3)
        self.assertEqual(len(value['distinctNameVersionLabels']), 1)
        self.assertEqual(value['generatedRegionLabels'][1]['line'], 2)
        self.assertEqual(canonical_sha256(value), canonical_sha256(dict(reversed(list(value.items())))))

    def test_unreviewed_names_versions_and_header_formats_remain_unknown(self):
        lines = [
            b'//#region ../../node_modules/.pnpm/other@1.0.0/node_modules/tool/index.js',
            b'//#region ../../node_modules/.pnpm/tool@latest/node_modules/tool/index.js',
            b'//#region ../../node_modules/.pnpm/tool@1.0.0/node_modules/Tool/index.js',
            b'//#region C:\\node_modules\\.pnpm\\tool@1.0.0\\index.js',
        ]
        value = inspect_labels({'dist/config.js': b'\n'.join(lines)})
        self.assertEqual(len(value['unparsedRegionLabels']), 4)
        self.assertEqual(value['status'], 'GENERATED_REGION_REVIEW_INCOMPLETE')
        self.assertEqual(value['distinctNameVersionLabels'], [])

    def test_lf_source_positions_ignore_other_controls_and_non_header_strings(self):
        raw = (b'const text = "\\u000b";\x0b\n'
               b'const example = "//#region ../../node_modules/.pnpm/tool@1.0.0/node_modules/tool/x.js";\n'
               b'//#region ../../node_modules/.pnpm/tool@1.0.0/node_modules/tool/x.js\n')
        value = inspect_labels({'dist/config.js': raw, 'README.md': b'not executable input'})
        self.assertEqual([row['line'] for row in value['generatedRegionLabels']], [3])
        self.assertEqual(set(value['sourceFilePins']), {'dist/config.js'})

    def test_paths_encoding_and_member_budget_are_checked_before_inventory(self):
        for files in ({'../private.js': b''}, {'dist/.env': b''}, {'dist/file.js': b'\xff'}, {'dist/file.js': b'x' * ((2 << 20) + 1)}):
            with self.subTest(names=list(files)), self.assertRaises(ValueError):
                inspect_labels(files)


if __name__ == '__main__':
    unittest.main()
