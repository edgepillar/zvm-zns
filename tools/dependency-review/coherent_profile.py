"""Install one explicit derivative into a new hosted regular-file profile."""

import json

from browser_staging import hosted_only, new_file, validate_source_plan
from coherent_derivation import PACKAGE, PARSER, MAPPER, derive_members
from lock_review import read_input, require
from mapper_rebuild import read_rebuilt
from openzeppelin_candidate import run_bounded, write_json
from profile_sources import pin, read_regular
from proposal_delta import registry_identity


def stage_coherent(repo, candidate, output, env, commands, rebuild, execution):
    hosted_only(); execution['status'] = 'COHERENT_PROFILE_SOURCE_PREPARATION_ATTEMPTED'
    inventory_raw = read_regular(output, 'candidate-profile-sources.json', 16 << 20); inventory = json.loads(inventory_raw)
    lock_raw = read_input(candidate, 'package-lock.json'); lock = json.loads(lock_raw)['packages']
    require(inventory['lockSha256'] == pin(lock_raw)['sha256'], 'coherent profile base lock differs')
    selected = registry_identity(PACKAGE.rstrip('/'), lock[PACKAGE.rstrip('/')])
    source = inventory['sources'][selected['integrity']]; require(source['selection'] == selected, 'coherent base publication differs')
    guard_raw = read_input(repo, 'tools/dependency-review/node-parser-guard.json'); guard = json.loads(guard_raw)
    require(selected == guard['publication'], 'coherent guarded publication differs')
    original = {}
    for name in [PARSER, PARSER + '.map', MAPPER, MAPPER + '.map']:
        raw = read_regular(candidate, PACKAGE + name, 16 << 20)
        require(pin(raw) == source['filePins'][name], 'coherent original member differs'); original[name] = raw
    rebuilt = {}
    for name, expected in rebuild['outputs'].items():
        raw = read_rebuilt(output / 'mapper-rebuilt', name, 16 << 20)
        require(pin(raw) == expected, 'coherent rebuilt input differs'); rebuilt[name] = raw
    effective = derive_members(original, guard, rebuilt, rebuild['sourceMapReview'])
    assets = dict(effective['files']); origins = dict(effective['origins'])
    for path, notice in rebuild['originalNotices'].items():
        raw = read_input(output, path); require(pin(raw) == notice['pin'], 'coherent original notice differs')
        name = 'notices/' + path.removeprefix('mapper-rebuilt/notices/')
        require(name not in source['filePins'], 'coherent notice destination collision')
        assets[name] = raw
        origins[PACKAGE + name] = {'original': None, 'effective': pin(raw), 'kind': 'RETAINED_ORIGINAL_NOTICE',
            'source': notice['source'], 'member': notice['member'], 'registryIntegrityCoversEffectiveBytes': False}
    root = output / 'coherent-profile' / 'web'
    require(not root.exists() and not root.is_symlink(), 'coherent profile must be new')
    for name in ['package.json', 'package-lock.json']:
        new_file(output, 'coherent-profile/web/' + name, read_input(candidate, name))
    copied = total = 0; packages = []
    for location in sorted(inventory['installed']):
        publication = inventory['sources'][lock[location]['integrity']]
        require(publication['selection'] == registry_identity(location, lock[location]), 'coherent copy source selection')
        for name, expected in publication['filePins'].items():
            raw = read_regular(candidate, location + '/' + name, 16 << 20)
            require(pin(raw) == expected, 'coherent copy source member differs')
            relative = location + '/' + name
            value = assets[name] if location == PACKAGE.rstrip('/') and name in assets else raw
            mode = (candidate / relative).stat().st_mode
            copied += 1; total += len(value); require(copied <= 32768 and total <= 256 << 20, 'coherent portable copy budget')
            new_file(root, relative, value, bool(mode & 0o111))
        packages.append({'location': location, 'selection': publication['selection'], 'regularMembers': len(publication['filePins'])})
    for name, raw in assets.items():
        if name in source['filePins']: continue
        copied += 1; total += len(raw); require(copied <= 32768 and total <= 256 << 20, 'coherent sidecar budget')
        new_file(root, PACKAGE + name, raw)
    first_party_raw = read_input(repo, 'tools/dependency-review/browser-app-sources.json'); first_party = json.loads(first_party_raw)
    first_party_records = []
    for row in validate_source_plan(first_party):
        source_root = repo if row['sourceRepository'] == 'main' else repo / 'zvm-core'
        raw = read_input(source_root, row['sourcePath']); require(pin(raw) == row['pin'], 'coherent first-party source differs')
        destination = row['destinationRelativeToOutput']
        if destination.startswith('candidate-web-parent/'):
            destination = 'coherent-profile/web/' + destination.removeprefix('candidate-web-parent/')
        else: destination = 'coherent-profile/' + destination
        new_file(output, destination, raw); first_party_records.append({'sourcePath': row['sourcePath'], 'destination': destination, 'pin': row['pin']})
    manifest = {'schema': 1, 'kind': 'REVIEWED_LOCAL_DERIVATIVE_PROFILE', 'baseProfile': 'candidate',
        'baseLockSha256': pin(lock_raw)['sha256'], 'sourceInventory': pin(inventory_raw),
        'publication': {'location': PACKAGE.rstrip('/'), 'selection': selected}, 'effectiveMembers': origins,
        'parserGuard': effective['parserGuard'], 'parserMap': effective['parserMap'], 'mapperMap': effective['mapperMap'],
        'probe': effective['probeReview'], 'registryArtifactOrPublisherAuthenticationClaimed': False,
        'originalRawSourceProfilesModified': False, 'productionGate': 'NO_GO'}
    manifest_path = output / 'coherent-profile-source-binding.json'; write_json(manifest_path, manifest)
    probe_path = new_file(output, 'coherent-mapper-runtime-probe.js', effective['probe'])
    execution['status'] = 'COHERENT_APPLICATION_BUILDS_ATTEMPTED'
    def build(label):
        package = json.loads(read_input(root, 'package.json'))
        require(package['scripts']['build'] == 'vue-tsc --noEmit && vite build' and not any(key in package['scripts'] for key in ['prebuild', 'postbuild']), 'coherent build script scope')
        for suffix, argv in [('types', ['node', 'node_modules/vue-tsc/bin/vue-tsc.js', '--noEmit']),
                ('vite', ['node', 'node_modules/vite/bin/vite.js', 'build'])]:
            row = run_bounded(argv, root, env, output, label + '-' + suffix, timeout=120)
            commands.append(row); execution['lastCommand'] = row
            require(row['actualExit'] == 0 and row['outputComplete'], label + '-' + suffix + ' failed or incomplete')
    from web_patches import dist_inventory
    build('coherent-normal-app-build'); normal = dist_inventory(root / 'dist')
    normal_root = output / 'coherent-normal-dist'; require(not normal_root.exists(), 'coherent normal distribution collision')
    (root / 'dist').rename(normal_root)
    deployment = (json.dumps(first_party['syntheticDeploymentFixture'], sort_keys=True, indent=2) + '\n').encode()
    new_file(output, 'coherent-profile/deployments/browser-fixture.json', deployment)
    build('coherent-fixture-app-build'); fixture = dist_inventory(root / 'dist')
    for name, row in origins.items():
        require(pin(read_regular(root, name, 16 << 20)) == row['effective'], 'coherent effective member changed during builds')
    execution['status'] = 'COHERENT_PROFILE_INSTALLED_AND_BUILT_RUNTIME_NOT_YET_RUN'
    result = {'schema': 1, 'status': execution['status'], 'sourceBinding': pin(manifest_path.read_bytes()),
        'regularPackageMembers': copied, 'regularPackageBytes': total, 'packageLocations': len(packages), 'packages': packages,
        'effectiveMembers': origins, 'firstPartySources': first_party_records, 'firstPartySourcePlan': pin(first_party_raw),
        'normalDistribution': normal, 'fixtureDistribution': fixture, 'fullBootstrapProbe': effective['probeReview'],
        'originalRawProfilesModified': False, 'hardLinksOrAliasesUsed': False, 'additionalPackageOrBrowserDownloads': 0,
        'applicationMigrationAdopted': False, 'productionGate': 'NO_GO'}
    write_json(output / 'coherent-profile.json', result)
    return result, {'root': root, 'manifest': manifest_path, 'manifestPin': pin(manifest_path.read_bytes()),
        'probe': probe_path, 'distributions': {'normal': normal_root, 'fixture': root / 'dist'}}
