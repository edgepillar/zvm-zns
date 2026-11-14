"""Build explicit local derivative members without changing registry evidence."""

import json
import re

from lock_review import require
from mapper_rebuild_map import BREAK, positions
from mapper_rebuild_plan import pin, strip_source_map
from openzeppelin_candidate import checked_name
from parser_guard import patch_parser

PACKAGE = 'node_modules/chromium-bidi/'
PARSER = 'out/Default/gen/src/protocol-parser/protocol-parser.js'
MAPPER = 'out/Default/gen/src/mapperTab.js'


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True) + '\n').encode()


def node_line_map(guarded, original_members):
    bare, removed = strip_source_map(PARSER, guarded, original_members)
    require(removed is not None, 'derived parser original map directive absent')
    source_lines = BREAK.split(bare.decode('utf8'))
    if source_lines[-1] == '': source_lines.pop()
    generated_lines = BREAK.split(guarded.decode('utf8'))
    require(len(source_lines) <= len(generated_lines) <= 4096, 'derived parser line-map budget')
    data = {'version': 3, 'file': 'protocol-parser.js', 'sources': ['derived-compiled-js/protocol-parser.js'],
        'sourcesContent': [bare.decode('utf8')], 'names': [],
        'mappings': ';'.join(['AAAA'] + ['AACA'] * (len(source_lines) - 1))}
    mapped = list(positions(data['mappings'], [source_lines], generated_lines, []))
    require(len(mapped) == len(source_lines) and all(row == (0, i, 0, i, 0) for i, row in enumerate(mapped)),
        'derived parser compiled-JS line-map binding')
    return encoded(data), {'kind': 'DERIVED_COMPILED_JS_LINE_MAP', 'source': pin(bare), 'generated': pin(guarded),
        'mappedLines': len(mapped), 'originalMap': removed, 'originalTypeScriptMapReused': False,
        'columnAccurateOriginalTypeScriptMappingClaimed': False}


def mapper_map(raw, generated):
    data = json.loads(raw)
    require(data.get('version') == 3 and not data.get('sourceRoot') and 'sections' not in data, 'derived mapper map profile')
    require(data.get('file') in (None, 'mapper.js') and 0 < len(data['sources']) <= 2048
        and len(data['sources']) == len(data['sourcesContent']), 'derived mapper map inputs')
    labels = []; seen = set()
    for name, content in zip(data['sources'], data['sourcesContent']):
        require(name.startswith('../mapper-rebuild-source/') and type(content) is str, 'derived mapper map source')
        relative = name.removeprefix('../mapper-rebuild-source/'); checked_name(relative)
        require(relative not in seen, 'derived mapper map source alias'); seen.add(relative)
        labels.append('derived-compiled-js/' + relative)
    rows = list(positions(data['mappings'], [BREAK.split(s) for s in data['sourcesContent']], BREAK.split(generated.decode('utf8')), data.get('names', [])))
    require(rows, 'derived mapper empty source mappings')
    result = {**data, 'file': 'mapperTab.js', 'sources': labels}
    require(result['mappings'] == data['mappings'] and result['sourcesContent'] == data['sourcesContent'], 'derived mapper mapping changed')
    return encoded(result), {'kind': 'REBASED_COMPILED_JS_MAPPER_MAP', 'original': pin(raw), 'mappedSources': len(labels),
        'mappedSegments': len(rows), 'mappingDeltasAndSourceContentsPreserved': True, 'originalTypeScriptMapsReused': False}


def runtime_probe(generated, review):
    require(pin(generated) == review['generatedMapper'] and review['bootstrapRemoved'] is True, 'runtime capture base pin')
    text = generated.decode('utf8'); lines = BREAK.split(text); bindings = review['bindings']; cut = bindings['bootstrap']['generatedLine']
    require(0 < cut < len(lines) and re.fullmatch(r'\s*generatePage\d*\(\);\s*', lines[cut]), 'runtime capture bootstrap boundary')
    expected = {'array', 'string', 'object', 'version', 'BidiParser', 'InvalidArgumentException'}
    require(set(bindings) == expected | {'bootstrap'}, 'runtime capture binding scope')
    for key in expected:
        value = bindings[key]
        require(value['generatedLine'] < cut and re.fullmatch(re.escape(key) + r'\d*', value['identifier']), 'runtime capture identifier')
    capture = 'globalThis.__rebuiltProbe=Object.freeze({' + ','.join(key + ':' + bindings[key]['identifier'] for key in sorted(expected)) + '});\n'
    boundaries = list(BREAK.finditer(text)); offset = len(text[:boundaries[cut - 1].end()].encode('utf8'))
    raw = generated[:offset] + capture.encode() + generated[offset:]
    prefix = b''
    if 'noticePrefix' in review:
        from derivative_notices import MAPPER_NOTICE
        require(review['noticePrefix'] == pin(MAPPER_NOTICE), 'runtime capture unreviewed notice')
        prefix = MAPPER_NOTICE
    require(raw.startswith(prefix + b'(() => {\n') and len(raw) <= 4 << 20, 'runtime capture output')
    return raw, {'kind': 'SOURCE_MAP_BOUND_FULL_BOOTSTRAP_INSPECTION_COPY', 'base': pin(generated), 'derived': pin(raw),
        'capture': pin(capture.encode()), 'bootstrapRetained': True, 'installedIntoPackage': False,
        'unchangedGeneratedSourceMapAttached': False}


def derive_members(original, guard, rebuilt, review):
    guarded, guard_review = patch_parser(original[PARSER], guard)
    parser_map, parser_review = node_line_map(guarded, original)
    main = rebuilt['mapper.js']; require(b'mapper.js.LEGAL.txt' in main, 'rebuilt mapper legal reference')
    mapped, map_review = mapper_map(rebuilt['mapper.js.map'], main)
    require(not re.search(rb'(?:^|\n)//# sourceMappingURL=', main), 'rebuilt mapper already carries an unreviewed map route')
    payload = main + b'//# sourceMappingURL=mapperTab.js.map\n'
    probe, probe_review = runtime_probe(main, review)
    files = {PARSER: guarded, PARSER + '.map': parser_map, MAPPER: payload, MAPPER + '.map': mapped,
        'out/Default/gen/src/mapper.js.LEGAL.txt': rebuilt['mapper.js.LEGAL.txt']}
    origins = {}
    for name, raw in files.items():
        checked_name(name)
        origins[PACKAGE + name] = {'original': pin(original[name]) if name in original else None, 'effective': pin(raw),
            'kind': 'REVIEWED_LOCAL_DERIVATIVE', 'registryIntegrityCoversEffectiveBytes': False}
    return {'files': files, 'origins': origins, 'probe': probe, 'probeReview': probe_review,
        'parserGuard': guard_review, 'parserMap': parser_review, 'mapperMap': map_review,
        'effectiveMapper': pin(payload), 'effectiveParser': pin(guarded)}
