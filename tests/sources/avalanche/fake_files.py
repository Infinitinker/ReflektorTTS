"""Builds Avalanche game files for tests: stringlookups, bundles, and .tab/.arc archives."""

import struct
import zlib
from collections.abc import Mapping, Sequence
from pathlib import Path

from reflektortts.sources.avalanche.lookup3 import hashlittle

HEADER = 0x40
INSTANCE = 24
STORED, DEFLATE, CHUNKED = "stored", "deflate", "chunked"
CHUNK = 64


def stringlookup(lines: Mapping[int, str]) -> bytes:
    """An ADF file with one stringlookup instance."""
    texts, offsets = b"", []
    for text in lines.values():
        offsets.append(len(texts))
        texts += text.encode("utf-8") + b"\0"
    index = 0x30
    entries = b"".join(
        struct.pack("<IIfIII", line_id, offset, 1.0, 0, 0, 1) for line_id, offset in zip(lines, offsets, strict=True)
    )
    text_offset = index + len(entries)
    instance = struct.pack("<QQQQ", index, len(lines), text_offset, len(texts)) + bytes(16) + entries + texts
    offset = HEADER + INSTANCE
    header = struct.pack("<4sIII", b" FDA", 4, 1, HEADER) + bytes(HEADER - 16)
    record = struct.pack("<IIIIq", 0, 0, offset, len(instance), 0)
    return header + record + instance


def bundle(files: Mapping[str, bytes]) -> bytes:
    """A SARC bundle holding files by path."""
    table = b""
    data = b""
    names = [name.encode() for name in files]
    table_size = sum(4 + len(name) + 8 for name in names)
    start = 16 + table_size
    for name, content in zip(names, files.values(), strict=True):
        table += struct.pack("<I", len(name)) + name + struct.pack("<II", start + len(data), len(content))
        data += content
    return struct.pack("<I4sII", 4, b"SARC", 2, table_size) + table + data


def _deflate(data: bytes) -> bytes:
    compressor = zlib.compressobj(wbits=-15)
    return compressor.compress(data) + compressor.flush()


def write_archive(tab: Path, files: Sequence[tuple[str, bytes, str]]) -> None:
    """A .tab and .arc pair holding files named (name, data, how stored)."""
    arc = b""
    chunked = b""
    chunked_count = 0
    entries = b""
    for name, data, how in files:
        name_hash = hashlittle(name.encode())
        if how == STORED:
            stored = data
        elif how == DEFLATE:
            stored = _deflate(data)
        else:
            pieces = [_deflate(data[i : i + CHUNK]) for i in range(0, len(data), CHUNK)]
            chunks = []
            compressed = 0
            for number, piece in enumerate(pieces):
                chunks.append((number * CHUNK, compressed))
                compressed += len(piece)
            stored = b"".join(pieces)
            chunked += struct.pack("<II", name_hash, len(chunks)) + b"".join(struct.pack("<II", *c) for c in chunks)
            chunked_count += 1
        entries += struct.pack("<IIII", name_hash, len(arc), len(stored), len(data))
        arc += stored
    tab.parent.mkdir(parents=True, exist_ok=True)
    tab.write_bytes(struct.pack("<II", 0x800, chunked_count) + chunked + entries)
    tab.with_suffix(".arc").write_bytes(arc)
