"""Reads a stringlookup file: a game's text, one table per language, keyed by line ID.

A stringlookup is an ADF file (Avalanche's data format, version 4, as Gibbed.MadMax reads it,
zlib license): a 0x40-byte header {" FDA", u32 version, u32 instance count, u32 instance offset,
...}, and per instance {u32 name hash, u32 type hash, u32 offset, u32 size, s64 name}. A
stringlookup instance starts {u64 index offset, u64 line count, u64 text offset, u64 text size},
offsets from the instance. Its index has a 24-byte entry per line: {u32 line ID, u32 offset in
the text, ...}; the text is UTF-8 lines ending in a zero byte.
"""

import struct

MAGIC = b" FDA"
VERSION = 4
ENTRY_SIZE = 24


class StringLookupError(Exception):
    """A stringlookup file is damaged or not one."""


def is_adf(header: bytes) -> bool:
    return header[:4] == MAGIC


def read_stringlookup(data: bytes) -> dict[int, str]:
    """Line ID to text. Line breaks and repeated spaces become one space, as a subtitle reads."""
    try:
        magic, version, instance_count, instance_offset = struct.unpack_from("<4sIII", data, 0)
        if magic != MAGIC or version != VERSION:
            raise StringLookupError("Not a stringlookup file of this game version.")
        lines = {}
        for _, _, offset, _, _ in struct.iter_unpack(
            "<IIIIq", data[instance_offset : instance_offset + 24 * instance_count]
        ):
            index, count, text, text_size = struct.unpack_from("<QQQQ", data, offset)
            texts = data[offset + text : offset + text + text_size]
            entries = data[offset + index : offset + index + ENTRY_SIZE * count]
            if len(texts) < text_size or len(entries) < ENTRY_SIZE * count:
                raise StringLookupError("A stringlookup file ends early.")
            for position in range(0, len(entries), ENTRY_SIZE):
                line_id, text_offset = struct.unpack_from("<II", entries, position)
                end = texts.find(b"\0", text_offset)
                if end == -1:
                    raise StringLookupError("A line in a stringlookup file has no end.")
                lines[line_id] = " ".join(texts[text_offset:end].decode("utf-8", errors="replace").split())
        return lines
    except (struct.error, OverflowError) as error:
        raise StringLookupError(f"A stringlookup file is damaged: {error}") from error
