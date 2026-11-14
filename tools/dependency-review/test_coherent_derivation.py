"""Pure map and full-bootstrap capture boundaries; no local browser fixtures."""

import copy
import json
import unittest

from coherent_derivation import PARSER, encoded, mapper_map, node_line_map, runtime_probe
from mapper_rebuild_plan import pin


class CoherentDerivation(unittest.TestCase):
    def test_compiled_parser_line_map(self):
        raw=b'export const value=1;\n//# sourceMappingURL=protocol-parser.js.map\n'
        result,review=node_line_map(raw,{PARSER+'.map':b'{}'})
        data=json.loads(result);self.assertEqual(data['file'],'protocol-parser.js')
        self.assertFalse(review['originalTypeScriptMapReused']);self.assertEqual(data['sourcesContent'],['export const value=1;\n'])

    def test_unicode_columns_and_line_separators(self):
        raw=('const text="\U0001f600";\u2028const next="\u03bb";\n//# sourceMappingURL=protocol-parser.js.map\n').encode()
        _,review=node_line_map(raw,{PARSER+'.map':b'{}'});self.assertEqual(review['mappedLines'],2)

    def test_absent_original_map_refused(self):
        with self.assertRaises(ValueError):node_line_map(b'const value=1;\n',{})

    def mapping(self):
        return {'version':3,'sources':['../mapper-rebuild-source/node_modules/zod/value.js'],
            'sourcesContent':['const value=1;\n'],'names':[],'mappings':'AAAA;AACA'}

    def test_mapper_relabels_preserve_contents_and_deltas(self):
        original=self.mapping();raw,review=mapper_map(encoded(original),b'const value=1;\n');data=json.loads(raw)
        self.assertEqual(data['mappings'],original['mappings']);self.assertEqual(data['sourcesContent'],original['sourcesContent'])
        self.assertEqual(data['sources'],['derived-compiled-js/node_modules/zod/value.js']);self.assertEqual(review['mappedSegments'],2)

    def test_absolute_source_refused(self):
        data=self.mapping();data['sources']=['/unreviewed/input.js']
        with self.assertRaises(ValueError):mapper_map(encoded(data),b'const value=1;\n')

    def test_source_root_refused(self):
        data=self.mapping();data['sourceRoot']='unreviewed'
        with self.assertRaises(ValueError):mapper_map(encoded(data),b'const value=1;\n')

    def test_indexed_map_refused(self):
        data=self.mapping();data['sections']=[]
        with self.assertRaises(ValueError):mapper_map(encoded(data),b'const value=1;\n')

    def test_duplicate_source_refused(self):
        data=self.mapping();data['sources']*=2;data['sourcesContent']*=2
        with self.assertRaises(ValueError):mapper_map(encoded(data),b'const value=1;\n')

    def probe(self):
        keys=['array','string','object','version','BidiParser','InvalidArgumentException']
        generated=('(() => {\n'+''.join('var '+key+'=null;\n' for key in keys)+'generatePage();\n})();\n').encode()
        bindings={key:{'identifier':key,'generatedLine':i+1} for i,key in enumerate(keys)}
        bindings['bootstrap']={'identifier':'','generatedLine':7}
        return generated,{'generatedMapper':pin(generated),'bootstrapRemoved':True,'bindings':bindings}

    def test_inspection_copy_keeps_actual_bootstrap(self):
        raw,review=self.probe();derived,record=runtime_probe(raw,review)
        self.assertIn(b'generatePage();',derived);self.assertTrue(record['bootstrapRetained'])
        self.assertFalse(record['installedIntoPackage']);self.assertFalse(record['unchangedGeneratedSourceMapAttached'])

    def test_injected_identifier_refused(self):
        raw,review=self.probe();review=copy.deepcopy(review);review['bindings']['array']['identifier']='array;unreviewed()'
        with self.assertRaises(ValueError):runtime_probe(raw,review)

    def test_python_only_control_separator_does_not_shift_capture(self):
        raw,review=self.probe();raw=raw.replace(b'(() => {\n',b'(() => {\n// control\x1c remains on this line\n')
        review=copy.deepcopy(review);review['generatedMapper']=pin(raw)
        for binding in review['bindings'].values():binding['generatedLine']+=1
        result,_=runtime_probe(raw,review)
        self.assertIn(b'globalThis.__rebuiltProbe',result)
        self.assertIn(b'});\ngeneratePage();',result)
