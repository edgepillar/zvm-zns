"""Verify the shipped notice index against exact package archives."""

from lock_review import decode, require
from openzeppelin_candidate import checked_name
from profile_sources import pin, read_regular
from proposal_delta import registry_identity

NOTICE_INDEX = 'notices/npm/index.json'


def read_notice_index(root):
    return read_regular(root, NOTICE_INDEX, 256 << 10).decode('utf-8')


def verify_notice_index(text, distribution, rows, publications, expected=None):
    files = distribution['files']
    raw = text.encode('utf-8')
    require(pin(raw) == files[NOTICE_INDEX], 'shipped notice index differs from the distribution')
    index = decode(raw)
    packages = index['packages']
    require(index['schema'] == 1 and type(packages) is list and 0 < len(packages) <= 128, 'shipped notice index schema differs')
    locations = [row['location'] for row in packages]
    require(locations == sorted(set(locations)), 'shipped notice package order or uniqueness differs')
    if expected is not None:
        require(set(locations) == expected, 'shipped notice index package roles differ from the bundle')
    by_digest = {}
    covered = []
    entries = 0
    for row in packages:
        location = row['location']
        archive = publications[location]
        selected = registry_identity(location, rows[location])
        require((row['name'], row['version']) == (selected['name'], selected['version'])
            and archive['selection'] == selected, 'shipped notice package identity differs')
        expected_members = archive['originalNotices']
        members = [item['member'] for item in row['notices']]
        require(members == sorted(expected_members), 'shipped notice members differ for ' + location)
        entries += len(members)
        require(entries <= 512, 'shipped notice record budget')
        for item in row['notices']:
            path = item['file']
            checked_name(path)
            value = {key: item[key] for key in ('bytes', 'sha256')}
            require(path.startswith('notices/') and path != NOTICE_INDEX and files.get(path) == value
                and expected_members[item['member']] == value, 'shipped notice bytes differ for ' + location)
            require(by_digest.setdefault(value['sha256'], path) == path, 'identical notice bytes occupy multiple output paths')
        if members:
            covered.append(location)
    return {'packageLocations': locations, 'locationsWithOriginalNotices': covered, 'noticeFiles': len(by_digest),
        'noticeReferences': entries, 'index': pin(raw)}
