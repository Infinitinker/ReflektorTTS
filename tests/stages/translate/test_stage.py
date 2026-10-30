from collections.abc import Sequence

from reflektortts.events import TextEvent
from reflektortts.pipeline.plugins import stage_plugins
from reflektortts.stages.translate.engine import Engine
from reflektortts.stages.translate.stage import PLUGIN, Translate


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


def translate(stage: Translate, text: str, game: str = "en", output: str = "pl") -> str:
    event = stage.process(TextEvent("messages", text, 0.0, output_language=output, game_language=game))
    assert event is not None
    return event.text


def make_stage(engines: Engines) -> Translate:
    return Translate([("en", "pl")], engines.open)


def test_lines_are_translated_sentence_by_sentence() -> None:
    engines = Engines()
    stage = make_stage(engines)

    assert translate(stage, "Nice wheels. Mind if I borrow them?") == "<Nice wheels.> <Mind if I borrow them?>"
    assert engines.engine.calls == [["Nice wheels.", "Mind if I borrow them?"]]
    assert engines.opened == [("en", "pl")]


def test_auto_game_language_is_taken_as_english() -> None:
    stage = make_stage(Engines())

    assert translate(stage, "Kill Frenzy!", game="auto") == "<Kill Frenzy!>"


def test_lines_already_in_the_output_language_pairs_without_a_model_and_empty_text_pass_unchanged() -> None:
    engines = Engines()
    stage = make_stage(engines)

    assert translate(stage, "Kill Frenzy!", output="en") == "Kill Frenzy!"
    assert translate(stage, "Zabij!", game="pl", output="en") == "Zabij!"
    assert translate(stage, "") == ""
    assert engines.opened == []


def test_the_engine_is_opened_once_and_repeated_lines_are_remembered() -> None:
    engines = Engines()
    stage = make_stage(engines)

    translate(stage, "Kill Frenzy!")
    translate(stage, "Mission complete!")
    translate(stage, "Kill Frenzy!")

    assert engines.opened == [("en", "pl")]
    assert engines.engine.calls == [["Kill Frenzy!"], ["Mission complete!"]]


def test_the_plugin_is_registered() -> None:
    assert stage_plugins()["translate"] is PLUGIN
