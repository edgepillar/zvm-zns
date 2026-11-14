"""Classify bundled lock rows using actual SHA-512-bound parent publications."""

import hashlib
import io
import json
import re
import tarfile

from bundled_archive import inspect_archive
from lock_review import (MAX_EDGES, MAX_INPUT, MAX_PACKAGES, SCOPES, bundled_names,
    decode, dependencies, effective_name, inventory, location_name, optional_peers,
    require, resolve)


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()


def metadata(row, manifest, *, bundled=True):
    require(type(row) is dict and 'link' not in row, 'unreviewed publication lock row')
    if bundled:
        require(row.get('inBundle') is True, 'bundled member flag absent')
        require('resolved' not in row and 'integrity' not in row, 'bundled member must not claim an independent tarball')
    require(row.get('name', manifest['name']) == manifest['name'] and row.get('version') == manifest['version'], 'bundled member identity differs')
    for scope in ('dependencies', 'optionalDependencies', 'peerDependencies'):
        require(dependencies(row, scope) == dependencies(manifest, scope), 'bundled member declarations differ')
    require(row.get('peerDependenciesMeta', {}) == manifest.get('peerDependenciesMeta', {}), 'bundled peer metadata differs')
    require(bundled_names(row) == bundled_names(manifest), 'nested bundle declarations differ')
    optional_peers(row)
    for flag in ('dev', 'optional', 'peer', 'devOptional', 'hasInstallScript'):
        require(flag not in row or type(row[flag]) is bool, 'invalid bundled package boolean')
    scripts = manifest.get('scripts', {})
    require(type(scripts) is dict, 'bundled scripts metadata differs')
    require(row.get('hasInstallScript', False) == any(key in scripts for key in ('preinstall', 'install', 'postinstall')),
        'bundled lifecycle declaration differs')
    for field in ('os', 'cpu', 'libc'):
        values = row.get(field, [])
        require(type(values) is list and len(values) <= 32 and all(type(value) is str
            and re.fullmatch(r'!?[a-z0-9_-]+', value) for value in values), 'invalid bundled platform declaration')
        require(values == manifest.get(field, []), 'bundled platform declaration differs')
    license_value = row.get('license')
    require(license_value == manifest.get('license') and (license_value is None or type(license_value) is str
        and 0 < len(license_value) <= 512 and license_value.isascii()
        and all(32 <= ord(char) < 127 for char in license_value)), 'bundled license declaration differs')
    if 'engines' in row:
        require(row['engines'] == manifest.get('engines'), 'bundled engine declaration differs')


def bind_members(packages, archives):
    require(type(archives) is dict and len(archives) <= 16, 'parent publication budget')
    require(all(type(raw) is bytes for raw in archives.values()) and sum(map(len, archives.values())) <= 64 << 20,
        'parent publication byte budget')
    bindings, publications = {}, {}
    for parent_location, raw in sorted(archives.items()):
        location_name(parent_location)
        require(parent_location in packages and type(packages[parent_location]) is dict
            and packages[parent_location].get('inBundle', False) is False, 'parent must have its own registry record')
        selected = packages[parent_location]
        review = inspect_archive(raw, {**selected, 'name': selected.get('name', location_name(parent_location))}, expanded_limit=32 << 20)
        manifests = review['allArchivePackageManifests']
        require(manifests and len(manifests) <= MAX_PACKAGES, 'selected publication has no bounded bundle manifests')
        requested = {value['manifestPath']: (relative, value) for relative, value in manifests.items()}
        parent_member, = [row for row in review['archiveMembers'] if row['path'] == 'package/package.json']
        requested['package/package.json'] = ('', {'manifestBytes': parent_member['bytes'], 'manifestSha256': parent_member['sha256']})
        found = {}
        # The inspector has already validated the complete compressed stream,
        # archive paths/types, member hashes and expansion bound. Decode only its
        # canonical package manifests, excluding package-internal data manifests.
        with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
            for member in archive:
                if member.name not in requested:
                    continue
                relative, expected = requested[member.name]
                require(member.isfile() and 0 < member.size <= MAX_INPUT, 'bundled manifest byte budget')
                body = archive.extractfile(member).read(MAX_INPUT + 1)
                require(len(body) == expected['manifestBytes'] and hashlib.sha256(body).hexdigest() == expected['manifestSha256'],
                    'bundled manifest changed after inspection')
                found[relative] = decode(body)
        require(set(found) == set(manifests) | {''}, 'bundled manifests incomplete')
        metadata(selected, found.pop(''), bundled=False)
        publications[parent_location] = {'publication': review['publication'],
            'parentManifestSha256': review['parentManifestSha256'],
            'archiveMemberCount': review['archiveMemberCount'], 'regularFileCount': review['regularFileCount'],
            'archiveMemberInventorySha256': hashlib.sha256(encoded(review['archiveMembers'])).hexdigest(),
            'bundleManifestCount': len(manifests), 'allRegularMemberSha256Observed': True,
            'archiveFilesystemExtractions': 0, 'publisherOrRegistryAttestationsVerified': False}
        for relative, manifest in found.items():
            location = parent_location + '/' + relative
            location_name(location)
            require(location not in bindings and location in packages, 'ambiguous or missing bundled lock location')
            row = packages[location]
            require(row.get('name', location_name(location)) == manifest['name'], 'bundled lock alias identity differs')
            metadata(row, manifest)
            bindings[location] = {'parentLockLocation': parent_location,
                'parentPublication': review['publication'], **manifests[relative]}
    return bindings, publications


