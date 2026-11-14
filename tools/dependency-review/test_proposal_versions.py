"""Version cases retain source identities, aliases and explicit unqualified gaps."""

import copy
import hashlib
import json
import unittest

from lock_review import ReviewError
from bundled_lock import declaration_graph
from proposal_versions import POLICIES, version_cases, version_review


def fixture():
    packages = {'': {'name': 'fixture', 'devDependencies': {'a': '^1'}},
        'node_modules/a': {'version': '1.0.0', 'engines': {'node': '>=22', 'npm': '^10'},
        'optional': True, 'cpu': ['wasm32'], 'dependencies': {'alias': 'npm:@scope/real@^2'},
        'peerDependencies': {'absent': '*'}, 'peerDependenciesMeta': {'absent': {'optional': True}},
        'optionalDependencies': {'missing': '^1'}}, 'node_modules/alias': {'name': '@scope/real', 'version': '2.0.1'}}
    raw = json.dumps({'packages': packages}).encode()
    inventory = {'packageLockSha256': hashlib.sha256(raw).hexdigest(), 'packageCount': 2,
        'sourceInventoryCoversEveryLockRow': True, 'allSelectedBundleManifestsBound': True,
        'packageRecords': [{'location': path, 'sourceKind': 'REGISTRY_TARBALL_DECLARATION'} for path in packages if path],
        **declaration_graph(packages, {})}
    return raw, inventory


class ProposalVersionControls(unittest.TestCase):
    def test_all_edges_aliases_and_recorded_engine_profiles_are_included(self):
        raw, inventory = fixture(); result = version_cases(raw, inventory, 'v22.23.4', '10.9.9')
        self.assertEqual((result['dependencyCaseCount'], result['engineCaseCount']), (2, 2))
        self.assertEqual([row['range'] for row in result['cases']], ['^1', '^2', '>=22', '^10'])
        self.assertEqual(result['caseSources']['declaration-00001']['effectiveName'], '@scope/real')
        self.assertEqual(result['caseSources']['engine-00000']['declaredCPU'], ['wasm32'])
        self.assertEqual([row['mode'] for row in result['cases']], ['dependency', 'dependency', 'engine', 'engine'])
        self.assertTrue(result['allRecordedResolvedDeclarationsIncluded'])
        self.assertFalse(result['semverSatisfactionIndependentlyVerified'])
        self.assertFalse(result['proposalAdopted'])

    def test_absent_peers_and_unresolved_declarations_are_retained_not_invented_as_matches(self):
        raw, inventory = fixture(); result = version_cases(raw, inventory, 'v22.23.4', '10.9.9')
        self.assertEqual(result['absentOptionalPeerDeclarations'], inventory['absentOptionalPeerDeclarations'])
        self.assertEqual(result['unresolvedDeclarations'], inventory['unresolvedDeclarations'])
        self.assertEqual(len(result['cases']), 4)
        self.assertFalse(result['supportedPlatformsQualified'])

    def test_changed_lock_or_incomplete_inventory_is_refused(self):
        raw, inventory = fixture()
        with self.assertRaises(ReviewError): version_cases(raw + b' ', inventory, 'v22.23.4', '10.9.9')
        for field in ['sourceInventoryCoversEveryLockRow', 'allSelectedBundleManifestsBound']:
            other = copy.deepcopy(inventory); other[field] = False
            with self.subTest(field=field), self.assertRaises(ReviewError): version_cases(raw, other, 'v22.23.4', '10.9.9')

    def test_duplicate_edge_or_wrong_target_identity_is_refused(self):
        raw, inventory = fixture(); duplicate = copy.deepcopy(inventory)
        duplicate['resolvedDeclarationEdges'].append(duplicate['resolvedDeclarationEdges'][0])
        wrong = copy.deepcopy(inventory); wrong['resolvedDeclarationEdges'][0]['to'] = 'node_modules/alias'
        for value in [duplicate, wrong]:
            with self.assertRaises(ReviewError): version_cases(raw, value, 'v22.23.4', '10.9.9')

    def test_missing_target_is_not_silently_omitted(self):
        raw, inventory = fixture(); inventory['resolvedDeclarationEdges'][0]['to'] = None
        with self.assertRaises(ReviewError): version_cases(raw, inventory, 'v22.23.4', '10.9.9')

    def test_omitted_edge_or_changed_gap_is_refused(self):
        raw, inventory = fixture()
        for field in ['resolvedDeclarationEdges', 'absentOptionalPeerDeclarations', 'unresolvedDeclarations']:
            other = copy.deepcopy(inventory); other[field].pop()
            with self.subTest(field=field), self.assertRaises(ReviewError): version_cases(raw, other, 'v22.23.4', '10.9.9')

    def test_target_toolchain_profile_must_be_recorded_concretely(self):
        raw, inventory = fixture()
        for node, npm in [('22', '10.9.9'), ('v22.23.4', 'latest'), ('v22.23.4', '')]:
            with self.subTest(node=node, npm=npm), self.assertRaises(ReviewError): version_cases(raw, inventory, node, npm)

    def evaluated(self):
        raw, inventory = fixture(); plan = version_cases(raw, inventory, 'v22.23.4', '10.9.9')
        return plan, [{**row, 'status': 'RANGE_EVALUATED', 'options': POLICIES[row['mode']],
            'normalizedVersion': row['version'], 'normalizedRange': row['range'], 'matches': True} for row in plan['cases']]

    def test_incomplete_duplicate_rebound_or_wrong_policy_evaluation_is_refused(self):
        plan, results = self.evaluated()
        incomplete = copy.deepcopy(results); incomplete.pop()
        duplicate = copy.deepcopy(results); duplicate[1] = duplicate[0]
        rebound = copy.deepcopy(results); rebound[0]['version'] = '9.0.0'
        policy = copy.deepcopy(results); policy[0]['options'] = POLICIES['advisory']
        for value in [incomplete, duplicate, rebound, policy]:
            with self.assertRaises(ReviewError): version_review(plan, value)

    def test_violations_and_unknowns_remain_distinct_and_prevent_qualification(self):
        plan, results = self.evaluated(); results[0]['matches'] = False
        results[2].update(status='UNKNOWN_INVALID_VERSION_OR_RANGE', matches=None, normalizedRange=None)
        result = version_review(plan, results)
        self.assertEqual(result['violatedCaseKeys'], [results[0]['key']])
        self.assertEqual(result['unknownCaseKeys'], [results[2]['key']])
        self.assertFalse(result['semverSatisfactionIndependentlyVerified'])
        self.assertFalse(result['allRecordedEngineRangesSatisfiedForProfile'])
        self.assertFalse(result['allRecordedVersionCasesEvaluated'])

    def test_complete_positive_evaluation_does_not_adopt_the_proposal(self):
        plan, results = self.evaluated(); result = version_review(plan, results)
        self.assertTrue(result['allResolvedDependencyRangesSatisfied'])
        self.assertTrue(result['allRecordedEngineRangesSatisfiedForProfile'])
        self.assertFalse(result['proposalAdopted'])
        self.assertFalse(result['installedPlatformProjectionEstablished'])
        self.assertEqual(result['productionGate'], 'NO_GO')


if __name__ == '__main__': unittest.main()
