"""Archives, bundles and stringlookup files, read as Mad Max stores them."""

from pathlib import Path

import pytest

from reflektortts.sources.avalanche.archives import Archive, ArchiveError
from reflektortts.sources.avalanche.bundles import BundleFile, bundle_files, is_bundle, table_size
from reflektortts.sources.avalanche.lookup3 import hashlittle
from reflektortts.sources.avalanche.stringlookup import StringLookupError, read_stringlookup
from tests.sources.avalanche.fake_files import CHUNKED, DEFLATE, STORED, bundle, stringlookup, write_archive

DATA = bytes(range(256)) * 3


@pytest.mark.parametrize("how", [STORED, DEFLATE, CHUNKED])
def test_a_file_reads_whole_or_in_part_however_it_is_stored(tmp_path: Path, how: str) -> None:
    write_archive(tmp_path / "game0.tab", [("other", b"x" * 100, DEFLATE), ("data.bin", DATA, how)])
    archive = Archive(tmp_path / "game0.tab")
    entry = archive.entries[hashlittle(b"data.bin")]

    assert archive.read(entry) == DATA
    assert archive.read(entry, 0, 16) == DATA[:16]
    assert archive.read(entry, 100, 200) == DATA[100:300]
    assert archive.read(entry, 700) == DATA[700:]
    archive.close()


def test_a_table_of_another_kind_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "game0.tab").write_bytes(bytes(16))

    with pytest.raises(ArchiveError, match="not an archive table .*: look for a profile for this version"):
        Archive(tmp_path / "game0.tab")


@pytest.mark.parametrize("damage", ["no arc", "short arc", "short tab"])
def test_a_damaged_archive_says_what_to_do_and_logs_why(tmp_path: Path, damage: str) -> None:
    tab = tmp_path / "game0.tab"
    write_archive(tab, [("data.bin", DATA, DEFLATE)])
    arc = tab.with_suffix(".arc")
    if damage == "no arc":
        arc.unlink()
    elif damage == "short arc":
        arc.write_bytes(arc.read_bytes()[:10])
    else:
        tab.write_bytes(tab.read_bytes()[:6])

    with pytest.raises(ArchiveError) as raised:
        archive = Archive(tab)
        try:
            archive.read(archive.entries[hashlittle(b"data.bin")])
        finally:
            archive.close()

    assert str(raised.value).endswith(
        "could not be read: check the game's files in Steam or GOG Galaxy, then start the game again."
    )
    assert raised.value.__cause__ is not None


def test_a_bundle_lists_its_files() -> None:
    data = bundle({"global/a_pol.stringlookup": b"abc", "b.bin": b"defgh"})

    assert is_bundle(data[:16])
    files = bundle_files(data[: 16 + table_size(data[:16])])
    assert files == [
        BundleFile("global/a_pol.stringlookup", files[0].offset, 3),
        BundleFile("b.bin", files[1].offset, 5),
    ]
    assert data[files[1].offset : files[1].offset + 5] == b"defgh"


def test_a_stringlookup_gives_lines_by_id_as_a_subtitle_reads() -> None:
    lines = read_stringlookup(
        stringlookup({0xAFA0D59E: "Tak jest,\nzabić  go!", 0x838A371D: "To ja zostanę czempinem!"})
    )

    assert lines == {0xAFA0D59E: "Tak jest, zabić go!", 0x838A371D: "To ja zostanę czempinem!"}


def test_a_damaged_stringlookup_is_an_error() -> None:
    with pytest.raises(StringLookupError):
        read_stringlookup(stringlookup({1: "Hello"})[:-10])
    with pytest.raises(StringLookupError, match="Not a stringlookup"):
        read_stringlookup(bytes(64))
