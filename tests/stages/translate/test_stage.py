from collections import OrderedDict
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest

from reflektortts.events import TextEvent
from reflektortts.languages import Languages
from reflektortts.pipeline.plugins import stage_plugins
from reflektortts.stages.translate import stage as translate_stage
from reflektortts.stages.translate.engine import Engine
from reflektortts.stages.translate.model import ModelNotInstalledError
from reflektortts.stages.translate.stage import PLUGIN, Translate, open_engine


class FakeEngine:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def translate(self, sentences: Sequence[str]) -> str:
        self.calls.append(list(sentences))
        return " ".join(f"<{sentence}>" for sentence in sentences)


class Engines:
    def __init__(self) -> None:
        self.opened: list[tuple[str, str]] = []
        self.engine = FakeEngine()

    def open(self, source: str, target: str) -> Engine:
        self.opened.append((source, target))
        return self.engine


def translate(stage: Translate, text: str, app: str = "en", output: str = "pl") -> str:
    event = stage.process(TextEvent("messages", text, 0.0, output_language=output, input_language=app))
    assert event is not None
    return event.text


def make_stage(engines: Engines) -> Translate:
    return Translate(engines.open)


def test_lines_are_translated_sentence_by_sentence() -> None:
    engines = Engines()
    stage = make_stage(engines)

    assert translate(stage, "Nice wheels. Mind if I borrow them?") == "<Nice wheels.> <Mind if I borrow them?>"
    assert engines.engine.calls == [["Nice wheels.", "Mind if I borrow them?"]]
    assert engines.opened == [("en", "pl")]


def test_empty_text_passes_without_opening_the_engine() -> None:
    engines = Engines()

    assert translate(make_stage(engines), "") == ""
    assert engines.opened == []


@pytest.mark.parametrize(
    ("app", "output", "installed", "reason"),
    [
        ("en", "pl", True, None),
        ("pl", "pl", True, "Input and output language are the same"),
        ("en", "en", True, "Input and output language are the same"),
        ("en", "pl", False, "No translation model for these languages"),
        ("pl", "en", False, "No translation model for these languages"),
    ],
)
def test_it_does_nothing_for_matching_languages_or_without_an_installed_model(
    app: str, output: str, installed: bool, reason: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(translate_stage, "installed_model", lambda package: Path("model") if installed else None)

    assert PLUGIN.inactive_reason(Languages(app, output)) == reason


def test_the_engine_is_opened_once_and_repeated_lines_are_remembered() -> None:
    engines = Engines()
    stage = make_stage(engines)

    translate(stage, "Kill Frenzy!")
    translate(stage, "Mission complete!")
    translate(stage, "Kill Frenzy!")

    assert engines.opened == [("en", "pl")]
    assert engines.engine.calls == [["Kill Frenzy!"], ["Mission complete!"]]


def test_stages_sharing_recent_translations_translate_a_line_once() -> None:
    engines = Engines()
    recent: translate_stage.Recent = OrderedDict()
    text, speech = Translate(engines.open, recent), Translate(engines.open, recent)

    assert translate(text, "Kill Frenzy!") == translate(speech, "Kill Frenzy!") == "<Kill Frenzy!>"
    assert engines.engine.calls == [["Kill Frenzy!"]]


@pytest.fixture
def loads(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """Replaces the installed model and loading it; lists each model loaded."""
    loaded: list[str] = []

    def fake_engine(model_dir: Path, source: str, target: str) -> FakeEngine:
        loaded.append(f"{source}-{target}")
        return FakeEngine()

    monkeypatch.setattr(translate_stage, "installed_model", lambda package: Path("model"))
    monkeypatch.setattr(translate_stage, "load_engine", fake_engine)
    open_engine.cache_clear()
    translate_stage.RECENT.clear()
    yield loaded
    open_engine.cache_clear()
    translate_stage.RECENT.clear()


def test_every_translate_stage_shares_one_loaded_model(loads: list[str]) -> None:
    subtitles, help_box = PLUGIN.create({}, ()), PLUGIN.create({}, ())

    assert isinstance(subtitles, Translate) and isinstance(help_box, Translate)
    assert translate(subtitles, "Kill Frenzy!") == "<Kill Frenzy!>"
    assert translate(help_box, "Press RETURN.") == "<Press RETURN.>"
    assert loads == ["en-pl"]


def test_a_model_is_never_downloaded_and_one_installed_later_is_used(
    loads: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(translate_stage, "installed_model", lambda package: None)
    with pytest.raises(ModelNotInstalledError, match="No translation model"):
        open_engine("en", "pl")
    monkeypatch.setattr(translate_stage, "installed_model", lambda package: Path("model"))

    open_engine("en", "pl")

    assert loads == ["en-pl"]


def test_the_plugin_is_registered() -> None:
    assert stage_plugins()["translate"] is PLUGIN
