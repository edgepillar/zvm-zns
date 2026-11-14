"""Evaluate a proposal with a separately pinned, job-owned SemVer source tree."""

import io
import json
import tarfile
import urllib.request

from bundled_archive import inspect_archive
from lock_review import read_input, require
from openzeppelin_candidate import checked_name, run_bounded, sha, write_json
from proposal_versions import POLICIES, range_controls, version_cases, version_review


def pin(raw):
    return {'bytes': len(raw), 'sha256': sha(raw)}


def checked_source(raw, selected):
    require(selected['name'] == 'semver' and selected['version'] == '7.8.4'
        and selected['resolved'] == 'https://registry.npmjs.org/semver/-/semver-7.8.4.tgz', 'unreviewed range-tool identity')
    require(type(selected['archiveBytes']) is int and 0 < selected['archiveBytes'] <= 128 << 10, 'range-tool transport cap')
    require(pin(raw) == {'bytes': selected['archiveBytes'], 'sha256': selected['archiveSha256']}, 'range-tool publication bytes differ')
    review = inspect_archive(raw, selected, expanded_limit=4 << 20)
    files = {row['path'].removeprefix('package/'): {'bytes': row['bytes'], 'sha256': row['sha256']}
        for row in review['archiveMembers'] if row['kind'] == 'file'}
    require(files == selected['filePins'] and len(files) <= 128, 'range-tool source inventory differs')
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
        manifest = archive.extractfile('package/package.json').read(64 << 10)
    require(pin(manifest) == files['package.json'], 'range-tool manifest differs')
    package = json.loads(manifest)
    require(package['name'] == selected['name'] and package['version'] == selected['version']
        and not package.get('dependencies'), 'range tool must have no runtime dependencies')
    return files


def acquire_source(output, selected):
    # Identity and the cap are checked before issuing the sole request.
    require(selected['name'] == 'semver' and selected['version'] == '7.8.4'
        and selected['resolved'] == 'https://registry.npmjs.org/semver/-/semver-7.8.4.tgz', 'unreviewed range-tool URL')
    require(type(selected['archiveBytes']) is int and 0 < selected['archiveBytes'] <= 128 << 10, 'range-tool byte budget')
    request = urllib.request.Request(selected['resolved'], headers={'User-Agent': 'edgepillar-dependency-review'})
    with urllib.request.urlopen(request, timeout=45) as response:
        raw = response.read(selected['archiveBytes'] + 1)
        require(response.status == 200 and response.geturl() == selected['resolved'], 'range-tool response differs')
        if response.headers.get('Content-Length') is not None:
            require(int(response.headers['Content-Length']) == len(raw), 'range-tool response incomplete')
    files = checked_source(raw, selected)
    root = output / 'reviewed-semver-source'; root.mkdir()
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
        for member in archive:
            if not member.isfile(): continue
            name = member.name.removeprefix('package/'); checked_name(name)
            body = archive.extractfile(member).read()
            require(pin(body) == files[name], 'range-tool member changed after review')
            target = root / name; target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as destination: destination.write(body)
    return root, {'url': selected['resolved'], 'bytes': len(raw), 'sha256': sha(raw), 'integrity': selected['integrity'],
        'filePins': files, 'requests': 1, 'packageManagerInstallationOrLifecycleExecution': False,
        'extractionScope': 'Explicit verified regular members in one new hosted job-owned tool directory.',
        'publisherOrRegistryAttestationsVerified': False}


def qualify_ranges(repo, parent_root, inventory, profile, output, env, commands, selected):
    lock_raw = read_input(parent_root, 'package-lock.json')
    plan = version_cases(lock_raw, inventory, profile['node'], profile['npm'])
    tool, transport = acquire_source(output, selected)
    controls = range_controls()
    input_file = output / 'proposal-version-input.json'
    write_json(input_file, {'semverVersion': selected['version'], 'semverSourcePins': selected['filePins'],
        'cases': controls + plan['cases']})
    command = run_bounded(['node', str(repo / 'tools/dependency-review/version_ranges.cjs'), str(tool), str(input_file)],
        parent_root, env, output, 'proposal-version-ranges')
    commands.append(command)
    require(command['actualExit'] == 0 and command['outputComplete'], 'proposal version command failed or incomplete')
    result = json.loads((output / 'streams/proposal-version-ranges.stdout.txt').read_bytes())
    require(result['policies'] == POLICIES and result['semverVersion'] == selected['version']
        and result['sourcePinsVerifiedBeforeAndAfter'] and result['nodeVersion'] == profile['node'], 'range tool or profile differs')
    require(len(result['results']) == len(controls) + len(plan['cases']), 'range result count differs')
    for case, observed in zip(controls, result['results'][:len(controls)]):
        require(all(observed.get(key) == case[key] for key in ('key', 'mode', 'version', 'range'))
            and observed['matches'] == case['expected'] and observed['options'] == POLICIES[case['mode']], 'range policy control differs')
    require(all(name in selected['filePins'] and value == selected['filePins'][name]
        for name, value in result['sourcePins'].items()), 'executed range-tool source differs')
    reviewed = version_review(plan, result['results'][len(controls):])
    require(not (parent_root / 'node_modules').exists(), 'proposal evaluation installed application packages')
    return {'schema': 1, 'versionPlan': plan, 'versionReview': reviewed, 'toolTransport': transport,
        'executedToolSourcePins': result['sourcePins'], 'policyControlsPassed': len(controls),
        'semverPolicies': POLICIES, 'recordedProfile': profile,
        'proposalPackagesInstalledOrExecuted': False, 'applicationInputsChanged': False,
        'browserRuntimeQualified': False, 'completeProposedGraphQualified': False,
        'proposalAdopted': False, 'productionGate': 'NO_GO'}
