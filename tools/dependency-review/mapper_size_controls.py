"""Prepare bounded generated-mapper/fixed-library controls without installation."""

import gzip
import io
import json
import tarfile
import urllib.request

from bundled_archive import inspect_archive
from bundled_lock import metadata
from lock_review import decode, read_input, require
from openzeppelin_candidate import run_bounded, sha, write_json
from proposal_delta import registry_identity

BOOTSTRAP = '\n    generatePage();\n    const mapperTabToServerTransport'
CAPTURE = '\n    globalThis.__dependencyProbe = Object.freeze({array, string, object, version});\n})();\n'
SUFFIX = '})();\n//# sourceMappingURL=mapperTab.js.map\n'


def instrument_mapper(raw):
    require(type(raw) is bytes and 0 < len(raw) <= 2 << 20, 'mapper script byte budget')
    text = raw.decode('utf8')
    require(text.startswith('(function () {\n') and text.endswith(SUFFIX), 'mapper wrapper differs')
    require(text.count(BOOTSTRAP) == 1, 'mapper bootstrap boundary absent or ambiguous')
    prefix = text[:text.index(BOOTSTRAP)]; instrumented = (prefix + CAPTURE).encode()
    return instrumented, {'originalMapperSha256': sha(raw), 'instrumentedMapperSha256': sha(instrumented),
        'captureSourceSha256': sha(CAPTURE.encode()), 'mapperBootstrapRemoved': True,
        'removedBootstrapUtf8Bytes': len(raw) - len(prefix.encode()),
        'originalPublicationOrApplicationFilesChanged': False}


def indexed_archive(raw, location, lock_row, expected):
    require(type(raw) is bytes and 0 < len(raw) <= 8 << 20, 'mapper control archive byte budget')
    require(registry_identity(location, lock_row) == expected['selection'], 'mapper control source selection differs')
    require({'bytes': len(raw), 'sha256': sha(raw)} == {key: expected['publication'][key] for key in ('bytes', 'sha256')},
        'mapper control raw source pin differs')
    reviewed = inspect_archive(raw, {**lock_row, 'name': expected['selection']['name']}, expanded_limit=64 << 20)
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream: expanded = stream.read((64 << 20) + 1)
    require(len(expanded) <= 64 << 20, 'mapper control expansion budget')
    members = {}; manifest = None
    with tarfile.open(fileobj=io.BytesIO(expanded), mode='r:') as archive:
        for member in archive:
            if not member.isfile(): continue
            relative = member.name.removeprefix('package/')
            require(relative in expected['filePins'], 'unreviewed source member in mapper control archive')
            body = expanded[member.offset_data:member.offset_data + member.size]
            require({'bytes': len(body), 'sha256': sha(body)} == expected['filePins'][relative], 'mapper control source member differs')
            members[relative] = {**expected['filePins'][relative], 'offset': member.offset_data}
            if relative == 'package.json': manifest = decode(body)
    require(set(members) == set(expected['filePins']) and manifest is not None, 'mapper control source inventory incomplete')
    metadata(lock_row, manifest, bundled=False)
    require(reviewed['parentManifestSha256'] == expected['manifestSha256'], 'mapper control manifest pin differs')
    return {'name': expected['selection']['name'], 'version': expected['selection']['version'],
        'bytes': len(raw), 'sha256': sha(raw), 'integrity': expected['selection']['integrity'],
        'expandedBytes': len(expanded), 'expandedSha256': sha(expanded), 'members': members}