def declaration_graph(packages, bindings):
    edges, unresolved, archive_routes, absent, direct = [], [], [], [], []
    for location, row in sorted(packages.items()):
        bundles, peers = bundled_names(row), optional_peers(row)
        for scope in (SCOPES if location == '' else ('dependencies', 'optionalDependencies', 'peerDependencies')):
            for name, spec in sorted(dependencies(row, scope).items()):
                target = resolve(location, name, packages)
                edge = {'from': location, 'scope': scope, 'name': name, 'requested': spec, 'to': target}
                archive_declared = scope in ('dependencies', 'optionalDependencies') and name in bundles
                if archive_declared:
                    if target in bindings:
                        source = bindings[target]
                        archive_routes.append({**edge, 'effectiveName': effective_name(name, spec),
                            'parentArchiveURL': source['parentPublication']['url'],
                            'parentArchiveIntegrity': source['parentPublication']['integrity'],
                            'parentArchiveSha256': source['parentPublication']['sha256'],
                            'manifestPath': source['manifestPath'], 'manifestSha256': source['manifestSha256'],
                            'status': 'BOUND_TO_PARENT_PUBLICATION_MANIFEST'})
                    else:
                        require(location not in bindings, 'nested bundle declaration has no verified member')
                        archive_routes.append({**edge, 'effectiveName': effective_name(name, spec),
                            'parentArchiveURL': row['resolved'], 'parentArchiveIntegrity': row['integrity'],
                            'status': 'DECLARED_BUNDLED_ARCHIVE_CONTENT_NOT_VERIFIED'})
                        require(sum(map(len, (edges, unresolved, archive_routes, absent))) <= MAX_EDGES, 'source declaration edge budget')
                        continue
                if target is None:
                    if scope == 'peerDependencies' and name in peers:
                        absent.append({**edge, 'status': 'OPTIONAL_PEER_NOT_RECORDED'})
                    else:
                        require(location != '', 'root declaration has no source location')
                        unresolved.append({**edge, 'parentLockDeclaredOptional': row.get('optional', False),
                            'parentDeclaredOS': row.get('os', []), 'parentDeclaredCPU': row.get('cpu', [])})
                else:
                    require(packages[target].get('name', location_name(target)) == effective_name(name, spec),
                        'resolved declaration package identity differs')
                    edges.append({**edge, 'sourceKind': 'PARENT_PUBLICATION_MEMBER' if target in bindings else 'REGISTRY_TARBALL_DECLARATION'})
                    if location == '': direct.append(edge)
                require(sum(map(len, (edges, unresolved, archive_routes, absent))) <= MAX_EDGES, 'source declaration edge budget')
    adjacency = {}
    for edge in edges: adjacency.setdefault(edge['from'], set()).add(edge['to'])
    routes, covered = [], set()
    for edge in direct:
        seen, pending = set(), [edge['to']]
        while pending:
            here = pending.pop()
            if here in seen: continue
            seen.add(here); pending.extend(adjacency.get(here, set()) - seen)
        covered.update(seen)
        routes.append({'scope': edge['scope'], 'name': edge['name'], 'lockedTarget': edge['to'],
            'declaredGraphLocations': sorted(seen)})
    return {'resolvedDeclarationEdges': edges, 'unresolvedDeclarations': unresolved,
        'unresolvedRequiredDeclarations': [row for row in unresolved if row['scope'] == 'dependencies'],
        'declaredBundledArchiveDependencies': archive_routes, 'absentOptionalPeerDeclarations': absent,
        'rootDeclarationRoutes': routes, 'locationsWithoutRootDeclarationRoute': sorted(set(packages) - {''} - covered),
        'allRequiredDeclarationsHaveRecordedSourceRoute': not any(row['scope'] == 'dependencies' for row in unresolved)
            and not any(row['scope'] == 'dependencies' and row['status'] != 'BOUND_TO_PARENT_PUBLICATION_MANIFEST' for row in archive_routes)}


