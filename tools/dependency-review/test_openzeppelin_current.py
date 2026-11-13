"""Refuse incomplete or changed tracked artifact reproductions."""

import unittest

from openzeppelin_current import require_output_parity


class CurrentOutputControls(unittest.TestCase):
    def test_current_build_cannot_qualify_missing_extra_or_changed_outputs(self):
        expected = {'contracts/out/' + str(index) + '.json': {'bytes': 100, 'sha256': 'a' * 64} for index in range(12)}
        require_output_parity(expected, dict(expected))
        changed = dict(expected); changed['contracts/out/0.json'] = {'bytes': 100, 'sha256': 'b' * 64}
        for actual in (changed, dict(list(expected.items())[1:]), {**expected, 'extra': {}}):
            with self.subTest(actual=actual), self.assertRaises(ValueError):
                require_output_parity(expected, actual)


if __name__ == '__main__':
    unittest.main()
