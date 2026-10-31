"""Avalanche's small archives (SARC version 2), which bundle the files a level or a cutscene needs.

From Gibbed.MadMax (zlib licence): a 16-byte header {u32 4, "SARC", u32 version, u32 table size},
then the table: per file {u32 name length, name padded with zeros, u32 offset, u32 size}, with
offsets from the bundle's start.
"""

import struct
from dataclasses import dataclass

HEADER_SIZE = 16
MAGIC = b"SARC"


class BundleError(Exception):
    """A bundle's table cannot be read."""


@dataclass(frozen=True)
class BundleFile:
    name: str
    """Its path, e.g. "missions/main_missions/mm1010/mm1010_cs010_p2_pol.stringlookup"."""
    offset: int
    size: int


def is_bundle(header: bytes) -> bool:
    return header[4:8] == MAGIC


def table_size(header: bytes) -> int:
    """How many bytes after the header the bundle's table takes."""
    size: int = struct.unpack_from("<I", header, 12)[0]
    return size


def bundle_files(header_and_table: bytes) -> list[BundleFile]:
    files = []
    table = header_and_table[HEADER_SIZE:]
    position = 0
    try:
        while position + 4 <= len(table):
            (length,) = struct.unpack_from("<I", table, position)
            if length == 0:
                break
            name = table[position + 4 : position + 4 + length].split(b"\0")[0].decode("utf-8")
            offset, size = struct.unpack_from("<II", table, position + 4 + length)
            files.append(BundleFile(name, offset, size))
            position += 4 + length + 8
    except (struct.error, UnicodeDecodeError) as error:
        raise BundleError(f"A bundle's table is damaged: {error}") from error
    return files
