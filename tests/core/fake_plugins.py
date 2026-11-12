"""Source and stage plugins that need no app: a source that reads a fixed text, and a stage that adds a suffix."""

import threading
from collections.abc import Mapping
from typing import Any

from reflektortts.apps.detector import ProcessInfo, RunningApp
from reflektortts.events import TextEvent
from reflektortts.glossary import Glossaries
from reflektortts.languages import Languages
from reflektortts.pipeline.plugins import SourcePlugin, StagePlugin
from reflektortts.profiles.model import App, Executable, Match, Profile, SourceSettings


class FixedSource:
    def __init__(self, name: str, text: str) -> None:
        self.name = name
        self.poll_interval = 0.01
        self.text = text
        self.closed = False

    def read(self, languages: Languages) -> str | None:
        return self.text

    def close(self) -> None:
        self.closed = True


class Suffix:
    def __init__(self, suffix: str) -> None:
        self.suffix = suffix

    def process(self, event: TextEvent) -> TextEvent | None:
        return TextEvent(event.source, event.text + self.suffix, event.time)


class RecordingSink:
    name = "recorder"

    def __init__(self) -> None:
        self.texts: list[str] = []
        self.received = threading.Event()

    def deliver(self, event: TextEvent) -> None:
        self.texts.append(event.text)
        self.received.set()

    def close(self) -> None:
        pass


def create_source(settings: SourceSettings, app: RunningApp) -> FixedSource:
    if settings.settings.get("broken"):
        raise RuntimeError("This version of the app is not supported")
    return FixedSource(settings.name, settings.settings["text"])


def create_stage(settings: Mapping[str, Any], glossaries: Glossaries) -> Suffix:
    return Suffix(settings["suffix"])


SOURCES = {"fixed": SourcePlugin("fixed", {}, create_source)}
STAGES = {
    "suffix": StagePlugin("suffix", {}, create_stage, summary="adds a suffix"),
    "polish": StagePlugin(
        "polish",
        {},
        create_stage,
        inactive_reason=lambda languages: None if languages.output == "pl" else "Only Polish",
    ),
}


def app_with(*sources: SourceSettings) -> RunningApp:
    profile = Profile("app", App("App", 2000), Match((Executable("app.exe"),)), sources)
    return RunningApp(profile, ProcessInfo(42, "app.exe"))
