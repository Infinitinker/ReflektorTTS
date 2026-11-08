from pathlib import Path

import pytest

from reflektortts.sources.vlc.errors import VlcError
from reflektortts.sources.vlc.formats import FORMATS
from reflektortts.sources.vlc.subtitles import SubtitleFile, find_subtitles, words


def found(media: Path, language: str) -> Path | None:
    """The file find_subtitles chooses, checked to come with the format its extension names."""
    file = find_subtitles(media, language)
    if file is None:
        return None
    assert file == SubtitleFile(file.path, FORMATS[file.path.suffix.lower()])
    return file.path


def files(folder: Path, *names: str) -> Path:
    """Creates the files, and returns the media's path: the first name."""
    for name in names:
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
    return folder / names[0]


def test_names_are_compared_as_lowercase_words_without_the_extension() -> None:
    assert words("The.Movie_(2019) - Part 2.en.srt") == ["the", "movie", "2019", "part", "2", "en"]
    assert words("Zażółć.mkv") == ["zażółć"]


def test_a_file_tagged_with_the_input_language_is_preferred(tmp_path: Path) -> None:
    media = files(tmp_path, "movie.mkv", "movie.srt", "movie.en.srt", "movie.pl.srt")

    assert found(media, "en") == tmp_path / "movie.en.srt"
    assert found(media, "pl") == tmp_path / "movie.pl.srt"


@pytest.mark.parametrize("name", ["Movie.2019.English.srt", "movie.en.forced.srt", "movie [eng].srt"])
def test_any_extra_word_may_name_the_language(tmp_path: Path, name: str) -> None:
    media = files(tmp_path, "Movie.mkv", name)

    assert found(media, "en") == tmp_path / name


def test_the_exact_name_is_the_fallback_but_never_another_language(tmp_path: Path) -> None:
    media = files(tmp_path, "movie.mkv", "movie.srt", "movie.de.srt", "movie.forced.srt")

    assert found(media, "en") == tmp_path / "movie.srt"


def test_the_file_with_the_fewest_extra_words_is_preferred(tmp_path: Path) -> None:
    media = files(tmp_path, "Movie.mkv", "Movie.en.sdh.srt", "Movie.en.srt", "Movie.2019.English.srt")

    assert found(media, "en") == tmp_path / "Movie.en.srt"


def test_a_forced_file_is_read_only_if_there_is_no_other(tmp_path: Path) -> None:
    media = files(tmp_path, "Movie.mkv", "Movie.en.forced.srt", "subs/Movie.srt")
    assert found(media, "en") == tmp_path / "subs" / "Movie.srt"

    (tmp_path / "subs" / "Movie.srt").unlink()
    assert found(media, "en") == tmp_path / "Movie.en.forced.srt"

    files(tmp_path, "Movie.en.srt")
    assert found(media, "en") == tmp_path / "Movie.en.srt"


@pytest.mark.parametrize(
    ("media", "other"),
    [("Show - 1.mkv", "Show - 10.en.srt"), ("ep01.mkv", "ep010.en.srt"), ("a.mkv", "banana.en.srt")],
)
def test_the_media_name_must_appear_as_whole_words(tmp_path: Path, media: str, other: str) -> None:
    path = files(tmp_path, media, other)
    with pytest.raises(VlcError, match="No English subtitles found"):
        found(path, "en")

    files(tmp_path, f"{path.stem}.en.srt")
    assert found(path, "en") == tmp_path / f"{path.stem}.en.srt"


def test_the_media_folder_comes_before_vlcs_subtitle_folders(tmp_path: Path) -> None:
    media = files(tmp_path, "movie.mkv", "subs/movie.en.srt", "Subtitles/x/other.srt")
    assert found(media, "en") == tmp_path / "subs" / "movie.en.srt"

    files(tmp_path, "movie.en.srt")
    assert found(media, "en") == tmp_path / "movie.en.srt"


def test_files_vlc_would_not_load_are_not_read(tmp_path: Path) -> None:
    media = files(tmp_path, "movie.mkv", "eng movie.srt", ".movie.en.srt", "other.en.srt")

    with pytest.raises(VlcError, match="No English subtitles found: put movie.en.srt or movie.srt next to movie.mkv"):
        found(media, "en")


def test_without_any_subtitle_file_there_is_quietly_nothing_to_read(tmp_path: Path) -> None:
    media = files(tmp_path, "song.mp3", "cover.jpg", "song.txt")

    assert found(media, "en") is None


def test_subtitles_only_in_another_language_say_which_files_to_add(tmp_path: Path) -> None:
    media = files(tmp_path, "movie.mkv", "movie.de.srt")

    with pytest.raises(VlcError) as raised:
        found(media, "pl")

    assert str(raised.value) == "No Polish subtitles found: put movie.pl.srt or movie.srt next to movie.mkv."


@pytest.mark.parametrize("suffix", [".srt", ".vtt", ".webvtt", ".ass", ".ssa", ".sbv", ".SRT", ".Vtt"])
def test_every_readable_format_is_found(tmp_path: Path, suffix: str) -> None:
    media = files(tmp_path, "movie.mkv", f"movie.en{suffix}", "movie.en.sub")

    assert found(media, "en") == tmp_path / f"movie.en{suffix}"


def test_srt_is_preferred_only_among_files_that_rank_alike(tmp_path: Path) -> None:
    media = files(tmp_path, "movie.mkv", "movie.vtt", "movie.en.ass", "movie.en.vtt", "movie.en.srt")
    assert found(media, "en") == tmp_path / "movie.en.srt"

    (tmp_path / "movie.en.srt").unlink()
    assert found(media, "en") == tmp_path / "movie.en.ass"

    files(tmp_path, "movie.en.sdh.srt", "subs/movie.en.srt")
    assert found(media, "en") == tmp_path / "movie.en.ass"


def test_a_tagged_file_in_another_readable_format_comes_before_the_exact_name(tmp_path: Path) -> None:
    media = files(tmp_path, "movie.mkv", "movie.srt", "movie.english.sbv")

    assert found(media, "en") == tmp_path / "movie.english.sbv"


def test_subtitles_only_in_formats_not_read_say_which_are_read(tmp_path: Path) -> None:
    media = files(tmp_path, "movie.mkv", "movie.sub", "movie.en.stl", "movie.de.srt")

    with pytest.raises(VlcError) as raised:
        found(media, "en")

    assert str(raised.value) == "movie.en.stl is in a format that cannot be read: convert it to movie.srt."