def qualify_mapper_controls(repo, parent_root, output, env, commands, source_plan, execution=None):
    execution = {} if execution is None else execution
    execution.update(status='PREPARING_REVIEWED_INPUTS', selectedPackageCodeExecution=False)
    source_root = output / 'mapper-control-sources'; source_root.mkdir(mode=0o700)
    lock = json.loads(read_input(parent_root, 'package-lock.json'))['packages']
    sources, transport, instrumentation = {}, {}, None
    for role, name, version in [('mapper', 'chromium-bidi', '157.0.8090-0'), ('fixed', 'zod', '4.6.7')]:
        location = 'node_modules/' + name; row = lock[location]
        expected = source_plan['publications'][row['integrity']]
        require(expected['selection']['name'] == name and expected['selection']['version'] == version, 'unreviewed mapper control profile')
        selected = expected['selection']; limit = expected['publication']['bytes']
        require(type(limit) is int and 0 < limit <= 8 << 20, 'mapper control transport cap')
        request = urllib.request.Request(selected['resolved'], headers={'User-Agent': 'edgepillar-dependency-review'})
        with urllib.request.urlopen(request, timeout=45) as response:
            raw = response.read(limit + 1)
            require(response.status == 200 and response.geturl() == selected['resolved'], 'mapper control source response differs')
            if response.headers.get('Content-Length') is not None:
                require(int(response.headers['Content-Length']) == len(raw), 'mapper control source response incomplete')
        index = indexed_archive(raw, location, row, expected)
        if role == 'mapper':
            with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
                original = archive.extractfile('package/out/Default/gen/src/mapperTab.js').read((2 << 20) + 1)
            _, instrumentation = instrument_mapper(original)
        path = source_root / (role + '.tgz')
        with path.open('xb') as target: target.write(raw)
        sources[role] = {**index, 'path': str(path)}
        transport[role] = {'url': selected['resolved'], 'bytes': len(raw), 'sha256': sha(raw),
            'integrity': selected['integrity'], 'requests': 1, 'filesystemArchiveExtractions': 0,
            'memberIndexSha256': sha(json.dumps(index['members'], sort_keys=True, separators=(',', ':')).encode())}
    input_path = output / 'mapper-size-input.json'; write_json(input_path, {'schema': 1, **sources})
    execution.update(status='COMMAND_ATTEMPTED', selectedPackageCodeExecution=None,
        inputSha256=sha(input_path.read_bytes()))
    command = run_bounded(['node', '--max-old-space-size=128', '--experimental-vm-modules',
        str(repo / 'tools/dependency-review/mapper-size-worker.cjs'), str(input_path)], parent_root, env, output, 'mapper-array-controls', timeout=45)
    commands.append(command); execution['command'] = command
    execution['status'] = 'COMMAND_RETURNED_RESULT_UNQUALIFIED'
    require(command['actualExit'] == 0 and command['outputComplete'], 'bounded mapper controls failed or incomplete')
    result = json.loads((output / 'streams/mapper-array-controls.stdout.txt').read_bytes())
    require(result['status'] == 'BOUNDED_ARRAY_ORDERING_DIFFERENCE_REPRODUCED_NO_MIGRATION_ACCEPTANCE'
        and result['totalCases'] == 16 and result['maximumContainerLength'] == 3, 'mapper control case scope differs')
    require(all(result[key] == instrumentation[key] for key in ('originalMapperSha256', 'instrumentedMapperSha256', 'captureSourceSha256')),
        'mapper instrumentation differs from reviewed boundary')
    require(result['mapperBootstrapRemoved'] and not result['mapperBrowserOrCDPBootstrapExecuted']
        and result['generatedDeclarationsAndSelectedZodCodeExecuted'] and not result['proposalAdopted'], 'mapper execution scope differs')
    for member in result['fixedLoadedMembers']:
        require(member == {'name': member['name'], **sources['fixed']['members'][member['name']]}, 'loaded fixed-library source pin differs')
    require(not (parent_root / 'node_modules').exists(), 'mapper controls installed the proposal graph')
    execution.update(status='QUALIFIED_BOUNDED_CONTROLS', selectedPackageCodeExecution=True)
    return {'schema': 1, 'status': result['status'], 'sourceTransport': transport,
        'instrumentation': instrumentation, 'result': result, 'maximumContainerLength': 3,
        'completeCandidateDependencyInstallation': False, 'selectedPublishedPackageCodeExecuted': True,
        'generatedBrowserBootstrapExecuted': False, 'actualBrowserOrRuntimeReachabilityQualified': False,
        'compiledSchemaJITQualified': False, 'migrationAcceptance': 'NO_GO', 'productionGate': 'NO_GO'}
