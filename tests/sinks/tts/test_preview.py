from reflektortts.events import PreviewEvent
from reflektortts.sinks.tts.preview import VoicePreview
from reflektortts.tts.service import NewLine
from tests.sinks.tts.test_narrator import Clients


def preview(clients: Clients, events: list[PreviewEvent]) -> VoicePreview:
    return VoicePreview(events.append, clients.start, lambda work: work())


def test_a_sample_is_spoken_once_cutting_off_any_line() -> None:
    clients = Clients()

    preview(clients, []).play("piper:a", "Hello.")

    assert [(client.voice, client.said, client.how) for client in clients.started] == [
        ("piper:a", ["Hello."], [(1.0, NewLine.CUT_OFF)])
    ]


def test_the_voice_is_unloaded_once_the_sample_is_spoken_and_the_preview_ends() -> None:
    clients, events = Clients(), list[PreviewEvent]()
    preview(clients, events).play("piper:a", "Hello.")
    client = clients.started[0]

    client.on_speaking(True)
    assert not client.closed
    client.on_speaking(False)

    assert client.closed
    assert events == [PreviewEvent("piper:a", playing=True), PreviewEvent("piper:a", playing=False)]


def test_a_voice_that_cannot_be_loaded_ends_the_preview() -> None:
    clients, events = Clients(), list[PreviewEvent]()
    preview(clients, events).play("piper:broken", "Hello.")

    clients.started[0].on_exit()

    assert events[-1] == PreviewEvent("piper:broken", playing=False)


def test_a_new_preview_cuts_off_the_one_playing() -> None:
    clients, events = Clients(), list[PreviewEvent]()
    previews = preview(clients, events)

    previews.play("piper:a", "Hello.")
    previews.play("piper:b", "Hello.")

    assert [client.closed for client in clients.started] == [True, False]
    assert events == [PreviewEvent("piper:a", playing=True), PreviewEvent("piper:b", playing=True)]
    previews.close()
    assert clients.started[1].closed
    assert events[-1] == PreviewEvent("piper:b", playing=False)
