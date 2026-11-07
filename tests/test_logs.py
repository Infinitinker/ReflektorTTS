import logging
import threading

import pytest

from reflektortts import logs


def test_an_error_no_thread_catches_is_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(threading, "excepthook", logs._log_uncaught_in_thread)

    def fail() -> None:
        raise KeyError("voices")

    thread = threading.Thread(target=fail, name="api request")
    thread.start()
    thread.join()

    record = next(record for record in caplog.records if record.levelno == logging.ERROR)
    assert record.getMessage() == "Uncaught error in the thread api request"
    assert record.exc_info is not None and record.exc_info[0] is KeyError
