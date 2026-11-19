"""Inventory current application locks with the reviewed parent publication."""

import argparse
import json
from pathlib import Path

from bundled_lock import inventory_and_archive_reports
from lock_review import inventory, read_input, require
from profile_sources import pin, read_regular


def review_application_locks(repo, raw):
    plan = json.loads(read_input(repo, 'tools/dependency-review/application-runtime.json'))
    parents = plan['bundledParents']; require(len(parents) == 1, 'reviewed parent count differs')
    location, selected = next(iter(parents.items()))
    require(pin(raw) == {'bytes': selected['archiveBytes'], 'sha256': selected['archiveSha256']}, 'reviewed parent archive differs')
    inputs = {folder: {name: read_input(repo, folder + '/' + name) for name in ['package.json', 'package-lock.json']}
        for folder in ['contracts', 'web']}
    web, archives = inventory_and_archive_reports(inputs['web']['package.json'], inputs['web']['package-lock.json'], {location: raw})
    require(web['sourceInventoryCoversEveryLockRow'] and web['allSelectedBundleManifestsBound'], 'current lock source inventory incomplete')
    parent = web['parentPublications'][location]
    require(parent['parentManifestSha256'] == selected['parentManifestSha256'], 'reviewed parent manifest differs')
    bound = {row['location']: {key: row['sourceBinding'][key] for key in ['name', 'version', 'manifestPath', 'manifestBytes', 'manifestSha256']}
        for row in web['packageRecords'] if row['sourceKind'] == 'PARENT_PUBLICATION_MEMBER'
        and row['sourceBinding']['parentLockLocation'] == location}
    require(bound == selected['memberManifestPins'], 'reviewed bundled members differ')
    contracts = inventory(inputs['contracts']['package.json'], inputs['contracts']['package-lock.json'])
    require(all(read_input(repo, folder + '/' + name) == body for folder, values in inputs.items()
        for name, body in values.items()), 'lock source changed during review')
    return {'schema': 1, 'roots': {'contracts': contracts, 'web': web},
        'reviewedParentArchive': pin(raw), 'actualApplicationInputsInventoried': True,
        'reviewedParentNoticeInventory': archives[location],
        'sourceInputsUnchanged': True, 'dependenciesInstalledOrExecuted': False,
        'publisherPlatformAdvisoryLegalOrProductionAcceptance': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', required=True, type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    path = args.archive.absolute()
    require(path.parent.resolve(strict=True) == path.parent, 'linked parent archive directory')
    print(json.dumps(review_application_locks(repo, read_regular(path.parent, path.name, 32 << 20)), sort_keys=True))


if __name__ == '__main__': main()
