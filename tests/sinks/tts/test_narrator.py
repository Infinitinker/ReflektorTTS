from collections.abc import Callable

from reflektortts.sinks.tts.narrator import Narrator


class FakeClient:
    def __init__(
        self, voice: str, on_speaking: Callable[[bool], None], on_exit: Callable[[], None] = lambda: None
    ) -> None:
        self.voice = voice
        self.on_speaking = on_speaking
        self.on_exit = on_exit
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
        """The process exits."""
        if not self.closed:
            self.closed = True
            self.on_exit()


class Clients:
    def __init__(self) -> None:
        self.started: list[FakeClient] = []

    def start(
        self, voice: str, on_speaking: Callable[[bool], None], on_exit: Callable[[], None] = lambda: None
    ) -> FakeClient:
        self.started.append(FakeClient(voice, on_speaking, on_exit))
        return self.started[-1]


def started(clients: Clients, on_speaking: Callable[[bool], None] = lambda active: None) -> Narrator:
    """A narrator with its voice loaded, as while a game is read."""
    narrator = Narrator("piper:a", clients.start, on_speaking)
    narrator.start()
    return narrator


def test_lines_are_spoken_with_the_current_voice() -> None:
    clients = Clients()
    narrator = started(clients)

    narrator.say("hello")

    assert narrator.voice == "piper:a"
    assert clients.started[0].said == ["hello"]


def test_the_voice_is_loaded_only_once_started_and_unloaded_when_closed() -> None:
    clients = Clients()
    narrator = Narrator("piper:a", start_client=clients.start)
    narrator.use_voice("windows:Microsoft Adam")
    narrator.say("nobody hears this")
    narrator.pause()
    narrator.resume()
    assert clients.started == []

    narrator.start()
    narrator.start()
    narrator.close()
    narrator.start()

    assert [client.voice for client in clients.started] == ["windows:Microsoft Adam"] * 2
    assert clients.started[0].closed and not clients.started[1].closed


def test_pause_stops_the_current_line_and_drops_new_ones_until_resumed() -> None:
    clients = Clients()
    narrator = started(clients)

    narrator.pause()
    narrator.say("dropped")
    narrator.resume()
    narrator.say("spoken")

    assert clients.started[0].stopped == 1
    assert clients.started[0].said == ["spoken"]
    assert not narrator.paused


def test_switching_voice_starts_a_new_service_and_closes_the_old_one() -> None:
    clients = Clients()
    narrator = started(clients)

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
    narrator = started(clients, on_speaking=reported.append)

    clients.started[0].on_speaking(True)
    narrator.use_voice("windows:Microsoft Adam")
    clients.started[1].on_speaking(True)
    clients.started[0].on_speaking(False)
    clients.started[1].on_speaking(False)

    assert reported == [True, False]


def test_lines_wait_their_turn_at_normal_speed_until_configured() -> None:
    clients = Clients()
    narrator = started(clients)

    narrator.say("one")
    narrator.configure(1.5, True)
    narrator.say("two")

    assert clients.started[0].how == [(1.0, False), (1.5, True)]


def test_stopping_a_line_keeps_the_waiting_ones_and_pausing_drops_them() -> None:
    clients = Clients()
    narrator = started(clients)

    narrator.stop_line()
    narrator.pause()

    assert clients.started[0].dropped_waiting == [False, True]


def test_close_closes_the_service() -> None:
    clients = Clients()
    narrator = started(clients)

    narrator.close()

    assert clients.started[0].closed
