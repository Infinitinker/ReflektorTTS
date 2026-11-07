"""Entry point of the TTS process. It imports little, so its log is set up before the service and
its engines load, and a failure while they do (such as a library missing from a release) is logged."""

import logging
from multiprocessing.connection import Connection
from pathlib import Path

from reflektortts.logs import log_to_file

logger = logging.getLogger(__name__)


def run(connection: Connection, events: Connection, voice: str, log_level: int, log_file: Path | None) -> None:
    """Runs the TTS service (see reflektortts.tts.service.run). Logs go to log_file when the core
    logs to files (it has no console), otherwise to the console. Processes that may run at the
    same time need files of their own: on Windows a file another process has open cannot be
    rotated, and the lines that would go to it are lost."""
    if log_file is None:
        logging.basicConfig(level=log_level, format="%(asctime)s %(processName)s %(name)s: %(message)s")
    else:
        log_to_file(log_file)
    try:
        from reflektortts.tts import service
    except Exception:
        # Exiting closes the connection, so the core's next line fails with TtsServiceError.
        logger.exception("The speech service cannot start")
        return
    service.run(connection, events, voice)
