"""Rebuild a separate guarded mapper from verified published JS and Zod 4.6.7."""

import gzip
import io
import json
from pathlib import Path
import re
import stat
import tarfile
import urllib.request

from bundled_archive import inspect_archive
from lock_review import read_input, require
from mapper_rebuild_plan import ENTRY, OUTPUT, check_metafile, pin, prepare_inputs
from mapper_rebuild_map import bind_map
from openzeppelin_candidate import run_bounded, write_json
from openzeppelin_candidate import checked_name


def read_rebuilt(root, name, limit):
    """Explicit larger budgets only for the newly derived compiler/map outputs."""
    checked_name(name); current = root
    for part in Path(name).parts:
        current /= part; require(not current.is_symlink(), 'linked rebuild output or ancestor')
    before = current.stat()
    require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 0 <= before.st_size <= limit, 'rebuild output type or budget')
    with current.open('rb') as source: raw = source.read(limit + 1)
    after = current.stat()
    identity = lambda item: (item.st_dev, item.st_ino, item.st_mode, item.st_nlink, item.st_size, item.st_mtime_ns, item.st_ctime_ns)
    require(identity(before) == identity(after) and len(raw) == before.st_size, 'rebuild output changed while reading')
    return raw


def retained_members(output, index, selected):
    raw = read_input(output / 'mapper-control-sources', 'mapper.tgz' if index['name'] == 'chromium-bidi' else 'fixed.tgz')
    require(pin(raw) == {key: index[key] for key in ('bytes', 'sha256')} and index['integrity'] == selected['selection']['integrity'], 'retained mapper source changed')
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream: expanded = stream.read((64 << 20) + 1)
    require(pin(expanded) == {'bytes': index['expandedBytes'], 'sha256': index['expandedSha256']}, 'retained expansion changed')
    require(set(index['members']) == set(selected['filePins']), 'retained source index scope differs')
    files = {}
    for name, row in index['members'].items():
        require(type(row['offset']) is int and row['offset'] >= 0 and row['offset'] + row['bytes'] <= len(expanded), 'retained source offset differs')
        body = expanded[row['offset']:row['offset'] + row['bytes']]
        require(pin(body) == selected['filePins'][name], 'retained source member changed')
        files[name] = body
    return files


def additional_source(selected):
    source = selected['selection']; limit = selected['publication']['bytes']
    require(type(limit) is int and 0 < limit <= 8 << 20, 'rebuild transport budget')
    request = urllib.request.Request(source['resolved'], headers={'User-Agent': 'edgepillar-dependency-review'})
    with urllib.request.urlopen(request, timeout=45) as response:
        raw = response.read(limit + 1)
        require(response.status == 200 and response.geturl() == source['resolved'], 'rebuild response route differs')
        if response.headers.get('Content-Length') is not None:
            require(int(response.headers['Content-Length']) == len(raw), 'rebuild response incomplete')
    require(pin(raw) == {key: selected['publication'][key] for key in ('bytes', 'sha256')}, 'rebuild raw source differs')
    reviewed = inspect_archive(raw, {**selected['lockRow'], 'name': source['name']}, expanded_limit=64 << 20)
    actual = {row['path'].removeprefix('package/'): {key: row[key] for key in ('bytes', 'sha256')}
        for row in reviewed['archiveMembers'] if row['kind'] == 'file'}
    require(actual == selected['filePins'], 'rebuild publication member scope differs')
    files = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
        for member in archive:
            if not member.isfile(): continue
            name = member.name.removeprefix('package/'); require(member.size <= 16 << 20, 'rebuild source member budget')
            body = archive.extractfile(member).read((16 << 20) + 1)
            require(pin(body) == actual[name], 'rebuild source member differs'); files[name] = body
    return files, {'selection': source, 'publication': pin(raw), 'requests': 1,
        'filePins': actual, 'packageManagerOrLifecycleExecution': False}


