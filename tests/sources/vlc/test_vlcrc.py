from pathlib import Path

import platformdirs
import pytest

from reflektortts.sources.vlc.vlcrc import BOM, Vlcrc, vlcrc_path
from tests.sources.vlc.fake_vlcrc import FRESH


def test_an_unchanged_file_is_written_back_byte_for_byte() -> None:
    assert Vlcrc(FRESH).to_bytes() == FRESH


def test_a_commented_default_is_set_in_its_place() -> None:
    rc = Vlcrc(FRESH)

    original = rc.set("extraintf", b"http")

    assert original == b"#extraintf="
    assert rc.value("extraintf") == b"http"
    assert rc.to_bytes() == FRESH.replace(b"#extraintf=\n", b"extraintf=http\n")


def test_description_comments_are_not_taken_for_a_setting() -> None:
    rc = Vlcrc(b"# extraintf=rc (comment)\n#extraintf=\n")

    rc.set("extraintf", b"http")

    assert rc.to_bytes() == b"# extraintf=rc (comment)\nextraintf=http\n"


def test_the_last_line_for_a_key_is_the_one_vlc_uses_and_the_one_replaced() -> None:
    rc = Vlcrc(b"[core]\nextraintf=rc\n[lua]\nextraintf=telnet\n")

    assert rc.value("extraintf") == b"telnet"
    assert rc.set("extraintf", b"telnet:http") == b"extraintf=telnet"
    assert rc.to_bytes() == b"[core]\nextraintf=rc\n[lua]\nextraintf=telnet:http\n"


def test_a_key_without_a_line_is_added_at_the_end_with_the_files_line_ending() -> None:
    rc = Vlcrc(b"[core]\r\nfoo=1")

    assert rc.value("http-host") is None
    assert rc.set("http-host", b"127.0.0.1") is None
    assert rc.to_bytes() == b"[core]\r\nfoo=1\r\nhttp-host=127.0.0.1\r\n"


def test_the_byte_order_mark_is_kept_only_where_there_was_one() -> None:
    assert Vlcrc(b"a=1\n").to_bytes() == b"a=1\n"
    assert Vlcrc(BOM + b"a=1\n").value("a") == b"1"
    assert Vlcrc(BOM + b"a=1\n").to_bytes() == BOM + b"a=1\n"


def test_crlf_line_endings_are_kept_and_not_part_of_the_value() -> None:
    rc = Vlcrc(b"#http-host=\r\nhttp-port=9090\r\n")

    assert rc.value("http-port") == b"9090"
    rc.set("http-host", b"127.0.0.1")
    assert rc.to_bytes() == b"http-host=127.0.0.1\r\nhttp-port=9090\r\n"


def test_the_file_always_ends_with_a_line_break() -> None:
    assert Vlcrc(b"a=1").to_bytes() == b"a=1\n"


def test_a_value_spanning_lines_is_refused() -> None:
    with pytest.raises(ValueError, match="cannot span lines"):
        Vlcrc(FRESH).set("http-password", b"a\nb")


def test_restoring_puts_the_original_line_back_or_removes_an_added_one() -> None:
    rc = Vlcrc(FRESH)
    original = rc.set("http-password", b"secret")
    rc.set("http-host", b"127.0.0.1")
    rc.restore("http-password", original)
    rc.restore("http-host", b"#http-host=")
    assert rc.to_bytes() == FRESH

    added = Vlcrc(b"a=1\n")
    added.restore("b", added.set("b", b"2"))
    assert added.to_bytes() == b"a=1\n"


def test_a_value_in_a_legacy_code_page_is_kept_as_it_is() -> None:
    rc = Vlcrc(b"# Has\xb3o\nhttp-password=\xb3\xf3d\xbc\n")

    rc.set("http-host", b"127.0.0.1")

    assert rc.value("http-password") == b"\xb3\xf3d\xbc"
    assert rc.to_bytes().startswith(b"# Has\xb3o\nhttp-password=\xb3\xf3d\xbc\n")


def test_module_lists_are_split_at_colons_in_lowercase() -> None:
    assert Vlcrc(b"extraintf=rc: HTTP::\n").values("extraintf") == ["rc", "http"]
    assert Vlcrc(b"").values("extraintf") == []


def test_vlcrc_is_in_vlcs_own_config_folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls = []

    def config_path(name: str, appauthor: bool, roaming: bool) -> Path:
        calls.append((name, appauthor, roaming))
        return tmp_path

    monkeypatch.setattr(platformdirs, "user_config_path", config_path)

    assert vlcrc_path() == tmp_path / "vlcrc"
    assert calls == [("vlc", False, True)]
