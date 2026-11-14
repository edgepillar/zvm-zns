"""Exercise mapping deltas and refuse unbound declarations before execution."""

import copy
import json
import unittest

from lock_review import ReviewError
from mapper_rebuild_map import ALPHABET, TARGETS, bind_map, fields, positions
from mapper_rebuild_plan import pin, strip_source_map


def vlq(value):
    value = (abs(value) << 1) | (value < 0); result = ''
    while True:
        digit = value & 31; value >>= 5
        result += ALPHABET[digit | (32 if value else 0)]
        if not value: return result


def fixture():
    staged = {}; target_rows = {}; generated = ['(() => {']
    for key, (path, _) in TARGETS.items():
        declaration = 'export function ' + key + '() {}' if key in ('array', 'string', 'object') else (
            'export const version = {};' if key == 'version' else 'export class ' + key + ' {}')
        if key == 'bootstrap': declaration = 'generatePage();'
        target_rows[key] = (path, len(staged.get(path, b'').decode().splitlines()))
        staged[path] = staged.get(path, b'') + (declaration + '\n').encode()
        generated.append('  ' + (declaration.removeprefix('export ').replace('const version', 'var version').replace('class ' + key + ' {}', 'var ' + key + ' = class {};')))
    generated.append('})();'); code = ('\n'.join(generated) + '\n').encode()
    sources = list(staged); source_index = line_index = column = 0; mappings = ['']
    for key in TARGETS:
        path, row = target_rows[key]; index = sources.index(path)
        mappings.append(''.join(vlq(value) for value in (2, index - source_index, row - line_index, -column)))
        source_index, line_index, column = index, row, 0
    mappings.append('')
    data = {'version': 3, 'sources': ['../mapper-rebuild-source/' + path for path in sources],
        'sourcesContent': [value.decode() for value in staged.values()], 'names': [], 'mappings': ';'.join(mappings)}
    origins = {path: {'staged': pin(value)} for path, value in staged.items()}
    return data, code, staged, origins, {'inputs': {path: {} for path in staged}}


class RebuiltMapControls(unittest.TestCase):
    def test_deltas_persist_across_lines_and_generated_column_resets(self):
        rows = list(positions('AAAAA,UAAUC;AACVD', [['0123456789', 'ab']], ['0123456789', 'ab'], ['a', 'b']))
        self.assertEqual(rows, [(0, 0, 0, 0, 0), (0, 0, 10, 0, 10), (0, 1, 0, 1, 0)])

    def test_original_columns_use_utf16_units(self):
        self.assertEqual(list(positions('AAAG', [['\U0001f600a']], [''], [])), [(0, 0, 3, 0, 0)])
        with self.assertRaises(ReviewError): list(positions('AAAI', [['\U0001f600a']], [''], []))

    def test_invalid_vlq_and_fields_are_refused(self):
        for value in ['B', 'g', 'AA', '!', '///////', 'gA', 'AAAAAA', '']:
            with self.subTest(value=value), self.assertRaises(ReviewError): fields(value)

    def test_out_of_bounds_generated_source_and_name_positions_are_refused(self):
        for value in ['CAAA', 'ACAA', 'AACA', 'AAAC', 'AAAAC', 'AAAA,,AAAA']:
            with self.subTest(value=value), self.assertRaises(ReviewError): list(positions(value, [['']], [''], []))

    def test_bound_declarations_cut_before_bootstrap(self):
        data, code, staged, origins, meta = fixture()
        instrumented, review = bind_map(json.dumps(data).encode(), code, staged, origins, meta)
        self.assertNotIn(b'generatePage();', instrumented)
        self.assertIn(b'array:array', instrumented)
        self.assertTrue(review['bootstrapRemoved']); self.assertEqual(len(review['bindings']), 7)

    def test_changed_content_source_root_and_escaping_sources_are_refused(self):
        base, code, staged, origins, meta = fixture()
        for kind in ['content', 'root', 'route', 'section']:
            data = copy.deepcopy(base)
            if kind == 'content': data['sourcesContent'][0] += ' '
            elif kind == 'root': data['sourceRoot'] = 'https://example.invalid/'
            elif kind == 'route': data['sources'][0] = '../mapper-rebuild-source/../outside.js'
            else: data['sections'] = []
            with self.subTest(kind=kind), self.assertRaises(ReviewError): bind_map(json.dumps(data).encode(), code, staged, origins, meta)

    def test_changed_generated_binding_or_bootstrap_is_refused(self):
        data, code, staged, origins, meta = fixture()
        for changed in [code.replace(b'function array', b'function replaced'), code.replace(b'generatePage();', b'runBrowser();')]:
            with self.assertRaises(ReviewError): bind_map(json.dumps(data).encode(), changed, staged, origins, meta)

    def test_old_map_directive_removed_without_changing_other_source_bytes(self):
        original = b'export const value = 1;\n//# sourceMappingURL=input.js.map\n'
        result, review = strip_source_map('input.js', original, {'input.js.map': b'{"version":3}'})
        self.assertEqual(result, b'export const value = 1;\n')
        self.assertFalse(review['originalMapReusedForChangedSource'])
        for source in [b'//# sourceMappingURL=../escape.map\n', b'//# sourceMappingURL=input.js.map\n']:
            with self.assertRaises(ReviewError): strip_source_map('input.js', source, {})


if __name__ == '__main__': unittest.main()
