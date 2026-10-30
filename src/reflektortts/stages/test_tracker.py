from reflektortts.events import TextEvent
from reflektortts.pipeline.plugins import stage_plugins
from reflektortts.stages.tracker import PLUGIN, Tracker


def feed(tracker: Tracker, readings: list[tuple[float, str]]) -> list[str]:
    """Feeds (time, text) readings and returns the texts the tracker passed on."""
    passed = []
    for time, text in readings:
        event = tracker.process(TextEvent("memory", text, time))
        if event is not None:
            passed.append(event.text)
    return passed


def test_line_is_passed_on_once_after_it_settles() -> None:
    readings = [(0.0, "Hello there"), (0.25, "Hello there"), (0.5, "Hello there"), (0.75, "Hello there")]

    assert feed(Tracker(stable_seconds=0.5, min_letters=4), readings) == ["Hello there"]


def test_text_still_typing_out_is_not_passed_on_until_it_settles() -> None:
    readings = [(0.0, "Hel"), (0.25, "Hello th"), (0.5, "Hello there"), (0.75, "Hello there"), (1.0, "Hello there")]

    assert feed(Tracker(stable_seconds=0.5, min_letters=4), readings) == ["Hello there"]


def test_same_line_is_passed_on_again_after_it_disappears() -> None:
    readings = [(0.0, "Kill Frenzy!"), (1.0, "Kill Frenzy!"), (2.0, ""), (3.0, "Kill Frenzy!"), (4.0, "Kill Frenzy!")]

    assert feed(Tracker(stable_seconds=0.5, min_letters=4), readings) == ["Kill Frenzy!", "Kill Frenzy!"]


def test_changed_line_is_passed_on() -> None:
    readings = [(0.0, "First line"), (1.0, "First line"), (2.0, "Second line"), (3.0, "Second line")]

    assert feed(Tracker(stable_seconds=0.5, min_letters=4), readings) == ["First line", "Second line"]


def test_lines_with_too_few_letters_are_ignored() -> None:
    readings = [(0.0, "$100"), (1.0, "$100"), (2.0, "Okay!"), (3.0, "Okay!")]

    assert feed(Tracker(stable_seconds=0.5, min_letters=4), readings) == ["Okay!"]


def test_plugin_defaults_and_registration() -> None:
    assert stage_plugins()["tracker"] is PLUGIN
    tracker = PLUGIN.create({})
    assert isinstance(tracker, Tracker)
    assert feed(tracker, [(0.0, "Hello"), (0.4, "Hello"), (0.5, "Hello")]) == ["Hello"]
