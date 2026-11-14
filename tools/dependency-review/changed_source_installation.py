"""Compare a selected installation with reviewed changed-publication members."""

import hashlib
import json
import stat

from lock_review import require
from openzeppelin_candidate import checked_name
from proposal_delta import package_table, registry_identity


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def read_publication_member(root, relative, expected_bytes):
    checked_name(relative)
    require(type(expected_bytes) is int and 0 <= expected_bytes <= 16 << 20, 'selected source member byte budget')
    path = root
    for part in relative.split('/'):
        path /= part
        require(not path.is_symlink(), 'linked selected source member or ancestor')
    before = path.stat()
    require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size == expected_bytes, 'selected source member type or size differs')
    with path.open('rb') as source: raw = source.read(expected_bytes + 1)
    after = path.stat()
    identity = lambda row: (row.st_dev, row.st_ino, row.st_mode, row.st_nlink, row.st_size, row.st_mtime_ns, row.st_ctime_ns)
    require(len(raw) == expected_bytes and identity(before) == identity(after), 'selected source changed during read')
    return raw


def verify_selected_installation(root, lock_raw, plan, role):
    require(role in ('baseline', 'candidate'), 'unknown changed-source role')
    require(plan['schema'] == 1 and plan['allChangedRegistryPublicationsBound'] is True, 'changed-source plan is incomplete')
    expected_lock = plan[role + 'LockSha256']
    require(hashlib.sha256(lock_raw).hexdigest() == expected_lock, 'selected source installation has a different lock')
    _, packages = package_table(lock_raw)
    records = []; identities = set()
    for pair in plan['pairs']:
        location = pair['location']; require(location not in identities, 'duplicate selected source location'); identities.add(location)
        selection = pair[role + 'Publication']; source = plan['publications'][selection['integrity']]
        require(registry_identity(location, packages[location]) == selection == source['selection'], 'selected source publication identity differs')
        expected = source['filePins']
        require(type(expected) is dict and 0 < len(expected) <= 8192 and 'package.json' in expected, 'selected source inventory budget')
        actual = {}
        for name, pin in sorted(expected.items()):
            checked_name(name)
            raw = read_publication_member(root, location + '/' + name, pin['bytes'])
            observed = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
            require(observed == pin, 'selected installed source bytes differ from reviewed publication')
            actual[name] = observed
        require(digest(actual) == digest(expected), 'selected installed source inventory differs')
        records.append({'location': location, 'selection': selection, 'publicationSha256': source['publication']['sha256'],
            'fileCount': len(actual), 'memberPinInventorySha256': digest(actual)})
    require(len(records) == plan['publicationPairCount'], 'selected installed source pair count differs')
    require(hashlib.sha256(lock_raw).hexdigest() == expected_lock, 'selected source input changed')
    return {'schema': 1, 'role': role, 'lockSha256': expected_lock, 'records': records,
        'selectedPackageLocations': len(records), 'selectedRegularFileOccurrences': sum(row['fileCount'] for row in records),
        'allReviewedSelectedSourceMembersMatch': True, 'unknownExtraFilesAuthenticated': False,
        'packageCodeExecutedByThisCheck': False, 'browserOrPlatformRuntimeQualified': False,
        'proposalAdopted': False, 'productionGate': 'NO_GO'}
