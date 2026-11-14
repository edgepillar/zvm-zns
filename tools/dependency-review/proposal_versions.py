"""Prepare complete proposal-version cases; evaluation remains a separate step."""

import hashlib
import re

from bundled_lock import declaration_graph
from lock_review import MAX_EDGES, decode, effective_name, location_name, require


POLICIES = {'dependency': {'includePrerelease': False, 'loose': False},
    'engine': {'includePrerelease': True, 'loose': False}, 'advisory': {'includePrerelease': True, 'loose': True}}


def range_controls():
    return [{'key': 'policy-control-' + str(index), 'mode': mode, 'version': version, 'range': spec, 'expected': expected}
        for index, (mode, version, spec, expected) in enumerate([
            ('dependency', '1.2.3', '^1', True), ('dependency', '2.0.0', '^1', False),
            ('dependency', '1.3.0-beta.1', '^1.2.0', False), ('dependency', '1.3.0-beta.1', '>=1.3.0-beta.0 <2', True),
            ('dependency', '=1.2.3', '^1', None), ('engine', '22.23.4-beta.1', '>=22.12', True),
            ('engine', '=22.23.4', '>=22.12', None), ('advisory', '1.3.0-beta.1', '^1.2.0', True),
            ('advisory', '=1.2.3', '^1', True), ('advisory', '1.2.3', 'not-a-range', None)])]


