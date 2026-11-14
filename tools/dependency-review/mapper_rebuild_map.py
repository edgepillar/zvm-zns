"""Bind one bounded esbuild flat map to the actual compiled-JS build inputs.

This intentionally accepts a narrow compiler profile, not arbitrary source maps.
Positions follow ECMA-426 (UTF-16 columns; persistent source/name deltas).
"""

import json
import posixpath
import re

from lock_review import require
from mapper_rebuild_plan import ENTRY, pin
from openzeppelin_candidate import checked_name

ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
VALUES = {char: i for i, char in enumerate(ALPHABET)}
BREAK = re.compile(r'\r\n|[\r\n\u2028\u2029]')
TARGETS = {
    'array': ('node_modules/zod/v4/classic/schemas.js', r'^export function array\('),
    'string': ('node_modules/zod/v4/classic/schemas.js', r'^export function string\('),
    'object': ('node_modules/zod/v4/classic/schemas.js', r'^export function object\('),
    'version': ('node_modules/zod/v4/core/versions.js', r'^export const version ='),
    'BidiParser': ('node_modules/chromium-bidi/out/Default/gen/src/bidiTab/BidiParser.js', r'^export class BidiParser\b'),
    'InvalidArgumentException': ('node_modules/chromium-bidi/out/Default/gen/src/protocol/ErrorResponse.js', r'^export class InvalidArgumentException\b'),
    'bootstrap': (ENTRY, r'^generatePage\(\);$'),
}


def fields(segment):
    require(type(segment) is str and 0 < len(segment) <= 40, 'map segment budget')
    result = []; value = shift = digits = 0
    for char in segment:
        require(char in VALUES, 'map VLQ alphabet')
        digit = VALUES[char]; value |= (digit & 31) << shift; digits += 1
        require(digits <= 7 and value < 1 << 31, 'map VLQ integer budget')
        if digit & 32:
            shift += 5
            continue
        require(value != 1 and (digits == 1 or digit & 31), 'map VLQ outside canonical bounded profile')
        result.append(-(value >> 1) if value & 1 else value >> 1)
        require(len(result) <= 5, 'map field count')
        value = shift = digits = 0
    require(digits == 0 and len(result) in (1, 4, 5), 'map incomplete VLQ or field count')
    return result


def positions(mappings, source_lines, generated_lines, names):
    require(type(mappings) is str and len(mappings) <= 8 << 20, 'map mappings budget')
    source = original_line = original_column = name = count = 0
    lines = mappings.split(';'); require(len(lines) <= len(generated_lines), 'map generated line exceeds output')
    widths = {}
    def width(kind, line, value):
        key = (kind, line)
        if key not in widths: widths[key] = len(value.encode('utf-16-le')) // 2
        return widths[key]
    for generated_line, encoded in enumerate(lines):
        column = 0
        if not encoded: continue
        for segment in encoded.split(','):
            count += 1; require(count <= 1000000, 'map segment count budget')
            row = fields(segment); column += row[0]
            require(row[0] >= 0 and column <= width('generated', generated_line, generated_lines[generated_line]), 'map generated column')
            if len(row) == 1: continue
            source += row[1]; original_line += row[2]; original_column += row[3]
            require(0 <= source < len(source_lines) and 0 <= original_line < len(source_lines[source]), 'map source or original line')
            require(0 <= original_column <= width(source, original_line, source_lines[source][original_line]), 'map original column')
            if len(row) == 5:
                name += row[4]; require(0 <= name < len(names), 'map name index')
            yield (source, original_line, original_column, generated_line, column)


