from collections.abc import Callable

from reflektortts.sinks.tts.narrator import Narrator


class FakeClient:
    def __init__(self, voice: str, on_speaking: Callable[[bool], None]) -> None:
        self.voice = voice
        self.on_speaking = on_speaking
        self.said: list[str] = []
        self.how: list[tuple[float, bool]] = []
        """Rate and cut-off of each line said."""
        self.stopped = 0
        self.dropped_waiting: list[bool] = []
        self.closed = False

    def say(self, text: str, rate: float, cut_off: bool) -> None:
        self.said.append(text)
        self.how.append((rate, cut_off))

    def stop(self, drop_waiting: bool) -> None:
        self.stopped += 1
        self.dropped_waiting.append(drop_waiting)

    def close(self) -> None:
        self.closed = True


class Clients:
    def __init__(self) -> None:
        self.started: list[FakeClient] = []

    def start(self, voice: str, on_speaking: Callable[[bool], None]) -> FakeClient:
        self.started.append(FakeClient(voice, on_speaking))
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


def test_speaking_is_reported_across_a_voice_switch() -> None:
    clients = Clients()
    reported: list[bool] = []
    narrator = Narrator("piper:a", clients.start, reported.append)

    clients.started[0].on_speaking(True)
    narrator.use_voice("windows:Microsoft Adam")
    clients.started[1].on_speaking(True)
    clients.started[0].on_speaking(False)
    clients.started[1].on_speaking(False)

    assert reported == [True, False]


def test_lines_wait_their_turn_at_normal_speed_until_configured() -> None:
    clients = Clients()
    narrator = Narrator("piper:a", clients.start)

    narrator.say("one")
    narrator.configure(1.5, True)
    narrator.say("two")

    assert clients.started[0].how == [(1.0, False), (1.5, True)]


def test_stopping_a_line_keeps_the_waiting_ones_and_pausing_drops_them() -> None:
    clients = Clients()
    narrator = Narrator("piper:a", clients.start)

    narrator.stop_line()
    narrator.pause()

    assert clients.started[0].dropped_waiting == [False, True]


def test_close_closes_the_service() -> None:
    clients = Clients()
    narrator = Narrator("piper:a", clients.start)

    narrator.close()

    assert clients.started[0].closed
