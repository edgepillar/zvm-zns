"""Derive bounded mapper build inputs while preserving publication evidence."""

import json
from pathlib import PurePosixPath
import re

from lock_review import require
from openzeppelin_candidate import checked_name, sha
from parser_guard import patch_parser

ENTRY = 'node_modules/chromium-bidi/out/Default/gen/src/bidiTab/bidiTab.js'
OUTPUT = '../mapper-rebuilt/mapper.js'
VERSIONS = {'chromium-bidi': '157.0.8090-0', 'zod': '4.6.7', 'mitt': '3.0.1'}


def pin(raw):
    return {'bytes': len(raw), 'sha256': sha(raw)}


def strip_source_map(name, raw, original_members):
    """Do not let a changed JS input silently reuse an older TypeScript map."""
    matches = list(re.finditer(rb'(?:^|\n)//# sourceMappingURL=([^\r\n]+)\r?\n?\Z', raw))
    if not matches:
        return raw, None
    require(len(matches) == 1 and raw.count(b'\n//# sourceMappingURL=') <= 1, 'ambiguous input source map directive')
    match = matches[0]; target = match.group(1).decode('ascii')
    require(target == PurePosixPath(name).name + '.map', 'unreviewed input source map route')
    relative = str(PurePosixPath(name).parent / target)
    require(relative in original_members, 'declared input source map is absent from original publication')
    # The original map remains in its retained raw publication. A new map will
    # bind the actual compiled-JS inputs, including the explicit parser guard.
    return raw[:match.start()] + b'\n', {'originalMap': relative, 'originalMapPin': pin(original_members[relative]),
        'originalDirectiveSha256': sha(raw[match.start():]), 'originalMapReusedForChangedSource': False}


def prepare_inputs(packages, guard):
    require(set(packages) == set(VERSIONS), 'mapper rebuild package scope differs')
    staged, origins, notices = {}, {}, {}
    guard_derivation = None; source_map_strips = 0; total = 0
    for name, version in VERSIONS.items():
        package = packages[name]; original = package['files']
        manifest = json.loads(original['package.json'])
        require(manifest['name'] == name and manifest['version'] == version, 'mapper rebuild source identity differs')
        require(package['selection']['name'] == name and package['selection']['version'] == version, 'mapper rebuild selection differs')
        prefix = 'node_modules/' + name + '/'
        notice_paths = []
        for relative, raw in sorted(original.items()):
            checked_name(relative)
            leaf = PurePosixPath(relative).name
            if re.fullmatch(r'(?:LICENSE|LICENCE|NOTICE)(?:\.[A-Za-z0-9_-]+)?', leaf, re.I):
                notice_paths.append(relative)
                notices[name + '/' + relative] = {'bytes': raw, 'pin': pin(raw), 'source': package['selection'], 'member': relative}
            if not (relative.endswith(('.js', '.mjs')) or leaf == 'package.json'):
                continue
            # The old precompiled mapper must never become a build input.
            if name == 'chromium-bidi' and relative == 'out/Default/gen/src/mapperTab.js':
                continue
            original_pin = pin(raw); transformations = []
            if name == 'chromium-bidi' and relative == guard['entry']:
                raw, guard_derivation = patch_parser(raw, guard)
                transformations.append({'kind': 'REVIEWED_GEOLOCATION_TYPE_GUARD', **guard_derivation})
            if relative.endswith(('.js', '.mjs')):
                raw.decode('utf8')
                raw, map_strip = strip_source_map(relative, raw, original)
                if map_strip is not None:
                    source_map_strips += 1
                    transformations.append({'kind': 'REMOVE_ORIGINAL_MAP_DIRECTIVE_FOR_NEW_COMPILED_JS_MAP', **map_strip})
            path = prefix + relative; checked_name(path)
            require(path not in staged and len(staged) < 2048 and len(raw) <= 4 << 20, 'mapper staged member budget')
            total += len(raw); require(total <= 16 << 20, 'mapper staged payload budget')
            staged[path] = raw
            origins[path] = {'selection': package['selection'], 'member': relative, 'original': original_pin,
                'staged': pin(raw), 'transformations': transformations}
        require(notice_paths, 'mapper source publication lacks a retained original notice')
    require(ENTRY in staged and guard_derivation is not None, 'mapper entry or guarded parser absent')
    return {'files': staged, 'origins': origins, 'notices': notices,
        'guardDerivation': guard_derivation, 'strippedOriginalMapDirectives': source_map_strips,
        'stagedFiles': len(staged), 'stagedBytes': total,
        'sourcePublicationOrApplicationFilesChanged': False}


def check_metafile(meta, origins, output_pins):
    require(type(meta) is dict and type(meta.get('inputs')) is dict and type(meta.get('outputs')) is dict, 'compiler metadata shape')
    require(0 < len(meta['inputs']) <= 2048, 'compiler input count budget')
    for path, value in meta['inputs'].items():
        checked_name(path); require(path in origins, 'compiler read an unreviewed input')
        require(value['bytes'] == origins[path]['staged']['bytes'], 'compiler input size differs')
        require('/zod/v3/' not in path and not path.endswith('/mapperTab.js'), 'old validator or precompiled mapper entered rebuild')
        for edge in value['imports']:
            require(not edge.get('external', False) and edge['path'] in meta['inputs'], 'unbound compiler import')
    expected = {OUTPUT, OUTPUT + '.map', OUTPUT + '.LEGAL.txt'}
    require({OUTPUT, OUTPUT + '.map'} <= set(meta['outputs']) <= expected, 'compiler output set differs')
    for path, value in meta['outputs'].items():
        require(value['bytes'] == output_pins[path]['bytes'] and not value['imports'], 'compiler output byte count or import differs')
    main = meta['outputs'][OUTPUT]
    require(main['entryPoint'] == ENTRY and main['exports'] == [], 'mapper public entry shape differs')
    for path in main['inputs']:
        require(path in origins, 'output contribution lacks reviewed source')
    require(any('/zod/v4/core/versions.js' in path for path in main['inputs']), 'fixed validator version source absent')
    return {'inputs': len(meta['inputs']), 'outputContributors': len(main['inputs']),
        'allCompilerInputsBound': True, 'externalImports': 0, 'oldPrecompiledMapperOrV3Inputs': 0,
        'compilerMetafileIsNotIndependentCompilerOrPublisherAuthentication': True}