def version_cases(lock_raw, source_inventory, node_version, npm_version):
    lock = decode(lock_raw); packages = lock['packages']
    require(source_inventory['packageLockSha256'] == hashlib.sha256(lock_raw).hexdigest(), 'version cases have a different lock source')
    require(source_inventory['sourceInventoryCoversEveryLockRow'] and source_inventory['allSelectedBundleManifestsBound'], 'source inventory is incomplete')
    require(source_inventory['packageCount'] == len(packages) - 1, 'source inventory row count differs')
    bindings = {row['location']: row['sourceBinding'] for row in source_inventory['packageRecords']
        if row['sourceKind'] == 'PARENT_PUBLICATION_MEMBER'}
    graph = declaration_graph(packages, bindings)
    for field in ('resolvedDeclarationEdges', 'absentOptionalPeerDeclarations', 'unresolvedDeclarations'):
        require(source_inventory[field] == graph[field], 'version declaration inventory differs from the lock')
    require(re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+', node_version) is not None
        and re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', npm_version) is not None, 'recorded target toolchain version differs')
    cases, sources = [], {}
    edges = source_inventory['resolvedDeclarationEdges']
    require(type(edges) is list and len(edges) <= MAX_EDGES, 'version edge budget')
    identities = set()
    for edge in edges:
        identity = (edge['from'], edge['scope'], edge['name'])
        require(identity not in identities, 'duplicate source declaration edge'); identities.add(identity)
        require(edge['from'] in packages and edge['to'] in packages and edge['to'] != '', 'version edge target absent')
        spec = edge['requested']; name = effective_name(edge['name'], spec)
        require(packages[edge['to']].get('name', location_name(edge['to'])) == name, 'version edge package identity differs')
        if spec.startswith('npm:'):
            match = re.fullmatch(r'npm:((?:@[a-z0-9_.-]+/)?[a-z0-9_][a-z0-9_.-]*)@(.+)', spec)
            require(match is not None, 'version alias range absent'); spec = match[2]
        key = 'declaration-' + str(len(cases)).zfill(5)
        cases.append({'key': key, 'version': packages[edge['to']]['version'], 'range': spec, 'mode': 'dependency'})
        sources[key] = {'kind': 'DECLARED_DEPENDENCY_VERSION', 'sourceEdge': edge, 'effectiveName': name}
    dependency_count = len(cases)
    for location, row in sorted(packages.items()):
        engines = row.get('engines', {})
        require(type(engines) is dict, 'engine declarations must be an object')
        for engine, version in [('node', node_version[1:]), ('npm', npm_version)]:
            if engine not in engines: continue
            spec = engines[engine]
            require(type(spec) is str and 0 < len(spec) <= 512 and spec.isascii()
                and all(32 <= ord(char) < 127 for char in spec), 'invalid recorded engine range')
            key = 'engine-' + str(len(cases) - dependency_count).zfill(5)
            cases.append({'key': key, 'version': version, 'range': spec, 'mode': 'engine'})
            sources[key] = {'kind': 'DECLARED_ENGINE_VERSION', 'engine': engine, 'location': location,
                'lockDeclaredOptional': row.get('optional', False), 'declaredOS': row.get('os', []),
                'declaredCPU': row.get('cpu', []), 'declaredLibc': row.get('libc', []),
                'installedPlatformProjectionEstablished': False}
    require(len(cases) <= 16384, 'proposal version case budget')
    return {'schema': 1, 'packageLockSha256': source_inventory['packageLockSha256'], 'cases': cases, 'caseSources': sources,
        'dependencyCaseCount': dependency_count, 'engineCaseCount': len(cases) - dependency_count,
        'absentOptionalPeerDeclarations': source_inventory['absentOptionalPeerDeclarations'],
        'unresolvedDeclarations': source_inventory['unresolvedDeclarations'],
        'allRecordedResolvedDeclarationsIncluded': dependency_count == len(edges) and len(cases) == len(sources),
        'recordedTargetNodeVersion': node_version, 'recordedTargetNpmVersion': npm_version,
        'sourceInventoryComplete': True, 'semverSatisfactionIndependentlyVerified': False,
        'applicationRuntimeReachabilityEstablished': False, 'supportedPlatformsQualified': False,
        'proposalAdopted': False, 'productionGate': 'NO_GO'}


def version_review(plan, results):
    """Refuse incomplete/rebound evaluations; preserve every violation/unknown."""
    require(type(results) is list and len(results) == len(plan['cases']), 'version evaluation count differs')
    indexed = {}
    for row in results:
        require(type(row) is dict and row.get('key') not in indexed, 'duplicate version evaluation')
        indexed[row['key']] = row
    require(set(indexed) == {row['key'] for row in plan['cases']}, 'version evaluation keys differ')
    matched, violated, unknown = [], [], []
    for case in plan['cases']:
        row = indexed[case['key']]
        require(all(row.get(key) == case[key] for key in ('mode', 'version', 'range'))
            and row.get('options') == POLICIES[case['mode']], 'version evaluation source or policy differs')
        if row.get('status') == 'RANGE_EVALUATED':
            require(type(row.get('matches')) is bool and type(row.get('normalizedVersion')) is str
                and type(row.get('normalizedRange')) is str, 'invalid evaluated version result')
            (matched if row['matches'] else violated).append(case['key'])
        else:
            require(row.get('status') == 'UNKNOWN_INVALID_VERSION_OR_RANGE' and row.get('matches') is None,
                'invalid unknown version result')
            unknown.append(case['key'])
    dependency_keys = {row['key'] for row in plan['cases'] if row['mode'] == 'dependency'}
    engine_keys = {row['key'] for row in plan['cases'] if row['mode'] == 'engine'}
    return {'schema': 1, 'packageLockSha256': plan['packageLockSha256'],
        'recordedTargetNodeVersion': plan['recordedTargetNodeVersion'], 'recordedTargetNpmVersion': plan['recordedTargetNpmVersion'],
        'dependencyCases': len(dependency_keys), 'engineCases': len(engine_keys),
        'matchedCaseKeys': matched, 'violatedCaseKeys': violated, 'unknownCaseKeys': unknown,
        'allRecordedVersionCasesEvaluated': not unknown,
        'allResolvedDependencyRangesSatisfied': not dependency_keys.intersection(violated + unknown),
        'allRecordedEngineRangesSatisfiedForProfile': not engine_keys.intersection(violated + unknown),
        'semverSatisfactionIndependentlyVerified': not dependency_keys.intersection(violated + unknown),
        'absentOptionalPeerDeclarations': plan['absentOptionalPeerDeclarations'],
        'unresolvedDeclarations': plan['unresolvedDeclarations'],
        'installedPlatformProjectionEstablished': False, 'applicationRuntimeReachabilityEstablished': False,
        'proposalAdopted': False, 'productionGate': 'NO_GO'}
