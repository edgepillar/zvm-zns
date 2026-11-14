"""Pure-data refusal controls for the first-party browser source boundary."""

import copy
import json
from pathlib import Path
import unittest

from browser_staging import validate_source_plan
from openzeppelin_candidate import sha


class SourceBoundary(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads((Path(__file__).parent / 'browser-app-sources.json').read_bytes())

    def repin(self):
        self.plan['fileListSha256'] = sha(json.dumps(self.plan['files'], sort_keys=True, separators=(',', ':')).encode())

    def test_complete_reviewed_packet(self):
        self.assertEqual(len(validate_source_plan(self.plan)), 71)

    def test_changed_member_without_new_list_pin(self):
        self.plan['files'][0]['pin']['sha256'] = '0' * 64
        with self.assertRaises(ValueError): validate_source_plan(self.plan)

    def test_operator_deployment_input(self):
        row = self.plan['files'][0]; row['sourcePath'] = 'deployments/7340469.json'; self.repin()
        with self.assertRaises(ValueError): validate_source_plan(self.plan)

    def test_funded_script_input(self):
        row = self.plan['files'][0]; row['sourcePath'] = 'web/scripts/verify.mjs'; self.repin()
        with self.assertRaises(ValueError): validate_source_plan(self.plan)

    def test_parent_escape(self):
        row = self.plan['files'][0]; row['sourcePath'] = 'web/src/../../operator.json'; self.repin()
        with self.assertRaises(ValueError): validate_source_plan(self.plan)

    def test_unlisted_destination(self):
        self.plan['files'][0]['destinationRelativeToOutput'] = '../operator.json'; self.repin()
        with self.assertRaises(ValueError): validate_source_plan(self.plan)

    def test_nonregular_source_mode(self):
        self.plan['files'][0]['gitMode'] = '120000'; self.repin()
        with self.assertRaises(ValueError): validate_source_plan(self.plan)

    def test_duplicate_destination(self):
        self.plan['files'][1] = copy.deepcopy(self.plan['files'][0]); self.repin()
        with self.assertRaises(ValueError): validate_source_plan(self.plan)

    def test_unknown_repository(self):
        self.plan['files'][0]['sourceRepository'] = 'operator'; self.repin()
        with self.assertRaises(ValueError): validate_source_plan(self.plan)

    def test_tracked_deployment_claim(self):
        self.plan['trackedDeploymentRecords'] = 1
        with self.assertRaises(ValueError): validate_source_plan(self.plan)
