"""Derive one reviewed type guard without modifying the original publication."""

from lock_review import require
from openzeppelin_candidate import sha

BEFORE = b"if ('coordinates' in params && 'error' in params) {"
AFTER = b"if (typeof params === 'object' && params !== null && 'coordinates' in params && 'error' in params) {"


def patch_parser(raw, plan):
    require(type(raw) is bytes and 0 < len(raw) <= 64 << 10, 'parser patch byte budget')
    require(plan['schema'] == 1 and plan['kind'] == 'REVIEW_ONLY_DERIVED_NODE_PARSER_TYPE_GUARD', 'parser patch kind differs')
    require({'bytes': len(raw), 'sha256': sha(raw)} == plan['original'], 'parser patch original pin differs')
    require(raw.count(BEFORE) == plan['replacementCount'] == 1, 'parser patch boundary absent or ambiguous')
    derived = raw.replace(BEFORE, AFTER)
    require({'bytes': len(derived), 'sha256': sha(derived)} == plan['derived'], 'parser patch derived pin differs')
    return derived, {'original': plan['original'], 'derived': plan['derived'], 'replacementCount': 1,
        'sourcePublicationAndApplicationFilesChanged': False, 'embeddedMapperOrValidatorChanged': False}
