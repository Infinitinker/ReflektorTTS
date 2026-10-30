from reflektortts.tts.narrator import Narrator


class FakeClient:
    def __init__(self, voice: str) -> None:
        self.voice = voice
        self.said: list[str] = []
        self.stopped = 0
        self.closed = False

    def say(self, text: str) -> None:
        self.said.append(text)

    def stop(self) -> None:
        self.stopped += 1

    def close(self) -> None:
        self.closed = True


class Clients:
    def __init__(self) -> None:
        self.started: list[FakeClient] = []

    def start(self, voice: str) -> FakeClient:
        self.started.append(FakeClient(voice))
        return self.started[-1]


def test_lines_are_spoken_with_the_current_voice() -> None:
    clients = Clients()
    narrator = Narrator("piper:a", clients.start)

    narrator.say("hello")

    assert narrator.voice == "piper:a"
    assert clients.started[0].said == ["hello"]


def test_pause_stops_the_current_line_and_drops_new_ones_until_resumed() -> None:
    clients = Clients()
    narrator = Narrator("piper:a", clients.start)

    narrator.pause()
    narrator.say("dropped")
    narrator.resume()
    narrator.say("spoken")

    assert clients.started[0].stopped == 1
    assert clients.started[0].said == ["spoken"]
    assert not narrator.paused


def test_switching_voice_starts_a_new_service_and_closes_the_old_one() -> None:
    clients = Clients()
    narrator = Narrator("piper:a", clients.start)

    narrator.use_voice("windows:Microsoft Adam")
    narrator.use_voice("windows:Microsoft Adam")
    narrator.say("hi")

    assert [client.voice for client in clients.started] == ["piper:a", "windows:Microsoft Adam"]
    assert clients.started[0].closed
    assert clients.started[1].said == ["hi"]
    assert narrator.voice == "windows:Microsoft Adam"


def test_close_closes_the_service() -> None:
    clients = Clients()
    narrator = Narrator("piper:a", clients.start)

    narrator.close()

    assert clients.started[0].closed
