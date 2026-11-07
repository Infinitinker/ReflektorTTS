"""Entry point of the TTS process. It imports little, so its log is set up before the service and
its engines load, and a failure while they do (such as a library missing from a release) is logged."""

import logging
from multiprocessing.connection import Connection
from pathlib import Path

from reflektortts.logs import log_to_file

LOG_FILE = "reflektortts-tts.log"

logger = logging.getLogger(__name__)


def run(connection: Connection, events: Connection, voice: str, log_level: int, log_dir: Path | None) -> None:
    """Runs the TTS service (see reflektortts.tts.service.run). Logs go to a file in log_dir when
    the core logs to files (it has no console), otherwise to the console."""
    if log_dir is None:
        logging.basicConfig(level=log_level, format="%(asctime)s %(processName)s %(name)s: %(message)s")
    else:
        log_to_file(log_dir / LOG_FILE)
    try:
        from reflektortts.tts import service
    except Exception:
        # Exiting closes the connection, so the core's next line fails with TtsServiceError.
        logger.exception("The speech service cannot start")
        return
    service.run(connection, events, voice)
