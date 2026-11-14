"""Annotate a frozen derivative without rebuilding or changing original notices."""

import copy
import json

from coherent_derivation import PACKAGE, PARSER, MAPPER, node_line_map, runtime_probe
from lock_review import require
from mapper_rebuild_map import BREAK, positions
from mapper_rebuild_plan import pin

PARSER_NOTICE = b'/*! Modified by edgepillar: reviewed parser type guard; compiled-JavaScript line map. See vendor NOTICE.md and manifest.json. */\n'
MAPPER_NOTICE = b'/*! Modified by edgepillar: rebuilt compiled JavaScript with Zod 4.6.7 and the reviewed parser guard; rebased source map. See vendor NOTICE.md and manifest.json. */\n'
MAP_NOTICE = 'Modified by edgepillar: derived compiled-JavaScript map; original TypeScript map is not reused. See vendor NOTICE.md and manifest.json.'


def noticed_map(raw):
    data = json.loads(raw)
    require('x_edgepillar_changes' not in data, 'map already annotated')
    return (json.dumps({'x_edgepillar_changes': MAP_NOTICE, **data}, separators=(',', ':'), ensure_ascii=True) + '\n').encode()


def shift_mapper_map(raw, before, after):
    data = json.loads(raw)
    require(data.get('version') == 3 and data.get('file') == 'mapperTab.js'
        and not data.get('sourceRoot') and 'sections' not in data, 'notice mapper map profile')
    require(after == MAPPER_NOTICE + before, 'notice mapper prefix differs')
    lines = [BREAK.split(value) for value in data['sourcesContent']]
    old = list(positions(data['mappings'], lines, BREAK.split(before.decode()), data['names']))
    data['mappings'] = ';' + data['mappings']
    new = list(positions(data['mappings'], lines, BREAK.split(after.decode()), data['names']))
    require(new == [(s, line, col, generated + 1, gc) for s, line, col, generated, gc in old], 'notice map line shift differs')
    return noticed_map(json.dumps(data).encode()), len(new)


def annotate(payloads, original_manifest, prior_commit, prior_manifest_pin):
    manifest = copy.deepcopy(original_manifest)
    require(len(payloads) == 9 and {name: pin(raw) for name, raw in payloads.items()} == manifest['payloads'], 'notice preimages differ')
    require('changeNotices' not in manifest, 'derivative already annotated')
    result = dict(payloads)
    parser = result[PARSER] = PARSER_NOTICE + payloads[PARSER]
    parser_map, parser_review = node_line_map(parser, {PARSER + '.map': payloads[PARSER + '.map']})
    parser_review['originalMap'] = manifest['parserMap']['originalMap']
    parser_review['priorDerivedMap'] = pin(payloads[PARSER + '.map'])
    result[PARSER + '.map'] = noticed_map(parser_map)
    mapper = result[MAPPER] = MAPPER_NOTICE + payloads[MAPPER]
    result[MAPPER + '.map'], segments = shift_mapper_map(payloads[MAPPER + '.map'], payloads[MAPPER], mapper)
    suffix = b'//# sourceMappingURL=mapperTab.js.map\n'
    require(mapper.endswith(suffix), 'notice mapper directive differs')
    bootstrap = manifest['bootstrapInspection']; bootstrap['generatedMapper'] = pin(mapper[:-len(suffix)])
    bootstrap['noticePrefix'] = pin(MAPPER_NOTICE)
    for value in bootstrap['bindings'].values(): value['generatedLine'] += 1
    probe, manifest['probe'] = runtime_probe(mapper[:-len(suffix)], bootstrap)
    manifest['parserGuard']['guardDerivedBeforeNotice'] = manifest['parserGuard']['derived']
    manifest['parserGuard']['derived'] = pin(parser); manifest['parserGuard']['noticePrefix'] = pin(PARSER_NOTICE)
    manifest['parserMap'] = parser_review
    manifest['mapperMap'].update(generatedLineOffset=1, priorMap=pin(payloads[MAPPER + '.map']),
        mappedSegments=segments, mappingDeltasAndSourceContentsPreserved=True)
    data = json.loads(result[MAPPER + '.map'])
    mapped = list(positions(data['mappings'], [BREAK.split(s) for s in data['sourcesContent']], BREAK.split(mapper.decode()), data['names']))
    samples = []
    for key, value in sorted(bootstrap['bindings'].items()):
        candidates = [row for row in mapped if row[3] == value['generatedLine'] and row[1] == value['originalLine']
            and data['sources'][row[0]] == 'derived-compiled-js/' + value['source']]
        require(candidates, 'notice debugger sample absent: ' + key)
        s, line, col, generated, gc = min(candidates, key=lambda row: row[4])
        samples.append({'binding': key, 'generatedLine': generated, 'generatedColumn': gc,
            'sourceIndex': s, 'source': data['sources'][s], 'originalLine': line, 'originalColumn': col})
    manifest['changeNotices'] = {'kind': 'EXPLICIT_PER_FILE_DERIVATIVE_NOTICES', 'priorCommit': prior_commit,
        'priorManifest': prior_manifest_pin, 'priorPayloads': original_manifest['payloads'],
        'parserPrefix': pin(PARSER_NOTICE), 'mapperPrefix': pin(MAPPER_NOTICE), 'mapProperty': 'x_edgepillar_changes',
        'modifiedPayloads': sorted([PARSER, PARSER + '.map', MAPPER, MAPPER + '.map']),
        'originalCopyrightLicenseAndLegalBytesPreserved': True, 'compilerOrPackageManagerExecuted': False}
    manifest['debuggerSamples'] = samples
    manifest['payloads'] = {name: pin(raw) for name, raw in result.items()}
    for name, raw in result.items(): manifest['effectiveMembers'][PACKAGE + name]['effective'] = pin(raw)
    return result, manifest, probe
