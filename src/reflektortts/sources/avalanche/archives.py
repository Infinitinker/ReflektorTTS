"""Avalanche's archives: a .tab file listing each file by the hash of its name, and an .arc file
with the data.

The layout comes from Gibbed.MadMax (zlib licence). The .tab starts with u32 0x800 (the
alignment), then the files stored in chunks: {u32 name hash, u32 chunk count, per chunk {u32
offset in the file, u32 offset in the compressed data}}; then, to its end, every file: {u32 name
hash, u32 offset in the .arc, u32 compressed size, u32 size}. A file is stored as is when both
sizes match, otherwise as raw deflate: one stream, or one per chunk.
"""

import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

ALIGNMENT = 0x800
FIRST_BLOCK = 1024
"""Compressed bytes read first: enough for a file's header, the read most often made."""
BLOCK = 64 * 1024


class ArchiveError(Exception):
    """An archive cannot be read."""


@dataclass(frozen=True)
class ArchiveEntry:
    offset: int
    compressed_size: int
    size: int
    chunks: tuple[tuple[int, int], ...] = ()
    """Where each chunk starts: (offset in the file, offset in the compressed data)."""


class Archive:
    """One .tab and .arc pair, open for reading."""

    def __init__(self, tab: Path) -> None:
        self.path = tab
        self.entries = read_tab(tab)
        self._arc: BinaryIO = tab.with_suffix(".arc").open("rb")

    def read(self, entry: ArchiveEntry, start: int = 0, size: int | None = None) -> bytes:
        """size bytes of a file from start, or the rest of it; only what they need is decompressed."""
        end = entry.size if size is None else min(entry.size, start + size)
        try:
            if entry.compressed_size == entry.size:
                self._arc.seek(entry.offset + start)
                return self._arc.read(end - start)
            if not entry.chunks:
                return self._inflate(entry.offset, entry.compressed_size, end)[start:end]
            return self._read_chunks(entry, start, end)
        except (OSError, zlib.error) as error:
            raise ArchiveError(f"Cannot read a file in {self.path.with_suffix('.arc')}: {error}") from error

    def close(self) -> None:
        self._arc.close()

    def _read_chunks(self, entry: ArchiveEntry, start: int, end: int) -> bytes:
        bounds = [*entry.chunks, (entry.size, entry.compressed_size)]
        data = bytearray()
        first = None
        for (begin, compressed_begin), (next_begin, compressed_end) in zip(bounds, bounds[1:], strict=False):
            if next_begin <= start or begin >= end:
                continue
            if first is None:
                first = begin
            data += self._inflate(
                entry.offset + compressed_begin, compressed_end - compressed_begin, min(next_begin, end) - begin
            )
        offset = start - (first or 0)
        return bytes(data[offset : offset + end - start])

    def _inflate(self, offset: int, compressed_size: int, wanted: int) -> bytes:
        """The first wanted bytes of a raw deflate stream, read and decompressed no further than
        they need: most reads only look at a file's header."""
        self._arc.seek(offset)
        inflater = zlib.decompressobj(-15)
        data = bytearray()
        remaining = compressed_size
        block_size = FIRST_BLOCK
        pending = b""
        while len(data) < wanted:
            if not pending:
                if not remaining:
                    break
                pending = self._arc.read(min(block_size, remaining))
                if not pending:
                    break
                remaining -= len(pending)
                block_size = min(block_size * 2, BLOCK)
            data += inflater.decompress(pending, wanted - len(data))
            pending = inflater.unconsumed_tail
        if len(data) < wanted:
            raise ArchiveError(f"A file in {self.path.with_suffix('.arc')} is shorter than its table says.")
        return bytes(data[:wanted])


def read_tab(tab: Path) -> dict[int, ArchiveEntry]:
    """The files a .tab lists, by name hash."""
    try:
        data = tab.read_bytes()
        (alignment, chunked) = struct.unpack_from("<II", data, 0)
        if alignment != ALIGNMENT:
            raise ArchiveError(f"{tab} is not an archive table this game version uses.")
        position = 8
        chunks: dict[int, tuple[tuple[int, int], ...]] = {}
        for _ in range(chunked):
            name_hash, count = struct.unpack_from("<II", data, position)
            position += 8
            chunks[name_hash] = tuple(struct.iter_unpack("<II", data[position : position + 8 * count]))
            position += 8 * count
        entries = {}
        for name_hash, offset, compressed_size, size in struct.iter_unpack(
            "<IIII", data[position : len(data) - (len(data) - position) % 16]
        ):
            entries[name_hash] = ArchiveEntry(offset, compressed_size, size, chunks.get(name_hash, ()))
        return entries
    except (OSError, struct.error) as error:
        raise ArchiveError(f"Cannot read {tab}: {error}") from error