def qualify_rebuild(repo, parent_root, output, env, commands, source_plan, execution):
    execution.update(status='PREPARING_INPUTS', compilerCodeExecution=False, generatedPackageCodeExecution=False)
    plan_raw = read_input(repo, 'tools/dependency-review/mapper-rebuild-sources.json'); plan = json.loads(plan_raw)
    require(plan['schema'] == 1 and set(plan['packages']) == {'esbuild', '@esbuild/linux-x64', 'mitt'}, 'rebuild source plan scope')
    lock = json.loads(read_input(repo, 'web/package-lock.json'))['packages']
    extra, transports = {}, {}
    for name, selected in plan['packages'].items():
        require(selected['lockRow'] == lock[selected['selection']['location']], 'compiler or emitter lock selection differs')
        extra[name], transports[name] = additional_source(selected)
    old = json.loads(read_input(output, 'mapper-size-input.json'))
    packages = {}
    for role in ('mapper', 'fixed'):
        index = old[role]; selected = source_plan['publications'][index['integrity']]
        packages[index['name']] = {'selection': selected['selection'], 'files': retained_members(output, index, selected)}
    packages['mitt'] = {'selection': plan['packages']['mitt']['selection'], 'files': extra['mitt']}
    guard = json.loads(read_input(repo, 'tools/dependency-review/node-parser-guard.json'))
    derived = prepare_inputs(packages, guard)
    root = output / 'mapper-rebuild-source'; root.mkdir(mode=0o700)
    built = output / 'mapper-rebuilt'; built.mkdir(mode=0o700)
    for name, raw in derived['files'].items():
        target = root / name; target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as destination: destination.write(raw)
    notices = dict(derived['notices'])
    for name, raw in extra['esbuild'].items():
        if re.fullmatch(r'(?:LICENSE|LICENCE|NOTICE)(?:\.[A-Za-z0-9_-]+)?', name, re.I):
            notices['esbuild/' + name] = {'bytes': raw, 'pin': pin(raw), 'source': plan['packages']['esbuild']['selection'], 'member': name}
    require(any(name.startswith('esbuild/') for name in notices), 'compiler original license absent')
    notice_pins = {}
    for name, notice in notices.items():
        target = built / 'notices' / name; target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as destination: destination.write(notice['bytes'])
        notice_pins['mapper-rebuilt/notices/' + name] = {key: value for key, value in notice.items() if key != 'bytes'}
    binary_raw = extra['@esbuild/linux-x64']['bin/esbuild']
    require(binary_raw[:6] == b'\x7fELF\x02\x01' and int.from_bytes(binary_raw[18:20], 'little') == 62, 'compiler ELF profile differs')
    tools = output / 'mapper-rebuild-tools'; tools.mkdir(mode=0o700); binary = tools / 'esbuild'
    with binary.open('xb') as destination: destination.write(binary_raw)
    binary.chmod(0o700)
    def run(label, argv, timeout):
        result = run_bounded(argv, root, env, output, label, timeout=timeout)
        commands.append(result); execution['lastCommand'] = result
        require(result['actualExit'] == 0 and result['outputComplete'], label + ' failed or incomplete')
        return result
    execution.update(status='COMPILER_VERSION_ATTEMPTED', compilerCodeExecution=None)
    run('mapper-rebuild-compiler-version', [str(binary), '--version'], 30)
    require(read_input(output, 'streams/mapper-rebuild-compiler-version.stdout.txt') == b'0.28.2\n', 'compiler version differs')
    execution.update(status='COMPILER_BUILD_ATTEMPTED', compilerCodeExecution=True)
    argv = [str(binary), ENTRY, '--bundle', '--platform=browser', '--format=iife', '--target=chrome157',
        '--charset=ascii', '--tree-shaking=true', '--sourcemap=external', '--sources-content=true',
        '--legal-comments=linked', '--metafile=../mapper-rebuilt/metafile.json', '--outfile=' + OUTPUT,
        '--tsconfig-raw={}', '--color=false', '--log-level=warning']
    run('mapper-rebuild', argv, 90)
    require(read_rebuilt(tools, 'esbuild', 16 << 20) == binary_raw, 'compiler binary changed during build')
    for name, raw in derived['files'].items(): require(read_input(root, name) == raw, 'build input changed during compilation')
    output_pins = {OUTPUT + suffix: pin(read_rebuilt(built, 'mapper.js' + suffix, (16 if suffix == '.map' else 4) << 20)) for suffix in ('', '.map', '.LEGAL.txt')}
    meta = json.loads(read_input(built, 'metafile.json'))
    meta_review = check_metafile(meta, derived['origins'], output_pins)
    instrumented, map_review = bind_map(read_rebuilt(built, 'mapper.js.map', 16 << 20), read_rebuilt(built, 'mapper.js', 4 << 20), derived['files'], derived['origins'], meta)
    with (built / 'declarations-only.js').open('xb') as destination: destination.write(instrumented)
    input_path = output / 'mapper-rebuild-probe.json'
    write_json(input_path, {'schema': 1, 'path': str(built / 'declarations-only.js'), 'pin': pin(instrumented)})
    execution.update(status='GENERATED_DECLARATION_CONTROLS_ATTEMPTED', generatedPackageCodeExecution=None)
    run('mapper-rebuilt-controls', ['node', '--max-old-space-size=128', str(repo / 'tools/dependency-review/rebuilt-mapper-worker.cjs'), str(input_path)], 45)
    result = json.loads(read_input(output, 'streams/mapper-rebuilt-controls.stdout.txt'))
    require(result['status'] == 'REBUILT_DECLARATIONS_QUALIFIED_BROWSER_AND_ADOPTION_NOT_ACCEPTED'
        and result['totalCases'] == 12 and result['instrumentedDeclarations'] == pin(instrumented), 'rebuilt controls result differs')
    require(result['versionObject'] == {'major': 4, 'minor': 6, 'patch': 7}
        and not result['browserOrCDPBootstrapExecuted'] and not result['proposalAdopted'], 'rebuilt execution scope differs')
    execution.update(status='COMPILED_JS_REBUILD_AND_SELECTED_DECLARATIONS_QUALIFIED', generatedPackageCodeExecution=True)
    for name, value in output_pins.items(): require(pin(read_rebuilt(built, name.rsplit('/', 1)[-1], (16 if name.endswith('.map') else 4) << 20)) == value, 'rebuilt payload changed after controls')
    return {'schema': 1, 'status': execution['status'], 'sourcePlan': pin(plan_raw), 'additionalSourceTransport': transports,
        'reusedRawPublications': 2, 'newRawPublications': 3, 'compilerBinary': pin(binary_raw),
        'compilerBinarySourceReproductionOrIndependentAuthentication': False,
        'compilerVersion': '0.28.2', 'compilerArguments': argv[1:],
        'stagedInputOrigins': derived['origins'], 'guardDerivation': derived['guardDerivation'],
        'stagedFiles': derived['stagedFiles'], 'stagedBytes': derived['stagedBytes'],
        'strippedOriginalMapDirectives': derived['strippedOriginalMapDirectives'],
        'originalNotices': notice_pins, 'outputs': {name.rsplit('/', 1)[-1]: value for name, value in output_pins.items()},
        'metafile': pin(read_input(built, 'metafile.json')), 'inputGraphReview': meta_review,
        'sourceMapReview': map_review, 'controls': result,
        'sourceMapScope': 'Actual derived published compiled-JS inputs. Original TypeScript maps were not reused.',
        'packageManagerOrLifecycleOrBrowserDownloadPerformed': False,
        'originalPublicationOrApplicationFilesChanged': False, 'fullCandidateGraphInstalled': False,
        'browserCSPOrProductionSourceMapAcceptance': False, 'proposalAdopted': False, 'productionGate': 'NO_GO'}
