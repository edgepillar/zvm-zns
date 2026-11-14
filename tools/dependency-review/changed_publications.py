"""Bind both sides of every changed registry publication to actual source bytes."""

import hashlib
import io
import tarfile

from bundled_archive import inspect_archive
from bundled_lock import metadata
from lock_review import decode, require
from proposal_delta import lock_delta, package_table

FIELDS = ('dependencies', 'optionalDependencies', 'peerDependencies', 'peerDependenciesMeta', 'engines',
    'exports', 'main', 'module', 'types', 'type', 'bin', 'browser', 'scripts', 'license', 'os', 'cpu', 'libc')


def source_requirements(baseline_raw, candidate_raw):
    delta = lock_delta(baseline_raw, candidate_raw)
    require(len(delta['publicationChanges']) <= 128, 'changed-publication pair budget')
    required = {}
    for row in delta['publicationChanges']:
        for role in ('baseline', 'candidate'):
            identity = row[role + 'Publication']; key = identity['integrity']
            if key in required:
                require(required[key]['selection'] == identity, 'one source digest claims conflicting publication identities')
            else: required[key] = {'selection': identity, 'uses': []}
            required[key]['uses'].append({'location': row['location'], 'role': role})
    return delta, required


def review_changed_publications(baseline_raw, candidate_raw, archives):
    delta, required = source_requirements(baseline_raw, candidate_raw)
    require(type(archives) is dict and set(archives) == set(required), 'missing or unrelated changed-publication archive')
    require(all(type(raw) is bytes and 0 < len(raw) <= 8 << 20 for raw in archives.values())
        and sum(map(len, archives.values())) <= 128 << 20, 'changed-publication archive budget')
    tables = {'baseline': package_table(baseline_raw)[1], 'candidate': package_table(candidate_raw)[1]}
    publications = {}; manifests = {}
    for integrity, request in required.items():
        raw = archives[integrity]; identity = request['selection']; first = request['uses'][0]
        row = tables[first['role']][first['location']]
        reviewed = inspect_archive(raw, {**row, 'name': identity['name']}, expanded_limit=64 << 20)
        with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
            member = archive.getmember('package/package.json')
            require(member.isfile() and 0 < member.size <= 2 << 20, 'changed publication manifest budget')
            body = archive.extractfile(member).read((2 << 20) + 1)
        require(hashlib.sha256(body).hexdigest() == reviewed['parentManifestSha256'], 'changed publication manifest pin differs')
        manifest = decode(body)
        for use in request['uses']:
            metadata(tables[use['role']][use['location']], manifest, bundled=False)
        files = {item['path'].removeprefix('package/'): {'bytes': item['bytes'], 'sha256': item['sha256']}
            for item in reviewed['archiveMembers'] if item['kind'] == 'file'}
        require(len(files) == reviewed['regularFileCount'], 'changed publication member inventory differs')
        publications[integrity] = {'selection': identity, 'uses': request['uses'], 'publication': reviewed['publication'],
            'manifestSha256': reviewed['parentManifestSha256'], 'filePins': files, 'regularFileCount': len(files),
            'expandedTarBytes': reviewed['expandedTarBytes'], 'selectedManifest': {key: manifest[key] for key in FIELDS if key in manifest},
            'originalNoticeCandidates': reviewed['originalNoticeCandidates'],
            'packageLocationsWithoutStandaloneNoticeCandidates': reviewed['packageLocationsWithoutStandaloneNoticeCandidates'],
            'publisherOrRegistryAttestationsVerified': False}
        manifests[integrity] = manifest
    pairs = []
    for row in delta['publicationChanges']:
        old, new = [manifests[row[role + 'Publication']['integrity']] for role in ('baseline', 'candidate')]
        old_files, new_files = [publications[row[role + 'Publication']['integrity']]['filePins'] for role in ('baseline', 'candidate')]
        pairs.append({**row, 'manifestChanges': {field: {'baselinePresent': field in old, 'candidatePresent': field in new,
            'baselineValue': old.get(field), 'candidateValue': new.get(field)} for field in FIELDS
            if (field in old) != (field in new) or old.get(field) != new.get(field)},
            'addedMembers': sorted(set(new_files) - set(old_files)), 'removedMembers': sorted(set(old_files) - set(new_files)),
            'changedMembers': sorted(name for name in set(old_files) & set(new_files) if old_files[name] != new_files[name])})
    return {'schema': 1, 'baselineLockSha256': delta['baselineLockSha256'], 'candidateLockSha256': delta['candidateLockSha256'],
        'status': 'CHANGED_REGISTRY_PUBLICATIONS_BOUND_API_AND_PLATFORM_REVIEW_REQUIRED', 'delta': delta,
        'publicationPairCount': len(pairs), 'uniquePublicationCount': len(publications), 'publications': publications, 'pairs': pairs,
        'regularMemberOccurrences': sum(row['regularFileCount'] for row in publications.values()),
        'allChangedRegistryPublicationsBound': True, 'samePublicationMetadataChanges': delta['samePublicationMetadataChanges'],
        'addedAndRemovedAndSourceKindChangesRetained': True,
        'archiveFilesystemExtractions': 0, 'packageCodeOrLifecycleScriptsExecuted': False,
        'completeProposedGraphIntegrityReview': False, 'APIOrBrowserRuntimeCompatibilityEstablished': False,
        'supportedPlatformsOrCompleteLegalReviewEstablished': False, 'proposalAdopted': False, 'productionGate': 'NO_GO'}
