import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from application_runtime import verify_inputs


class ApplicationInputControls(unittest.TestCase):
    def test_multi_megabyte_map_uses_the_explicit_larger_bound(self):
        raw = b'x' * (3 << 20)
        value = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        with patch('application_runtime.read_regular', return_value=raw) as reader:
            verify_inputs(Path('/synthetic'), {'mapper.map': value})
        reader.assert_called_once_with(Path('/synthetic'), 'mapper.map', 16 << 20)

    def test_changed_source_is_refused(self):
        with patch('application_runtime.read_regular', return_value=b'changed'):
            with self.assertRaises(ValueError):
                verify_inputs(Path('/synthetic'), {'file': {'bytes': 1, 'sha256': '0' * 64}})

    def test_aggregate_budget_is_not_only_a_per_file_limit(self):
        raw = b'x' * (9 << 20); value = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        with patch('application_runtime.read_regular', return_value=raw):
            with self.assertRaises(ValueError): verify_inputs(Path('/synthetic'), {'a': value, 'b': value})

    def test_actual_payloads_and_maps_match_the_committed_manifest(self):
        root = Path(__file__).resolve().parents[2] / 'web/vendor/chromium-bidi-157-reviewed'
        manifest = json.loads((root / 'manifest.json').read_bytes())
        self.assertEqual(len(manifest['payloads']), 9)
        for name, value in manifest['payloads'].items():
            raw = (root / 'payload' / name).read_bytes()
            self.assertEqual(value, {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
            self.assertEqual(value, manifest['effectiveMembers']['node_modules/chromium-bidi/' + name]['effective'])
        node_map = json.loads((root / 'payload/out/Default/gen/src/protocol-parser/protocol-parser.js.map').read_bytes())
        browser_map = json.loads((root / 'payload/out/Default/gen/src/mapperTab.js.map').read_bytes())
        self.assertEqual(node_map['file'], 'protocol-parser.js')
        self.assertEqual(browser_map['file'], 'mapperTab.js')
        self.assertEqual(len(browser_map['sources']), 177)
        self.assertTrue(all(name.startswith('derived-compiled-js/') for name in browser_map['sources']))
        self.assertFalse(manifest['registryArtifactOrPublisherAuthenticationClaimed'])

    def test_current_application_declarations_match_the_reviewed_lock(self):
        web = Path(__file__).resolve().parents[2] / 'web'
        package = json.loads((web / 'package.json').read_bytes())
        lock = json.loads((web / 'package-lock.json').read_bytes())
        for scope in ['dependencies', 'devDependencies']:
            self.assertEqual(package[scope], lock['packages'][''][scope])
        self.assertEqual(package['devDependencies']['puppeteer-core'], '25.17.0')
        self.assertEqual(package['devDependencies']['zod'], '4.6.7')
        self.assertIn('ignore-scripts=true', (web / '.npmrc').read_text())
        self.assertTrue(package['scripts']['build'].startswith('node scripts/prepare-runtime.mjs && '))


if __name__ == '__main__': unittest.main()
