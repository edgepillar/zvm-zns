"""Inspect the complete selected Linux Chrome ZIP without extracting or running it."""

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import zipfile

from lock_review import require

MAX_RAW = 256 << 20
MAX_MEMBERS = 2048
MAX_CENTRAL = 4 << 20
MAX_EXPANDED = 1 << 30
MAX_FILE = 512 << 20
ROOT = 'chrome-linux64'


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def safe_name(value):
    require(type(value) is str and 0 < len(value) <= 2048 and value.isascii(), 'browser archive name encoding or length')
    path = PurePosixPath(value)
    require(path.as_posix() == value and not path.is_absolute() and value != '.'
        and '..' not in path.parts and '\\' not in value and ':' not in value
        and not any(ord(char) < 32 or ord(char) == 127 for char in value), 'browser archive path')
    require(path.parts[0] == ROOT, 'browser archive root')
    require(not any(part.casefold() in ('.git', '.ssh', '.codex', '.env', 'credentials', 'wallet.json') for part in path.parts),
        'browser archive protected name')
    return path


def inspect_stream(source, expected):
    require(type(expected['bytes']) is int and 22 <= expected['bytes'] <= MAX_RAW
        and type(expected['sha256']) is str and re.fullmatch('[0-9a-f]{64}', expected['sha256']), 'browser raw pin')
    source.seek(0, 2); raw_bytes = source.tell()
    require(raw_bytes == expected['bytes'], 'browser raw byte count')
    source.seek(0); digest = hashlib.sha256()
    while True:
        chunk = source.read(1 << 20)
        if not chunk: break
        digest.update(chunk)
    require(digest.hexdigest() == expected['sha256'], 'browser raw SHA-256')
    source.seek(0); require(source.read(4) == b'PK\x03\x04', 'browser ZIP prefix')
    source.seek(-22, 2); end = source.read(22)
    signature, disk, central_disk, disk_count, count, central_size, central_offset, comment = struct.unpack('<4s4H2LH', end)
    require(signature == b'PK\x05\x06' and disk == central_disk == comment == 0
        and 0 < count == disk_count <= MAX_MEMBERS, 'browser ZIP end, disk or member count')
    require(0 < central_size <= MAX_CENTRAL and central_offset + central_size == raw_bytes - 22,
        'browser central directory budget or extent')
    seen = set(); non_directories = set(); files = {}; directories = []; expanded = payload_bytes = 0; chrome_header = None
    with zipfile.ZipFile(source) as archive:
        members = archive.infolist()
        require(len(members) == count and archive.start_dir == central_offset and archive.comment == b'', 'browser ZIP directory differs')
        require(sum(member.file_size for member in members) <= MAX_EXPANDED, 'browser archive expanded budget')
        for member in members:
            directory = member.is_dir()
            name = member.filename[:-1] if directory else member.filename
            path = safe_name(name); folded = name.casefold()
            require(folded not in seen, 'browser archive alias'); seen.add(folded)
            ancestors = ['/'.join(path.parts[:index]).casefold() for index in range(1, len(path.parts))]
            require(not any(parent in non_directories for parent in ancestors), 'browser archive file ancestor')
            if not directory:
                require(not any(other.startswith(folded + '/') for other in seen), 'browser archive file ancestor')
                non_directories.add(folded)
            mode = member.external_attr >> 16; kind = stat.S_IFMT(mode)
            require(not (member.flag_bits & 1) and member.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED),
                'browser archive encryption or compression')
            require(len(member.extra) <= 4096 and len(member.comment) <= 1024
                and 0 <= member.header_offset < central_offset and 0 <= member.file_size <= MAX_FILE,
                'browser archive member metadata or byte budget')
            require(kind in ((0, stat.S_IFDIR) if directory else (0, stat.S_IFREG)), 'browser archive nonregular member')
            if directory:
                require(member.file_size == 0, 'browser directory payload'); directories.append(name); continue
            require(len(path.parts) >= 2, 'browser file outside root')
            relative = '/'.join(path.parts[1:]); total = 0; member_digest = hashlib.sha256(); prefix = bytearray()
            with archive.open(member) as stream:
                while True:
                    chunk = stream.read(1 << 20)
                    if not chunk: break
                    total += len(chunk); require(total <= member.file_size, 'browser member expansion differs')
                    member_digest.update(chunk)
                    if len(prefix) < 64: prefix.extend(chunk[:64 - len(prefix)])
            require(total == member.file_size, 'browser archive truncated member')
            files[relative] = {'bytes': total, 'sha256': member_digest.hexdigest(), 'unixPermissions': mode & 0o7777}
            expanded += member.file_size; payload_bytes += total
            if relative == 'chrome': chrome_header = bytes(prefix)
    require(chrome_header is not None and len(chrome_header) == 64, 'browser Chrome ELF header absent')
    require(chrome_header[:7] == b'\x7fELF\x02\x01\x01', 'browser ELF class, encoding or version')
    elf_type, machine, version = struct.unpack('<HHI', chrome_header[16:24])
    require(elf_type in (2, 3) and machine == 62 and version == 1, 'browser ELF architecture or type')
    require(files['chrome']['unixPermissions'] & 0o111, 'browser executable mode absent')
    require(expanded == payload_bytes <= MAX_EXPANDED, 'browser complete expanded count')
    notices = sorted(name for name in files if name.rsplit('/', 1)[-1].upper().startswith(
        ('ABOUT', 'LICENSE', 'LICENCE', 'COPYING', 'NOTICE', 'COPYRIGHT', 'CREDITS')))
    inventory_raw = json.dumps(files, sort_keys=True, separators=(',', ':')).encode()
    require(len(inventory_raw) <= 2 << 20, 'browser file inventory metadata budget')
    return {'schema': 1, 'archive': dict(expected), 'root': ROOT, 'archiveMembers': count,
        'regularFiles': len(files), 'directories': sorted(directories), 'expandedBytes': expanded,
        'filePins': files, 'filePinInventorySha256': hashlib.sha256(inventory_raw).hexdigest(),
        'noticeCandidates': notices, 'elf': {'class': 64, 'encoding': 'little-endian', 'machine': 62, 'type': elf_type},
        'completeMemberBytesAndCRCRead': True, 'archiveFilesystemExtractionOrBrowserExecution': False,
        'publisherSignatureReproducibleBuildOrLegalAcceptanceEstablished': False, 'productionGate': 'NO_GO'}


def inspect_file(path, expected):
    path = Path(path)
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size == expected['bytes'],
        'browser input file identity or type')
    identity = lambda value: (value.st_dev, value.st_ino, value.st_mode, value.st_nlink,
        value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    with path.open('rb') as source: result = inspect_stream(source, expected)
    require(identity(path.lstat()) == identity(before), 'browser input changed during inspection')
    return result
