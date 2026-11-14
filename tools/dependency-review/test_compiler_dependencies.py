"""Reject broadened compiler overrides and unreviewed control graph edits."""

import copy
import json
import unittest

from compiler_dependencies import OVERRIDE, dependency_test_counts, patch_test_compiler_graph


def sample():
    package = {'name': 'controls', 'private': True, 'devDependencies': {'solc': '0.8.26', 'unchanged': '1.0.0'}}
    lock = {'packages': {'': {'devDependencies': dict(package['devDependencies'])},
        'node_modules/solc': {'version': '0.8.26', 'dependencies': {'follow-redirects': '^1.12.1', 'tmp': '0.0.33'}},
        'node_modules/follow-redirects': {'version': '1.16.0', 'dev': True},
        'node_modules/tmp': {'version': '0.0.33', 'dependencies': {'os-tmpdir': '~1.0.2'}, 'dev': True},
        'node_modules/os-tmpdir': {'version': '1.0.2'}, 'node_modules/unchanged': {'version': '1.0.0'}}}
    selected = {name: {'publication': {'name': name, 'version': version, 'resolved': 'https://registry.npmjs.org/example',
        'integrity': 'sha512-reviewed'}, 'lockMetadata': {'license': 'MIT', 'engines': {'node': '>=14.14'}}}
        for name, version in [('follow-redirects', '1.16.3'), ('tmp', '0.2.7')]}
    return package, lock, selected


class CompilerDependencyControls(unittest.TestCase):
    def apply(self, package, lock, selected):
        return [json.loads(raw) for raw in patch_test_compiler_graph(json.dumps(package), json.dumps(lock), selected)]

    def test_scoped_override_preserves_compiler_and_unrelated_inputs(self):
        p, lock, selected = sample(); before = copy.deepcopy(lock)
        updated, result = self.apply(p, lock, selected)
        self.assertEqual(updated['overrides'], OVERRIDE)
        self.assertEqual(updated['devDependencies'], p['devDependencies'])
        self.assertEqual(result['packages']['node_modules/solc'], before['packages']['node_modules/solc'])
        self.assertEqual(result['packages']['node_modules/unchanged'], before['packages']['node_modules/unchanged'])
        self.assertNotIn('node_modules/os-tmpdir', result['packages'])
        self.assertNotIn('dependencies', result['packages']['node_modules/tmp'])

    def test_an_existing_override_is_not_silently_replaced(self):
        p, lock, selected = sample(); p['overrides'] = {'another': '2.0.0'}
        with self.assertRaises(ValueError): self.apply(p, lock, selected)

    def test_compiler_version_change_is_not_hidden_by_the_override(self):
        p, lock, selected = sample(); p['devDependencies']['solc'] = '0.8.27'
        with self.assertRaises(ValueError): self.apply(p, lock, selected)

    def test_an_unreviewed_baseline_is_rejected(self):
        p, lock, selected = sample(); lock['packages']['node_modules/tmp']['version'] = '0.2.6'
        with self.assertRaises(ValueError): self.apply(p, lock, selected)

    def test_a_still_used_transitive_dependency_is_preserved_by_refusal(self):
        p, lock, selected = sample(); lock['packages']['node_modules/unchanged']['dependencies'] = {'os-tmpdir': '1.0.2'}
        with self.assertRaises(ValueError): self.apply(p, lock, selected)

    def test_candidate_identity_and_version_need_the_reviewed_selection(self):
        p, lock, selected = sample(); selected['tmp']['publication']['version'] = '0.3.0'
        with self.assertRaises(ValueError): self.apply(p, lock, selected)

    def test_small_dependency_suite_requires_complete_unambiguous_passing_totals(self):
        raw = b'# tests 5\n# pass 5\n# fail 0\n# cancelled 0\n# skipped 0\n# todo 0\n'
        self.assertEqual(dependency_test_counts(raw, 5)['pass'], 5)
        for changed in [raw.replace(b'# skipped 0\n', b''), raw + b'# pass 5\n',
                raw.replace(b'# fail 0', b'# fail 1'), raw.replace(b'# tests 5', b'# tests 4')]:
            with self.subTest(totals=changed), self.assertRaises(ValueError): dependency_test_counts(changed, 5)


if __name__ == '__main__': unittest.main()
