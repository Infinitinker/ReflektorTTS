"""Reading one app: creating its sources and, for each output, their stages, and running them until
the app exits."""

import threading
from collections.abc import Callable, Mapping, Sequence

import psutil

from reflektortts.apps.detector import RunningApp
from reflektortts.events import ErrorEvent, Output
from reflektortts.languages import DEFAULT_INPUT_LANGUAGE, DEFAULT_OUTPUT_LANGUAGE, Languages
from reflektortts.pipeline.plugins import SourcePlugin, StagePlugin, inactive_reason
from reflektortts.pipeline.protocols import Sink
from reflektortts.pipeline.runner import Chain, Route, Runner, log_error
from reflektortts.profiles.model import SourceSettings, StageSettings

APP_CHECK_SECONDS = 2.0


def stage_key(source: str, position: int, stage_type: str) -> str:
    """Identifies a stage within its profile, e.g. "subtitles/3:normalize"."""
    return f"{source}/{position}:{stage_type}"


def stage_on(stage: StageSettings, output: Output, switch: bool | None) -> bool:
    """Whether a stage is on for an output: as the user switched it, else as its profile starts it."""
    if switch is not None:
        return switch
    return stage.text if output is Output.TEXT else stage.speech


def _enabled_check(
    source: SourceSettings,
    output: Output,
    plugins: Mapping[str, StagePlugin],
    stage_switch: Callable[[str, Output], bool | None],
    languages: Callable[[], Languages],
) -> Callable[[int], bool]:
    """Whether the stage at a position runs for an output: it is on there, and it works with the
    user's languages."""
    stages = source.stages
    return lambda position: (
        stage_on(
            stages[position], output, stage_switch(stage_key(source.name, position, stages[position].type), output)
        )
        and inactive_reason(plugins[stages[position].type], languages()) is None
    )


def _source_check(source: str, is_source_enabled: Callable[[str], bool]) -> Callable[[], bool]:
    return lambda: is_source_enabled(source)


def build_routes(
    app: RunningApp,
    sources: Mapping[str, SourcePlugin],
    stages: Mapping[str, StagePlugin],
    on_error: Callable[[ErrorEvent], None],
    stage_switch: Callable[[str, Output], bool | None] = lambda key, output: None,
    is_source_enabled: Callable[[str], bool] = lambda name: True,
    languages: Callable[[], Languages] = lambda: Languages(DEFAULT_INPUT_LANGUAGE, DEFAULT_OUTPUT_LANGUAGE),
) -> list[Route]:
    """Creates the app's sources and, for each output, their stages; a source that cannot start,
    or one of whose stages cannot, is reported and skipped.

    stage_switch tells, by stage key and output, how the user switched the stage, or None if they
    have not; is_source_enabled tells whether the user has a source, by name, switched on. A stage
    that does nothing with the user's languages is skipped too.
    """
    routes = []
    for settings in app.profile.sources:
        try:
            source = sources[settings.type].create(settings, app)
        except Exception as error:
            on_error(ErrorEvent("source.error", settings.name, str(error)))
            continue
        try:
            chains = {
                output: Chain(
                    [stages[stage.type].create(stage.settings, app.profile.glossary) for stage in settings.stages],
                    _enabled_check(settings, output, stages, stage_switch, languages),
                )
                for output in Output
            }
        except Exception as error:
            source.close()
            on_error(ErrorEvent("source.error", settings.name, f"A processing stage cannot start ({error})."))
            continue
        routes.append(Route(source, chains, _source_check(settings.name, is_source_enabled)))
    return routes


def read_app(
    app: RunningApp,
    routes: Sequence[Route],
    sinks: Mapping[Output, Sequence[Sink]],
    stop: threading.Event,
    on_error: Callable[[ErrorEvent], None] = log_error,
    is_running: Callable[[int], bool] = psutil.pid_exists,
    check_seconds: float = APP_CHECK_SECONDS,
    languages: Callable[[], Languages] = lambda: Languages(DEFAULT_INPUT_LANGUAGE, DEFAULT_OUTPUT_LANGUAGE),
    on_works_again: Callable[[str, str], None] = lambda kind, origin: None,
    on_still_failing: Callable[[ErrorEvent], None] = lambda error: None,
) -> None:
    """Runs the pipeline until the app exits or stop is set, then closes the sources; see Runner
    for on_error, on_works_again and on_still_failing."""
    runner_stop = threading.Event()
    runner = Runner(
        routes,
        sinks,
        on_error,
        languages=languages,
        on_works_again=on_works_again,
        on_still_failing=on_still_failing,
    )
    worker = threading.Thread(target=runner.run, args=(runner_stop,), name="runner")
    worker.start()
    try:
        while is_running(app.process.pid) and not stop.wait(check_seconds):
            pass
    finally:
        runner_stop.set()
        worker.join()
        for route in routes:
            route.source.close()
