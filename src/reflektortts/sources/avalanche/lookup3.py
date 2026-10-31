"""Bob Jenkins' lookup3 hashlittle (public domain), which Avalanche's archives name files by."""

MASK = 0xFFFFFFFF


def _rotate(value: int, bits: int) -> int:
    return ((value << bits) | (value >> (32 - bits))) & MASK


def hashlittle(data: bytes, seed: int = 0) -> int:
    length = len(data)
    a = b = c = (0xDEADBEEF + length + seed) & MASK
    position = 0
    while length > 12:
        a = (a + int.from_bytes(data[position : position + 4], "little")) & MASK
        b = (b + int.from_bytes(data[position + 4 : position + 8], "little")) & MASK
        c = (c + int.from_bytes(data[position + 8 : position + 12], "little")) & MASK
        a = (a - c) & MASK ^ _rotate(c, 4)
        c = (c + b) & MASK
        b = (b - a) & MASK ^ _rotate(a, 6)
        a = (a + c) & MASK
        c = (c - b) & MASK ^ _rotate(b, 8)
        b = (b + a) & MASK
        a = (a - c) & MASK ^ _rotate(c, 16)
        c = (c + b) & MASK
        b = (b - a) & MASK ^ _rotate(a, 19)
        a = (a + c) & MASK
        c = (c - b) & MASK ^ _rotate(b, 4)
        b = (b + a) & MASK
        position += 12
        length -= 12
    if length == 0:
        return c
    tail = data[position:] + bytes(12 - length)
    a = (a + int.from_bytes(tail[0:4], "little")) & MASK
    b = (b + int.from_bytes(tail[4:8], "little")) & MASK
    c = (c + int.from_bytes(tail[8:12], "little")) & MASK
    c = (c ^ b) - _rotate(b, 14) & MASK
    a = (a ^ c) - _rotate(c, 11) & MASK
    b = (b ^ a) - _rotate(a, 25) & MASK
    c = (c ^ b) - _rotate(b, 16) & MASK
    a = (a ^ c) - _rotate(c, 4) & MASK
    b = (b ^ a) - _rotate(a, 14) & MASK
    c = (c ^ b) - _rotate(b, 24) & MASK
    return c