def bind_map(map_raw, generated_raw, staged, origins, meta):
    require(type(map_raw) is bytes and len(map_raw) <= 16 << 20, 'map payload budget')
    require(type(generated_raw) is bytes and 0 < len(generated_raw) <= 4 << 20, 'generated UTF-8 mapper budget')
    data = json.loads(map_raw)
    require(data.get('version') == 3 and not data.get('sourceRoot') and 'sections' not in data, 'unreviewed source map profile')
    require(data.get('file') in (None, 'mapper.js'), 'map generated file differs')
    names = data.get('names', []); sources = data['sources']; contents = data['sourcesContent']
    require(type(names) is list and len(names) <= 100000 and all(type(x) is str for x in names), 'map names budget')
    require(type(sources) is list and 0 < len(sources) <= 2048 and len(sources) == len(contents), 'map source count')
    mapped, lines, targets = {}, [], {}
    for index, (relative, text) in enumerate(zip(sources, contents)):
        require(type(relative) is str and relative.startswith('../mapper-rebuild-source/'), 'map source outside derived tree')
        path = relative.removeprefix('../mapper-rebuild-source/'); checked_name(path)
        require(posixpath.normpath(relative) == relative and path not in mapped and path in meta['inputs'], 'map source route differs')
        require(type(text) is str and text.encode('utf8') == staged[path] and pin(text.encode('utf8')) == origins[path]['staged'], 'map content differs from actual build input')
        mapped[path] = pin(text.encode('utf8')); rows = BREAK.split(text); lines.append(rows)
        for key, (source, pattern) in TARGETS.items():
            if path != source: continue
            matches = [i for i, row in enumerate(rows) if re.match(pattern, row)]
            require(len(matches) == 1, 'map target declaration absent or ambiguous: ' + key)
            targets[key] = (index, matches[0])
    require(set(targets) == set(TARGETS), 'map selected declaration scope differs')
    generated = generated_raw.decode('utf8'); generated_lines = BREAK.split(generated)
    require(generated.startswith('(() => {\n') and re.search(r'\n\}\)\(\);\n(?:/\*![^\x00]{0,256}\*/\n)?\Z', generated), 'generated mapper wrapper differs')
    found = {key: set() for key in TARGETS}; segments = 0
    for source, line, _, generated_line, _ in positions(data['mappings'], lines, generated_lines, names):
        segments += 1
        for key, target in targets.items():
            if target != (source, line): continue
            row = generated_lines[generated_line]
            if key == 'bootstrap':
                match = re.fullmatch(r'\s*generatePage\d*\(\);', row)
                if match: found[key].add((generated_line, ''))
            else:
                base = re.escape(key)
                pattern = r'^\s*function (' + base + r'\d*)\(' if key in ('array', 'string', 'object') else r'^\s*var (' + base + r'\d*) = '
                match = re.match(pattern, row)
                if match: found[key].add((generated_line, match.group(1)))
    require(all(len(value) == 1 for value in found.values()), 'map generated declaration absent or ambiguous')
    bindings = {key: {'generatedLine': next(iter(value))[0], 'identifier': next(iter(value))[1],
        'source': TARGETS[key][0], 'originalLine': targets[key][1]} for key, value in found.items()}
    cut = bindings['bootstrap']['generatedLine']
    require(all(value['generatedLine'] < cut for key, value in bindings.items() if key != 'bootstrap'), 'capture crosses mapper bootstrap')
    prefix = '\n'.join(generated_lines[:cut]) + '\n'
    capture = 'globalThis.__rebuiltProbe = Object.freeze({' + ','.join(key + ':' + value['identifier'] for key, value in bindings.items() if key != 'bootstrap') + '});\n})();\n'
    instrumented = (prefix + capture).encode('utf8')
    return instrumented, {'schema': 1, 'generatedMapper': pin(generated_raw), 'sourceMap': pin(map_raw),
        'instrumentedDeclarations': pin(instrumented), 'capture': pin(capture.encode('ascii')),
        'mappedSources': mapped, 'mappedSourceCount': len(mapped), 'mappedSegments': segments,
        'bindings': bindings, 'bootstrapRemoved': True, 'originalTypeScriptMapsReused': False,
        'generalSourceMapConsumerConformanceClaimed': False, 'browserRuntimeQualified': False}