def inventory_with_archives(package_raw, lock_raw, archives):
    lock = decode(lock_raw); packages = lock.get('packages')
    require(type(packages) is dict and 1 <= len(packages) <= MAX_PACKAGES + 1
        and all(type(row) is dict for row in packages.values()), 'source package table budget or type')
    require(all('inBundle' not in row or type(row['inBundle']) is bool for row in packages.values()), 'invalid inBundle flag')
    require(not packages.get('', {}).get('inBundle'), 'project root cannot be a bundled member')
    claimed = {location for location, row in packages.items() if row.get('inBundle') is True}
    bindings, publications = bind_members(packages, archives)
    require(set(bindings) == claimed, 'bundled lock claims and archive members are not a bijection')
    projection = {**lock, 'packages': {name: row for name, row in packages.items() if name not in bindings}}
    projection_raw = encoded(projection)
    # Preserve the original strict registry validator. No URI, integrity or
    # placeholder package entry is invented for a bundled source member.
    registry = inventory(package_raw, projection_raw)
    records = [{**row, 'sourceKind': 'REGISTRY_TARBALL_DECLARATION',
        'sourcePayloadVerified': row['location'] in publications} for row in registry['packageRecords']]
    for location, binding in sorted(bindings.items()):
        row = packages[location]
        records.append({'location': location, 'name': location_name(location), 'effectiveName': binding['name'],
            'version': binding['version'], 'resolved': None, 'integrity': None,
            'sourceKind': 'PARENT_PUBLICATION_MEMBER', 'sourcePayloadVerified': True,
            'sourceBinding': binding, 'declaredLicense': row.get('license'),
            'lockDeclaredDev': row.get('dev', False), 'lockDeclaredOptional': row.get('optional', False),
            'lockDeclaredPeer': row.get('peer', False), 'declaredInstallScript': row.get('hasInstallScript', False),
            'declaredOS': row.get('os', []), 'declaredCPU': row.get('cpu', []), 'declaredLibc': row.get('libc', []),
            'declaredBundledDependencies': bundled_names(row), 'declaredOptionalPeers': optional_peers(row),
            'peerMetadataWithoutDeclaration': sorted(set(row.get('peerDependenciesMeta', {})) - set(row.get('peerDependencies', {})))})
    graph = declaration_graph(packages, bindings)
    return {'schema': 3, 'status': 'LOCK_ROWS_AND_SELECTED_PARENT_ARCHIVE_MEMBERS_INVENTORIED_REVIEW_REQUIRED',
        'packageJsonSha256': hashlib.sha256(package_raw).hexdigest(), 'packageLockSha256': hashlib.sha256(lock_raw).hexdigest(),
        'packageCount': len(records), 'packageRecords': sorted(records, key=lambda row: row['location']),
        'registryPackageCount': len(registry['packageRecords']), 'boundArchiveMemberCount': len(bindings),
        'parentPublications': publications, **graph,
        'registryProjection': {'packageCount': len(registry['packageRecords']), 'packageLockSha256': hashlib.sha256(projection_raw).hexdigest(),
            'removedArchiveMemberLocations': sorted(bindings), 'strictRegistryValidatorUnchanged': True},
        'sourceInventoryCoversEveryLockRow': len(records) == len(packages) - 1,
        'allSelectedBundleManifestsBound': True, 'archiveFilesystemExtractions': 0,
        'allPackagePayloadsVerified': len(publications) + len(bindings) == len(records),
        'publisherOrRegistryAttestationsVerified': False, 'semverSatisfactionIndependentlyVerified': False,
        'vulnerabilityScanExecuted': False, 'applicationRuntimeReachabilityEstablished': False,
        'licenseReviewComplete': False, 'installedPlatformQualified': False,
        'completeLockIntegrityReview': False, 'completeSBOM': False, 'releaseAccepted': False}
