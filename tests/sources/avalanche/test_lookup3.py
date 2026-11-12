"""lookup3's hashlittle, against lookup3.c's own self-test and a file name in Mad Max's patch archive."""

import pytest

from reflektortts.sources.avalanche.lookup3 import hashlittle


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (b"", 0xDEADBEEF),
        # From lookup3.c's own self-test.
        (b"Four score and seven years ago", 0x17770551),
        # A file name in Mad Max's patch archive.
        (b"mm1010_cs010_p2_pol.stringlookup", 0x4A55622B),
    ],
)
def test_hashlittle(text: bytes, expected: int) -> None:
    assert hashlittle(text) == expected
